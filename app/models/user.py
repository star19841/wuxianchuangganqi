"""用户数据访问层。"""

import hashlib
import secrets
import sqlite3

from app.models.db import get_connection


def _hash_password(password: str, salt: bytes) -> str:
    derived_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return derived_key.hex()


class UserRepository:
    """面向 Controller 暴露的用户仓储方法。"""

    DEFAULT_ADMIN = {
        "username": "star",
        "password": "12345678",
        "display_name": "超级管理员",
        "phone": "13800000000",
    }

    @staticmethod
    def ensure_default_admin():
        if UserRepository.get_user_by_username(UserRepository.DEFAULT_ADMIN["username"]):
            return
        UserRepository.create_user(**UserRepository.DEFAULT_ADMIN)

    @staticmethod
    def create_user(username: str, password: str, display_name: str, phone: str) -> bool:
        salt = secrets.token_bytes(16)
        password_hash = _hash_password(password, salt)
        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO users (username, display_name, phone, password_hash, salt, is_disabled)
                    VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (username, display_name, phone, password_hash, salt.hex()),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def get_user_by_username(username: str):
        with get_connection() as conn:
            return conn.execute(
                """
                SELECT id, username, display_name, phone, password_hash, salt, is_disabled, created_at
                FROM users
                WHERE username = ?
                """,
                (username,),
            ).fetchone()

    @staticmethod
    def get_user_by_id(user_id: int):
        with get_connection() as conn:
            return conn.execute(
                """
                SELECT id, username, display_name, phone, password_hash, salt, is_disabled, created_at
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()

    @staticmethod
    def verify_user(username: str, password: str) -> bool:
        row = UserRepository.get_user_by_username(username)
        if not row or row["is_disabled"]:
            return False
        salt = bytes.fromhex(row["salt"])
        return _hash_password(password, salt) == row["password_hash"]

    @staticmethod
    def is_disabled(username: str) -> bool:
        row = UserRepository.get_user_by_username(username)
        return bool(row and row["is_disabled"])

    @staticmethod
    def list_users(page: int, page_size: int, keyword: str):
        offset = max(page - 1, 0) * page_size
        normalized = f"%{keyword.strip()}%"
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, username, display_name, phone, is_disabled, created_at
                FROM users
                WHERE username LIKE ? OR display_name LIKE ? OR phone LIKE ?
                ORDER BY id ASC
                LIMIT ? OFFSET ?
                """,
                (normalized, normalized, normalized, page_size, offset),
            ).fetchall()
            total = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM users
                WHERE username LIKE ? OR display_name LIKE ? OR phone LIKE ?
                """,
                (normalized, normalized, normalized),
            ).fetchone()["total"]
        return rows, total

    @staticmethod
    def update_user(user_id: int, display_name: str, phone: str, password: str = "") -> bool:
        try:
            with get_connection() as conn:
                if password:
                    salt = secrets.token_bytes(16)
                    password_hash = _hash_password(password, salt)
                    conn.execute(
                        """
                        UPDATE users
                        SET display_name = ?, phone = ?, password_hash = ?, salt = ?
                        WHERE id = ?
                        """,
                        (display_name, phone, password_hash, salt.hex(), user_id),
                    )
                else:
                    conn.execute(
                        "UPDATE users SET display_name = ?, phone = ? WHERE id = ?",
                        (display_name, phone, user_id),
                    )
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def delete_user(user_id: int):
        with get_connection() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    @staticmethod
    def set_user_disabled(username: str, disabled: bool):
        with get_connection() as conn:
            conn.execute(
                "UPDATE users SET is_disabled = ? WHERE username = ?",
                (1 if disabled else 0, username),
            )

    @staticmethod
    def set_user_disabled_by_id(user_id: int, disabled: bool):
        with get_connection() as conn:
            conn.execute(
                "UPDATE users SET is_disabled = ? WHERE id = ?",
                (1 if disabled else 0, user_id),
            )
