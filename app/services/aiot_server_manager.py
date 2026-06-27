"""AIOT TCP 服务管理器。"""

import json
import socket
import threading
import time

from app.models.aiot_server import AiotServerRepository
from app.models.device import DeviceRepository


def _extract_box_id(message):
    text = (message or "").strip()
    if not text:
        return None

    lowered = text.lower()
    for prefix in (
        "box_id:",
        "box_id=",
        "boxid:",
        "boxid=",
        "device_id:",
        "device_id=",
        "deviceid:",
        "deviceid=",
    ):
        if lowered.startswith(prefix):
            candidate = text[len(prefix) :].strip()
            return candidate or None

    if text.startswith("{") and text.endswith("}"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {}
        for key in ("box_id", "boxid", "device_id", "deviceid"):
            candidate = (payload.get(key) or "").strip()
            if candidate:
                return candidate

    if len(text) <= 64 and all(char.isalnum() or char in "-_:" for char in text):
        return text
    return None


class ManagedAiotTcpServer:
    IDLE_OFFLINE_SECONDS = 3

    def __init__(self, server_row):
        self.server_id = server_row["id"]
        self.server_name = server_row["server_name"]
        self.listen_ip = server_row["listen_ip"]
        self.listen_port = int(server_row["listen_port"])
        self._thread = None
        self._stop_event = threading.Event()
        self._server_socket = None
        self._connections = {}
        self._connections_lock = threading.Lock()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.listen_ip, self.listen_port))
        sock.listen(5)
        sock.settimeout(1)
        self._server_socket = sock
        AiotServerRepository.set_running(self.server_id, True)
        self._thread = threading.Thread(target=self._serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass
        if self._thread:
            self._thread.join(timeout=1.5)
        with self._connections_lock:
            self._connections.clear()
        AiotServerRepository.set_running(self.server_id, False)

    def bind_device_connection(self, box_id, conn):
        normalized_box_id = (box_id or "").strip()
        if not normalized_box_id or conn is None:
            return
        with self._connections_lock:
            self._connections[normalized_box_id] = conn

    def unbind_device_connection(self, box_id, conn=None):
        normalized_box_id = (box_id or "").strip()
        if not normalized_box_id:
            return
        with self._connections_lock:
            current = self._connections.get(normalized_box_id)
            if current is None:
                return
            if conn is not None and current is not conn:
                return
            self._connections.pop(normalized_box_id, None)

    def send_command(self, box_id, command_text):
        normalized_box_id = (box_id or "").strip()
        normalized_command = (command_text or "").strip()
        if not normalized_box_id:
            raise ValueError("device_not_selected")
        if not normalized_command:
            raise ValueError("command_empty")
        with self._connections_lock:
            conn = self._connections.get(normalized_box_id)
        if conn is None:
            raise LookupError("device_offline")
        conn.sendall(f"{normalized_command}\n".encode("utf-8"))
        AiotServerRepository.append_server_message(
            server_id=self.server_id,
            box_id=normalized_box_id,
            message_text=f"CMD> {normalized_command}",
        )

    def _serve_forever(self):
        sock = self._server_socket

        try:
            while not self._stop_event.is_set():
                try:
                    conn, _addr = sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self._stop_event.is_set():
                        break
                    raise
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
        finally:
            try:
                sock.close()
            except OSError:
                pass
            AiotServerRepository.set_running(self.server_id, False)

    def _handle_client(self, conn):
        current_box_id = None
        last_message_at = time.monotonic()
        try:
            with conn:
                conn.settimeout(1)
                while not self._stop_event.is_set():
                    try:
                        raw = conn.recv(1024)
                    except socket.timeout:
                        if current_box_id and (time.monotonic() - last_message_at) >= self.IDLE_OFFLINE_SECONDS:
                            break
                        continue
                    if not raw:
                        break
                    last_message_at = time.monotonic()
                    message = raw.decode("utf-8", errors="ignore").strip()
                    if not message:
                        continue
                    box_id = _extract_box_id(message)
                    if box_id:
                        current_box_id = box_id
                        self.bind_device_connection(current_box_id, conn)
                    AiotServerRepository.append_server_message(
                        server_id=self.server_id,
                        box_id=box_id or current_box_id,
                        message_text=message,
                    )
                    if box_id:
                        DeviceRepository.set_device_connection_status(
                            box_id=box_id,
                            is_online=True,
                            server_id=self.server_id,
                        )
                        AiotServerRepository.append_server_message(
                            server_id=self.server_id,
                            box_id=box_id,
                            message_text=f"设备 {box_id} 已接入 {self.server_name}",
                        )
        finally:
            if current_box_id:
                self.unbind_device_connection(current_box_id, conn)
                DeviceRepository.set_device_connection_status(
                    box_id=current_box_id,
                    is_online=False,
                    server_id=None,
                )
                AiotServerRepository.append_server_message(
                    server_id=self.server_id,
                    box_id=current_box_id,
                    message_text=f"设备 {current_box_id} 已断开连接",
                )


class AiotServerManager:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._servers = {}

    @classmethod
    def instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def start_server(self, server_id):
        server_row = AiotServerRepository.get_server_by_id(server_id)
        if not server_row:
            raise ValueError("server_not_found")
        self.stop_server(server_id)
        managed = ManagedAiotTcpServer(server_row)
        managed.start()
        self._servers[server_id] = managed

    def stop_server(self, server_id):
        managed = self._servers.pop(server_id, None)
        if managed:
            managed.stop()
        else:
            AiotServerRepository.set_running(server_id, False)

    def restart_server(self, server_id):
        self.stop_server(server_id)
        self.start_server(server_id)

    def send_command(self, server_id, box_id, command_text):
        managed = self._servers.get(server_id)
        if not managed:
            raise LookupError("server_not_running")
        managed.send_command(box_id, command_text)

    def bootstrap_enabled_servers(self):
        for row in AiotServerRepository.list_enabled_servers():
            try:
                self.start_server(row["id"])
            except OSError:
                AiotServerRepository.set_running(row["id"], False)
