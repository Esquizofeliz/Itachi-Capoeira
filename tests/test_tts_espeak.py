"""Testes de seleção do eSpeak NG do sistema para o Kokoro."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from itachi_capoeira import tts


class SystemEspeakConfig(unittest.TestCase):
    def test_uses_system_library_and_data_reported_by_espeak(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            lib = base / "libespeak-ng.so.1"
            data = base / "espeak-ng-data"
            data.mkdir()
            lib.touch()
            for name in ("phontab", "phondata", "phonindex"):
                (data / name).touch()

            def fake_is_file(path):
                return path.parent == data and path.name in ("phontab", "phondata", "phonindex")

            with mock.patch.object(tts.sys, "platform", "linux"), \
                 mock.patch.object(tts.shutil, "which", return_value="/usr/bin/espeak-ng"), \
                 mock.patch.object(tts.subprocess, "run", return_value=mock.Mock(
                     stdout=f"eSpeak NG\nData at: {data}\n", stderr="", returncode=0)), \
                 mock.patch.object(tts.ctypes.util, "find_library", return_value=str(lib)), \
                 mock.patch.object(tts.Path, "is_file", new=fake_is_file):
                cfg = tts._system_espeak_config(lambda **kw: SimpleNamespace(**kw))

            self.assertIsNotNone(cfg)
            self.assertEqual(cfg.lib_path, str(lib))
            self.assertEqual(cfg.data_path, str(data))


if __name__ == "__main__":
    unittest.main()
