"""Data report repository for unified device activity history."""

from app.models.db import get_connection


class DataReportRepository:
    @staticmethod
    def record_event(
        event_type,
        action_name,
        detail_text="",
        *,
        actor_name="",
        box_id="",
        device_name="",
        server_id=None,
    ):
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO device_event_logs (
                    event_type,
                    actor_name,
                    box_id,
                    device_name,
                    action_name,
                    detail_text,
                    server_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (event_type or "").strip(),
                    (actor_name or "").strip(),
                    (box_id or "").strip(),
                    (device_name or "").strip(),
                    (action_name or "").strip(),
                    (detail_text or "").strip()[:500],
                    server_id,
                ),
            )

    @staticmethod
    def list_recent_events(limit=20):
        with get_connection() as conn:
            return conn.execute(
                """
                SELECT
                    id,
                    event_type,
                    actor_name,
                    box_id,
                    device_name,
                    action_name,
                    detail_text,
                    server_id,
                    created_at
                FROM device_event_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    @staticmethod
    def build_summary():
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_count,
                    SUM(CASE WHEN event_type = 'device_report' THEN 1 ELSE 0 END) AS device_report_count,
                    SUM(CASE WHEN event_type = 'user_action' THEN 1 ELSE 0 END) AS user_action_count,
                    SUM(CASE WHEN date(created_at) = date('now') THEN 1 ELSE 0 END) AS today_count
                FROM device_event_logs
                """
            ).fetchone()
            active_devices = conn.execute(
                """
                SELECT COUNT(DISTINCT box_id) AS total
                FROM device_event_logs
                WHERE box_id != ''
                  AND created_at >= datetime('now', '-1 day')
                """
            ).fetchone()["total"]
        return {
            "total_count": row["total_count"] or 0,
            "device_report_count": row["device_report_count"] or 0,
            "user_action_count": row["user_action_count"] or 0,
            "today_count": row["today_count"] or 0,
            "active_device_count": active_devices or 0,
        }

    @staticmethod
    def build_daily_trend(days=7):
        with get_connection() as conn:
            rows = conn.execute(
                """
                WITH RECURSIVE day_series(day_index, day_label) AS (
                    SELECT 0, date('now', ?)
                    UNION ALL
                    SELECT day_index + 1, date(day_label, '+1 day')
                    FROM day_series
                    WHERE day_index < ?
                )
                SELECT
                    day_label,
                    COALESCE(SUM(CASE WHEN logs.event_type = 'device_report' THEN 1 ELSE 0 END), 0) AS device_report_count,
                    COALESCE(SUM(CASE WHEN logs.event_type = 'user_action' THEN 1 ELSE 0 END), 0) AS user_action_count
                FROM day_series
                LEFT JOIN device_event_logs logs ON date(logs.created_at) = day_series.day_label
                GROUP BY day_label
                ORDER BY day_label ASC
                """,
                (f"-{days - 1} day", days - 1),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def build_source_breakdown():
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT event_type, COUNT(*) AS total
                FROM device_event_logs
                GROUP BY event_type
                ORDER BY total DESC, event_type ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]
