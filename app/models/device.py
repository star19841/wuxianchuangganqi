"""设备数据访问层。"""

import sqlite3

from app.models.data_report import DataReportRepository
from app.models.db import get_connection


class DeviceRepository:
    @staticmethod
    def create_device(box_id, esp32_ip, manage_url, device_name, category, sensors):
        try:
            with get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO devices (box_id, esp32_ip, manage_url, device_name, category)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (box_id, esp32_ip, manage_url, device_name, category),
                )
                device_id = cursor.lastrowid
                for sensor in sensors:
                    conn.execute(
                        """
                        INSERT INTO device_sensors (device_id, sensor_name, pin_code, pin_remark)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            device_id,
                            sensor["sensor_name"],
                            sensor["pin_code"],
                            sensor.get("pin_remark", ""),
                        ),
                    )
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def list_devices(page, page_size, keyword):
        offset = max(page - 1, 0) * page_size
        normalized = f"%{keyword.strip()}%"
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    d.id,
                    d.box_id,
                    d.esp32_ip,
                    d.manage_url,
                    d.device_name,
                    d.category,
                    d.online_status,
                    d.last_seen_at,
                    d.connected_server_id,
                    s.server_name AS connected_server_name,
                    COALESCE(sensor_stats.sensor_summary, '') AS sensor_summary,
                    d.created_at
                FROM devices d
                LEFT JOIN aiot_servers s ON s.id = d.connected_server_id
                LEFT JOIN (
                    SELECT
                        device_id,
                        GROUP_CONCAT(sensor_name || ' / ' || pin_code, ' | ') AS sensor_summary
                    FROM device_sensors
                    GROUP BY device_id
                ) sensor_stats ON sensor_stats.device_id = d.id
                WHERE d.box_id LIKE ? OR d.device_name LIKE ? OR d.category LIKE ? OR d.esp32_ip LIKE ?
                ORDER BY d.id DESC
                LIMIT ? OFFSET ?
                """,
                (normalized, normalized, normalized, normalized, page_size, offset),
            ).fetchall()
            total = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM devices
                WHERE box_id LIKE ? OR device_name LIKE ? OR category LIKE ? OR esp32_ip LIKE ?
                """,
                (normalized, normalized, normalized, normalized),
            ).fetchone()["total"]
        return rows, total

    @staticmethod
    def get_device_detail(device_id):
        with get_connection() as conn:
            device = conn.execute(
                """
                SELECT
                    d.id,
                    d.box_id,
                    d.esp32_ip,
                    d.manage_url,
                    d.device_name,
                    d.category,
                    d.online_status,
                    d.last_seen_at,
                    d.connected_server_id,
                    s.server_name AS connected_server_name,
                    d.created_at
                FROM devices d
                LEFT JOIN aiot_servers s ON s.id = d.connected_server_id
                WHERE d.id = ?
                """,
                (device_id,),
            ).fetchone()
            if not device:
                return None
            sensors = conn.execute(
                """
                SELECT id, device_id, sensor_name, pin_code, pin_remark
                FROM device_sensors
                WHERE device_id = ?
                ORDER BY id ASC
                """,
                (device_id,),
            ).fetchall()
        return {"device": device, "sensors": sensors}

    @staticmethod
    def get_device_detail_by_box_id(box_id):
        with get_connection() as conn:
            row = conn.execute("SELECT id FROM devices WHERE box_id = ?", (box_id,)).fetchone()
        if not row:
            return None
        return DeviceRepository.get_device_detail(row["id"])

    @staticmethod
    def update_device(device_id, box_id, esp32_ip, manage_url, device_name, category, sensors):
        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE devices
                    SET box_id = ?, esp32_ip = ?, manage_url = ?, device_name = ?, category = ?
                    WHERE id = ?
                    """,
                    (box_id, esp32_ip, manage_url, device_name, category, device_id),
                )
                conn.execute("DELETE FROM device_sensors WHERE device_id = ?", (device_id,))
                for sensor in sensors:
                    conn.execute(
                        """
                        INSERT INTO device_sensors (device_id, sensor_name, pin_code, pin_remark)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            device_id,
                            sensor["sensor_name"],
                            sensor["pin_code"],
                            sensor.get("pin_remark", ""),
                        ),
                    )
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def sync_device_runtime_data(box_id, runtime_data):
        normalized_box_id = (box_id or "").strip()
        payload = dict(runtime_data or {})
        if not normalized_box_id:
            return False

        updates = []
        values = []
        for column in ("esp32_ip", "manage_url", "device_name", "category"):
            value = payload.get(column)
            if isinstance(value, str) and value.strip():
                updates.append(f"{column} = ?")
                values.append(value.strip())

        if not updates:
            return False

        values.append(normalized_box_id)
        with get_connection() as conn:
            existing = conn.execute(
                """
                SELECT id, device_name, esp32_ip, manage_url, category
                FROM devices
                WHERE box_id = ?
                """,
                (normalized_box_id,),
            ).fetchone()
            if not existing:
                return False
            conn.execute(
                f"""
                UPDATE devices
                SET {", ".join(updates)}
                WHERE box_id = ?
                """,
                values,
            )
            refreshed = conn.execute(
                """
                SELECT id, device_name, esp32_ip, manage_url, category
                FROM devices
                WHERE box_id = ?
                """,
                (normalized_box_id,),
            ).fetchone()

        changed_fields = []
        for column in ("device_name", "esp32_ip", "manage_url", "category"):
            if refreshed[column] != existing[column]:
                changed_fields.append(f"{column}={refreshed[column]}")
        if changed_fields:
            DataReportRepository.record_event(
                "system_sync",
                "runtime_sync",
                ", ".join(changed_fields),
                box_id=normalized_box_id,
                device_name=refreshed["device_name"],
            )
        return True

    @staticmethod
    def set_device_connection_status(box_id, is_online, server_id=None):
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE devices
                SET online_status = ?,
                    last_seen_at = datetime('now'),
                    connected_server_id = ?
                WHERE box_id = ?
                """,
                (1 if is_online else 0, server_id if is_online else None, box_id),
            )

    @staticmethod
    def delete_device(device_id):
        with get_connection() as conn:
            conn.execute("DELETE FROM device_sensors WHERE device_id = ?", (device_id,))
            conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
