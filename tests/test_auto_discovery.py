import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np
import yaml

from camera_discovery import (
    validate_capture, merge_cameras, replace_video_cameras_yaml,
    discover_and_sync, scan_webcams,
)
from camera_stream import resolve_video_source
from config import load_config


class FakeCap:
    def __init__(self, changing=True):
        self.count = 0
        self.changing = changing
        self.released = False
    def read(self):
        self.count += 1
        image = np.zeros((60, 80, 3), dtype=np.uint8)
        if self.changing:
            image[:, : (self.count * 7) % 80] = 200
        return True, image
    def release(self):
        self.released = True


class AutoDiscoveryTests(unittest.TestCase):
    def test_static_placeholder_is_rejected(self):
        ok, msg = validate_capture(FakeCap(changing=False), samples=5, sample_delay=0)
        self.assertFalse(ok)
        self.assertIn("sem mudancas", msg)

    def test_actual_changing_camera_is_accepted(self):
        ok, msg = validate_capture(FakeCap(changing=True), samples=5, sample_delay=0)
        self.assertTrue(ok, msg)

    def test_webcam_scanner_opens_once_and_closes_handle(self):
        fake = FakeCap()
        with patch("camera_discovery.open_video_source", side_effect=lambda idx, **kw: fake if idx == 1 else None) as opened:
            with patch("camera_discovery.time.sleep", return_value=None):
                found = scan_webcams({"backend": "dshow", "max_index": 3, "samples": 4}, {"width": 640, "height": 480})
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["source"], 1)
        self.assertEqual(found[0]["backend"], "dshow")
        self.assertEqual(opened.call_count, 3)
        self.assertTrue(fake.released)

    def test_ids_persist_and_unavailable_are_disabled(self):
        existing = [
            {"id": "camera_1", "source": 0, "enabled": True, "name": "USB", "gate": {"left_x": .30}},
            {"id": "camera_2", "source": 1, "enabled": True, "name": "Iriun"},
        ]
        merged = merge_cameras(existing, [{"source": 1, "backend": "dshow", "kind": "webcam"},
                                         {"source": 2, "backend": "dshow", "kind": "webcam"}])
        self.assertEqual({x["id"]: x["enabled"] for x in merged},
                         {"camera_1": False, "camera_2": True, "camera_3": True})
        self.assertEqual(merged[-1]["gate"]["left_x"], .30)

    def test_yaml_preserves_global_settings_and_comments(self):
        original = '''app:\n  show_window: true\nvideo:\n  fps: 20\n  cameras:\n    - id: camera_1\n      source: 0\n      enabled: true\n\nmodel:\n  classes: [0] # pessoas\n'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'config.yaml'
            path.write_text(original, encoding='utf-8')
            replace_video_cameras_yaml(path, [{"id": "camera_1", "source": 1, "enabled": True}])
            updated = path.read_text(encoding='utf-8')
            self.assertIn('classes: [0] # pessoas', updated)
            self.assertIn('show_window: true', updated)
            self.assertEqual(yaml.safe_load(updated)['video']['cameras'][0]['source'], 1)
            self.assertFalse(replace_video_cameras_yaml(path, [{"id": "camera_1", "source": 1, "enabled": True}]))

    def test_sync_disables_missing_without_deleting_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'config.yaml'
            path.write_text('''discovery:\n  enabled: true\n  webcam: {enabled: true}\n  onvif: {enabled: false}\nvideo:\n  cameras:\n    - id: camera_1\n      source: 0\n      enabled: true\n    - id: camera_2\n      source: 1\n      enabled: true\nmodel:\n  classes: [0]\n''', encoding='utf-8')
            with patch('camera_discovery.scan_webcams', return_value=[{'source': 1,'backend':'dshow'}]):
                with patch('camera_discovery.scan_ip_streams', return_value=[]):
                    result = discover_and_sync(path)
            self.assertEqual({r['id']:r['enabled'] for r in result}, {'camera_2': True, 'camera_1': False})
            cfg = load_config(path)
            self.assertEqual(sum(c['enabled'] for c in cfg['video']['cameras']), 1)

    def test_empty_discovery_does_not_create_phantom_camera(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'config.yaml'
            path.write_text('discovery:\n  enabled: true\nvideo:\n  cameras: []\n', encoding='utf-8')
            self.assertEqual(load_config(path)['video']['cameras'], [])

    def test_ip_user_credentials_come_from_env(self):
        with patch.dict(os.environ, {'IP_US':'abc@example.com', 'IP_PW':'pass:word'}, clear=False):
            stream = resolve_video_source('rtsp://192.168.1.50:554/live', 'IP_US','IP_PW')
            self.assertEqual(stream, 'rtsp://abc%40example.com:pass%3Aword@192.168.1.50:554/live')


if __name__ == '__main__':
    unittest.main()
