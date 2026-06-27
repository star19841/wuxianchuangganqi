import os
import shutil
import tempfile
import unittest

from app.models import db


class ModelEngineRepositoryTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir, "test.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_db_creates_default_model(self):
        from app.models.model_engine import ModelEngineRepository

        rows, total = ModelEngineRepository.list_models(page=1, page_size=6, keyword="")
        self.assertGreaterEqual(total, 1)
        default_model = ModelEngineRepository.get_default_model()
        self.assertIsNotNone(default_model)
        self.assertEqual(default_model["model_name"], "qwen3.5-flash")
        self.assertEqual(default_model["is_default"], 1)

    def test_set_default_model_keeps_single_default(self):
        from app.models.model_engine import ModelEngineRepository

        ModelEngineRepository.create_model(
            name="备用模型",
            api_key="test-key",
            api_url="https://example.com/v1",
            model_name="demo-model",
            temperature=0.6,
            max_tokens=2048,
            is_default=False,
        )
        rows, _ = ModelEngineRepository.list_models(page=1, page_size=6, keyword="")
        latest = rows[0]
        ModelEngineRepository.set_default_model(latest["id"])

        default_rows = [row for row in ModelEngineRepository.list_all_models() if row["is_default"]]
        self.assertEqual(len(default_rows), 1)
        self.assertEqual(default_rows[0]["id"], latest["id"])

    def test_list_models_supports_search_and_pagination(self):
        from app.models.model_engine import ModelEngineRepository

        for index in range(7):
            ModelEngineRepository.create_model(
                name=f"模型{index}",
                api_key=f"key-{index}",
                api_url="https://example.com/v1",
                model_name=f"model-{index}",
                temperature=0.5,
                max_tokens=1024,
                is_default=False,
            )

        page1, total = ModelEngineRepository.list_models(page=1, page_size=6, keyword="")
        page2, _ = ModelEngineRepository.list_models(page=2, page_size=6, keyword="")
        search_rows, search_total = ModelEngineRepository.list_models(page=1, page_size=6, keyword="模型3")

        self.assertGreaterEqual(total, 8)
        self.assertEqual(len(page1), 6)
        self.assertGreaterEqual(len(page2), 2)
        self.assertEqual(search_total, 1)
        self.assertEqual(search_rows[0]["name"], "模型3")


if __name__ == "__main__":
    unittest.main()
