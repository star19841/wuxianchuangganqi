import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tornado.testing import AsyncHTTPTestCase

from app.models import db
from app.models.model_engine import ModelEngineRepository

APP_MODULE_PATH = Path(__file__).resolve().parents[1] / "app.py"
APP_SPEC = importlib.util.spec_from_file_location("agent_app_module_mobile", APP_MODULE_PATH)
app_module = importlib.util.module_from_spec(APP_SPEC)
APP_SPEC.loader.exec_module(app_module)


class MobileAppFlowTestCase(AsyncHTTPTestCase):
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

    def test_mobile_chat_uses_default_model(self):
        model_created = ModelEngineRepository.create_model(
            name="Mobile Default",
            api_key="test-key",
            api_url="https://example.test/api/v1",
            model_name="qwen-mobile",
            temperature=0.7,
            max_tokens=1024,
            is_default=True,
        )
        self.assertTrue(model_created)

        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"reply": "浣犲ソ锛岃繖閲屾槸绉诲姩绔 AI", "target_box_id": "", "command_text": ""},
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }

        with mock.patch("app.controllers.model_engine._request_json", return_value=fake_response):
            response = self.fetch(
                "/mobile/chat",
                method="POST",
                headers={"Content-Type": "application/json"},
                body=json.dumps({"message": "浣犲ソ"}),
            )

        payload = json.loads(response.body.decode("utf-8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(payload["reply"], "浣犲ソ锛岃繖閲屾槸绉诲姩绔 AI")
        self.assertEqual(payload["model"], "qwen-mobile")
