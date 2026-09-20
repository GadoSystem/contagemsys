import tempfile
import unittest
from pathlib import Path

from config import load_config


class ConfigTests(unittest.TestCase):
    def test_two_cameras_are_loaded(self):
        yaml = """
video:
  cameras:
    - id: camera_1
      name: Primeira
      source: 0
    - id: camera_2
      name: Segunda
      source: 1
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(yaml, encoding="utf-8")
            cfg = load_config(path)
        self.assertEqual(len(cfg["video"]["cameras"]), 2)
        self.assertEqual(cfg["video"]["cameras"][1]["source"], 1)

    def test_duplicate_camera_id_is_rejected(self):
        yaml = """
video:
  cameras:
    - id: camera_1
      source: 0
    - id: camera_1
      source: 1
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(yaml, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
