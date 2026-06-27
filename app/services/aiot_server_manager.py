"""AIOT TCP 服务管理器。"""

import json
import re
import socket
import threading

from app.models.aiot_server import AiotServerRepository
from app.models.data_report import DataReportRepository
from app.models.device import DeviceRepository


RUNTIME_STATUS_FIELD_ORDER = (
    "LED",
    "mode",
    "light",
    "human",
    "screen",
    "wifi",
    "tcp",
    "device_ip",
    "temperature",
    "humidity",
    "beep",
)

TEXT_RUNTIME_LABEL_MAP = {
    "设备id": "box_id",
    "box_id": "box_id",
    "boxid": "box_id",
    "device_id": "box_id",
    "deviceid": "box_id",
    "模式": "mode",
    "mode": "mode",
    "led": "LED",
    "蜂鸣器": "beep",
    "beep": "beep",
    "光敏": "light",
    "light": "light",
    "人体": "human",
    "human": "human",
    "屏幕": "screen",
    "screen": "screen",
    "wifi": "wifi",
    "tcp": "tcp",
    "设备ip": "device_ip",
    "device_ip": "device_ip",
    "ip": "device_ip",
    "温度": "temperature",
    "temperature": "temperature",
    "temp": "temperature",
    "湿度": "humidity",
    "humidity": "humidity",
    "humi": "humidity",
}


def _extract_box_id(message):
    text = (message or "").strip()
    if not text:
        return None

    tagged_match = re.fullmatch(
        r"(?:\[[^\]]+\]\s*)?(?:box_id|boxid|device_id|deviceid|设备id)\s*[:=]\s*([A-Za-z0-9_-]{1,64})",
        text,
        flags=re.IGNORECASE,
    )
    if tagged_match:
        return tagged_match.group(1)

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

    if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", text):
        return text
    return None


def _normalize_runtime_label(label):
    cleaned = (label or "").strip()
    if not cleaned:
        return ""
    if re.fullmatch(r"[A-Za-z0-9_]+", cleaned):
        return TEXT_RUNTIME_LABEL_MAP.get(cleaned.lower(), "")
    return TEXT_RUNTIME_LABEL_MAP.get(cleaned, "")


def _build_runtime_status_summary(status_values):
    parts = []
    for key in RUNTIME_STATUS_FIELD_ORDER:
        value = (status_values.get(key) or "").strip()
        if value:
            parts.append(f"{key}={value}")
    return " | ".join(parts)


def _extract_text_runtime_payload(text):
    cleaned_text = (text or "").strip()
    if not cleaned_text:
        return {}

    tagged_body = re.sub(r"^\[[^\]]+\]\s*", "", cleaned_text).strip()
    candidates = []
    if "|" in tagged_body:
        candidates.extend(segment.strip() for segment in tagged_body.split("|"))
    else:
        candidates.extend(match.group(0).strip() for match in re.finditer(r"([A-Za-z_]+|[\u4e00-\u9fff]+)\s*[:：=]\s*[^\s|]+", tagged_body))

    extracted = {}
    for segment in candidates:
        match = re.match(r"([A-Za-z_]+|[\u4e00-\u9fff]+)\s*[:：=]\s*(.+)", segment)
        if not match:
            continue
        normalized_key = _normalize_runtime_label(match.group(1))
        if not normalized_key:
            continue
        extracted[normalized_key] = match.group(2).strip()

    if cleaned_text.startswith("[上线]"):
        extracted["tcp"] = "online"
    elif cleaned_text.startswith("[周期上报]") or cleaned_text.startswith("[状态]") or cleaned_text.startswith("[传感器]"):
        extracted.setdefault("tcp", "online")

    if not extracted:
        return {}

    normalized = {}
    device_ip = (extracted.get("device_ip") or "").strip()
    if device_ip:
        normalized["esp32_ip"] = device_ip
        normalized["manage_url"] = f"http://{device_ip}:80"

    status_values = {}
    for key in RUNTIME_STATUS_FIELD_ORDER:
        value = extracted.get(key)
        if isinstance(value, str) and value.strip():
            status_values[key] = value.strip()
    summary = _build_runtime_status_summary(status_values)
    if summary:
        normalized["status_summary"] = summary
    normalized["raw_status_text"] = cleaned_text
    return normalized


def _build_runtime_event_summary(message, runtime_payload):
    summary = (runtime_payload or {}).get("status_summary", "").strip()
    if summary:
        return summary
    text = re.sub(r"^\[[^\]]+\]\s*", "", (message or "").strip())
    return text[:255] if text else "runtime status received"


def _extract_runtime_device_payload(message):
    text = (message or "").strip()
    if not (text.startswith("{") and text.endswith("}")):
        return _extract_text_runtime_payload(text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _extract_text_runtime_payload(text)
    if not isinstance(payload, dict):
        return {}

    normalized = {}
    field_aliases = {
        "esp32_ip": ("esp32_ip", "ip", "device_ip"),
        "manage_url": ("manage_url", "url"),
        "device_name": ("device_name", "name"),
        "category": ("category", "device_type"),
    }
    for target, aliases in field_aliases.items():
        for key in aliases:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                normalized[target] = value.strip()
                break
    if isinstance(payload.get("sensors"), list):
        normalized["sensors"] = payload.get("sensors")
    if normalized.get("esp32_ip") and not normalized.get("manage_url"):
        normalized["manage_url"] = f"http://{normalized['esp32_ip']}:80"

    status_values = {}
    for key in RUNTIME_STATUS_FIELD_ORDER:
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            cleaned = value.strip()
        else:
            cleaned = str(value).strip()
        if cleaned:
            status_values[key] = cleaned
    summary = _build_runtime_status_summary(status_values)
    if summary:
        normalized["status_summary"] = summary
    normalized["raw_status_text"] = text
    return normalized


class ManagedAiotTcpServer:
    IDLE_OFFLINE_SECONDS = 360
    KEEPALIVE_TIME_MS = 4000
    KEEPALIVE_INTERVAL_MS = 1000

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

    def _append_event(self, box_id, event_type, event_summary="", raw_payload=""):
        AiotServerRepository.append_server_event(
            server_id=self.server_id,
            box_id=box_id,
            event_type=event_type,
            event_summary=event_summary,
            raw_payload=raw_payload,
        )

    def _mark_device_offline(self, box_id, conn=None):
        normalized_box_id = (box_id or "").strip()
        if not normalized_box_id:
            return
        self.unbind_device_connection(normalized_box_id, conn)
        DeviceRepository.set_device_connection_status(
            box_id=normalized_box_id,
            is_online=False,
            server_id=None,
        )

    def _configure_device_connection(self, conn):
        if conn is None:
            return
        try:
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except (AttributeError, OSError):
            return

        keepalive_ioctl = getattr(socket, "SIO_KEEPALIVE_VALS", None)
        if keepalive_ioctl is None or not hasattr(conn, "ioctl"):
            return

        try:
            conn.ioctl(
                keepalive_ioctl,
                (1, self.KEEPALIVE_TIME_MS, self.KEEPALIVE_INTERVAL_MS),
            )
        except OSError:
            return

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
            self._mark_device_offline(normalized_box_id)
            self._append_event(
                normalized_box_id,
                "command_failed",
                "device offline when sending command",
                normalized_command,
            )
            raise LookupError("device_offline")
        try:
            conn.sendall(f"{normalized_command}\n".encode("utf-8"))
        except OSError:
            self._mark_device_offline(normalized_box_id, conn)
            self._append_event(
                normalized_box_id,
                "command_failed",
                "socket write failed when sending command",
                normalized_command,
            )
            raise LookupError("device_offline")
        AiotServerRepository.append_server_message(
            server_id=self.server_id,
            box_id=normalized_box_id,
            message_text=f"CMD> {normalized_command}",
        )
        self._append_event(
            normalized_box_id,
            "command_sent",
            f"command sent: {normalized_command}",
            normalized_command,
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
        disconnect_error = None
        try:
            with conn:
                conn.settimeout(1)
                self._configure_device_connection(conn)
                while not self._stop_event.is_set():
                    try:
                        raw = conn.recv(1024)
                    except socket.timeout:
                        continue
                    except OSError as exc:
                        disconnect_error = str(exc).strip() or exc.__class__.__name__
                        break
                    if not raw:
                        break
                    message = raw.decode("utf-8", errors="ignore").strip()
                    if not message:
                        continue
                    box_id = _extract_box_id(message)
                    runtime_payload = _extract_runtime_device_payload(message)
                    if box_id:
                        is_first_bind = current_box_id != box_id
                        current_box_id = box_id
                        self.bind_device_connection(current_box_id, conn)
                        if is_first_bind:
                            self._append_event(
                                current_box_id,
                                "device_identify",
                                f"device identified by {self.server_name}",
                                message,
                            )
                            self._append_event(
                                current_box_id,
                                "device_online",
                                "tcp=online",
                                message,
                            )
                    resolved_box_id = box_id or current_box_id
                    if runtime_payload and resolved_box_id:
                        DeviceRepository.sync_device_runtime_data(resolved_box_id, runtime_payload)
                    if resolved_box_id and (runtime_payload or not box_id):
                        self._append_event(
                            resolved_box_id,
                            "status_report",
                            _build_runtime_event_summary(message, runtime_payload),
                            message,
                        )
                    AiotServerRepository.append_server_message(
                        server_id=self.server_id,
                        box_id=box_id or current_box_id,
                        message_text=message,
                    )
                    if current_box_id:
                        DataReportRepository.record_event(
                            "device_report",
                            "runtime_message",
                            message,
                            box_id=current_box_id,
                            device_name=(runtime_payload.get("device_name") or ""),
                            server_id=self.server_id,
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
                self._mark_device_offline(current_box_id, conn)
                if disconnect_error:
                    self._append_event(
                        current_box_id,
                        "device_disconnect_error",
                        "socket disconnected unexpectedly",
                        disconnect_error,
                    )
                self._append_event(
                    current_box_id,
                    "device_offline",
                    "tcp=offline",
                    "",
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
