import unittest

from counting import GateCounter


class GateCounterTests(unittest.TestCase):
    def setUp(self):
        self.counter = GateCounter(left_x=0.4, right_x=0.6, stable_frames=1, stale_after_frames=20)
        self.width = 100

    def bbox_at(self, x):
        return (x - 5, 10, x + 5, 40)

    def step(self, track_id, x, frame):
        return self.counter.update(track_id, self.bbox_at(x), self.width, 0.9, frame)

    def test_right_center_left_counts_once(self):
        self.assertIsNone(self.step(1, 80, 1))
        self.assertIsNone(self.step(1, 50, 2))
        event = self.step(1, 20, 3)
        self.assertIsNotNone(event)
        self.assertTrue(event["contabilizado"])

    def test_left_center_right_is_return(self):
        self.step(2, 20, 1)
        self.step(2, 50, 2)
        event = self.step(2, 80, 3)
        self.assertFalse(event["contabilizado"])
        self.assertEqual(event["direcao"], "esquerda_para_direita")

    def test_turning_back_does_not_count(self):
        self.step(3, 80, 1)
        self.step(3, 50, 2)
        self.assertIsNone(self.step(3, 80, 3))

    def test_track_born_in_center_must_reach_side_first(self):
        self.step(4, 50, 1)
        self.assertIsNone(self.step(4, 20, 2))
        self.step(4, 50, 3)
        event = self.step(4, 80, 4)
        self.assertFalse(event["contabilizado"])

    def test_same_id_not_counted_twice(self):
        self.step(5, 80, 1)
        self.step(5, 50, 2)
        first = self.step(5, 20, 3)
        self.assertTrue(first["contabilizado"])
        self.step(5, 50, 4)
        self.step(5, 80, 5)  # retorno
        self.step(5, 50, 6)
        second = self.step(5, 20, 7)
        self.assertIsNone(second)

    def test_bottom_center_anchor(self):
        self.assertEqual(GateCounter.bottom_center((10, 20, 30, 80)), (20.0, 80))

    def test_cleanup_removes_stale_tracks(self):
        self.step(8, 80, 1)
        self.counter.cleanup(30)
        self.assertNotIn(8, self.counter.tracks)


if __name__ == "__main__":
    unittest.main()
