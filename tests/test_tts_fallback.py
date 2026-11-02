"""Se o Kokoro travar, a fala não pode ficar muda: cai para a voz do sistema e avisa no log."""
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from itachi_capoeira import tts

CFG = SimpleNamespace(TTS_ENGINE="auto", TTS_MAX_CHARS=900, TTS_SYNTH_TIMEOUT=5, VOICE="pm_santa", KOKORO_SPEED=1.0,
                      KOKORO_LANG="pt-br", AUDIO_OUT_DEVICE="", AUDIO_PLAYER="auto")


class Fallback(unittest.TestCase):
    def make(self, synth):
        sp = tts.Speaker(CFG, threading.Event())
        sp.kokoro.available = lambda: not sp.kokoro.failed          # modelo "instalado"
        sp.kokoro.synth = synth
        sp.system = mock.Mock()
        sp.system.available.return_value = True
        sp.system.speak.return_value = True
        return sp

    def test_hang_falls_back_to_system_voice_and_sticks(self):
        release = threading.Event()
        sp = self.make(lambda s: (release.wait(30), (np.zeros(10, np.float32), 24000))[1])
        t0 = time.time()
        with mock.patch.object(tts.audio, "play_samples", return_value=True), \
                self.assertLogs("itachi_capoeira.tts", level="INFO") as cm:
            ok = sp.speak("Olá. Tudo bem?")
        release.set()
        self.assertTrue(ok)
        self.assertLess(time.time() - t0, 15)
        sp.system.speak.assert_called_once()
        self.assertTrue(sp.kokoro.failed)
        self.assertIn("não sintetizou", "\n".join(cm.output))
        self.assertIs(sp.engine(), sp.system)                       # próximas falas já vão direto para o sistema

    def test_normal_path_plays_and_logs_each_sentence(self):
        sp = self.make(lambda s: (np.zeros(240, np.float32), 24000))
        with mock.patch.object(tts.audio, "play_samples", return_value=True) as play, \
                self.assertLogs("itachi_capoeira.tts", level="INFO") as cm:
            self.assertTrue(sp.speak("Primeira frase. Segunda frase."))
        self.assertEqual(play.call_count, 2)
        sp.system.speak.assert_not_called()
        self.assertIn("Frase 2/2 pronta", "\n".join(cm.output))

    def test_stop_during_synthesis_does_not_fall_back(self):
        release = threading.Event()
        sp = self.make(lambda s: (release.wait(30), (np.zeros(10, np.float32), 24000))[1])
        threading.Timer(0.5, sp.stop.set).start()
        with mock.patch.object(tts.audio, "play_samples", return_value=True):
            self.assertFalse(sp.speak("Olá. Tudo bem?"))
        release.set()
        sp.system.speak.assert_not_called()


if __name__ == "__main__":
    unittest.main()
