import tempfile
import unittest
from pathlib import Path

import yaml

from ajustar_contagem import ajustar


class CountingConfigTests(unittest.TestCase):
    def test_preserves_ids_other_options_and_creates_backup(self):
        text = '''app:\n  port: 8000\ndisplay:\n  max_box_age_ms: 700\nvideo:\n  inference_fps: 2.0\n  cameras:\n  - id: camera_91\n    source: 2\n    backend: msmf\n    enabled: true\nmodel:\n  confidence: 0.35\n  imgsz: 320\ngate:\n  stable_frames: 2\n'''
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'config.yaml'
            p.write_text(text, encoding='utf-8')
            self.assertTrue(ajustar(p))
            output = yaml.safe_load(p.read_text(encoding='utf-8'))
            self.assertEqual(output['video']['cameras'][0]['id'], 'camera_91')
            self.assertEqual(output['video']['cameras'][0]['backend'], 'msmf')
            self.assertEqual(output['app']['port'], 8000)
            self.assertEqual(output['model']['confidence'], 0.25)
            self.assertEqual(output['gate']['stable_frames'], 1)
            self.assertEqual(output['video']['inference_fps'], 5.0)
            self.assertFalse(ajustar(p))
            self.assertEqual(p.with_name('config.yaml.antes_contagem.bak').read_text(), text)
