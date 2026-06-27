import os
import shutil
import tempfile
import unittest

from app.models import db


class AiotServerRepositoryTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir, "test.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_server_and_list_summary(self):
        from app.models.aiot_server import AiotServerRepository

        created = AiotServerRepository.create_server(
            server_name="主控 TCP 服务",
            listen_ip="127.0.0.1",
            listen_port=9101,
            is_enabled=True,
        )
        self.assertTrue(created)

        rows, total = AiotServerRepository.list_servers(page=1, page_size=6, keyword="")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["server_name"], "主控 TCP 服务")
        self.assertEqual(rows[0]["online_count"], 0)

    def test_list_servers_supports_search_and_connected_devices(self):
        from app.models.aiot_server import AiotServerRepository
        from app.models.device import DeviceRepository

        AiotServerRepository.create_server("服务一", "127.0.0.1", 9101, True)
        AiotServerRepository.create_server("服务二", "127.0.0.1", 9102, False)
        rows, _ = AiotServerRepository.list_servers(page=1, page_size=6, keyword="")
        first_server_id = rows[-1]["id"]

        DeviceRepository.create_device(
            box_id="BOX-ONLINE-01",
            esp32_ip="192.168.1.10",
            manage_url="http://192.168.1.10",
            device_name="在线设备",
            category="环境",
            sensors=[],
        )
        DeviceRepository.set_device_connection_status(
            box_id="BOX-ONLINE-01",
            is_online=True,
            server_id=first_server_id,
        )

        page_rows, total = AiotServerRepository.list_servers(page=1, page_size=6, keyword="")
        search_rows, search_total = AiotServerRepository.list_servers(page=1, page_size=6, keyword="服务二")

        self.assertEqual(total, 2)
        self.assertEqual(search_total, 1)
        self.assertEqual(search_rows[0]["server_name"], "服务二")
        matched = next(row for row in page_rows if row["id"] == first_server_id)
        self.assertEqual(matched["online_count"], 1)
        self.assertIn("BOX-ONLINE-01", matched["online_box_ids"])

    def test_recent_messages_can_be_collected_per_server(self):
        from app.models.aiot_server import AiotServerRepository

        server_id = AiotServerRepository.create_server(
            server_name="消息采集服务",
            listen_ip="127.0.0.1",
            listen_port=9301,
            is_enabled=True,
        )
        AiotServerRepository.append_server_message(server_id, "BOX-01", "temperature=26.5")
        AiotServerRepository.append_server_message(server_id, "BOX-01", "humidity=58")

        messages = AiotServerRepository.list_recent_messages_by_server_ids([server_id], limit_per_server=5)

        self.assertEqual(len(messages[server_id]), 2)
        self.assertEqual(messages[server_id][0]["message_text"], "humidity=58")
        self.assertEqual(messages[server_id][1]["box_id"], "BOX-01")


    def test_online_devices_include_sensor_rows_for_server(self):
        from app.models.aiot_server import AiotServerRepository
        from app.models.device import DeviceRepository

        server_id = AiotServerRepository.create_server(
            server_name="sensor control service",
            listen_ip="127.0.0.1",
            listen_port=9302,
            is_enabled=True,
        )
        DeviceRepository.create_device(
            box_id="BOX-SENSOR-01",
            esp32_ip="192.168.1.11",
            manage_url="http://192.168.1.11",
            device_name="Living Screen",
            category="Display",
            sensors=[
                {"sensor_name": "OLED", "pin_code": "GPIO21", "pin_remark": "SDA"},
                {"sensor_name": "Light", "pin_code": "GPIO34", "pin_remark": "ADC"},
            ],
        )
        DeviceRepository.set_device_connection_status(
            box_id="BOX-SENSOR-01",
            is_online=True,
            server_id=server_id,
        )

        online_devices = AiotServerRepository.list_online_devices_by_server_ids([server_id])

        self.assertEqual(len(online_devices[server_id]), 1)
        self.assertEqual(online_devices[server_id][0]["box_id"], "BOX-SENSOR-01")
        self.assertEqual(online_devices[server_id][0]["device_name"], "Living Screen")
        self.assertEqual(len(online_devices[server_id][0]["sensors"]), 2)
        self.assertEqual(online_devices[server_id][0]["sensors"][0]["sensor_name"], "OLED")


if __name__ == "__main__":
    unittest.main()
