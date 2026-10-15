import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from persistence import EventDatabase
from state import LiveFrameStore


class DetailsTests(unittest.TestCase):
    def test_history_survives_session_restart_and_camera_isolated(self):
        with tempfile.TemporaryDirectory() as d:
            db = EventDatabase(Path(d) / 'db.sqlite')
            s1 = db.start_session('camera_1')
            ev = {'track_id': 10, 'direcao': 'direita_para_esquerda', 'contabilizado': True, 'confidence': 0.8, 'frame_index': 7}
            db.insert_event(s1, 'camera_1', ev)
            s2 = db.start_session('camera_1')
            self.assertNotEqual(s1, s2)
            self.assertEqual(db.camera_statistics('camera_1')['total_historico'], 1)
            self.assertEqual(db.camera_statistics('camera_2')['total_historico'], 0)
            self.assertEqual(db.camera_statistics('camera_1')['total_hoje'], 1)
            ev['contabilizado'] = False
            ev['direcao'] = 'esquerda_para_direita'
            db.insert_event(s2, 'camera_1', ev)
            self.assertEqual(db.camera_statistics('camera_1')['total_retornos'], 1)

    def test_clear_removes_old_video(self):
        s = LiveFrameStore()
        s.update_jpeg(b'jpeg1')
        s.clear()
        self.assertIsNone(s.jpeg()[1])


if __name__ == '__main__':
    unittest.main()
