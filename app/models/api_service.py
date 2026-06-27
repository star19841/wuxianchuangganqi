"""第三方接口数据访问层。"""

import sqlite3

from app.models.db import get_connection


class ApiServiceRepository:
    @staticmethod
    def create_service(
        name,
        category,
        base_url,
        method,
        headers_json,
        sample_params,
        description,
        is_enabled,
    ):
        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO api_services (
                        name, category, base_url, method, headers_json, sample_params, description, is_enabled
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        category,
                        base_url,
                        method.upper(),
                        headers_json,
                        sample_params,
                        description,
                        1 if is_enabled else 0,
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def list_services(page, page_size, keyword):
        offset = max(page - 1, 0) * page_size
        normalized = f"%{keyword.strip()}%"
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, name, category, base_url, method, headers_json, sample_params, description, is_enabled, created_at
                FROM api_services
                WHERE name LIKE ? OR category LIKE ? OR base_url LIKE ? OR description LIKE ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (normalized, normalized, normalized, normalized, page_size, offset),
            ).fetchall()
            total = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM api_services
                WHERE name LIKE ? OR category LIKE ? OR base_url LIKE ? OR description LIKE ?
                """,
                (normalized, normalized, normalized, normalized),
            ).fetchone()["total"]
        return rows, total

    @staticmethod
    def get_service_by_id(service_id):
        with get_connection() as conn:
            return conn.execute(
                """
                SELECT id, name, category, base_url, method, headers_json, sample_params, description, is_enabled, created_at
                FROM api_services
                WHERE id = ?
                """,
                (service_id,),
            ).fetchone()

    @staticmethod
    def update_service(
        service_id,
        name,
        category,
        base_url,
        method,
        headers_json,
        sample_params,
        description,
        is_enabled,
    ):
        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE api_services
                    SET name = ?, category = ?, base_url = ?, method = ?, headers_json = ?, sample_params = ?, description = ?, is_enabled = ?
                    WHERE id = ?
                    """,
                    (
                        name,
                        category,
                        base_url,
                        method.upper(),
                        headers_json,
                        sample_params,
                        description,
                        1 if is_enabled else 0,
                        service_id,
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def delete_service(service_id):
        with get_connection() as conn:
            conn.execute("DELETE FROM api_services WHERE id = ?", (service_id,))
