import os
import shutil
import socket
import tempfile
import unittest
from unittest import mock

from app.models import db
from app.models.aiot_server import AiotServerRepository
from app.models.device import DeviceRepository
from app.services.aiot_server_manager import ManagedAiotTcpServer, _extract_box_id


class AiotServerManagerTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir, "test.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_extract_box_id_supports_alias_prefixes(self):
        self.assertEqual(_extract_box_id("box_id:BOX-001"), "BOX-001")
        self.assertEqual(_extract_box_id("boxid=BOX-002"), "BOX-002")
        self.assertEqual(_extract_box_id("device_id:DEV-001"), "DEV-001")
        self.assertEqual(_extract_box_id("deviceid=DEV-002"), "DEV-002")

    def test_extract_box_id_supports_alias_json_keys(self):
        self.assertEqual(_extract_box_id('{"box_id":"BOX-101"}'), "BOX-101")
        self.assertEqual(_extract_box_id('{"boxid":"BOX-102"}'), "BOX-102")
        self.assertEqual(_extract_box_id('{"device_id":"DEV-101"}'), "DEV-101")
        self.assertEqual(_extract_box_id('{"deviceid":"DEV-102"}'), "DEV-102")

    def test_extract_box_id_supports_chinese_online_prefix(self):
        self.assertEqual(_extract_box_id("[上线]设备ID:12345"), "12345")

    def test_extract_box_id_does_not_treat_runtime_status_text_as_device_id(self):
        self.assertIsNone(_extract_box_id("计时:87s"))
        self.assertIsNone(_extract_box_id("灯状态：手动关闭"))
        self.assertIsNone(_extract_box_id("光敏:日间 人体:无人"))

    def test_send_command_writes_to_bound_online_device(self):
        class FakeConnection:
            def __init__(self):
                self.sent_payloads = []

            def sendall(self, payload):
                self.sent_payloads.append(payload)

        fake_connection = FakeConnection()
        fake_connection = FakeConnection()
        fake_connection = FakeConnection()
        managed = ManagedAiotTcpServer(
            {
                "id": 1,
                "server_name": "AIOT TCP",
                "listen_ip": "127.0.0.1",
                "listen_port": 9001,
            }
        )
        connection = FakeConnection()

        managed.bind_device_connection("BOX-101", connection)
        managed.send_command("BOX-101", "sensor OLED GPIO21")

        self.assertEqual(connection.sent_payloads, [b"sensor OLED GPIO21\n"])

    def test_send_command_records_success_event(self):
        class FakeConnection:
            def sendall(self, _payload):
                return None

        managed = ManagedAiotTcpServer(
            {
                "id": 11,
                "server_name": "AIOT TCP",
                "listen_ip": "127.0.0.1",
                "listen_port": 9401,
            }
        )
        managed.bind_device_connection("BOX-CMD-01", FakeConnection())

        with mock.patch("app.services.aiot_server_manager.AiotServerRepository.append_server_event") as append_event:
            managed.send_command("BOX-CMD-01", "status")

        self.assertEqual(append_event.call_args.kwargs["event_type"], "command_sent")
        self.assertEqual(append_event.call_args.kwargs["box_id"], "BOX-CMD-01")

    def test_send_command_marks_device_offline_when_connection_missing(self):
        managed = ManagedAiotTcpServer(
            {
                "id": 1,
                "server_name": "AIOT TCP",
                "listen_ip": "127.0.0.1",
                "listen_port": 9001,
            }
        )

        with mock.patch(
            "app.services.aiot_server_manager.DeviceRepository.set_device_connection_status"
        ) as set_status:
            with self.assertRaises(LookupError):
                managed.send_command("BOX-404", "status")

        self.assertEqual(set_status.call_count, 1)
        self.assertEqual(set_status.call_args.kwargs["box_id"], "BOX-404")
        self.assertFalse(set_status.call_args.kwargs["is_online"])

    def test_send_command_records_failure_event_when_device_offline(self):
        managed = ManagedAiotTcpServer(
            {
                "id": 12,
                "server_name": "AIOT TCP",
                "listen_ip": "127.0.0.1",
                "listen_port": 9402,
            }
        )

        with (
            self.assertRaises(LookupError),
            mock.patch("app.services.aiot_server_manager.AiotServerRepository.append_server_event") as append_event,
        ):
            managed.send_command("BOX-CMD-02", "status")

        self.assertEqual(append_event.call_args.kwargs["event_type"], "command_failed")

    def test_handle_client_does_not_mark_device_offline_only_for_idle_timeout(self):
        class FakeConnection:
            def __init__(self):
                self.recv_count = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def settimeout(self, _seconds):
                return None

            def recv(self, _size):
                self.recv_count += 1
                if self.recv_count == 1:
                    return b"boxid=BOX-201"
                if self.recv_count <= 5:
                    raise socket.timeout()
                if self.recv_count == 6:
                    return b""
                raise AssertionError("connection should stay alive until the peer closes it")

        fake_connection = FakeConnection()
        managed = ManagedAiotTcpServer(
            {
                "id": 1,
                "server_name": "AIOT TCP",
                "listen_ip": "127.0.0.1",
                "listen_port": 9001,
            }
        )

        with (
            mock.patch("app.services.aiot_server_manager.DeviceRepository.set_device_connection_status") as set_status,
            mock.patch("app.services.aiot_server_manager.AiotServerRepository.append_server_message"),
        ):
            managed._handle_client(fake_connection)

        self.assertEqual(fake_connection.recv_count, 6)
        self.assertEqual(set_status.call_args_list[0].kwargs["box_id"], "BOX-201")
        self.assertTrue(set_status.call_args_list[0].kwargs["is_online"])
        self.assertEqual(set_status.call_args_list[-1].kwargs["box_id"], "BOX-201")
        self.assertFalse(set_status.call_args_list[-1].kwargs["is_online"])

    def test_handle_client_enables_socket_keepalive_for_device_connection(self):
        class FakeConnection:
            def __init__(self):
                self.messages = [b"boxid=BOX-KEEP-01", b""]
                self.socket_options = []
                self.ioctl_calls = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def settimeout(self, _seconds):
                return None

            def setsockopt(self, level, optname, value):
                self.socket_options.append((level, optname, value))

            def ioctl(self, control_code, values):
                self.ioctl_calls.append((control_code, values))

            def recv(self, _size):
                return self.messages.pop(0)

        fake_connection = FakeConnection()
        managed = ManagedAiotTcpServer(
            {
                "id": 15,
                "server_name": "AIOT TCP",
                "listen_ip": "127.0.0.1",
                "listen_port": 9407,
            }
        )

        with (
            mock.patch("app.services.aiot_server_manager.AiotServerRepository.append_server_message"),
            mock.patch("app.services.aiot_server_manager.DeviceRepository.set_device_connection_status"),
        ):
            managed._handle_client(fake_connection)

        self.assertIn((socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1), fake_connection.socket_options)
        if hasattr(socket, "SIO_KEEPALIVE_VALS"):
            self.assertIn((socket.SIO_KEEPALIVE_VALS, (1, 4000, 1000)), fake_connection.ioctl_calls)
        else:
            self.assertEqual(fake_connection.ioctl_calls, [])

    def test_handle_client_keeps_connection_during_short_idle_window(self):
        class FakeConnection:
            def __init__(self):
                self.recv_count = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def settimeout(self, _seconds):
                return None

            def recv(self, _size):
                self.recv_count += 1
                if self.recv_count == 1:
                    return b"boxid=BOX-202"
                if self.recv_count <= 5:
                    raise socket.timeout()
                if self.recv_count == 6:
                    return b""
                raise AssertionError("connection should stay alive until peer closes it")

        fake_connection = FakeConnection()
        managed = ManagedAiotTcpServer(
            {
                "id": 1,
                "server_name": "AIOT TCP",
                "listen_ip": "127.0.0.1",
                "listen_port": 9001,
            }
        )

        with (
            mock.patch("app.services.aiot_server_manager.DeviceRepository.set_device_connection_status") as set_status,
            mock.patch("app.services.aiot_server_manager.AiotServerRepository.append_server_message"),
        ):
            managed._handle_client(fake_connection)

        self.assertEqual(fake_connection.recv_count, 6)
        self.assertEqual(set_status.call_args_list[0].kwargs["box_id"], "BOX-202")
        self.assertTrue(set_status.call_args_list[0].kwargs["is_online"])
        self.assertEqual(set_status.call_args_list[-1].kwargs["box_id"], "BOX-202")
        self.assertFalse(set_status.call_args_list[-1].kwargs["is_online"])

    def test_handle_client_updates_device_basic_info_from_json_payload(self):
        DeviceRepository.create_device(
            box_id="BOX-301",
            esp32_ip="192.168.1.10",
            manage_url="http://192.168.1.10",
            device_name="Old Device",
            category="Old Category",
            sensors=[],
        )

        class FakeConnection:
            def __init__(self):
                self.messages = [
                    b'{"box_id":"BOX-301","device_name":"New Device","esp32_ip":"192.168.1.88","manage_url":"http://192.168.1.88:80","category":"Climate"}',
                    b"",
                ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def settimeout(self, _seconds):
                return None

            def recv(self, _size):
                return self.messages.pop(0)

        managed = ManagedAiotTcpServer(
            {
                "id": 1,
                "server_name": "AIOT TCP",
                "listen_ip": "127.0.0.1",
                "listen_port": 9001,
            }
        )

        with mock.patch("app.services.aiot_server_manager.AiotServerRepository.append_server_message"):
            managed._handle_client(FakeConnection())

        detail = DeviceRepository.get_device_detail_by_box_id("BOX-301")
        self.assertEqual(detail["device"]["device_name"], "New Device")
        self.assertEqual(detail["device"]["esp32_ip"], "192.168.1.88")
        self.assertEqual(detail["device"]["manage_url"], "http://192.168.1.88:80")
        self.assertEqual(detail["device"]["category"], "Climate")
        self.assertEqual(detail["device"]["online_status"], 0)

    def test_handle_client_keeps_original_box_id_for_runtime_status_messages(self):
        class FakeConnection:
            def __init__(self):
                self.messages = [
                    b"boxid=BOX-401",
                    "计时:87s".encode("utf-8"),
                    b"",
                ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def settimeout(self, _seconds):
                return None

            def recv(self, _size):
                return self.messages.pop(0)

        managed = ManagedAiotTcpServer(
            {
                "id": 1,
                "server_name": "AIOT TCP",
                "listen_ip": "127.0.0.1",
                "listen_port": 9001,
            }
        )

        with (
            mock.patch("app.services.aiot_server_manager.DeviceRepository.set_device_connection_status") as set_status,
            mock.patch("app.services.aiot_server_manager.AiotServerRepository.append_server_message"),
        ):
            managed._handle_client(FakeConnection())

        self.assertEqual(set_status.call_args_list[0].kwargs["box_id"], "BOX-401")
        self.assertEqual(set_status.call_args_list[-1].kwargs["box_id"], "BOX-401")

    def test_handle_client_marks_device_online_from_chinese_online_message(self):
        class FakeConnection:
            def __init__(self):
                self.messages = [
                    "[上线]设备ID:12345".encode("utf-8"),
                    b"",
                ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def settimeout(self, _seconds):
                return None

            def recv(self, _size):
                return self.messages.pop(0)

        managed = ManagedAiotTcpServer(
            {
                "id": 1,
                "server_name": "AIOT TCP",
                "listen_ip": "127.0.0.1",
                "listen_port": 9001,
            }
        )

        with (
            mock.patch("app.services.aiot_server_manager.DeviceRepository.set_device_connection_status") as set_status,
            mock.patch("app.services.aiot_server_manager.AiotServerRepository.append_server_message"),
        ):
            managed._handle_client(FakeConnection())

        self.assertEqual(set_status.call_args_list[0].kwargs["box_id"], "12345")
        self.assertTrue(set_status.call_args_list[0].kwargs["is_online"])
        self.assertEqual(set_status.call_args_list[-1].kwargs["box_id"], "12345")
        self.assertFalse(set_status.call_args_list[-1].kwargs["is_online"])

    def test_handle_client_updates_runtime_status_from_board_periodic_report(self):
        server_id = AiotServerRepository.create_server(
            server_name="Board Text Service",
            listen_ip="127.0.0.1",
            listen_port=9404,
            is_enabled=True,
        )
        DeviceRepository.create_device(
            box_id="12345",
            esp32_ip="192.168.1.120",
            manage_url="http://192.168.1.120:80",
            device_name="Board Device",
            category="AIOT",
            sensors=[],
        )

        class FakeConnection:
            def __init__(self):
                self.messages = [
                    "[上线]设备ID:12345".encode("utf-8"),
                    "[周期上报] 设备ID:12345 | 模式:自动 | LED:点亮 | 蜂鸣器:关闭 | 光敏:夜间 | 人体:有人 | 温度:26℃ | 湿度:55%RH | 屏幕:点亮".encode("utf-8"),
                    b"",
                ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def settimeout(self, _seconds):
                return None

            def recv(self, _size):
                return self.messages.pop(0)

        managed = ManagedAiotTcpServer(
            {
                "id": server_id,
                "server_name": "Board Text Service",
                "listen_ip": "127.0.0.1",
                "listen_port": 9404,
            }
        )

        managed._handle_client(FakeConnection())

        detail = DeviceRepository.get_device_detail_by_box_id("12345")
        self.assertIn("LED=点亮", detail["device"]["status_summary"])
        self.assertIn("mode=自动", detail["device"]["status_summary"])
        self.assertIn("light=夜间", detail["device"]["status_summary"])
        self.assertIn("human=有人", detail["device"]["status_summary"])
        self.assertIn("screen=点亮", detail["device"]["status_summary"])
        self.assertIn("tcp=online", detail["device"]["status_summary"])
        self.assertIn("temperature=26℃", detail["device"]["status_summary"])
        self.assertIn("humidity=55%RH", detail["device"]["status_summary"])
        self.assertIn("[周期上报]", detail["device"]["raw_status_text"])

        recent_events = AiotServerRepository.list_recent_events_by_server_ids([server_id])[server_id]
        status_event = next(event for event in recent_events if event["event_type"] == "status_report")
        self.assertIn("LED=点亮", status_event["event_summary"])

    def test_handle_client_updates_current_device_from_sensor_report_without_box_id(self):
        server_id = AiotServerRepository.create_server(
            server_name="Board Sensor Service",
            listen_ip="127.0.0.1",
            listen_port=9405,
            is_enabled=True,
        )
        DeviceRepository.create_device(
            box_id="12345",
            esp32_ip="192.168.1.121",
            manage_url="http://192.168.1.121:80",
            device_name="Board Sensor Device",
            category="AIOT",
            sensors=[],
        )

        class FakeConnection:
            def __init__(self):
                self.messages = [
                    "[上线]设备ID:12345".encode("utf-8"),
                    "[传感器] 光敏:日间 人体:无人 温度:27℃ 湿度:60%RH".encode("utf-8"),
                    b"",
                ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def settimeout(self, _seconds):
                return None

            def recv(self, _size):
                return self.messages.pop(0)

        managed = ManagedAiotTcpServer(
            {
                "id": server_id,
                "server_name": "Board Sensor Service",
                "listen_ip": "127.0.0.1",
                "listen_port": 9405,
            }
        )

        managed._handle_client(FakeConnection())

        detail = DeviceRepository.get_device_detail_by_box_id("12345")
        self.assertIn("light=日间", detail["device"]["status_summary"])
        self.assertIn("human=无人", detail["device"]["status_summary"])
        self.assertIn("temperature=27℃", detail["device"]["status_summary"])
        self.assertIn("humidity=60%RH", detail["device"]["status_summary"])
        self.assertIn("tcp=online", detail["device"]["status_summary"])
        self.assertEqual(detail["device"]["raw_status_text"], "[传感器] 光敏:日间 人体:无人 温度:27℃ 湿度:60%RH")

    def test_handle_client_auto_registers_device_from_runtime_payload(self):
        class FakeConnection:
            def __init__(self):
                self.messages = [
                    b'{"box_id":"BOX-AUTO-JSON","device_name":"Runtime Join","device_ip":"192.168.1.120","device_type":"Sensor","LED":"On","wifi":"connected"}',
                    b"",
                ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def settimeout(self, _seconds):
                return None

            def recv(self, _size):
                return self.messages.pop(0)

        managed = ManagedAiotTcpServer(
            {
                "id": 1,
                "server_name": "AIOT TCP",
                "listen_ip": "127.0.0.1",
                "listen_port": 9001,
            }
        )

        with mock.patch("app.services.aiot_server_manager.AiotServerRepository.append_server_message"):
            managed._handle_client(FakeConnection())

        detail = DeviceRepository.get_device_detail_by_box_id("BOX-AUTO-JSON")
        self.assertIsNotNone(detail)
        self.assertEqual(detail["device"]["device_name"], "Runtime Join")
        self.assertEqual(detail["device"]["esp32_ip"], "192.168.1.120")
        self.assertEqual(detail["device"]["category"], "Sensor")
        self.assertIn("LED=On", detail["device"]["status_summary"])
        self.assertIn('"wifi":"connected"', detail["device"]["raw_status_text"])

    def test_handle_client_auto_registers_sensor_manifest_from_runtime_payload(self):
        class FakeConnection:
            def __init__(self):
                self.messages = [
                    b'{"box_id":"BOX-AUTO-MANIFEST","device_name":"Runtime Join","device_ip":"192.168.1.121","device_type":"AIOT","sensors":[{"sensor_name":"LED","pin_code":"GPIO15","pin_remark":"board"},{"sensor_name":"DHT11","pin_code":"GPIO16","pin_remark":"temp"}]}',
                    b"",
                ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def settimeout(self, _seconds):
                return None

            def recv(self, _size):
                return self.messages.pop(0)

        managed = ManagedAiotTcpServer(
            {
                "id": 1,
                "server_name": "AIOT TCP",
                "listen_ip": "127.0.0.1",
                "listen_port": 9001,
            }
        )

        with mock.patch("app.services.aiot_server_manager.AiotServerRepository.append_server_message"):
            managed._handle_client(FakeConnection())

        detail = DeviceRepository.get_device_detail_by_box_id("BOX-AUTO-MANIFEST")
        self.assertIsNotNone(detail)
        self.assertEqual(len(detail["sensors"]), 2)
        self.assertEqual(detail["sensors"][0]["sensor_name"], "LED")
        self.assertEqual(detail["sensors"][1]["pin_code"], "GPIO16")

    def test_handle_client_records_identify_report_and_offline_events(self):
        events = []

        class FakeConnection:
            def __init__(self):
                self.calls = 0

            def settimeout(self, _seconds):
                return None

            def recv(self, _size):
                self.calls += 1
                if self.calls == 1:
                    return b'{"box_id":"BOX-EVT-01","device_name":"Panel","wifi":"ok"}'
                return b""

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        managed = ManagedAiotTcpServer(
            {
                "id": 13,
                "server_name": "AIOT TCP",
                "listen_ip": "127.0.0.1",
                "listen_port": 9403,
            }
        )

        with (
            mock.patch(
                "app.services.aiot_server_manager.AiotServerRepository.append_server_event",
                side_effect=lambda **kwargs: events.append(kwargs),
            ),
            mock.patch("app.services.aiot_server_manager.AiotServerRepository.append_server_message"),
            mock.patch("app.services.aiot_server_manager.DeviceRepository.set_device_connection_status"),
            mock.patch("app.services.aiot_server_manager.DeviceRepository.sync_device_runtime_data"),
            mock.patch("app.services.aiot_server_manager.DataReportRepository.record_event"),
        ):
            managed._handle_client(FakeConnection())

        event_types = [item["event_type"] for item in events]
        self.assertIn("device_identify", event_types)
        self.assertIn("status_report", event_types)
        self.assertIn("device_offline", event_types)

    def test_handle_client_records_disconnect_error_before_offline_event(self):
        events = []

        class FakeConnection:
            def __init__(self):
                self.calls = 0

            def settimeout(self, _seconds):
                return None

            def recv(self, _size):
                self.calls += 1
                if self.calls == 1:
                    return b'{"box_id":"BOX-EVT-ERR","device_name":"Panel","wifi":"ok"}'
                raise OSError("connection reset by peer")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        managed = ManagedAiotTcpServer(
            {
                "id": 14,
                "server_name": "AIOT TCP",
                "listen_ip": "127.0.0.1",
                "listen_port": 9406,
            }
        )

        with (
            mock.patch(
                "app.services.aiot_server_manager.AiotServerRepository.append_server_event",
                side_effect=lambda **kwargs: events.append(kwargs),
            ),
            mock.patch("app.services.aiot_server_manager.AiotServerRepository.append_server_message"),
            mock.patch("app.services.aiot_server_manager.DeviceRepository.set_device_connection_status"),
            mock.patch("app.services.aiot_server_manager.DeviceRepository.sync_device_runtime_data"),
            mock.patch("app.services.aiot_server_manager.DataReportRepository.record_event"),
        ):
            managed._handle_client(FakeConnection())

        event_types = [item["event_type"] for item in events]
        self.assertIn("device_disconnect_error", event_types)
        self.assertIn("device_offline", event_types)
        disconnect_event = next(item for item in events if item["event_type"] == "device_disconnect_error")
        self.assertIn("connection reset by peer", disconnect_event["raw_payload"])


if __name__ == "__main__":
    unittest.main()
