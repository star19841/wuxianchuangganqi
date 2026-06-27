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
            name="weather-demo-service",
            category="weather-demo",
            base_url="https://example.com/weather",
            method="GET",
            headers_json='{"Authorization":"Bearer token"}',
            sample_params='{"city":"beijing"}',
            description="weather lookup",
            is_enabled=True,
        )
        self.assertTrue(created)
        rows, total = ApiServiceRepository.list_services(page=1, page_size=20, keyword="")
        self.assertEqual(total, 2)
        self.assertEqual(rows[0]["name"], "weather-demo-service")

    def test_list_services_supports_search_and_pagination(self):
        from app.models.api_service import ApiServiceRepository

        for index in range(21):
            ApiServiceRepository.create_service(
                name=f"service-{index}",
                category="news" if index % 2 else "music",
                base_url=f"https://example.com/{index}",
                method="GET",
                headers_json="{}",
                sample_params="{}",
                description="test service",
                is_enabled=True,
            )

        page1, total = ApiServiceRepository.list_services(page=1, page_size=20, keyword="")
        page2, _ = ApiServiceRepository.list_services(page=2, page_size=20, keyword="")
        search_rows, search_total = ApiServiceRepository.list_services(page=1, page_size=20, keyword="service-3")

        self.assertEqual(total, 22)
        self.assertEqual(len(page1), 20)
        self.assertEqual(len(page2), 2)
        self.assertEqual(search_total, 1)
        self.assertEqual(search_rows[0]["name"], "service-3")

    def test_init_db_seeds_builtin_weather_service(self):
        from app.models.api_service import ApiServiceRepository

        rows, total = ApiServiceRepository.list_services(page=1, page_size=20, keyword="wttr.in")

        self.assertGreaterEqual(total, 1)
        self.assertIn("wttr.in", rows[0]["base_url"])
        self.assertIn("{city}", rows[0]["base_url"])
        self.assertIn("city", rows[0]["sample_params"])


if __name__ == "__main__":
    unittest.main()
