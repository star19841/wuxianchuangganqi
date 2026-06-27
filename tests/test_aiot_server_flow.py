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
            server_name="AIOT 消息服务",
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
        self.assertIn("AIOT 服务器管理", html)
        self.assertIn("AIOT 消息服务", html)
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
        self.assertIn("data-sensor-select", html)
        self.assertIn("data-command-input", html)
        self.assertIn("例如 on", html)

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
