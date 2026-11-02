"""Reprodução de áudio: seleção de player, avisos visíveis e dispositivo de saída."""
import logging
import threading
import unittest
from unittest import mock

import numpy as np

from itachi_capoeira import audio, tts

TONE = np.zeros(2205, dtype=np.float32)


class PlaySamples(unittest.TestCase):
    def test_system_player_skips_sounddevice(self):
        sd = mock.Mock()
        with mock.patch.object(audio, "sounddevice_module", return_value=sd), \
                mock.patch.object(audio, "_play_with_file_player", return_value=True) as fp:
            self.assertTrue(audio.play_samples(TONE, 22050, player="system"))
        sd.play.assert_not_called()
        fp.assert_called_once()

    def test_sounddevice_failure_is_a_warning_and_falls_back(self):
        sd = mock.Mock()
        sd.play.side_effect = OSError("PortAudio error")
        with mock.patch.object(audio, "sounddevice_module", return_value=sd), \
                mock.patch.object(audio, "_play_with_file_player", return_value=True) as fp, \
                self.assertLogs("itachi_capoeira.audio", level="WARNING") as cm:
            self.assertTrue(audio.play_samples(TONE, 22050))
        fp.assert_called_once()
        self.assertTrue(any("sounddevice falhou" in m for m in cm.output))

    def test_sounddevice_only_does_not_fall_back(self):
        sd = mock.Mock()
        sd.play.side_effect = OSError("x")
        with mock.patch.object(audio, "sounddevice_module", return_value=sd), \
                mock.patch.object(audio, "_play_with_file_player") as fp, \
                self.assertLogs("itachi_capoeira.audio", level="WARNING"):
            self.assertFalse(audio.play_samples(TONE, 22050, player="sounddevice"))
        fp.assert_not_called()

    def test_output_device_is_passed(self):
        sd = mock.Mock()
        sd.get_stream.return_value.active = False
        with mock.patch.object(audio, "sounddevice_module", return_value=sd):
            audio.play_samples(TONE, 22050, device="7")
        self.assertEqual(sd.play.call_args.kwargs["device"], 7)


class SpeakerLogging(unittest.TestCase):
    def test_failed_playback_is_reported(self):
        cfg = mock.Mock(TTS_ENGINE="auto", TTS_MAX_CHARS=900)
        sp = tts.Speaker(cfg, threading.Event())
        fake = mock.Mock(name="eng")
        fake.name = "system"
        fake.speak.return_value = False
        with mock.patch.object(sp, "engine", return_value=fake), \
                self.assertLogs("itachi_capoeira.tts", level="INFO") as cm:
            self.assertFalse(sp.speak("Olá, mundo."))
        joined = "\n".join(cm.output)
        self.assertIn("Falando (system", joined)
        self.assertIn("não foi reproduzida", joined)


if __name__ == "__main__":
    unittest.main()
