import os
import shutil
import tempfile
import unittest

from app.models import db
from app.models.user import UserRepository


class UserRepositoryTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir, "test.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_db_creates_default_admin_user(self):
        admin = UserRepository.get_user_by_username("star")
        self.assertIsNotNone(admin)
        self.assertEqual(admin["username"], "star")
        self.assertEqual(admin["display_name"], "超级管理员")
        self.assertEqual(admin["phone"], "13800000000")
        self.assertEqual(admin["is_disabled"], 0)
        self.assertTrue(UserRepository.verify_user("star", "12345678"))

    def test_create_user_requires_unique_username_and_phone(self):
        created = UserRepository.create_user(
            username="alice",
            password="pass12345",
            display_name="爱丽丝",
            phone="13900000001",
        )
        self.assertTrue(created)

        duplicate_username = UserRepository.create_user(
            username="alice",
            password="pass12345",
            display_name="重复用户",
            phone="13900000002",
        )
        duplicate_phone = UserRepository.create_user(
            username="alice2",
            password="pass12345",
            display_name="重复手机号",
            phone="13900000001",
        )
        self.assertFalse(duplicate_username)
        self.assertFalse(duplicate_phone)

    def test_list_users_supports_search_and_pagination(self):
        for index in range(25):
            UserRepository.create_user(
                username=f"user{index}",
                password="pass12345",
                display_name=f"用户{index}",
                phone=f"13900000{index:03d}",
            )

        page1, total1 = UserRepository.list_users(page=1, page_size=20, keyword="")
        page2, total2 = UserRepository.list_users(page=2, page_size=20, keyword="")
        search_rows, search_total = UserRepository.list_users(page=1, page_size=20, keyword="用户2")

        self.assertEqual(total1, 26)
        self.assertEqual(total2, 26)
        self.assertEqual(len(page1), 20)
        self.assertEqual(len(page2), 6)
        self.assertGreaterEqual(search_total, 1)
        self.assertTrue(any(row["display_name"] == "用户2" for row in search_rows))

    def test_disable_user_blocks_login_verification(self):
        UserRepository.create_user(
            username="blocked_user",
            password="pass12345",
            display_name="被禁用用户",
            phone="13900000999",
        )

        self.assertTrue(UserRepository.verify_user("blocked_user", "pass12345"))
        UserRepository.set_user_disabled("blocked_user", True)
        self.assertFalse(UserRepository.verify_user("blocked_user", "pass12345"))


if __name__ == "__main__":
    unittest.main()
