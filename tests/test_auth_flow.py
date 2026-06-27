import importlib.util
import os
import shutil
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from tornado.testing import AsyncHTTPTestCase

from app.models import db
from app.models.user import UserRepository

APP_MODULE_PATH = Path(__file__).resolve().parents[1] / "app.py"
APP_SPEC = importlib.util.spec_from_file_location("agent_app_module", APP_MODULE_PATH)
app_module = importlib.util.module_from_spec(APP_SPEC)
APP_SPEC.loader.exec_module(app_module)


class AuthFlowTestCase(AsyncHTTPTestCase):
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

    def _xsrf_cookie(self):
        response = self.fetch("/auth/login")
        set_cookie = response.headers.get_list("Set-Cookie")
        for item in set_cookie:
            if "_xsrf=" in item:
                return item.split("_xsrf=")[1].split(";")[0]
        self.fail("未获取到 _xsrf cookie")

    def _form_headers(self, xsrf_value):
        return {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": f"_xsrf={xsrf_value}",
        }

    def test_default_admin_can_login(self):
        xsrf_value = self._xsrf_cookie()
        body = urllib.parse.urlencode(
            {"username": "star", "password": "12345678", "_xsrf": xsrf_value}
        )
        response = self.fetch(
            "/auth/login",
            method="POST",
            headers=self._form_headers(xsrf_value),
            body=body,
            follow_redirects=False,
        )
        self.assertEqual(response.code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_auth_pages_use_unified_brand_layout(self):
        for path in ["/auth/login", "/auth/register"]:
            response = self.fetch(path)
            html = response.body.decode("utf-8")
            self.assertEqual(response.code, 200)
            self.assertIn('class="auth-shell ops-auth-shell"', html)
            self.assertIn('auth-card ops-auth-card', html)
            self.assertIn("CdutAgentOS", html)

    def test_register_accepts_display_name_and_phone(self):
        xsrf_value = self._xsrf_cookie()
        body = urllib.parse.urlencode(
            {
                "username": "newuser",
                "password": "pass12345",
                "password2": "pass12345",
                "display_name": "新用户",
                "phone": "13900001111",
                "_xsrf": xsrf_value,
            }
        )
        response = self.fetch(
            "/auth/register",
            method="POST",
            headers=self._form_headers(xsrf_value),
            body=body,
            follow_redirects=False,
        )
        self.assertEqual(response.code, 302)
        self.assertEqual(response.headers["Location"], "/auth/login")
        created = UserRepository.get_user_by_username("newuser")
        self.assertEqual(created["display_name"], "新用户")
        self.assertEqual(created["phone"], "13900001111")

    def test_disabled_user_cannot_login(self):
        UserRepository.create_user(
            username="disabled_user",
            password="pass12345",
            display_name="禁用用户",
            phone="13900002222",
        )
        UserRepository.set_user_disabled("disabled_user", True)
        xsrf_value = self._xsrf_cookie()
        body = urllib.parse.urlencode(
            {"username": "disabled_user", "password": "pass12345", "_xsrf": xsrf_value}
        )
        response = self.fetch(
            "/auth/login",
            method="POST",
            headers=self._form_headers(xsrf_value),
            body=body,
        )
        self.assertEqual(response.code, 403)
        self.assertIn("已被禁用", response.body.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
