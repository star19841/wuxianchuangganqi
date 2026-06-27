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

    def test_create_device_persists_remark_and_runtime_status_fields(self):
        from app.models.device import DeviceRepository

        created = DeviceRepository.create_device(
            box_id="BOX-STATUS-01",
            esp32_ip="192.168.1.91",
            manage_url="http://192.168.1.91:80",
            device_name="Runtime Box",
            category="Lamp",
            sensors=[],
            remark="desk lamp",
        )

        self.assertTrue(created)
        DeviceRepository.sync_device_runtime_data(
            "BOX-STATUS-01",
            {
                "status_summary": "LED=On | wifi=connected",
                "raw_status_text": '{"LED":"On","wifi":"connected"}',
            },
        )

        detail = DeviceRepository.get_device_detail_by_box_id("BOX-STATUS-01")
        self.assertEqual(detail["device"]["remark"], "desk lamp")
        self.assertEqual(detail["device"]["status_summary"], "LED=On | wifi=connected")
        self.assertIn('"LED":"On"', detail["device"]["raw_status_text"])

    def test_sync_device_runtime_data_auto_registers_minimal_device(self):
        from app.models.device import DeviceRepository

        synced = DeviceRepository.sync_device_runtime_data(
            "BOX-AUTO-01",
            {
                "esp32_ip": "192.168.1.92",
                "device_name": "Auto Device",
                "category": "Sensor",
                "status_summary": "human=detected",
                "raw_status_text": '{"human":"detected"}',
            },
        )

        self.assertTrue(synced)
        detail = DeviceRepository.get_device_detail_by_box_id("BOX-AUTO-01")
        self.assertEqual(detail["device"]["esp32_ip"], "192.168.1.92")
        self.assertEqual(detail["device"]["device_name"], "Auto Device")
        self.assertEqual(detail["device"]["category"], "Sensor")
        self.assertEqual(detail["device"]["status_summary"], "human=detected")

    def test_sync_device_runtime_data_auto_registers_sensor_manifest(self):
        from app.models.device import DeviceRepository

        synced = DeviceRepository.sync_device_runtime_data(
            "BOX-AUTO-SENSORS-01",
            {
                "esp32_ip": "192.168.1.94",
                "device_name": "Manifest Device",
                "category": "AIOT",
                "sensors": [
                    {"sensor_name": "LED", "pin_code": "GPIO15", "pin_remark": "板载LED"},
                    {"sensor_name": "DHT11", "pin_code": "GPIO16", "pin_remark": "温湿度"},
                ],
            },
        )

        self.assertTrue(synced)
        detail = DeviceRepository.get_device_detail_by_box_id("BOX-AUTO-SENSORS-01")
        self.assertEqual(len(detail["sensors"]), 2)
        self.assertEqual(detail["sensors"][0]["sensor_name"], "LED")
        self.assertEqual(detail["sensors"][1]["pin_code"], "GPIO16")

    def test_sync_device_runtime_data_keeps_manual_remark_while_refreshing_runtime_fields(self):
        from app.models.device import DeviceRepository

        DeviceRepository.create_device(
            box_id="BOX-MANUAL-01",
            esp32_ip="192.168.1.93",
            manage_url="http://192.168.1.93:80",
            device_name="Manual Device",
            category="Lighting",
            sensors=[],
            remark="keep me",
        )

        DeviceRepository.sync_device_runtime_data(
            "BOX-MANUAL-01",
            {
                "esp32_ip": "10.0.0.5",
                "manage_url": "http://10.0.0.5:80",
                "device_name": "Runtime Override",
                "category": "Runtime Type",
                "status_summary": "tcp=online",
                "raw_status_text": '{"tcp":"online"}',
            },
        )

        detail = DeviceRepository.get_device_detail_by_box_id("BOX-MANUAL-01")
        self.assertEqual(detail["device"]["esp32_ip"], "10.0.0.5")
        self.assertEqual(detail["device"]["manage_url"], "http://10.0.0.5:80")
        self.assertEqual(detail["device"]["device_name"], "Runtime Override")
        self.assertEqual(detail["device"]["category"], "Runtime Type")
        self.assertEqual(detail["device"]["remark"], "keep me")
        self.assertEqual(detail["device"]["status_summary"], "tcp=online")

    def test_sync_device_runtime_data_replaces_sensor_manifest_when_runtime_payload_provides_it(self):
        from app.models.device import DeviceRepository

        DeviceRepository.create_device(
            box_id="BOX-MANIFEST-UPDATE-01",
            esp32_ip="192.168.1.95",
            manage_url="http://192.168.1.95:80",
            device_name="Update Device",
            category="AIOT",
            sensors=[
                {"sensor_name": "Old Sensor", "pin_code": "GPIO1", "pin_remark": "old"},
            ],
            remark="keep me",
        )

        DeviceRepository.sync_device_runtime_data(
            "BOX-MANIFEST-UPDATE-01",
            {
                "sensors": [
                    {"sensor_name": "LED", "pin_code": "GPIO15", "pin_remark": "板载LED"},
                    {"sensor_name": "人体", "pin_code": "GPIO17", "pin_remark": "PIR"},
                ],
            },
        )

        detail = DeviceRepository.get_device_detail_by_box_id("BOX-MANIFEST-UPDATE-01")
        self.assertEqual(detail["device"]["remark"], "keep me")
        self.assertEqual(len(detail["sensors"]), 2)
        self.assertEqual(detail["sensors"][0]["sensor_name"], "LED")
        self.assertEqual(detail["sensors"][1]["sensor_name"], "人体")


if __name__ == "__main__":
    unittest.main()
