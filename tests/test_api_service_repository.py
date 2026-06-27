import os
import shutil
import tempfile
import unittest

from app.models import db


class ApiServiceRepositoryTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir, "test.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_api_service(self):
        from app.models.api_service import ApiServiceRepository

        created = ApiServiceRepository.create_service(
            name="天气接口",
            category="天气",
            base_url="https://example.com/weather",
            method="GET",
            headers_json='{"Authorization":"Bearer token"}',
            sample_params='{"city":"beijing"}',
            description="天气查询",
            is_enabled=True,
        )
        self.assertTrue(created)
        rows, total = ApiServiceRepository.list_services(page=1, page_size=20, keyword="")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["name"], "天气接口")

    def test_list_services_supports_search_and_pagination(self):
        from app.models.api_service import ApiServiceRepository

        for index in range(21):
            ApiServiceRepository.create_service(
                name=f"接口{index}",
                category="新闻" if index % 2 else "音乐",
                base_url=f"https://example.com/{index}",
                method="GET",
                headers_json="{}",
                sample_params="{}",
                description="测试接口",
                is_enabled=True,
            )

        page1, total = ApiServiceRepository.list_services(page=1, page_size=20, keyword="")
        page2, _ = ApiServiceRepository.list_services(page=2, page_size=20, keyword="")
        search_rows, search_total = ApiServiceRepository.list_services(page=1, page_size=20, keyword="接口3")

        self.assertEqual(total, 21)
        self.assertEqual(len(page1), 20)
        self.assertEqual(len(page2), 1)
        self.assertEqual(search_total, 1)
        self.assertEqual(search_rows[0]["name"], "接口3")


if __name__ == "__main__":
    unittest.main()
