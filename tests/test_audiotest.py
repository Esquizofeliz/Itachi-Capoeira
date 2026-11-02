import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from itachi_capoeira import audiotest, tts


def cfg(**kw):
    base = dict(TTS_ENGINE="auto", TTS_MAX_CHARS=900, TTS_SYNTH_TIMEOUT=2, AUDIO_OUT_DEVICE="", AUDIO_PLAYER="auto",
                TTS_RATE=1.0, KOKORO_VOICE="pf_dora", KOKORO_SPEED=1.0, KOKORO_LANG="pt-br")
    base.update(kw)
    return SimpleNamespace(**base)


class AudioTest(unittest.TestCase):
    def test_no_engine_gives_hint(self):
        sp = mock.Mock()
        sp.engine.return_value = None
        r = audiotest.run(cfg(), sp)
        self.assertFalse(r["ok"])
        self.assertIn("espeak-ng", r["hint"])

    def test_reports_ok_and_timings(self):
        sp = mock.Mock()
        eng = mock.Mock()
        eng.name = "kokoro"
        sp.engine.return_value = eng
        sp.kokoro = eng
        sp.speak.return_value = True
        r = audiotest.run(cfg(), sp)
        self.assertTrue(r["ok"])
        self.assertEqual(r["engine"], "kokoro")
        self.assertIsNotNone(r["synth_s"])
        self.assertIn("Kokoro", audiotest.format_report(r))

    def test_failure_suggests_system_player(self):
        sp = mock.Mock()
        eng = mock.Mock()
        eng.name = "system"
        sp.engine.return_value = eng
        sp.kokoro = mock.Mock()
        sp.speak.return_value = False
        r = audiotest.run(cfg(), sp)
        self.assertFalse(r["ok"])
        self.assertTrue(r["hint"])


class KokoroWatchdog(unittest.TestCase):
    def test_hung_synth_times_out_instead_of_freezing(self):
        k = tts.KokoroEngine(cfg(TTS_SYNTH_TIMEOUT=2))
        k.synth = lambda s: time.sleep(30)                 # simula o travamento
        t = time.time()
        with self.assertRaises(TimeoutError):
            k.speak("Olá mundo.", threading.Event())
        self.assertLess(time.time() - t, 8)

    def test_speaker_falls_back_to_system_voice_on_timeout(self):
        sp = tts.Speaker(cfg(TTS_SYNTH_TIMEOUT=1), threading.Event())
        sp.kokoro = mock.Mock()
        sp.kokoro.name = "kokoro"
        sp.kokoro.available.return_value = True
        sp.kokoro.speak.side_effect = TimeoutError("travou")
        sp.system = mock.Mock()
        sp.system.available.return_value = True
        sp.system.speak.return_value = True
        with self.assertLogs("itachi_capoeira.tts", level="INFO"):
            self.assertTrue(sp.speak("Teste."))
        sp.system.speak.assert_called_once()


if __name__ == "__main__":
    unittest.main()
