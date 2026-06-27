"""设备数据访问层。"""

import sqlite3

from app.models.data_report import DataReportRepository
from app.models.db import get_connection


class DeviceRepository:
    @staticmethod
    def _normalize_runtime_sensors(raw_sensors):
        normalized = []
        if not isinstance(raw_sensors, list):
            return normalized
        for sensor in raw_sensors:
            if not isinstance(sensor, dict):
                continue
            sensor_name = str(sensor.get("sensor_name") or "").strip()
            pin_code = str(sensor.get("pin_code") or "").strip()
            pin_remark = str(sensor.get("pin_remark") or "").strip()
            if not sensor_name and not pin_code and not pin_remark:
                continue
            normalized.append(
                {
                    "sensor_name": sensor_name,
                    "pin_code": pin_code,
                    "pin_remark": pin_remark,
                }
            )
        return normalized

    @staticmethod
    def _replace_device_sensors(conn, device_id, sensors):
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

    @staticmethod
    def create_device(box_id, esp32_ip, manage_url, device_name, category, sensors, remark=""):
        try:
            with get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO devices (box_id, esp32_ip, manage_url, device_name, category, remark)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (box_id, esp32_ip, manage_url, device_name, category, remark),
                )
                device_id = cursor.lastrowid
                DeviceRepository._replace_device_sensors(
                    conn,
                    device_id,
                    DeviceRepository._normalize_runtime_sensors(sensors),
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
                    d.remark,
                    d.status_summary,
                    d.raw_status_text,
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
                WHERE d.box_id LIKE ? OR d.device_name LIKE ? OR d.category LIKE ? OR d.esp32_ip LIKE ? OR d.manage_url LIKE ? OR d.remark LIKE ?
                ORDER BY d.id DESC
                LIMIT ? OFFSET ?
                """,
                (normalized, normalized, normalized, normalized, normalized, normalized, page_size, offset),
            ).fetchall()
            total = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM devices
                WHERE box_id LIKE ? OR device_name LIKE ? OR category LIKE ? OR esp32_ip LIKE ? OR manage_url LIKE ? OR remark LIKE ?
                """,
                (normalized, normalized, normalized, normalized, normalized, normalized),
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
                    d.remark,
                    d.status_summary,
                    d.raw_status_text,
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
    def update_device(device_id, box_id, esp32_ip, manage_url, device_name, category, sensors, remark=""):
        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE devices
                    SET box_id = ?, esp32_ip = ?, manage_url = ?, device_name = ?, category = ?, remark = ?
                    WHERE id = ?
                    """,
                    (box_id, esp32_ip, manage_url, device_name, category, remark, device_id),
                )
                DeviceRepository._replace_device_sensors(
                    conn,
                    device_id,
                    DeviceRepository._normalize_runtime_sensors(sensors),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def sync_device_runtime_data(box_id, runtime_data):
        normalized_box_id = (box_id or "").strip()
        payload = dict(runtime_data or {})
        runtime_sensors = DeviceRepository._normalize_runtime_sensors(payload.get("sensors"))
        if not normalized_box_id:
            return False

        with get_connection() as conn:
            existing = conn.execute(
                """
                SELECT id, device_name, esp32_ip, manage_url, category, remark, status_summary, raw_status_text
                FROM devices
                WHERE box_id = ?
                """,
                (normalized_box_id,),
            ).fetchone()
            if not existing:
                conn.execute(
                    """
                    INSERT INTO devices (box_id, esp32_ip, manage_url, device_name, category, remark, status_summary, raw_status_text)
                    VALUES (?, ?, ?, ?, ?, '', '', '')
                    """,
                    (
                        normalized_box_id,
                        (payload.get("esp32_ip") or "").strip(),
                        (payload.get("manage_url") or "").strip(),
                        (payload.get("device_name") or "").strip() or "ESP32 Device",
                        (payload.get("category") or "").strip() or "未分类",
                    ),
                )
                existing = conn.execute(
                    """
                    SELECT id, device_name, esp32_ip, manage_url, category, remark, status_summary, raw_status_text
                    FROM devices
                    WHERE box_id = ?
                    """,
                    (normalized_box_id,),
                ).fetchone()
            device_id = existing["id"]

            updates = []
            values = []
            for column in ("esp32_ip", "manage_url", "device_name", "category"):
                incoming_value = payload.get(column)
                if isinstance(incoming_value, str) and incoming_value.strip():
                    updates.append(f"{column} = ?")
                    values.append(incoming_value.strip())

            for column in ("status_summary", "raw_status_text"):
                incoming_value = payload.get(column)
                if isinstance(incoming_value, str):
                    updates.append(f"{column} = ?")
                    values.append(incoming_value.strip())

            if not updates:
                if runtime_sensors:
                    DeviceRepository._replace_device_sensors(conn, device_id, runtime_sensors)
                return True

            values.append(normalized_box_id)
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
                SELECT id, device_name, esp32_ip, manage_url, category, remark, status_summary, raw_status_text
                FROM devices
                WHERE box_id = ?
                """,
                (normalized_box_id,),
            ).fetchone()
            if runtime_sensors:
                DeviceRepository._replace_device_sensors(conn, device_id, runtime_sensors)

        changed_fields = []
        for column in ("device_name", "esp32_ip", "manage_url", "category", "status_summary", "raw_status_text"):
            if refreshed[column] != existing[column]:
                changed_fields.append(f"{column}={refreshed[column]}")
        if runtime_sensors:
            changed_fields.append(f"sensors={len(runtime_sensors)}")
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
