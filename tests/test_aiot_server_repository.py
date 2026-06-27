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

    def test_aiot_server_events_can_be_recorded_and_listed(self):
        from app.models.aiot_server import AiotServerRepository

        server_id = AiotServerRepository.create_server(
            server_name="event service",
            listen_ip="127.0.0.1",
            listen_port=9306,
            is_enabled=True,
        )

        AiotServerRepository.append_server_event(
            server_id=server_id,
            box_id="BOX-EVENT-01",
            event_type="status_report",
            event_summary="temperature=26",
            raw_payload='{"temp":26}',
        )

        events = AiotServerRepository.list_recent_events_by_server_ids([server_id], limit_per_server=5)

        self.assertEqual(len(events[server_id]), 1)
        self.assertEqual(events[server_id][0]["event_type"], "status_report")
        self.assertEqual(events[server_id][0]["box_id"], "BOX-EVENT-01")

    def test_recent_reported_devices_include_latest_event_even_if_device_is_offline(self):
        from app.models.aiot_server import AiotServerRepository

        server_id = AiotServerRepository.create_server(
            server_name="recent device service",
            listen_ip="127.0.0.1",
            listen_port=9307,
            is_enabled=True,
        )

        AiotServerRepository.append_server_event(
            server_id=server_id,
            box_id="BOX-RECENT-01",
            event_type="device_offline",
            event_summary="device disconnected",
            raw_payload="socket closed",
        )

        devices = AiotServerRepository.list_recent_reported_devices_by_server_ids([server_id], limit_per_server=5)

        self.assertEqual(len(devices[server_id]), 1)
        self.assertEqual(devices[server_id][0]["box_id"], "BOX-RECENT-01")
        self.assertEqual(devices[server_id][0]["last_event_type"], "device_offline")

    def test_delete_server_clears_related_messages_events_and_online_bindings(self):
        from app.models.aiot_server import AiotServerRepository
        from app.models.device import DeviceRepository

        server_id = AiotServerRepository.create_server(
            server_name="cleanup service",
            listen_ip="127.0.0.1",
            listen_port=9308,
            is_enabled=True,
        )
        DeviceRepository.create_device(
            box_id="BOX-CLEAN-01",
            esp32_ip="192.168.1.45",
            manage_url="http://192.168.1.45:80",
            device_name="Cleanup Device",
            category="AIOT",
            sensors=[],
        )
        DeviceRepository.set_device_connection_status(
            box_id="BOX-CLEAN-01",
            is_online=True,
            server_id=server_id,
        )
        AiotServerRepository.append_server_message(server_id, "BOX-CLEAN-01", "hello")
        AiotServerRepository.append_server_event(
            server_id=server_id,
            box_id="BOX-CLEAN-01",
            event_type="device_offline",
            event_summary="offline",
            raw_payload="socket closed",
        )

        AiotServerRepository.delete_server(server_id)

        self.assertIsNone(AiotServerRepository.get_server_by_id(server_id))
        self.assertEqual(AiotServerRepository.list_recent_messages_by_server_ids([server_id])[server_id], [])
        self.assertEqual(AiotServerRepository.list_recent_events_by_server_ids([server_id])[server_id], [])
        detail = DeviceRepository.get_device_detail_by_box_id("BOX-CLEAN-01")
        self.assertEqual(detail["device"]["online_status"], 0)
        self.assertIsNone(detail["device"]["connected_server_id"])

    def test_init_db_clears_stale_online_device_status(self):
        from app.models.aiot_server import AiotServerRepository
        from app.models.device import DeviceRepository

        server_id = AiotServerRepository.create_server(
            server_name="restart-safe-service",
            listen_ip="127.0.0.1",
            listen_port=9305,
            is_enabled=True,
        )
        DeviceRepository.create_device(
            box_id="BOX-STALE-01",
            esp32_ip="192.168.1.31",
            manage_url="http://192.168.1.31",
            device_name="Restart Device",
            category="Lamp",
            sensors=[],
        )
        DeviceRepository.set_device_connection_status(
            box_id="BOX-STALE-01",
            is_online=True,
            server_id=server_id,
        )

        db.init_db()

        detail = DeviceRepository.get_device_detail_by_box_id("BOX-STALE-01")
        self.assertEqual(detail["device"]["online_status"], 0)
        self.assertIsNone(detail["device"]["connected_server_id"])


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
