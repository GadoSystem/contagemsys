import unittest

from state import SharedState


class SharedStateTests(unittest.TestCase):
    def test_register_count_and_return(self):
        state = SharedState("camera_1", "Camera 1")
        state.register_event({"contabilizado": True, "direcao": "direita_para_esquerda"})
        state.register_event({"contabilizado": False, "direcao": "esquerda_para_direita"})
        snap = state.snapshot()
        self.assertEqual(snap["camera_id"], "camera_1")
        self.assertEqual(snap["total_contado"], 1)
        self.assertEqual(snap["retornos_esquerda_para_direita"], 1)

    def test_reset(self):
        state = SharedState("camera_2", "Camera 2")
        state.register_event({"contabilizado": True, "direcao": "direita_para_esquerda"})
        state.reset_counters(session_id=3)
        snap = state.snapshot()
        self.assertEqual(snap["total_contado"], 0)
        self.assertEqual(snap["session_id"], 3)


if __name__ == "__main__":
    unittest.main()
