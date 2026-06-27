"""Device management handlers."""

import math
from urllib.parse import quote

import tornado.web

from app.controllers.base import BaseHandler
from app.models.data_report import DataReportRepository
from app.models.device import DeviceRepository


DEVICE_PAGE_SIZE = 6


def _build_sensor_rows(sensor_names, pin_codes, pin_remarks):
    sensors = []
    for sensor_name, pin_code, pin_remark in zip(sensor_names, pin_codes, pin_remarks):
        sensor_name = (sensor_name or "").strip()
        pin_code = (pin_code or "").strip()
        pin_remark = (pin_remark or "").strip()
        if not sensor_name and not pin_code and not pin_remark:
            continue
        sensors.append(
            {
                "sensor_name": sensor_name,
                "pin_code": pin_code,
                "pin_remark": pin_remark,
            }
        )
    return sensors


class DeviceListHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        keyword = (self.get_argument("keyword", "") or "").strip()
        page = max(int(self.get_argument("page", "1") or "1"), 1)
        edit_id = int(self.get_argument("edit_id", "0") or "0")

        devices, total = DeviceRepository.list_devices(page=page, page_size=DEVICE_PAGE_SIZE, keyword=keyword)
        editing = DeviceRepository.get_device_detail(edit_id) if edit_id else None
        total_pages = max(math.ceil(total / DEVICE_PAGE_SIZE), 1)

        self.render(
            "devices.html",
            title="设备管理",
            username=self.current_user,
            devices=devices,
            keyword=keyword,
            page=page,
            total=total,
            total_pages=total_pages,
            editing=editing,
            error=self.get_argument("error", ""),
            success=self.get_argument("success", ""),
            active_nav="devices",
        )


class DeviceSaveHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        device_id = int(self.get_body_argument("device_id", "0") or "0")
        form_data = {
            "box_id": (self.get_body_argument("box_id", "") or "").strip(),
            "esp32_ip": (self.get_body_argument("esp32_ip", "") or "").strip(),
            "manage_url": (self.get_body_argument("manage_url", "") or "").strip(),
            "device_name": (self.get_body_argument("device_name", "") or "").strip(),
            "category": (self.get_body_argument("category", "") or "").strip(),
        }
        sensors = _build_sensor_rows(
            self.get_body_arguments("sensor_name"),
            self.get_body_arguments("pin_code"),
            self.get_body_arguments("pin_remark"),
        )
        if not all(form_data.values()):
            target = f"/devices?error={quote('请完整填写设备信息')}"
            if device_id:
                target += f"&edit_id={device_id}"
            self.redirect(target)
            return

        if device_id:
            updated = DeviceRepository.update_device(
                device_id=device_id,
                box_id=form_data["box_id"],
                esp32_ip=form_data["esp32_ip"],
                manage_url=form_data["manage_url"],
                device_name=form_data["device_name"],
                category=form_data["category"],
                sensors=sensors,
            )
            if not updated:
                self.redirect(f"/devices?edit_id={device_id}&error={quote('设备唯一编码已存在')}")
                return
            DataReportRepository.record_event(
                "user_action",
                "update_device",
                f"updated device {form_data['box_id']}",
                actor_name=self.current_user,
                box_id=form_data["box_id"],
                device_name=form_data["device_name"],
            )
            self.redirect(f"/devices?success={quote('设备更新成功')}")
            return

        created = DeviceRepository.create_device(
            box_id=form_data["box_id"],
            esp32_ip=form_data["esp32_ip"],
            manage_url=form_data["manage_url"],
            device_name=form_data["device_name"],
            category=form_data["category"],
            sensors=sensors,
        )
        if not created:
            self.redirect(f"/devices?error={quote('设备唯一编码已存在')}")
            return
        DataReportRepository.record_event(
            "user_action",
            "create_device",
            f"created device {form_data['box_id']}",
            actor_name=self.current_user,
            box_id=form_data["box_id"],
            device_name=form_data["device_name"],
        )
        self.redirect(f"/devices?success={quote('设备创建成功')}")


class DeviceDeleteHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        device_id = int(self.get_body_argument("device_id"))
        detail = DeviceRepository.get_device_detail(device_id)
        DeviceRepository.delete_device(device_id)
        if detail:
            DataReportRepository.record_event(
                "user_action",
                "delete_device",
                f"deleted device {detail['device']['box_id']}",
                actor_name=self.current_user,
                box_id=detail["device"]["box_id"],
                device_name=detail["device"]["device_name"],
            )
        self.redirect(f"/devices?success={quote('设备删除成功')}")
