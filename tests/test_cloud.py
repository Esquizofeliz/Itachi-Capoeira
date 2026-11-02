"""Modo nuvem do Ollama: chave de API, escolha de modelos, segredos e comportamento do cliente."""
import json
import os
import stat
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

from itachi_capoeira import cloud, config
from itachi_capoeira.llm import Ollama, OllamaError, is_local_url
from tests.fake_ollama import FakeOllama

NAMES = ["gpt-oss:120b", "gpt-oss:20b", "qwen3-vl:235b", "deepseek-v3.1:671b"]


class Urls(unittest.TestCase):
    def test_is_local(self):
        for u in ("http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"):
            self.assertTrue(is_local_url(u), u)
        self.assertFalse(is_local_url("https://ollama.com"))

    def test_key_only_over_https_and_cloud(self):
        self.assertNotIn("Authorization", Ollama("http://ollama.example", api_key="k")._headers())     # sem TLS
        self.assertNotIn("Authorization", Ollama("http://127.0.0.1:11434", api_key="k")._headers())    # local
        self.assertEqual(Ollama("https://ollama.com", api_key="abc")._headers()["Authorization"], "Bearer abc")

    def test_cloud_omits_local_only_options_and_never_pulls(self):
        srv = FakeOllama(["gpt-oss:120b"])
        try:
            c = Ollama(srv.url, api_key="k", cloud=True)
            c.chat("gpt-oss:120b", [{"role": "user", "content": "oi"}], keep_alive="10m", num_ctx=4096)
            payload = srv.calls[-1][1]
            self.assertNotIn("keep_alive", payload)
            self.assertNotIn("options", payload)
            self.assertTrue(c.alive())
            self.assertEqual(c.version(), "nuvem")
            self.assertEqual(c.running(), [])
            with self.assertRaises(OllamaError):
                c.pull("x")
        finally:
            srv.close()

    def test_friendly_http_errors(self):
        class H(BaseHTTPRequestHandler):
            code = 401

            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(H.code)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

        httpd = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            c = Ollama(f"http://127.0.0.1:{httpd.server_address[1]}", cloud=True)
            for code, word in ((401, "cloud setup"), (403, "plano pago"), (429, "Limite")):
                H.code = code
                with self.assertRaises(OllamaError) as cm:
                    c.list_models()
                self.assertIn(word, str(cm.exception))
        finally:
            httpd.shutdown()


class Picking(unittest.TestCase):
    def test_pick(self):
        self.assertEqual(cloud.pick_models(NAMES), ("gpt-oss:120b", "qwen3-vl:235b"))
        self.assertEqual(cloud.pick_models(["foo:1b"]), ("foo:1b", None))
        self.assertEqual(cloud.pick_models([]), (None, None))


class Enable(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.srv = FakeOllama(NAMES)
        clean = {k: v for k, v in os.environ.items() if not k.startswith("ITACHI_CAPOEIRA_") and k != "OLLAMA_API_KEY"}
        patches = [mock.patch.dict(os.environ, clean, clear=True),
                   mock.patch.object(config, "LOCAL_FILE", self.tmp / "local.txt"),
                   mock.patch.object(config, "SECRETS_FILE", self.tmp / "secrets.txt"),
                   mock.patch.object(config, "CONFIG_DIR", self.tmp),
                   mock.patch.object(cloud, "CLOUD_URL", self.srv.url),
                   mock.patch.object(cloud, "remove_local", config.remove_local),
                   mock.patch.object(cloud, "_tty", return_value=False)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.srv.close)
        self.out = []

    def test_enable_saves_key_securely_and_models(self):
        cfg = config.Config()
        rc = cloud.enable(cfg, key="secret-key-1234", out=self.out.append)
        self.assertEqual(rc, 0, "\n".join(self.out))
        self.assertEqual(cfg.CHAT_MODEL, "gpt-oss:120b")
        self.assertEqual(cfg.VISION_MODEL, "qwen3-vl:235b")
        sec = self.tmp / "secrets.txt"
        self.assertIn("secret-key-1234", sec.read_text())
        self.assertEqual(stat.S_IMODE(sec.stat().st_mode), 0o600)
        self.assertNotIn("secret-key", (self.tmp / "local.txt").read_text())   # a chave nunca vai pro local.txt
        again = config.Config()                                               # persiste entre execuções
        self.assertEqual(again.OLLAMA_API_KEY, "secret-key-1234")
        self.assertEqual(again.OLLAMA_URL, self.srv.url)
        self.assertNotIn("secret-key", str(again.as_dict(mask_secrets=True)))
        self.assertTrue(any("internet" in l or "ollama.com" in l for l in self.out))   # aviso de privacidade

    def test_unknown_model_rejected(self):
        rc = cloud.enable(config.Config(), key="k", chat_model="nao-existe:1b", out=self.out.append)
        self.assertEqual(rc, 1)
        self.assertFalse((self.tmp / "secrets.txt").exists())

    def test_no_key_fails_cleanly(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OLLAMA_API_KEY", None)
            self.assertEqual(cloud.enable(config.Config(), out=self.out.append), 1)

    def test_disable_removes_key_and_overrides(self):
        cfg = config.Config()
        cloud.enable(cfg, key="k123456", out=self.out.append)
        cloud.disable(cfg, out=self.out.append)
        self.assertFalse((self.tmp / "secrets.txt").exists())
        text = (self.tmp / "local.txt").read_text()
        for k in ("OLLAMA_URL", "CHAT_MODEL", "VISION_MODEL"):
            self.assertNotIn(k, text)

    def test_env_key_fallback(self):
        with mock.patch.dict(os.environ, {"OLLAMA_API_KEY": "from-env-9999"}):
            self.assertEqual(config.Config().OLLAMA_API_KEY, "from-env-9999")


if __name__ == "__main__":
    unittest.main()
