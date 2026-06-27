import socket
import unittest
from unittest import mock

from app.services.aiot_server_manager import ManagedAiotTcpServer, _extract_box_id


class AiotServerManagerTestCase(unittest.TestCase):
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

    def test_send_command_writes_to_bound_online_device(self):
        class FakeConnection:
            def __init__(self):
                self.sent_payloads = []

            def sendall(self, payload):
                self.sent_payloads.append(payload)

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

    def test_handle_client_marks_device_offline_after_idle_timeout(self):
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
                if self.recv_count <= 4:
                    raise socket.timeout()
                raise AssertionError("connection should be closed after idle timeout")

        managed = ManagedAiotTcpServer(
            {
                "id": 1,
                "server_name": "AIOT TCP",
                "listen_ip": "127.0.0.1",
                "listen_port": 9001,
            }
        )

        with (
            mock.patch("app.services.aiot_server_manager.time.monotonic", side_effect=[0, 0, 1, 3.5, 3.6]),
            mock.patch("app.services.aiot_server_manager.DeviceRepository.set_device_connection_status") as set_status,
            mock.patch("app.services.aiot_server_manager.AiotServerRepository.append_server_message"),
        ):
            managed._handle_client(FakeConnection())

        self.assertEqual(set_status.call_args_list[0].kwargs["box_id"], "BOX-201")
        self.assertTrue(set_status.call_args_list[0].kwargs["is_online"])
        self.assertEqual(set_status.call_args_list[-1].kwargs["box_id"], "BOX-201")
        self.assertFalse(set_status.call_args_list[-1].kwargs["is_online"])


if __name__ == "__main__":
    unittest.main()
