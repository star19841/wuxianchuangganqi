import os
import shutil
import tempfile
import unittest

from app.models import db


class DeviceRepositoryTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir, "test.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_device_persists_sensor_rows(self):
        from app.models.device import DeviceRepository

        created = DeviceRepository.create_device(
            box_id="BOX-001",
            esp32_ip="192.168.1.50",
            manage_url="http://192.168.1.50:80",
            device_name="展厅一号盒子",
            category="环境监测",
            sensors=[
                {"sensor_name": "DHT22", "pin_code": "GPIO4", "pin_remark": "温湿度"},
                {"sensor_name": "LED", "pin_code": "GPIO2", "pin_remark": "状态灯"},
            ],
        )

        self.assertTrue(created)
        detail = DeviceRepository.get_device_detail_by_box_id("BOX-001")
        self.assertIsNotNone(detail)
        self.assertEqual(detail["device"]["device_name"], "展厅一号盒子")
        self.assertEqual(len(detail["sensors"]), 2)
        self.assertEqual(detail["sensors"][0]["sensor_name"], "DHT22")

    def test_box_id_must_be_unique(self):
        from app.models.device import DeviceRepository

        first = DeviceRepository.create_device(
            box_id="BOX-UNIQUE",
            esp32_ip="192.168.1.51",
            manage_url="http://192.168.1.51:80",
            device_name="设备一",
            category="测试",
            sensors=[],
        )
        second = DeviceRepository.create_device(
            box_id="BOX-UNIQUE",
            esp32_ip="192.168.1.52",
            manage_url="http://192.168.1.52:80",
            device_name="设备二",
            category="测试",
            sensors=[],
        )

        self.assertTrue(first)
        self.assertFalse(second)

    def test_list_devices_supports_search_and_pagination(self):
        from app.models.device import DeviceRepository

        for index in range(7):
            DeviceRepository.create_device(
                box_id=f"BOX-{index:03d}",
                esp32_ip=f"192.168.1.{100 + index}",
                manage_url=f"http://192.168.1.{100 + index}:80",
                device_name=f"设备{index}",
                category="照明" if index % 2 == 0 else "环境",
                sensors=[],
            )

        page1, total1 = DeviceRepository.list_devices(page=1, page_size=6, keyword="")
        page2, total2 = DeviceRepository.list_devices(page=2, page_size=6, keyword="")
        search_rows, search_total = DeviceRepository.list_devices(page=1, page_size=6, keyword="设备3")

        self.assertEqual(total1, 7)
        self.assertEqual(total2, 7)
        self.assertEqual(len(page1), 6)
        self.assertEqual(len(page2), 1)
        self.assertEqual(search_total, 1)
        self.assertEqual(search_rows[0]["box_id"], "BOX-003")

    def test_delete_device_removes_sensor_rows(self):
        from app.models.device import DeviceRepository

        DeviceRepository.create_device(
            box_id="BOX-DEL",
            esp32_ip="192.168.1.88",
            manage_url="http://192.168.1.88:80",
            device_name="待删除设备",
            category="测试",
            sensors=[{"sensor_name": "人体红外", "pin_code": "GPIO13", "pin_remark": "门禁"}],
        )
        detail = DeviceRepository.get_device_detail_by_box_id("BOX-DEL")

        DeviceRepository.delete_device(detail["device"]["id"])
        deleted = DeviceRepository.get_device_detail_by_box_id("BOX-DEL")

        self.assertIsNone(deleted)


if __name__ == "__main__":
    unittest.main()
