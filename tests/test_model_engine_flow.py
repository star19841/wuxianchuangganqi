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
APP_SPEC = importlib.util.spec_from_file_location("agent_app_module_models", APP_MODULE_PATH)
app_module = importlib.util.module_from_spec(APP_SPEC)
APP_SPEC.loader.exec_module(app_module)


class ModelEngineFlowTestCase(AsyncHTTPTestCase):
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

    def test_model_engines_page_renders(self):
        cookies = self._login_cookies()
        response = self.fetch(
            "/model-engines",
            headers={"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())},
        )
        html = response.body.decode("utf-8")
        self.assertEqual(response.code, 200)
        self.assertIn("模型引擎", html)
        self.assertIn("data-model-chat-modal", html)
        self.assertIn("data-model-chat-open", html)

    def test_model_chat_endpoint_can_auto_send_aiot_command(self):
        from app.models.aiot_server import AiotServerRepository
        from app.models.device import DeviceRepository
        from app.models.model_engine import ModelEngineRepository

        model_created = ModelEngineRepository.create_model(
            name="AIOT Assistant",
            api_key="test-key",
            api_url="https://example.test/api/v1",
            model_name="qwen-test",
            temperature=0.7,
            max_tokens=1024,
            is_default=True,
        )
        self.assertTrue(model_created)
        model = ModelEngineRepository.get_default_model()

        server_id = AiotServerRepository.create_server(
            server_name="AIOT Service",
            listen_ip="0.0.0.0",
            listen_port=9010,
            is_enabled=True,
        )
        DeviceRepository.create_device(
            box_id="BOX-AI-01",
            esp32_ip="192.168.1.88",
            manage_url="http://192.168.1.88",
            device_name="Living Board",
            category="AIOT",
            sensors=[
                {"sensor_name": "LED", "pin_code": "GPIO15", "pin_remark": "status"},
                {"sensor_name": "Screen", "pin_code": "GPIO21", "pin_remark": "oled"},
            ],
        )
        DeviceRepository.set_device_connection_status(
            box_id="BOX-AI-01",
            is_online=True,
            server_id=server_id,
        )

        cookies = self._login_cookies()
        xsrf_value = cookies["_xsrf"]
        cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
        body = urllib.parse.urlencode(
            {
                "_xsrf": xsrf_value,
                "model_id": str(model["id"]),
                "message": "打开客厅开发板的LED",
            }
        )

        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "reply": "已为您打开客厅开发板 LED。",
                                "target_box_id": "BOX-AI-01",
                                "command_text": "on",
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }

        class FakeManager:
            def __init__(self):
                self.calls = []

            def send_command(self, current_server_id, box_id, command_text):
                self.calls.append((current_server_id, box_id, command_text))

        fake_manager = FakeManager()

        with (
            mock.patch("app.controllers.model_engine._request_json", return_value=fake_response),
            mock.patch("app.controllers.model_engine.AiotServerManager.instance", return_value=fake_manager),
        ):
            response = self.fetch(
                "/model-engines/chat",
                method="POST",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Cookie": cookie_header,
                    "Accept": "application/json",
                },
                body=body,
            )

        payload = json.loads(response.body.decode("utf-8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(payload["reply"], "已为您打开客厅开发板 LED。")
        self.assertTrue(payload["command_sent"])
        self.assertEqual(payload["command_text"], "on")
        self.assertEqual(fake_manager.calls, [(server_id, "BOX-AI-01", "on")])

    def test_parse_aiot_chat_response_extracts_json_from_markdown_block(self):
        from app.controllers.model_engine import _parse_aiot_chat_response

        content = """根据您的描述，下面是结果：

```json
{"reply":"已为您关闭灯光","target_box_id":"12345","command_text":"off"}
```
"""

        payload = _parse_aiot_chat_response(content)

        self.assertEqual(payload["reply"], "已为您关闭灯光")
        self.assertEqual(payload["target_box_id"], "12345")
        self.assertEqual(payload["command_text"], "off")

    def test_aiot_chat_system_prompt_uses_simple_light_commands(self):
        from app.controllers.model_engine import _build_aiot_chat_system_prompt

        prompt = _build_aiot_chat_system_prompt(
            [
                {
                    "server_id": 4,
                    "server_name": "AIOT Service",
                    "box_id": "12345",
                    "device_name": "ESP32开发板",
                    "category": "AIOT",
                    "sensors": [{"sensor_name": "LED", "pin_code": "GPIO15", "pin_remark": "status"}],
                }
            ]
        )

        self.assertIn("on", prompt)
        self.assertIn("off", prompt)
        self.assertIn("status", prompt)
        self.assertNotIn("sensor LED GPIO15 on", prompt)

    def test_model_chat_endpoint_uses_extended_timeout(self):
        from app.models.model_engine import ModelEngineRepository

        model_created = ModelEngineRepository.create_model(
            name="Timeout Probe",
            api_key="test-key",
            api_url="https://example.test/api/v1",
            model_name="qwen-test",
            temperature=0.7,
            max_tokens=1024,
            is_default=True,
        )
        self.assertTrue(model_created)
        model = ModelEngineRepository.get_default_model()

        cookies = self._login_cookies()
        xsrf_value = cookies["_xsrf"]
        cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
        body = urllib.parse.urlencode(
            {
                "_xsrf": xsrf_value,
                "model_id": str(model["id"]),
                "message": "你好",
            }
        )

        captured = {}

        def fake_request_json(url, payload, headers, timeout=8):
            captured["url"] = url
            captured["timeout"] = timeout
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "reply": "你好",
                                    "target_box_id": "",
                                    "command_text": "",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

        with mock.patch("app.controllers.model_engine._request_json", side_effect=fake_request_json):
            response = self.fetch(
                "/model-engines/chat",
                method="POST",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Cookie": cookie_header,
                    "Accept": "application/json",
                },
                body=body,
            )

        self.assertEqual(response.code, 200)
        self.assertEqual(captured["url"], "https://example.test/api/v1/chat/completions")
        self.assertEqual(captured["timeout"], 90)


if __name__ == "__main__":
    unittest.main()
