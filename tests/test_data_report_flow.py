import importlib.util
import json
import os
import shutil
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from tornado.testing import AsyncHTTPTestCase

from app.models import db

APP_MODULE_PATH = Path(__file__).resolve().parents[1] / "app.py"
APP_SPEC = importlib.util.spec_from_file_location("agent_app_module_data_reports", APP_MODULE_PATH)
app_module = importlib.util.module_from_spec(APP_SPEC)
APP_SPEC.loader.exec_module(app_module)


class DataReportFlowTestCase(AsyncHTTPTestCase):
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

    def test_data_reports_page_renders_chart_and_history_sections(self):
        cookies = self._login_cookies()
        response = self.fetch(
            "/data-reports",
            headers={"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())},
        )
        html = response.body.decode("utf-8")

        self.assertEqual(response.code, 200)
        self.assertIn("数据报表统计", html)
        self.assertIn("data-report-runtime-url", html)
        self.assertIn("report-trend-chart", html)
        self.assertIn("report-source-chart", html)
        self.assertIn("report-history-table", html)

    def test_send_command_is_recorded_in_report_history(self):
        from app.models.aiot_server import AiotServerRepository
        from app.models.device import DeviceRepository

        server_id = AiotServerRepository.create_server(
            server_name="Report Server",
            listen_ip="0.0.0.0",
            listen_port=8898,
            is_enabled=True,
        )
        DeviceRepository.create_device(
            box_id="BOX-REPORT-01",
            esp32_ip="192.168.1.30",
            manage_url="http://192.168.1.30",
            device_name="Report Device",
            category="Display",
            sensors=[],
        )

        class FakeManager:
            def send_command(self, server_id, box_id, command_text):
                return None

        cookies = self._login_cookies()
        xsrf_value = cookies["_xsrf"]
        cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
        body = urllib.parse.urlencode(
            {
                "_xsrf": xsrf_value,
                "server_id": str(server_id),
                "box_id": "BOX-REPORT-01",
                "command_text": "status",
            }
        )

        with mock.patch("app.controllers.aiot_server.AiotServerManager.instance", return_value=FakeManager()):
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

        runtime = self.fetch("/data-reports/runtime", headers={"Cookie": cookie_header})
        payload = json.loads(runtime.body.decode("utf-8"))
        self.assertEqual(runtime.code, 200)
        self.assertGreaterEqual(payload["summary"]["user_action_count"], 1)
        self.assertTrue(
            any(
                event["box_id"] == "BOX-REPORT-01"
                and event["action_name"] == "send_command"
                and event["actor_name"] == "star"
                for event in payload["recent_events"]
            )
        )

