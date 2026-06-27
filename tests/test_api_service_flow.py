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
APP_SPEC = importlib.util.spec_from_file_location("agent_app_module_apis", APP_MODULE_PATH)
app_module = importlib.util.module_from_spec(APP_SPEC)
APP_SPEC.loader.exec_module(app_module)


class ApiServiceFlowTestCase(AsyncHTTPTestCase):
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

    def test_api_services_page_renders(self):
        cookies = self._login_cookies()
        response = self.fetch(
            "/api-services",
            headers={"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())},
        )
        html = response.body.decode("utf-8")
        self.assertEqual(response.code, 200)
        self.assertIn("接口管理", html)
        self.assertIn("第三方接口管理", html)

    def test_weather_proxy_endpoint_supports_wttr_city_template(self):
        class FakeResponse:
            def __init__(self, payload):
                self.status = 200
                self._payload = payload

            def read(self):
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        captured = {}

        def fake_urlopen(request, timeout=8):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return FakeResponse(b'{"current_condition":[{"temp_C":"28"}]}')

        with mock.patch("app.controllers.api_service.urlopen", side_effect=fake_urlopen):
            response = self.fetch("/api-services/weather?city=chengdu")

        payload = json.loads(response.body.decode("utf-8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(payload["city"], "chengdu")
        self.assertIn("https://wttr.in/chengdu?format=j1", captured["url"])
        self.assertEqual(captured["timeout"], 20)
        self.assertEqual(payload["data"]["current_condition"][0]["temp_C"], "28")


if __name__ == "__main__":
    unittest.main()
