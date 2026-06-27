"""AIOT server management handlers."""

from datetime import datetime, timedelta
import math
from urllib.parse import quote

import tornado.web

from app.controllers.base import BaseHandler
from app.models.aiot_server import AiotServerRepository
from app.models.data_report import DataReportRepository
from app.services.aiot_server_manager import AiotServerManager


AIOT_SERVER_PAGE_SIZE = 6
CHINA_TIME_OFFSET = timedelta(hours=8)


def _format_message_created_at(created_at):
    timestamp = (created_at or "").strip()
    if not timestamp:
        return ""
    try:
        utc_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return timestamp
    return (utc_time + CHINA_TIME_OFFSET).strftime("%Y-%m-%d %H:%M:%S")


def _build_runtime_summary(row):
    if row["online_count"] > 0 and row["recent_messages"]:
        return "已收到设备上报消息，下面展示最近运行记录。"
    if row["online_count"] > 0:
        return "已有设备在线，当前正在等待新的上报消息。"
    latest_event = (row.get("recent_events") or [])[-1] if row.get("recent_events") else None
    if row["is_running"] and latest_event:
        latest_type = (latest_event.get("event_type") or "").strip()
        latest_box_id = (latest_event.get("box_id") or "").strip()
        if latest_type == "device_offline":
            if latest_box_id:
                return f"设备 {latest_box_id} 已离线，TCPServer 仍在监听，等待重新连接。"
            return "设备已离线，TCPServer 仍在监听，等待重新连接。"
        if latest_type == "device_disconnect_error":
            if latest_box_id:
                return f"设备 {latest_box_id} 异常断开，TCPServer 仍在监听，等待重新连接。"
            return "设备异常断开，TCPServer 仍在监听，等待重新连接。"
    if row["is_running"]:
        return "TCPServer 正在监听，等待设备主动接入并上报 boxid / deviceid。"
    return "服务当前未运行，启动后即可接收设备主动上报的消息。"


def _decorate_server_rows(rows):
    server_ids = [row["id"] for row in rows]
    messages_by_server = AiotServerRepository.list_recent_messages_by_server_ids(server_ids)
    events_by_server = AiotServerRepository.list_recent_events_by_server_ids(server_ids)
    recent_devices_by_server = AiotServerRepository.list_recent_reported_devices_by_server_ids(server_ids)
    online_devices_by_server = AiotServerRepository.list_online_devices_by_server_ids(server_ids)
    decorated = []
    for row in rows:
        item = dict(row)
        recent_messages = [dict(message) for message in reversed(messages_by_server.get(row["id"], []))]
        for message in recent_messages:
            message["created_at"] = _format_message_created_at(message["created_at"])
        recent_events = [dict(event) for event in reversed(events_by_server.get(row["id"], []))]
        for event in recent_events:
            event["created_at"] = _format_message_created_at(event["created_at"])
        item["recent_messages"] = recent_messages
        item["recent_events"] = recent_events
        item["recent_reported_devices"] = [dict(device) for device in recent_devices_by_server.get(row["id"], [])]
        item["online_devices"] = online_devices_by_server.get(row["id"], [])
        item["runtime_summary"] = _build_runtime_summary(item)
        decorated.append(item)
    return decorated


def _build_command_devices(rows):
    devices = []
    for row in rows:
        for device in row.get("online_devices", []):
            devices.append(
                {
                    "server_id": row["id"],
                    "box_id": device["box_id"],
                    "device_name": device["device_name"],
                    "category": device["category"],
                    "sensors": device["sensors"],
                }
            )
    return devices


def _serialize_server_runtime(row):
    return {
        "id": row["id"],
        "online_count": row["online_count"],
        "online_box_ids": row["online_box_ids"],
        "is_running": bool(row["is_running"]),
        "is_enabled": bool(row["is_enabled"]),
        "runtime_summary": row["runtime_summary"],
        "recent_messages": [
            {
                "box_id": message["box_id"],
                "message_text": message["message_text"],
                "created_at": message["created_at"],
            }
            for message in row["recent_messages"]
        ],
        "recent_events": [
            {
                "box_id": event["box_id"],
                "event_type": event["event_type"],
                "event_summary": event["event_summary"],
                "created_at": event["created_at"],
            }
            for event in row["recent_events"]
        ],
        "recent_reported_devices": [
            {
                "box_id": device["box_id"],
                "last_event_type": device["last_event_type"],
                "event_summary": device["event_summary"],
            }
            for device in row["recent_reported_devices"]
        ],
        "online_devices": [
            {
                "server_id": row["id"],
                "box_id": device["box_id"],
                "device_name": device["device_name"],
                "category": device["category"],
                "sensors": [
                    {
                        "sensor_name": sensor["sensor_name"],
                        "pin_code": sensor["pin_code"],
                        "pin_remark": sensor["pin_remark"],
                    }
                    for sensor in device["sensors"]
                ],
            }
            for device in row["online_devices"]
        ],
    }


class AiotServerListHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        keyword = (self.get_argument("keyword", "") or "").strip()
        page = max(int(self.get_argument("page", "1") or "1"), 1)
        edit_id = int(self.get_argument("edit_id", "0") or "0")

        rows, total = AiotServerRepository.list_servers(
            page=page,
            page_size=AIOT_SERVER_PAGE_SIZE,
            keyword=keyword,
        )
        decorated_rows = _decorate_server_rows(rows)
        editing = AiotServerRepository.get_server_by_id(edit_id) if edit_id else None
        total_pages = max(math.ceil(total / AIOT_SERVER_PAGE_SIZE), 1)

        self.render(
            "aiot_servers.html",
            title="AIOT服务管理",
            username=self.current_user,
            servers=decorated_rows,
            command_devices=_build_command_devices(decorated_rows),
            keyword=keyword,
            page=page,
            total=total,
            total_pages=total_pages,
            editing=editing,
            error=self.get_argument("error", ""),
            success=self.get_argument("success", ""),
            runtime_url=f"/aiot-servers/runtime?page={page}&keyword={quote(keyword)}",
            active_nav="aiot_servers",
        )


class AiotServerRuntimeHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        keyword = (self.get_argument("keyword", "") or "").strip()
        page = max(int(self.get_argument("page", "1") or "1"), 1)
        rows, _total = AiotServerRepository.list_servers(
            page=page,
            page_size=AIOT_SERVER_PAGE_SIZE,
            keyword=keyword,
        )
        decorated_rows = _decorate_server_rows(rows)
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write({"servers": [_serialize_server_runtime(row) for row in decorated_rows]})


class AiotServerSaveHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        server_id = int(self.get_body_argument("server_id", "0") or "0")
        server_name = (self.get_body_argument("server_name", "") or "").strip()
        listen_ip = (self.get_body_argument("listen_ip", "0.0.0.0") or "0.0.0.0").strip()
        listen_port = (self.get_body_argument("listen_port", "") or "").strip()
        is_enabled = self.get_body_argument("is_enabled", "0") == "1"

        if not server_name or not listen_port:
            target = f"/aiot-servers?error={quote('请完整填写服务器信息')}"
            if server_id:
                target += f"&edit_id={server_id}"
            self.redirect(target)
            return

        try:
            listen_port_int = int(listen_port)
        except ValueError:
            target = f"/aiot-servers?error={quote('监听端口必须是数字')}"
            if server_id:
                target += f"&edit_id={server_id}"
            self.redirect(target)
            return

        if server_id:
            updated = AiotServerRepository.update_server(
                server_id=server_id,
                server_name=server_name,
                listen_ip=listen_ip,
                listen_port=listen_port_int,
                is_enabled=is_enabled,
            )
            if not updated:
                self.redirect(f"/aiot-servers?edit_id={server_id}&error={quote('服务名称或端口已存在')}")
                return
            try:
                if is_enabled:
                    AiotServerManager.instance().restart_server(server_id)
                else:
                    AiotServerManager.instance().stop_server(server_id)
            except OSError as exc:
                self.redirect(f"/aiot-servers?edit_id={server_id}&error={quote(f'服务启动失败：{exc}')}")
                return
            self.redirect(f"/aiot-servers?success={quote('服务配置已更新')}")
            return

        created = AiotServerRepository.create_server(
            server_name=server_name,
            listen_ip=listen_ip,
            listen_port=listen_port_int,
            is_enabled=is_enabled,
        )
        if not created:
            self.redirect(f"/aiot-servers?error={quote('服务名称或端口已存在')}")
            return

        if is_enabled:
            try:
                AiotServerManager.instance().start_server(created)
            except OSError as exc:
                self.redirect(f"/aiot-servers?error={quote(f'服务创建成功，但启动失败：{exc}')}")
                return
        self.redirect(f"/aiot-servers?success={quote('服务创建成功')}")


class AiotServerDeleteHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        server_id = int(self.get_body_argument("server_id"))
        AiotServerManager.instance().stop_server(server_id)
        AiotServerRepository.delete_server(server_id)
        self.redirect(f"/aiot-servers?success={quote('服务已删除')}")


class AiotServerToggleHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        server_id = int(self.get_body_argument("server_id"))
        is_enabled = self.get_body_argument("is_enabled", "0") == "1"
        AiotServerRepository.set_enabled(server_id, is_enabled)
        try:
            if is_enabled:
                AiotServerManager.instance().start_server(server_id)
                message = "服务已启用并启动"
            else:
                AiotServerManager.instance().stop_server(server_id)
                message = "服务已停用"
        except OSError as exc:
            self.redirect(f"/aiot-servers?error={quote(f'服务启用失败：{exc}')}")
            return
        self.redirect(f"/aiot-servers?success={quote(message)}")


class AiotServerStartHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        server_id = int(self.get_body_argument("server_id"))
        try:
            AiotServerManager.instance().start_server(server_id)
        except OSError as exc:
            self.redirect(f"/aiot-servers?error={quote(f'服务启动失败：{exc}')}")
            return
        self.redirect(f"/aiot-servers?success={quote('服务已启动')}")


class AiotServerStopHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        server_id = int(self.get_body_argument("server_id"))
        AiotServerManager.instance().stop_server(server_id)
        self.redirect(f"/aiot-servers?success={quote('服务已停止')}")


class AiotServerSendCommandHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        server_id = int(self.get_body_argument("server_id", "0") or "0")
        box_id = (
            self.get_body_argument("box_id", "")
            or self.get_body_argument("boxid", "")
            or self.get_body_argument("device_id", "")
            or self.get_body_argument("deviceid", "")
            or ""
        ).strip()
        command_text = (self.get_body_argument("command_text", "") or "").strip()

        if not server_id or not box_id or not command_text:
            self.redirect(f"/aiot-servers?error={quote('请选择在线设备并填写命令')}")
            return

        try:
            AiotServerManager.instance().send_command(server_id, box_id, command_text)
        except (LookupError, ValueError, OSError) as exc:
            self.redirect(f"/aiot-servers?error={quote(f'命令发送失败：{exc}')}")
            return

        DataReportRepository.record_event(
            "user_action",
            "send_command",
            command_text,
            actor_name=self.current_user,
            box_id=box_id,
            server_id=server_id,
        )
        self.redirect(f"/aiot-servers?success={quote(f'命令已发送到 {box_id}')}")
