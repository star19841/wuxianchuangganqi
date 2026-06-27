"""Data report handlers."""

from datetime import datetime, timedelta

import tornado.web

from app.controllers.base import BaseHandler
from app.models.data_report import DataReportRepository


CHINA_TIME_OFFSET = timedelta(hours=8)


def _format_created_at(created_at):
    timestamp = (created_at or "").strip()
    if not timestamp:
        return ""
    try:
        utc_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return timestamp
    return (utc_time + CHINA_TIME_OFFSET).strftime("%Y-%m-%d %H:%M:%S")


def _serialize_event(row):
    return {
        "id": row["id"],
        "event_type": row["event_type"],
        "actor_name": row["actor_name"],
        "box_id": row["box_id"],
        "device_name": row["device_name"],
        "action_name": row["action_name"],
        "detail_text": row["detail_text"],
        "server_id": row["server_id"],
        "created_at": _format_created_at(row["created_at"]),
    }


class DataReportListHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        summary = DataReportRepository.build_summary()
        recent_events = [_serialize_event(row) for row in DataReportRepository.list_recent_events(limit=12)]
        self.render(
            "data_reports.html",
            title="数据报表统计",
            username=self.current_user,
            summary=summary,
            recent_events=recent_events,
            runtime_url="/data-reports/runtime",
            active_nav="data_reports",
            success=self.get_argument("success", ""),
            error=self.get_argument("error", ""),
        )


class DataReportRuntimeHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        payload = {
            "summary": DataReportRepository.build_summary(),
            "daily_trend": DataReportRepository.build_daily_trend(),
            "source_breakdown": DataReportRepository.build_source_breakdown(),
            "recent_events": [_serialize_event(row) for row in DataReportRepository.list_recent_events(limit=12)],
        }
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write(payload)
