import unittest
from unittest.mock import patch
import numpy as np

from listar_cameras import abrir, confirmar_frames


class FakeCapture:
    def __init__(self):
        self.read_count = 0
        self.released = False
    def isOpened(self):
        return True
    def set(self, *_):
        return True
    def read(self):
        self.read_count += 1
        return True, np.zeros((480, 640, 3), dtype=np.uint8)
    def release(self):
        self.released = True


class CameraDiscoveryTests(unittest.TestCase):
    def test_probe_reuses_one_device_handle(self):
        fake = FakeCapture()
        with patch('listar_cameras.cv2.VideoCapture', return_value=fake) as mocked:
            cam = abrir(1, 700)
            ok, frame = confirmar_frames(cam)
            self.assertTrue(ok)
            self.assertEqual(frame.shape, (480, 640, 3))
            self.assertEqual(mocked.call_count, 1, 'Nao reabrir entre verificacao e visualizacao')
            self.assertFalse(fake.released, 'Manter dispositivo aberto no preview')
            cam.release()
            self.assertTrue(fake.released)


if __name__ == '__main__':
    unittest.main()
