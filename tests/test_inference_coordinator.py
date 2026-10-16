import threading
import time
import unittest

from main import InferenceCoordinator


class InferenceCoordinatorTests(unittest.TestCase):
    def _medir_sobreposicao(self, coordinator, chamadas_por_thread):
        ativos = 0
        pico = 0
        trava = threading.Lock()

        def inferencia():
            nonlocal ativos, pico
            with trava:
                ativos += 1
                pico = max(pico, ativos)
            time.sleep(0.05)
            with trava:
                ativos -= 1
            return "ok"

        barreira = threading.Barrier(2)

        def camera():
            barreira.wait()
            for _ in range(chamadas_por_thread):
                self.assertEqual(coordinator.run(inferencia)[0], "ok")

        threads = [threading.Thread(target=camera) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return pico

    def test_primeira_inferencia_de_cada_camera_e_serializada(self):
        # Duas cameras, uma inferencia cada: mesmo com 2 vagas nao ha paralelo.
        self.assertEqual(self._medir_sobreposicao(InferenceCoordinator(2), 1), 1)

    def test_depois_do_aquecimento_volta_a_rodar_em_paralelo(self):
        self.assertEqual(self._medir_sobreposicao(InferenceCoordinator(2), 4), 2)


if __name__ == "__main__":
    unittest.main()
