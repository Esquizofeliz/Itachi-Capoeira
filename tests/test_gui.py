"""Testes da interface Itachi Capoeira (servidor local + ponte do celular) com Ollama simulado."""
import json
import os
import tempfile
import threading
import unittest
import unittest.mock
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np

os.environ["ITACHI_CAPOEIRA_HOME"] = tempfile.mkdtemp(prefix="itachi-capoeira-gui-test-")
for _k, _v in {"CHAT_MODEL": "gemma4:e4b", "VISION_MODEL": "gemma4:e4b", "TTS_ENGINE": "off", "WHISPER_DEVICE": "cpu"}.items():
    os.environ["ITACHI_CAPOEIRA_" + _k] = _v

from tests.fake_ollama import FakeOllama  # noqa: E402

_fake = FakeOllama()
os.environ["ITACHI_CAPOEIRA_OLLAMA_URL"] = _fake.url

from itachi_capoeira import config, gui  # noqa: E402


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = gui.App(config.Config({"OLLAMA_URL": _fake.url, "TTS_ENGINE": "off"}))
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), gui.make_handler(cls.app))
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        _fake.close()

    def get(self, p, headers=None):
        return urllib.request.urlopen(urllib.request.Request(self.base + p, headers=headers or {}), timeout=20).read()

    def post(self, p, d, headers=None):
        r = urllib.request.Request(self.base + p, json.dumps(d).encode(), {"Content-Type": "application/json", **(headers or {})})
        try:
            return 200, json.loads(urllib.request.urlopen(r, timeout=30).read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_html_and_status(self):
        self.assertIn(b"ITACHI CAPOEIRA", self.get("/"))
        st = json.loads(self.get("/api/status"))
        self.assertTrue(st["ollama"])
        self.assertTrue(next(m for m in st["models"] if m["id"] == "chat")["installed"])

    def test_ask_and_vision(self):
        self.assertIn("Resposta", self.post("/api/ask", {"text": "oi"})[1]["reply"])
        self.assertIn("[com imagem]", self.post("/api/vision", {"question": "q", "image": "AAAA"})[1]["reply"])

    def test_models_and_errors(self):
        self.assertEqual(self.post("/api/models", {"action": "unload_all"})[0], 200)
        self.assertEqual(self.post("/api/models", {"action": "pull", "id": "xx"})[0], 400)
        self.assertEqual(self.post("/api/ask", {"text": ""})[0], 400)

    def test_blocks_foreign_origin_and_host(self):
        self.assertEqual(self.post("/api/ask", {"text": "x"}, {"Origin": "http://evil.com"})[0], 403)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/api/status", {"Host": "evil.com"})
        self.assertEqual(cm.exception.code, 403)

    # ------------------------------------------------------------ celular (assistente de mesa via USB)
    def test_mobile_page_and_assets(self):
        html = self.get("/mobile/")
        self.assertIn(b"Itachi Capoeira", html)
        self.assertIn(b"Jarvis", html)                       # crédito: inspirado no projeto Jarvis
        self.assertIn(b"INICIAR SISTEMA", html)
        self.assertIn(b"DESCONECTAR", html)
        self.assertTrue(self.get("/mobile/itachi.png").startswith(b"\x89PNG"))
        self.assertTrue(self.get("/itachi.png").startswith(b"\x89PNG"))          # imagem do painel principal
        self.assertTrue(self.get("/Itachi-em-Ginga-Brasileira.png").startswith(b"\x89PNG"))

    def test_static_blocks_traversal_and_non_images(self):
        for bad in ("/itachi_capoeira/config.py", "/mobile/Itachi.html.bak", "/%2e%2e/config/persona.txt", "/mobile/..%2fconfig%2fpersona.txt"):
            with self.assertRaises(urllib.error.HTTPError, msg=bad) as cm:
                self.get(bad)
            self.assertIn(cm.exception.code, (403, 404))

    def test_mobile_ping(self):
        info = json.loads(self.get("/api/mobile/ping"))
        self.assertTrue(info["ok"])
        self.assertTrue(info["ollama"])

    def _wav(self, seconds=1.0, sr=16000):
        t = np.arange(int(sr * seconds)) / sr
        return gui.samples_to_wav((0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), sr)

    def _post_wav(self, raw, headers=None):
        r = urllib.request.Request(self.base + "/api/mobile/voice", raw, {"Content-Type": "audio/wav", **(headers or {})})
        try:
            return 200, json.loads(urllib.request.urlopen(r, timeout=30).read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_mobile_voice_roundtrip(self):
        app = self.__class__.app
        app.a.stt.transcribe = lambda samples, language=None: "que horas são"   # Whisper simulado
        code, out = self._post_wav(self._wav())
        self.assertEqual(code, 200)
        self.assertEqual(out["text"], "que horas são")
        self.assertIn("Resposta", out["reply"])
        self.assertIsNone(out["audio"])                      # TTS desligado nos testes → sem áudio

    def test_mobile_voice_rejects_bad_audio_and_ignores_silence(self):
        self.assertEqual(self._post_wav(b"isto nao e um wav")[0], 400)
        code, out = self._post_wav(self._wav(0.1))
        self.assertEqual((code, out["text"]), (200, ""))
        self.assertEqual(self._post_wav(self._wav(), {"Origin": "http://evil.com"})[0], 403)

    def test_wav_helpers_resample(self):
        x = gui.wav_to_samples(self._wav(1.0, 48000))
        self.assertAlmostEqual(len(x), 16000, delta=2)

    def test_usb_connect_without_adb(self):
        with unittest.mock.patch("shutil.which", return_value=None):
            ok, msg = gui.usb_connect(8765)
        self.assertFalse(ok)
        self.assertIn("adb", msg)


if __name__ == "__main__":
    unittest.main()
