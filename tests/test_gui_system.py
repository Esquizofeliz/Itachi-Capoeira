"""GUI/mobile: /api/system (atalhos, nuvem, voz) sem tocar no desktop nem na internet."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

os.environ.setdefault("ITACHI_CAPOEIRA_HOME", tempfile.mkdtemp(prefix="itachi-capoeira-sys-test-"))

from itachi_capoeira import cloud, config, gui, shortcuts  # noqa: E402
from tests.fake_ollama import FakeOllama  # noqa: E402


class SystemApi(unittest.TestCase):
    def setUp(self):
        self.fake = FakeOllama(["gpt-oss:120b", "qwen3-vl:235b"])
        self.cfg = config.Config({"OLLAMA_URL": self.fake.url, "TTS_ENGINE": "off"})
        self.app = gui.App(self.cfg)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), gui.make_handler(self.app))
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.shutdown)
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.fake.close)

    def get(self, p):
        return json.loads(urllib.request.urlopen(self.base + p, timeout=20).read())

    def post(self, p, body, headers=None):
        req = urllib.request.Request(self.base + p, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except urllib.error.HTTPError as e:
            return {"_status": e.code, **json.loads(e.read() or b"{}")}

    def test_system_info_shape_and_no_secrets(self):
        self.cfg._v["OLLAMA_API_KEY"] = "sekret-abcd"
        info = self.get("/api/system")
        for k in ("session", "wayland", "shortcuts", "cloud", "audio"):
            self.assertIn(k, info)
        self.assertTrue(info["cloud"]["key"])
        self.assertEqual(info["cloud"]["key_tail"], "abcd")
        self.assertNotIn("sekret", json.dumps(info))             # a chave inteira nunca sai do servidor

    def test_status_and_mobile_ping_expose_cloud_flag(self):
        self.assertIn("cloud", self.get("/api/status"))
        ping = self.get("/api/mobile/ping")
        self.assertIn("cloud", ping)
        self.assertIn("daemon", ping)

    def test_up_registers_shortcuts_and_starts_daemon(self):
        with mock.patch.object(shortcuts, "ensure", return_value="Atalhos ok") as ens, \
                mock.patch.object(gui, "read_pid", return_value=None), \
                mock.patch("itachi_capoeira.daemon.start_background", return_value=999):
            r = self.post("/api/system", {"action": "up"})
        self.assertTrue(r["ok"])
        self.assertIn("999", r["message"])
        ens.assert_called_once()

    def test_shortcuts_actions(self):
        with mock.patch.object(shortcuts, "install", return_value=(True, "instalado")) as ins, \
                mock.patch.object(shortcuts, "remove", return_value=(True, "removido")) as rem:
            self.assertEqual(self.post("/api/system", {"action": "shortcuts_install"})["message"], "instalado")
            self.assertEqual(self.post("/api/system", {"action": "shortcuts_remove"})["message"], "removido")
        ins.assert_called_once()
        rem.assert_called_once()

    def test_audiotest_runs_as_job(self):
        fake_result = {"ok": True, "engine": "system", "hint": "ok", "synth_s": None, "play_s": 1.0,
                       "device": "x", "sounddevice": True}
        with mock.patch("itachi_capoeira.audiotest.run", return_value=fake_result):
            self.assertTrue(self.post("/api/system", {"action": "audiotest"})["started"])
            for _ in range(50):
                job = self.get("/api/system").get("job")
                if job and job["state"] == "done":
                    break
                threading.Event().wait(0.1)
        self.assertEqual(job["state"], "done")
        self.assertTrue(job["result"]["ok"])

    def test_cloud_enable_from_gui_never_prompts_and_rebuilds_client(self):
        with mock.patch.object(cloud, "CLOUD_URL", self.fake.url), \
                mock.patch.object(config, "LOCAL_FILE", config.Path(tempfile.mkdtemp()) / "local.txt"), \
                mock.patch.object(config, "SECRETS_FILE", config.Path(tempfile.mkdtemp()) / "secrets.txt"), \
                mock.patch.object(cloud, "_tty", return_value=True), \
                mock.patch("builtins.input", side_effect=AssertionError("não pode perguntar no terminal")), \
                mock.patch("getpass.getpass", side_effect=AssertionError("não pode pedir a chave no terminal")):
            r = self.post("/api/system", {"action": "cloud_enable", "key": "k-1234567"})
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.cfg.CHAT_MODEL, "gpt-oss:120b")
        self.assertNotIn("k-1234567", r["message"])

    def test_cloud_enable_without_key_fails_cleanly(self):
        os.environ.pop("OLLAMA_API_KEY", None)
        with mock.patch.object(cloud, "_tty", return_value=True), \
                mock.patch("builtins.input", side_effect=AssertionError("não pode perguntar")), \
                mock.patch("getpass.getpass", side_effect=AssertionError("não pode perguntar")):
            r = self.post("/api/system", {"action": "cloud_enable", "key": ""})
        self.assertFalse(r["ok"])

    def test_pages_ship_the_new_controls(self):
        desk = urllib.request.urlopen(self.base + "/", timeout=20).read().decode()
        for needle in ("sys-rows", "sysAct('up')", "sysAct('audiotest')", "cloudEnable", "cloud-ok", "/api/system"):
            self.assertIn(needle, desk)
        mob = urllib.request.urlopen(self.base + "/mobile/", timeout=20).read().decode()
        for needle in ("pc-status", "up-btn", "vt-btn", "/api/system"):
            self.assertIn(needle, mob)
        self.assertNotIn("cloud_enable", mob)                    # a chave de API nunca é pedida no celular

    def test_bad_action_and_foreign_origin_rejected(self):
        self.assertEqual(self.post("/api/system", {"action": "rm -rf"})["_status"], 400)
        r = self.post("/api/system", {"action": "up"}, headers={"Origin": "http://evil.example"})
        self.assertEqual(r["_status"], 403)                       # CSRF: outro site não aciona nada


if __name__ == "__main__":
    unittest.main()
