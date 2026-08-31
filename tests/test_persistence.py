import tempfile
import unittest
from pathlib import Path

from persistence import EventDatabase


class PersistenceTests(unittest.TestCase):
    def test_session_and_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = EventDatabase(Path(tmp) / "test.db")
            session_id = db.start_session("teste")
            event_id = db.insert_event(session_id, {
                "track_id": 7,
                "direcao": "direita_para_esquerda",
                "contabilizado": True,
                "confidence": 0.91,
                "frame_index": 10,
            })
            db.update_evidence(event_id, snapshot_path="x.jpg", clip_path="x.mp4")
            rows = db.list_events(session_id=session_id)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["track_id"], 7)
            self.assertEqual(rows[0]["snapshot_path"], "x.jpg")
            self.assertEqual(db.get_event(event_id)["clip_path"], "x.mp4")


if __name__ == "__main__":
    unittest.main()
