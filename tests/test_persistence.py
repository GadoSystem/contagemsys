import tempfile
import unittest
from pathlib import Path

from persistence import EventDatabase


class PersistenceTests(unittest.TestCase):
    def test_sessions_and_events_are_separated_by_camera(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = EventDatabase(Path(tmp) / "test.db")
            session_1 = db.start_session("camera_1", "teste 1")
            session_2 = db.start_session("camera_2", "teste 2")

            event_id = db.insert_event(
                session_1,
                "camera_1",
                {
                    "track_id": 7,
                    "direcao": "direita_para_esquerda",
                    "contabilizado": True,
                    "confidence": 0.91,
                    "frame_index": 10,
                },
            )
            db.insert_event(
                session_2,
                "camera_2",
                {
                    "track_id": 9,
                    "direcao": "esquerda_para_direita",
                    "contabilizado": False,
                    "confidence": 0.87,
                    "frame_index": 12,
                },
            )

            db.update_evidence(event_id, snapshot_path="x.jpg", clip_path="x.mp4")

            camera_1_rows = db.list_events(camera_id="camera_1")
            camera_2_rows = db.list_events(camera_id="camera_2")
            self.assertEqual(len(camera_1_rows), 1)
            self.assertEqual(len(camera_2_rows), 1)
            self.assertEqual(camera_1_rows[0]["track_id"], 7)
            self.assertEqual(camera_1_rows[0]["camera_id"], "camera_1")
            self.assertEqual(camera_1_rows[0]["snapshot_path"], "x.jpg")
            self.assertEqual(db.get_event(event_id)["clip_path"], "x.mp4")

            self.assertEqual(len(db.list_sessions(camera_id="camera_1")), 1)
            self.assertEqual(len(db.list_sessions(camera_id="camera_2")), 1)

    def test_camera_owner_can_be_linked_and_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = EventDatabase(Path(tmp) / "test.db")
            db.set_camera_owner("camera_1", 7, "Guilherme", "gui@teste.com")

            owner = db.get_camera_owner("camera_1")
            self.assertIsNotNone(owner)
            self.assertEqual(owner["usuario_id"], 7)
            self.assertEqual(len(db.list_camera_owners(usuario_id=7)), 1)

            db.remove_camera_owner("camera_1")
            self.assertIsNone(db.get_camera_owner("camera_1"))


if __name__ == "__main__":
    unittest.main()
