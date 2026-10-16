import unittest
from unittest.mock import Mock

from counting import GateCounter
from tracking import Detection, MultiObjectTracker, boxes_to_detections


class TrackerTests(unittest.TestCase):
    @staticmethod
    def boxes_at(*xs):
        return [Detection((x - 44, 50, x + 44, 300), 0.88) for x in xs]

    def test_boxes_without_ultralytics_ids_are_kept(self):
        boxes = Mock()
        boxes.xyxy.cpu.return_value.tolist.return_value = [[5, 8, 40, 80], [55, 10, 105, 100]]
        boxes.conf.cpu.return_value.tolist.return_value = [0.8, 0.7]
        boxes.cls.int.return_value.cpu.return_value.tolist.return_value = [0, 0]
        boxes.id = None
        result = boxes_to_detections(boxes)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1].bbox, (55., 10., 105., 100.))

    def test_two_entities_keep_ids_when_crossing_and_are_counted_individually(self):
        tracker = MultiObjectTracker()
        counter = GateCounter(left_x=0.42, right_x=0.58, stable_frames=1)
        counted = []
        returns = []
        for i, positions in enumerate([(550, 90), (490, 140), (405, 210), (320, 260),
                                        (250, 340), (170, 420), (105, 515)]):
            tracks = tracker.update(self.boxes_at(*positions), timestamp=10 + 0.25*i)
            self.assertEqual([t.track_id for t in tracks], [1, 2])
            for track in tracks:
                event = counter.update(track.track_id, track.bbox, 640, track.confidence, i)
                if event:
                    (counted if event["contabilizado"] else returns).append(event)
        self.assertEqual([e["track_id"] for e in counted], [1])
        self.assertEqual([e["track_id"] for e in returns], [2])

    def test_same_track_retains_id_after_short_missing_interval(self):
        tracker = MultiObjectTracker(max_missing_seconds=3.0)
        first = tracker.update(self.boxes_at(510), timestamp=1)[0].track_id
        tracker.update([], timestamp=1.5)
        second = tracker.update(self.boxes_at(490), timestamp=2)[0].track_id
        self.assertEqual(first, second)

    def test_after_long_disappearance_id_is_not_recycled(self):
        tracker = MultiObjectTracker(max_missing_seconds=2.0)
        first = tracker.update(self.boxes_at(510), timestamp=1)[0].track_id
        new_id = tracker.update(self.boxes_at(510), timestamp=10)[0].track_id
        self.assertNotEqual(first, new_id)

    def test_direct_jump_across_gate_is_a_count(self):
        counter = GateCounter(left_x=.42, right_x=.58, stable_frames=1)
        self.assertIsNone(counter.update(8, (490, 10, 550, 100), 640, .8, 0))
        counted = counter.update(8, (100, 10, 160, 100), 640, .8, 1)
        self.assertTrue(counted["contabilizado"])

    def test_return_changes_status_without_duplicate_count(self):
        tracker = MultiObjectTracker()
        counter = GateCounter(left_x=.42, right_x=.58, stable_frames=1)
        events = []
        for i, x in enumerate((530, 380, 280, 180, 300, 390, 510, 300, 150)):
            track = tracker.update(self.boxes_at(x), timestamp=1 + .25*i)[0]
            event = counter.update(track.track_id, track.bbox, 640, track.confidence, i)
            if event: events.append(event)
        self.assertEqual(sum(bool(e["contabilizado"]) for e in events), 1)
        self.assertEqual(sum(e["direcao"] == "esquerda_para_direita" for e in events), 1)


if __name__ == '__main__':
    unittest.main()
