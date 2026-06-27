import importlib.util
import json
import os
import shutil
import tempfile
import unittest
import urllib.parse
from unittest import mock
from pathlib import Path

from tornado.testing import AsyncHTTPTestCase

from app.models import db

APP_MODULE_PATH = Path(__file__).resolve().parents[1] / "app.py"
APP_SPEC = importlib.util.spec_from_file_location("agent_app_module_aiot_server", APP_MODULE_PATH)
app_module = importlib.util.module_from_spec(APP_SPEC)
APP_SPEC.loader.exec_module(app_module)


class AiotServerFlowTestCase(AsyncHTTPTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir, "test.db")
        db.init_db()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        db.DB_PATH = self.original_db_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def get_app(self):
        return app_module.make_app(debug=False)

    def _split_cookies(self, response):
        cookies = {}
        for item in response.headers.get_list("Set-Cookie"):
            name, value = item.split(";", 1)[0].split("=", 1)
            cookies[name] = value
        return cookies

    def _login_cookies(self):
        login_page = self.fetch("/auth/login")
        cookies = self._split_cookies(login_page)
        xsrf_value = cookies["_xsrf"]
        body = urllib.parse.urlencode(
            {"username": "star", "password": "12345678", "_xsrf": xsrf_value}
        )
        response = self.fetch(
            "/auth/login",
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"_xsrf={xsrf_value}",
            },
            body=body,
            follow_redirects=False,
        )
        cookies.update(self._split_cookies(response))
        return cookies

    def test_aiot_servers_page_renders(self):
        from app.models.aiot_server import AiotServerRepository

        server_id = AiotServerRepository.create_server(
            server_name="AIOT Message Service",
            listen_ip="0.0.0.0",
            listen_port=8888,
            is_enabled=True,
        )
        AiotServerRepository.append_server_message(server_id, "BOX-HTTP-01", "status=ready")

        cookies = self._login_cookies()
        response = self.fetch(
            "/aiot-servers",
            headers={"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())},
        )
        html = response.body.decode("utf-8")
        self.assertEqual(response.code, 200)
        self.assertIn("AIOT", html)
        self.assertIn("AIOT Message Service", html)
        self.assertIn("status=ready", html)
        self.assertIn("BOX-HTTP-01", html)
        self.assertIn("aiot-form-intro", html)
        self.assertIn("aiot-message-stream", html)

    def test_aiot_runtime_endpoint_returns_server_messages(self):
        from app.models.aiot_server import AiotServerRepository
        from app.models.device import DeviceRepository

        server_id = AiotServerRepository.create_server(
            server_name="AIOT Runtime Service",
            listen_ip="0.0.0.0",
            listen_port=8890,
            is_enabled=True,
        )
        DeviceRepository.create_device(
            box_id="BOX-RUNTIME-01",
            esp32_ip="192.168.1.20",
            manage_url="http://192.168.1.20",
            device_name="Runtime Device",
            category="Display",
            sensors=[
                {"sensor_name": "Screen", "pin_code": "GPIO21", "pin_remark": "SDA"},
                {"sensor_name": "Light", "pin_code": "GPIO34", "pin_remark": "ADC"},
            ],
        )
        DeviceRepository.set_device_connection_status(
            box_id="BOX-RUNTIME-01",
            is_online=True,
            server_id=server_id,
        )
        AiotServerRepository.append_server_message(server_id, "BOX-RUNTIME-01", "humidity=48")

        cookies = self._login_cookies()
        response = self.fetch(
            "/aiot-servers/runtime?page=1&keyword=",
            headers={"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())},
        )

        payload = json.loads(response.body.decode("utf-8"))
        self.assertEqual(response.code, 200)
        self.assertIn("servers", payload)
        matched = next(item for item in payload["servers"] if item["id"] == server_id)
        self.assertEqual(matched["recent_messages"][0]["message_text"], "humidity=48")
        self.assertEqual(matched["recent_messages"][0]["box_id"], "BOX-RUNTIME-01")
        self.assertEqual(matched["online_devices"][0]["box_id"], "BOX-RUNTIME-01")
        self.assertEqual(matched["online_devices"][0]["sensors"][0]["sensor_name"], "Screen")

    def test_aiot_runtime_endpoint_returns_recent_events_and_recent_devices(self):
        from app.models.aiot_server import AiotServerRepository

        server_id = AiotServerRepository.create_server(
            server_name="AIOT Event Service",
            listen_ip="0.0.0.0",
            listen_port=8892,
            is_enabled=True,
        )
        AiotServerRepository.append_server_event(
            server_id=server_id,
            box_id="BOX-HISTORY-01",
            event_type="device_offline",
            event_summary="device disconnected",
            raw_payload="socket closed",
        )

        cookies = self._login_cookies()
        response = self.fetch(
            "/aiot-servers/runtime?page=1&keyword=",
            headers={"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())},
        )

        payload = json.loads(response.body.decode("utf-8"))
        matched = next(item for item in payload["servers"] if item["id"] == server_id)

        self.assertEqual(matched["recent_events"][0]["event_type"], "device_offline")
        self.assertEqual(matched["recent_reported_devices"][0]["box_id"], "BOX-HISTORY-01")
        self.assertEqual(matched["recent_reported_devices"][0]["last_event_type"], "device_offline")

    def test_aiot_runtime_summary_shows_disconnect_hint_when_latest_event_is_offline(self):
        from app.models.aiot_server import AiotServerRepository

        server_id = AiotServerRepository.create_server(
            server_name="AIOT Offline Summary Service",
            listen_ip="0.0.0.0",
            listen_port=8897,
            is_enabled=True,
        )
        AiotServerRepository.set_running(server_id, True)
        AiotServerRepository.append_server_event(
            server_id=server_id,
            box_id="BOX-OFFLINE-01",
            event_type="device_offline",
            event_summary="tcp=offline",
            raw_payload="",
        )

        cookies = self._login_cookies()
        response = self.fetch(
            "/aiot-servers/runtime?page=1&keyword=",
            headers={"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())},
        )

        payload = json.loads(response.body.decode("utf-8"))
        matched = next(item for item in payload["servers"] if item["id"] == server_id)

        self.assertIn("BOX-OFFLINE-01", matched["runtime_summary"])
        self.assertIn("离线", matched["runtime_summary"])

    def test_aiot_runtime_endpoint_keeps_latest_event_at_bottom(self):
        from app.models.aiot_server import AiotServerRepository

        server_id = AiotServerRepository.create_server(
            server_name="AIOT Event Order Service",
            listen_ip="0.0.0.0",
            listen_port=8896,
            is_enabled=True,
        )
        AiotServerRepository.append_server_event(
            server_id=server_id,
            box_id="BOX-ORDER-01",
            event_type="device_online",
            event_summary="tcp=online",
            raw_payload="first",
        )
        AiotServerRepository.append_server_event(
            server_id=server_id,
            box_id="BOX-ORDER-01",
            event_type="status_report",
            event_summary="LED=On",
            raw_payload="second",
        )

        cookies = self._login_cookies()
        response = self.fetch(
            "/aiot-servers/runtime?page=1&keyword=",
            headers={"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())},
        )

        payload = json.loads(response.body.decode("utf-8"))
        matched = next(item for item in payload["servers"] if item["id"] == server_id)

        self.assertEqual(matched["recent_events"][0]["event_type"], "device_online")
        self.assertEqual(matched["recent_events"][1]["event_type"], "status_report")

    def test_sendable_devices_remain_separate_from_recent_reported_devices(self):
        from app.models.aiot_server import AiotServerRepository

        server_id = AiotServerRepository.create_server(
            server_name="AIOT Separation Service",
            listen_ip="0.0.0.0",
            listen_port=8893,
            is_enabled=True,
        )
        AiotServerRepository.append_server_event(
            server_id=server_id,
            box_id="BOX-RECENT-ONLY",
            event_type="device_offline",
            event_summary="offline",
            raw_payload="",
        )

        cookies = self._login_cookies()
        response = self.fetch(
            "/aiot-servers/runtime?page=1&keyword=",
            headers={"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())},
        )

        payload = json.loads(response.body.decode("utf-8"))
        matched = next(item for item in payload["servers"] if item["id"] == server_id)

        self.assertEqual(matched["online_devices"], [])
        self.assertEqual(matched["recent_reported_devices"][0]["box_id"], "BOX-RECENT-ONLY")

    def test_aiot_message_timestamps_render_in_china_timezone(self):
        from app.models.aiot_server import AiotServerRepository

        server_id = AiotServerRepository.create_server(
            server_name="AIOT TZ Service",
            listen_ip="0.0.0.0",
            listen_port=8891,
            is_enabled=True,
        )
        AiotServerRepository.append_server_message(server_id, "BOX-TZ-01", "boxid:BOX-TZ-01")
        with db.get_connection() as conn:
            conn.execute(
                """
                UPDATE aiot_server_messages
                SET created_at = ?
                WHERE server_id = ?
                """,
                ("2026-06-27 00:40:19", server_id),
            )

        cookies = self._login_cookies()
        cookie_header = {"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())}

        page_response = self.fetch("/aiot-servers", headers=cookie_header)
        runtime_response = self.fetch("/aiot-servers/runtime?page=1&keyword=", headers=cookie_header)

        page_html = page_response.body.decode("utf-8")
        runtime_payload = json.loads(runtime_response.body.decode("utf-8"))
        matched = next(item for item in runtime_payload["servers"] if item["id"] == server_id)

        self.assertIn("2026-06-27 08:40:19", page_html)
        self.assertEqual(matched["recent_messages"][0]["created_at"], "2026-06-27 08:40:19")

    def test_aiot_servers_page_renders_command_panel(self):
        cookies = self._login_cookies()
        response = self.fetch(
            "/aiot-servers",
            headers={"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())},
        )
        html = response.body.decode("utf-8")

        self.assertEqual(response.code, 200)
        self.assertIn("data-command-form", html)
        self.assertIn("data-online-device-select", html)
        self.assertNotIn("data-sensor-select", html)
        self.assertIn("data-command-picker-open", html)
        self.assertIn("data-command-picker-modal", html)
        self.assertIn("led_on", html)
        self.assertIn("get_status", html)

    def test_aiot_servers_page_renders_recent_event_and_recent_device_sections(self):
        from app.models.aiot_server import AiotServerRepository

        server_id = AiotServerRepository.create_server(
            server_name="AIOT UI Service",
            listen_ip="0.0.0.0",
            listen_port=8894,
            is_enabled=True,
        )
        AiotServerRepository.append_server_event(
            server_id=server_id,
            box_id="BOX-UI-01",
            event_type="status_report",
            event_summary="wifi=ok",
            raw_payload='{"wifi":"ok"}',
        )

        cookies = self._login_cookies()
        response = self.fetch(
            "/aiot-servers",
            headers={"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())},
        )

        html = response.body.decode("utf-8")
        self.assertIn("data-recent-events", html)
        self.assertIn("data-recent-reported-devices", html)
        self.assertIn("BOX-UI-01", html)
        self.assertIn("wifi=ok", html)

    def test_send_command_accepts_boxid_alias_field(self):
        class FakeManager:
            def __init__(self):
                self.calls = []

            def send_command(self, server_id, box_id, command_text):
                self.calls.append((server_id, box_id, command_text))

        fake_manager = FakeManager()
        cookies = self._login_cookies()
        xsrf_value = cookies["_xsrf"]
        cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
        body = urllib.parse.urlencode(
            {
                "_xsrf": xsrf_value,
                "server_id": "7",
                "boxid": "BOX-ALIAS-01",
                "command_text": "status",
            }
        )

        with mock.patch("app.controllers.aiot_server.AiotServerManager.instance", return_value=fake_manager):
            response = self.fetch(
                "/aiot-servers/send-command",
                method="POST",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Cookie": cookie_header,
                },
                body=body,
                follow_redirects=False,
            )

        self.assertEqual(response.code, 302)
        self.assertEqual(fake_manager.calls, [(7, "BOX-ALIAS-01", "status")])


if __name__ == "__main__":
    unittest.main()
