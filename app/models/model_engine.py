"""模型引擎数据访问层。"""

import sqlite3

from app.models.db import get_connection


class ModelEngineRepository:
    DEFAULT_MODEL = {
        "name": "默认模型引擎",
        "api_key": "sk-aigc-1a1e29be656757152aee327e2c3481355c3b5596",
        "api_url": "https://aigc-api.aitoolcore.com/api/v1",
        "model_name": "qwen3.5-flash",
        "temperature": 0.7,
        "max_tokens": 2048,
        "is_default": True,
    }

    @staticmethod
    def ensure_default_model():
        if ModelEngineRepository.get_default_model():
            return
        ModelEngineRepository.create_model(**ModelEngineRepository.DEFAULT_MODEL)

    @staticmethod
    def list_models(page, page_size, keyword):
        offset = max(page - 1, 0) * page_size
        normalized = f"%{keyword.strip()}%"
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, name, api_key, api_url, model_name, temperature, max_tokens, is_default, created_at
                FROM model_engines
                WHERE name LIKE ? OR model_name LIKE ? OR api_url LIKE ?
                ORDER BY is_default DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (normalized, normalized, normalized, page_size, offset),
            ).fetchall()
            total = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM model_engines
                WHERE name LIKE ? OR model_name LIKE ? OR api_url LIKE ?
                """,
                (normalized, normalized, normalized),
            ).fetchone()["total"]
        return rows, total

    @staticmethod
    def list_all_models():
        with get_connection() as conn:
            return conn.execute(
                """
                SELECT id, name, api_key, api_url, model_name, temperature, max_tokens, is_default, created_at
                FROM model_engines
                ORDER BY is_default DESC, id DESC
                """
            ).fetchall()

    @staticmethod
    def get_model_by_id(model_id):
        with get_connection() as conn:
            return conn.execute(
                """
                SELECT id, name, api_key, api_url, model_name, temperature, max_tokens, is_default, created_at
                FROM model_engines
                WHERE id = ?
                """,
                (model_id,),
            ).fetchone()

    @staticmethod
    def get_default_model():
        with get_connection() as conn:
            return conn.execute(
                """
                SELECT id, name, api_key, api_url, model_name, temperature, max_tokens, is_default, created_at
                FROM model_engines
                WHERE is_default = 1
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

    @staticmethod
    def create_model(name, api_key, api_url, model_name, temperature, max_tokens, is_default):
        try:
            with get_connection() as conn:
                if is_default:
                    conn.execute("UPDATE model_engines SET is_default = 0")
                conn.execute(
                    """
                    INSERT INTO model_engines (
                        name, api_key, api_url, model_name, temperature, max_tokens, is_default
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        api_key,
                        api_url,
                        model_name,
                        float(temperature),
                        int(max_tokens),
                        1 if is_default else 0,
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def update_model(model_id, name, api_key, api_url, model_name, temperature, max_tokens, is_default):
        try:
            with get_connection() as conn:
                if is_default:
                    conn.execute("UPDATE model_engines SET is_default = 0")
                conn.execute(
                    """
                    UPDATE model_engines
                    SET name = ?, api_key = ?, api_url = ?, model_name = ?, temperature = ?, max_tokens = ?, is_default = ?
                    WHERE id = ?
                    """,
                    (
                        name,
                        api_key,
                        api_url,
                        model_name,
                        float(temperature),
                        int(max_tokens),
                        1 if is_default else 0,
                        model_id,
                    ),
                )
            if not ModelEngineRepository.get_default_model():
                ModelEngineRepository.set_default_model(model_id)
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def set_default_model(model_id):
        with get_connection() as conn:
            conn.execute("UPDATE model_engines SET is_default = 0")
            conn.execute("UPDATE model_engines SET is_default = 1 WHERE id = ?", (model_id,))

    @staticmethod
    def delete_model(model_id):
        with get_connection() as conn:
            row = conn.execute(
                "SELECT is_default FROM model_engines WHERE id = ?",
                (model_id,),
            ).fetchone()
            conn.execute("DELETE FROM model_engines WHERE id = ?", (model_id,))
        if row and row["is_default"]:
            fallback = ModelEngineRepository.list_all_models()
            if fallback:
                ModelEngineRepository.set_default_model(fallback[0]["id"])
