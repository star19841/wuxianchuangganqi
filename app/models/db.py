"""SQLite 数据库基础设施。"""

import os
import sqlite3


def _project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


DB_PATH = os.path.join(_project_root(), "database", "app.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn, table_name: str, column_name: str, definition: str):
    columns = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def init_db():
    """初始化数据库结构，并兼容旧库缺失列。"""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '' UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                is_disabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        _ensure_column(conn, "users", "display_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "users", "phone", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "users", "is_disabled", "INTEGER NOT NULL DEFAULT 0")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS aiot_servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_name TEXT NOT NULL UNIQUE,
                listen_ip TEXT NOT NULL DEFAULT '0.0.0.0',
                listen_port INTEGER NOT NULL UNIQUE,
                is_enabled INTEGER NOT NULL DEFAULT 1,
                is_running INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                box_id TEXT NOT NULL UNIQUE,
                esp32_ip TEXT NOT NULL,
                manage_url TEXT NOT NULL,
                device_name TEXT NOT NULL,
                category TEXT NOT NULL,
                online_status INTEGER NOT NULL DEFAULT 0,
                last_seen_at TEXT NOT NULL DEFAULT '',
                connected_server_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        _ensure_column(conn, "devices", "online_status", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "devices", "last_seen_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "devices", "connected_server_id", "INTEGER")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS aiot_server_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER NOT NULL,
                box_id TEXT NOT NULL DEFAULT '',
                message_text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(server_id) REFERENCES aiot_servers(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS device_event_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                actor_name TEXT NOT NULL DEFAULT '',
                box_id TEXT NOT NULL DEFAULT '',
                device_name TEXT NOT NULL DEFAULT '',
                action_name TEXT NOT NULL DEFAULT '',
                detail_text TEXT NOT NULL DEFAULT '',
                server_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS device_sensors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                sensor_name TEXT NOT NULL,
                pin_code TEXT NOT NULL,
                pin_remark TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(device_id) REFERENCES devices(id)
            )
            """
        )
        conn.execute("UPDATE aiot_servers SET is_running = 0")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS model_engines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                api_key TEXT NOT NULL,
                api_url TEXT NOT NULL,
                model_name TEXT NOT NULL,
                temperature REAL NOT NULL DEFAULT 0.7,
                max_tokens INTEGER NOT NULL DEFAULT 2048,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                base_url TEXT NOT NULL,
                method TEXT NOT NULL DEFAULT 'GET',
                headers_json TEXT NOT NULL DEFAULT '{}',
                sample_params TEXT NOT NULL DEFAULT '{}',
                description TEXT NOT NULL DEFAULT '',
                is_enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
    from app.models.user import UserRepository
    from app.models.model_engine import ModelEngineRepository

    UserRepository.ensure_default_admin()
    ModelEngineRepository.ensure_default_model()
