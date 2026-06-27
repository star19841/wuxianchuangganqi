import importlib.util
import os
import shutil
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from tornado.testing import AsyncHTTPTestCase

from app.models import db

APP_MODULE_PATH = Path(__file__).resolve().parents[1] / "app.py"
APP_SPEC = importlib.util.spec_from_file_location("agent_app_module_device", APP_MODULE_PATH)
app_module = importlib.util.module_from_spec(APP_SPEC)
APP_SPEC.loader.exec_module(app_module)


class DeviceFlowTestCase(AsyncHTTPTestCase):
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

    def test_devices_page_renders_sidebar_navigation(self):
        cookies = self._login_cookies()
        response = self.fetch(
            "/devices",
            headers={"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())},
        )
        html = response.body.decode("utf-8")
        self.assertEqual(response.code, 200)
        self.assertIn("用户列表", html)
        self.assertIn("设备管理", html)
        self.assertIn("新增设备", html)

    def test_create_device_via_http(self):
        from app.models.device import DeviceRepository

        cookies = self._login_cookies()
        xsrf_value = cookies["_xsrf"]
        body = urllib.parse.urlencode(
            [
                ("box_id", "HTTP-BOX-01"),
                ("esp32_ip", "192.168.1.66"),
                ("manage_url", "http://192.168.1.66:80"),
                ("device_name", "HTTP创建设备"),
                ("category", "照明"),
                ("sensor_name", "DHT22"),
                ("pin_code", "GPIO4"),
                ("pin_remark", "温湿度"),
                ("sensor_name", "OLED"),
                ("pin_code", "GPIO21"),
                ("pin_remark", "显示屏"),
                ("_xsrf", xsrf_value),
            ]
        )
        response = self.fetch(
            "/devices/save",
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items()),
            },
            body=body,
            follow_redirects=False,
        )

        self.assertEqual(response.code, 302)
        self.assertEqual(
            response.headers["Location"],
            "/devices?success=%E8%AE%BE%E5%A4%87%E5%88%9B%E5%BB%BA%E6%88%90%E5%8A%9F",
        )
        detail = DeviceRepository.get_device_detail_by_box_id("HTTP-BOX-01")
        self.assertIsNotNone(detail)
        self.assertEqual(len(detail["sensors"]), 2)

        list_response = self.fetch(
            "/devices",
            headers={"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())},
        )
        list_html = list_response.body.decode("utf-8")
        self.assertIn("DHT22", list_html)
        self.assertIn("OLED", list_html)
        self.assertIn("data-sensor-chip", list_html)


if __name__ == "__main__":
    unittest.main()
