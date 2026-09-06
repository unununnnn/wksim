import unittest

from tools.migrate_prometheus_interfaces import convert, expected_files, snake, TARGET


class PrometheusInterfacesTests(unittest.TestCase):
    def test_name_mapping_and_aliases_preserve_numbers(self):
        original = "Header header\ntime start_time\nuint8 Init_Pos_Hover=1\nuint32 Command_ID\nfloat32[3] position_ref\n"
        text, changes = convert(original, "UAVCommand.msg")
        self.assertIn("std_msgs/Header header\nbuiltin_interfaces/Time start_time", text)
        self.assertIn("uint8 INIT_POS_HOVER=1\nuint32 command_id\nfloat32[3] position_ref", text)
        self.assertEqual(snake("angleRTRate"), "angle_rt_rate")
        self.assertEqual(len(changes), 4)

    def test_reserved_name_and_service_sections(self):
        text, _ = convert("string Class\n", "BoundingBox.msg")
        self.assertIn("string class_name", text)
        text, _ = convert("uint8 id\n---\nuint8 id\n", "Example.srv")
        self.assertEqual(text.count("uint8 id"), 2)
        with self.assertRaises(ValueError):
            convert("uint8 moveMode\nuint8 move_mode\n", "Collision.msg")

    def test_entire_port_matches_pinned_source(self):
        files, provenance = expected_files()
        self.assertEqual(len(provenance), 47)
        for name, expected in files.items():
            self.assertEqual((TARGET/name).read_text(encoding="utf-8"), expected, name)
        uav, _ = convert("uint8 Move=4\nuint8 XYZ_POS=0\nfloat64 latitude\nfloat32 battery_percetage\n", "UAVCommand.msg")
        self.assertIn("uint8 MOVE=4\nuint8 XYZ_POS=0\nfloat64 latitude\nfloat32 battery_percetage", uav)


if __name__ == "__main__":
    unittest.main()
