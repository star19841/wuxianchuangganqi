"""AIOT 服务器数据访问层。"""

import sqlite3

from app.models.db import get_connection


class AiotServerRepository:
    @staticmethod
    def create_server(server_name, listen_ip, listen_port, is_enabled):
        try:
            with get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO aiot_servers (server_name, listen_ip, listen_port, is_enabled, is_running)
                    VALUES (?, ?, ?, ?, 0)
                    """,
                    (server_name, listen_ip, int(listen_port), 1 if is_enabled else 0),
                )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def update_server(server_id, server_name, listen_ip, listen_port, is_enabled):
        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE aiot_servers
                    SET server_name = ?, listen_ip = ?, listen_port = ?, is_enabled = ?
                    WHERE id = ?
                    """,
                    (
                        server_name,
                        listen_ip,
                        int(listen_port),
                        1 if is_enabled else 0,
                        server_id,
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def list_servers(page, page_size, keyword):
        offset = max(page - 1, 0) * page_size
        normalized = f"%{keyword.strip()}%"
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.id,
                    s.server_name,
                    s.listen_ip,
                    s.listen_port,
                    s.is_enabled,
                    s.is_running,
                    s.created_at,
                    COALESCE(stats.online_count, 0) AS online_count,
                    COALESCE(stats.online_box_ids, '') AS online_box_ids
                FROM aiot_servers s
                LEFT JOIN (
                    SELECT
                        connected_server_id AS server_id,
                        COUNT(*) AS online_count,
                        GROUP_CONCAT(box_id, ', ') AS online_box_ids
                    FROM devices
                    WHERE online_status = 1 AND connected_server_id IS NOT NULL
                    GROUP BY connected_server_id
                ) stats ON stats.server_id = s.id
                WHERE s.server_name LIKE ? OR s.listen_ip LIKE ? OR CAST(s.listen_port AS TEXT) LIKE ?
                ORDER BY s.id DESC
                LIMIT ? OFFSET ?
                """,
                (normalized, normalized, normalized, page_size, offset),
            ).fetchall()
            total = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM aiot_servers
                WHERE server_name LIKE ? OR listen_ip LIKE ? OR CAST(listen_port AS TEXT) LIKE ?
                """,
                (normalized, normalized, normalized),
            ).fetchone()["total"]
        return rows, total

    @staticmethod
    def append_server_message(server_id, box_id, message_text):
        cleaned_box_id = (box_id or "").strip()
        cleaned_message = (message_text or "").strip()
        if not cleaned_message:
            return
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO aiot_server_messages (server_id, box_id, message_text)
                VALUES (?, ?, ?)
                """,
                (server_id, cleaned_box_id, cleaned_message[:500]),
            )

    @staticmethod
    def list_recent_messages_by_server_ids(server_ids, limit_per_server=6):
        normalized_ids = [int(server_id) for server_id in server_ids if server_id]
        if not normalized_ids:
            return {}

        placeholders = ",".join("?" for _ in normalized_ids)
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, server_id, box_id, message_text, created_at
                FROM aiot_server_messages
                WHERE server_id IN ({placeholders})
                ORDER BY id DESC
                """,
                normalized_ids,
            ).fetchall()

        grouped = {server_id: [] for server_id in normalized_ids}
        for row in rows:
            messages = grouped.setdefault(row["server_id"], [])
            if len(messages) >= limit_per_server:
                continue
            messages.append(row)
        return grouped

    @staticmethod
    def append_server_event(server_id, box_id, event_type, event_summary="", raw_payload=""):
        cleaned_box_id = (box_id or "").strip()
        cleaned_type = (event_type or "").strip()
        if not cleaned_type:
            return
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO aiot_server_events (server_id, box_id, event_type, event_summary, raw_payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    server_id,
                    cleaned_box_id,
                    cleaned_type[:64],
                    (event_summary or "").strip()[:255],
                    (raw_payload or "").strip()[:1000],
                ),
            )

    @staticmethod
    def list_recent_events_by_server_ids(server_ids, limit_per_server=6):
        normalized_ids = [int(server_id) for server_id in server_ids if server_id]
        if not normalized_ids:
            return {}

        placeholders = ",".join("?" for _ in normalized_ids)
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, server_id, box_id, event_type, event_summary, raw_payload, created_at
                FROM aiot_server_events
                WHERE server_id IN ({placeholders})
                ORDER BY id DESC
                """,
                normalized_ids,
            ).fetchall()

        grouped = {server_id: [] for server_id in normalized_ids}
        for row in rows:
            events = grouped.setdefault(row["server_id"], [])
            if len(events) >= limit_per_server:
                continue
            events.append(row)
        return grouped

    @staticmethod
    def list_recent_reported_devices_by_server_ids(server_ids, limit_per_server=5):
        normalized_ids = [int(server_id) for server_id in server_ids if server_id]
        if not normalized_ids:
            return {}

        placeholders = ",".join("?" for _ in normalized_ids)
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT recent.server_id, recent.box_id, recent.event_type AS last_event_type, recent.event_summary
                FROM aiot_server_events recent
                INNER JOIN (
                    SELECT server_id, box_id, MAX(id) AS latest_id
                    FROM aiot_server_events
                    WHERE server_id IN ({placeholders}) AND box_id <> ''
                    GROUP BY server_id, box_id
                ) latest
                  ON latest.server_id = recent.server_id
                 AND latest.box_id = recent.box_id
                 AND latest.latest_id = recent.id
                ORDER BY recent.id DESC
                """,
                normalized_ids,
            ).fetchall()

        grouped = {server_id: [] for server_id in normalized_ids}
        for row in rows:
            devices = grouped.setdefault(row["server_id"], [])
            if len(devices) >= limit_per_server:
                continue
            devices.append(dict(row))
        return grouped

    @staticmethod
    def list_online_devices_by_server_ids(server_ids):
        normalized_ids = [int(server_id) for server_id in server_ids if server_id]
        if not normalized_ids:
            return {}

        placeholders = ",".join("?" for _ in normalized_ids)
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    d.connected_server_id AS server_id,
                    d.id AS device_id,
                    d.box_id,
                    d.device_name,
                    d.category,
                    ds.id AS sensor_id,
                    ds.sensor_name,
                    ds.pin_code,
                    ds.pin_remark
                FROM devices d
                LEFT JOIN device_sensors ds ON ds.device_id = d.id
                WHERE d.online_status = 1
                  AND d.connected_server_id IN ({placeholders})
                ORDER BY d.connected_server_id ASC, d.id ASC, ds.id ASC
                """,
                normalized_ids,
            ).fetchall()

        grouped = {server_id: [] for server_id in normalized_ids}
        device_index = {}
        for row in rows:
            key = (row["server_id"], row["device_id"])
            device = device_index.get(key)
            if not device:
                device = {
                    "server_id": row["server_id"],
                    "device_id": row["device_id"],
                    "box_id": row["box_id"],
                    "device_name": row["device_name"],
                    "category": row["category"],
                    "sensors": [],
                }
                device_index[key] = device
                grouped.setdefault(row["server_id"], []).append(device)
            if row["sensor_id"]:
                device["sensors"].append(
                    {
                        "sensor_name": row["sensor_name"],
                        "pin_code": row["pin_code"],
                        "pin_remark": row["pin_remark"],
                    }
                )
        return grouped

    @staticmethod
    def get_server_by_id(server_id):
        with get_connection() as conn:
            return conn.execute(
                """
                SELECT id, server_name, listen_ip, listen_port, is_enabled, is_running, created_at
                FROM aiot_servers
                WHERE id = ?
                """,
                (server_id,),
            ).fetchone()

    @staticmethod
    def list_enabled_servers():
        with get_connection() as conn:
            return conn.execute(
                """
                SELECT id, server_name, listen_ip, listen_port, is_enabled, is_running, created_at
                FROM aiot_servers
                WHERE is_enabled = 1
                ORDER BY id ASC
                """
            ).fetchall()

    @staticmethod
    def set_enabled(server_id, is_enabled):
        with get_connection() as conn:
            conn.execute(
                "UPDATE aiot_servers SET is_enabled = ? WHERE id = ?",
                (1 if is_enabled else 0, server_id),
            )

    @staticmethod
    def set_running(server_id, is_running):
        with get_connection() as conn:
            conn.execute(
                "UPDATE aiot_servers SET is_running = ? WHERE id = ?",
                (1 if is_running else 0, server_id),
            )

    @staticmethod
    def delete_server(server_id):
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE devices
                SET online_status = 0, connected_server_id = NULL
                WHERE connected_server_id = ?
                """,
                (server_id,),
            )
            conn.execute("DELETE FROM aiot_server_messages WHERE server_id = ?", (server_id,))
            conn.execute("DELETE FROM aiot_server_events WHERE server_id = ?", (server_id,))
            conn.execute("DELETE FROM aiot_servers WHERE id = ?", (server_id,))
