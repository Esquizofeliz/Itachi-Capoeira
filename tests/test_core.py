import os
import tempfile
import threading
import unittest
from pathlib import Path

import numpy as np

_tmp = tempfile.mkdtemp(prefix="itachi-capoeira-test-")
os.environ["ITACHI_CAPOEIRA_HOME"] = _tmp   # isola dados dos testes
# Isola da configuração local do usuário (config/local.txt gerado pelo 'setup'): env tem prioridade.
for _k, _v in {"CHAT_MODEL": "gemma4:e4b", "VISION_MODEL": "gemma4:e4b", "LOW_VRAM_MODE": "false",
               "WHISPER_MODEL": "base", "WHISPER_DEVICE": "cpu", "TTS_ENGINE": "off", "WAKE_WORD_ENABLED": "false",
               "OLLAMA_URL": "http://127.0.0.1:9"}.items():
    os.environ["ITACHI_CAPOEIRA_" + _k] = _v

from itachi_capoeira import audio, config, hardware, persona, tts  # noqa: E402
from itachi_capoeira.assistant import Assistant, Busy  # noqa: E402
from itachi_capoeira.llm import Ollama, OllamaError  # noqa: E402
from itachi_capoeira.memory import Memory  # noqa: E402
from itachi_capoeira.wake import match_wake_word  # noqa: E402
from tests.fake_ollama import FakeOllama  # noqa: E402


class ConfigTests(unittest.TestCase):
    def test_parse_persona_original(self):
        v = config.parse_file(config.PERSONA_FILE)
        self.assertEqual(v["NAME"], "Itachi Capoeira")
        self.assertEqual(v["HUMOR"], "60")

    def test_inline_comment_and_quotes(self):
        p = Path(_tmp) / "x.txt"
        p.write_text('A="oi # nao" # comentario\nB=12 # c\n# C=3\n', encoding="utf-8")
        v = config.parse_file(p)
        self.assertEqual(v["A"], "oi # nao")
        self.assertEqual(v["B"], "12")
        self.assertNotIn("C", v)

    def test_types_and_env(self):
        os.environ["ITACHI_CAPOEIRA_HUMOR"] = "99"
        os.environ["ITACHI_CAPOEIRA_WAKE_WORD_ENABLED"] = "true"
        try:
            c = config.Config()
            self.assertEqual(c.HUMOR, 99)
            self.assertIs(c.WAKE_WORD_ENABLED, True)
            self.assertIn("itachi", c.wake_words)
        finally:
            del os.environ["ITACHI_CAPOEIRA_HUMOR"], os.environ["ITACHI_CAPOEIRA_WAKE_WORD_ENABLED"]


class MemoryTests(unittest.TestCase):
    def test_json_safe_and_limit(self):
        m = Memory(Path(_tmp) / "mem.json", max_items=3)
        for i in range(5):
            m.add("t", f'aspas "quebram" \\ {i}\nlinha')   # o shell original quebrava aqui
        items = m.recent()
        self.assertEqual(len(items), 3)
        self.assertIn('"quebram"', items[-1]["content"])
        m.clear()
        self.assertEqual(m.recent(), [])


class PersonaTests(unittest.TestCase):
    def test_prompt_has_no_cjk_and_uses_name(self):
        p = persona.system_prompt(config.Config(), [{"type": "tela", "content": "algo"}])
        self.assertIn("Itachi", p)
        self.assertIn("algo", p)
        self.assertFalse(any("\u4e00" <= ch <= "\u9fff" for ch in p))


class HardwareTests(unittest.TestCase):
    def test_tiers(self):
        G = hardware.GpuInfo
        self.assertEqual(hardware.pick_tier(G("cuda", "x", 24 * 1024), 32).key, "xl")
        self.assertEqual(hardware.pick_tier(G("cuda", "x", 12 * 1024), 32).key, "m")
        self.assertEqual(hardware.pick_tier(G("cuda", "x", 8 * 1024), 16).key, "m")
        self.assertEqual(hardware.pick_tier(G("cuda", "x", 6 * 1024), 16).key, "s")
        self.assertEqual(hardware.pick_tier(G("cuda", "x", 2 * 1024), 16).key, "cpu")
        self.assertEqual(hardware.pick_tier(G(), 16).key, "cpu")
        self.assertEqual(hardware.pick_tier(G("metal", "M2", int(16 * 1024 * 0.65)), 16).key, "m")


class VadTests(unittest.TestCase):
    def _tone(self, secs, amp):
        t = np.arange(int(16000 * secs)) / 16000
        return (np.sin(2 * np.pi * 220 * t) * amp).astype(np.float32)

    def test_detects_utterance(self):
        vad = audio.VAD(silence_s=0.6)
        sig = np.concatenate([np.random.randn(16000).astype(np.float32) * 0.001,
                              self._tone(1.0, 0.3),
                              np.random.randn(16000).astype(np.float32) * 0.001])
        out = None
        for i in range(0, len(sig) - vad.frame_len, vad.frame_len):
            r = vad.feed(sig[i:i + vad.frame_len])
            if r is not None:
                out = r
                break
        self.assertIsNotNone(out)
        self.assertGreater(len(out) / 16000, 0.9)
        self.assertLess(len(out) / 16000, 2.2)

    def test_silence_is_ignored(self):
        vad = audio.VAD()
        sig = np.random.randn(16000 * 3).astype(np.float32) * 0.002
        for i in range(0, len(sig) - vad.frame_len, vad.frame_len):
            self.assertIsNone(vad.feed(sig[i:i + vad.frame_len]))

    def test_resample(self):
        x = np.zeros(48000, dtype=np.float32)
        self.assertEqual(len(audio.resample(x, 48000, 16000)), 16000)


class WakeTests(unittest.TestCase):
    def test_match(self):
        self.assertEqual(match_wake_word("Itachi, que horas são?", ["itachi"]), (True, "que horas são?"))
        self.assertTrue(match_wake_word("ei itáchi", ["itachi"])[0])
        self.assertTrue(match_wake_word("itaxi abre isso", ["itachi", "itaxi"])[0])
        self.assertFalse(match_wake_word("bom dia a todos", ["itachi"])[0])


class TtsTextTests(unittest.TestCase):
    def test_clean(self):
        t = tts.clean_for_speech("# Título\n**Olá** `x` [link](http://a.b) 😀\n```py\nprint(1)\n```\n- item")
        self.assertNotIn("*", t)
        self.assertNotIn("http", t)
        self.assertNotIn("print", t)
        self.assertNotIn("😀", t)
        self.assertIn("Olá", t)

    def test_limit_and_split(self):
        long = "Frase um. " * 200
        self.assertLessEqual(len(tts.clean_for_speech(long, 100)), 101)
        parts = tts.split_sentences("Olá, mundo. Tudo bem? Sim!")
        self.assertEqual(len(parts), 3)


class OllamaClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = FakeOllama(["gemma4:e4b", "llava:latest"])
        cls.c = Ollama(cls.srv.url)

    @classmethod
    def tearDownClass(cls):
        cls.srv.close()

    def test_basic(self):
        self.assertTrue(self.c.alive())
        self.assertTrue(self.c.has_model("gemma4:e4b"))
        self.assertTrue(self.c.has_model("llava"))      # resolve :latest
        self.assertFalse(self.c.has_model("nao-existe"))

    def test_chat_with_image_and_think_flag(self):
        out = self.c.chat("gemma4:e4b", [{"role": "user", "content": "oi"}], images_b64=["AAA"])
        self.assertIn("[com imagem]", out)
        path, payload = self.srv.calls[-1]
        self.assertIs(payload["think"], False)
        self.assertEqual(payload["messages"][-1]["images"], ["AAA"])

    def test_errors(self):
        with self.assertRaises(OllamaError):
            self.c.chat("modelo-x", [{"role": "user", "content": "oi"}])
        with self.assertRaises(OllamaError):
            Ollama("http://127.0.0.1:9").version()

    def test_pull_and_unload(self):
        seen = []
        self.c.pull("novo:1b", lambda s, d, t: seen.append(s))
        self.assertIn("success", seen)
        self.assertTrue(self.c.has_model("novo:1b"))
        self.c.chat("gemma4:e4b", [{"role": "user", "content": "x"}])
        self.assertIn("gemma4:e4b", self.c.unload_all())


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.srv = FakeOllama(["gemma4:e4b", "visao"])
        os.environ["ITACHI_CAPOEIRA_OLLAMA_URL"] = self.srv.url
        os.environ["ITACHI_CAPOEIRA_TTS_ENGINE"] = "off"
        os.environ["ITACHI_CAPOEIRA_MEMORY_MAX_ITEMS"] = "10"
        self.cfg = config.Config()
        self.a = Assistant(self.cfg)
        self.a.memory = Memory(Path(_tmp) / "asst-mem.json", 10)

    def tearDown(self):
        self.srv.close()
        os.environ["ITACHI_CAPOEIRA_OLLAMA_URL"] = "http://127.0.0.1:9"
        os.environ["ITACHI_CAPOEIRA_TTS_ENGINE"] = "off"
        os.environ.pop("ITACHI_CAPOEIRA_MEMORY_MAX_ITEMS", None)

    def test_ask_and_memory(self):
        r = self.a.ask("Qual é a capital do Brasil?", speak=False)
        self.assertTrue(r.startswith("Resposta"))
        kinds = [i["type"] for i in self.a.memory.recent()]
        self.assertEqual(kinds, ["pergunta", "resposta"])
        # a memória volta no prompt de sistema da próxima chamada
        self.a.ask("e a de Portugal?", speak=False)
        sys_prompt = self.srv.calls[-1][1]["messages"][0]["content"]
        self.assertIn("capital do Brasil", sys_prompt)

    def test_missing_model_message(self):
        self.a.cfg._v["CHAT_MODEL"] = "nao-existe"
        with self.assertRaises(OllamaError) as cm:
            self.a.ask("oi", speak=False)
        self.assertIn("itachi-capoeira setup", str(cm.exception))

    def test_busy_lock(self):
        self.a._begin()
        try:
            with self.assertRaises(Busy):
                self.a.ask("oi", speak=False)
        finally:
            self.a._end()

    def test_screen_pipeline_single_model(self):
        from itachi_capoeira import screen
        orig = screen.capture_jpeg
        screen.capture_jpeg = lambda *a, **k: b"\xff\xd8fakejpeg"
        try:
            r = self.a.describe_screen("o que é isso?", speak=False)
        finally:
            screen.capture_jpeg = orig
        self.assertIn("[com imagem]", r)

    def test_screen_pipeline_two_models_low_vram(self):
        from itachi_capoeira import screen
        self.a.cfg._v.update({"VISION_MODEL": "visao", "LOW_VRAM_MODE": True})
        orig = screen.capture_jpeg
        screen.capture_jpeg = lambda *a, **k: b"\xff\xd8fakejpeg"
        try:
            r = self.a.describe_screen(speak=False)
        finally:
            screen.capture_jpeg = orig
        self.assertTrue(r.startswith("Resposta"))
        unloads = [p for path, p in self.srv.calls if path == "/api/generate" and p.get("keep_alive") == 0]
        self.assertEqual({u["model"] for u in unloads}, {"gemma4:e4b", "visao"})

    def test_dictate_with_fake_audio(self):
        from itachi_capoeira import audio as au, screen
        copied = []
        self.a.cfg._v.update({"AUTO_PASTE": False, "CORRECT_GRAMMAR": True})
        o = (au.record_command, au.beep, screen.set_clipboard)
        au.record_command = lambda *a, **k: np.ones(16000, dtype=np.float32) * 0.1
        au.beep = lambda *a, **k: None
        screen.set_clipboard = lambda t: copied.append(t) or True
        self.a.stt.transcribe = lambda clip, language=None: "olá mundo isso é um teste"
        try:
            text = self.a.dictate()
        finally:
            au.record_command, au.beep, screen.set_clipboard = o
        self.assertTrue(text)
        self.assertEqual(copied, [text])


if __name__ == "__main__":
    unittest.main()


class FakeMic:
    """Microfone simulado: entrega silêncio, uma 'fala' e silêncio."""
    script = None

    def __init__(self, *a, **k):
        self.i = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def read(self):
        frames = FakeMic.script
        if self.i >= len(frames):
            import time
            time.sleep(0.01)
            return np.zeros(480, dtype=np.float32)
        f = frames[self.i]
        self.i += 1
        return f


def _speech_script(speech_s=1.0, lead_s=0.5, tail_s=1.6):
    n = 480
    t = np.arange(int(16000 * speech_s)) / 16000
    speech = (np.sin(2 * np.pi * 200 * t) * 0.3).astype(np.float32)
    sig = np.concatenate([np.zeros(int(16000 * lead_s), np.float32) + 0.0005, speech,
                          np.zeros(int(16000 * tail_s), np.float32) + 0.0005])
    return [sig[i:i + n] for i in range(0, len(sig) - n, n)]


class RecordFlowTests(unittest.TestCase):
    def test_record_command_returns_utterance(self):
        orig = audio.MicStream
        audio.MicStream = FakeMic
        FakeMic.script = _speech_script()
        try:
            clip = audio.record_command(silence_seconds=0.8, no_speech_timeout=3)
        finally:
            audio.MicStream = orig
        self.assertIsNotNone(clip)
        self.assertGreater(len(clip) / 16000, 0.9)

    def test_record_command_nobody_speaks(self):
        orig = audio.MicStream
        audio.MicStream = FakeMic
        FakeMic.script = [np.zeros(480, np.float32) + 0.0003] * 200
        try:
            clip = audio.record_command(no_speech_timeout=1.0)
        finally:
            audio.MicStream = orig
        self.assertIsNone(clip)

    def test_manual_stop_flushes(self):
        orig = audio.MicStream
        audio.MicStream = FakeMic
        FakeMic.script = _speech_script(speech_s=5.0, tail_s=0)
        stop = threading.Event()
        threading.Timer(0.0, stop.set).start()
        try:
            clip = audio.record_command(silence_seconds=5, stop_event=stop, no_speech_timeout=3)
        finally:
            audio.MicStream = orig
        # parou manualmente: devolve o que tinha (ou None se ainda nem começou a falar) sem travar
        self.assertTrue(clip is None or len(clip) > 0)


class WakeListenerFlowTests(unittest.TestCase):
    def test_wake_word_triggers_converse(self):
        from itachi_capoeira import wake
        srv = FakeOllama(["gemma4:e4b"])
        os.environ["ITACHI_CAPOEIRA_OLLAMA_URL"] = srv.url
        os.environ["ITACHI_CAPOEIRA_TTS_ENGINE"] = "off"
        try:
            cfg = config.Config()
            asst = Assistant(cfg)
            asst.memory = Memory(Path(_tmp) / "wake-mem.json", 10)
            asst.stt.transcribe = lambda clip, language=None: "Itachi, que horas são?"
            orig = audio.MicStream
            audio.MicStream = FakeMic
            FakeMic.script = _speech_script()
            stop = threading.Event()
            wl = wake.WakeListener(asst, stop)
            wl.start()
            for _ in range(60):
                if asst.memory.recent():
                    break
                stop.wait(0.1)
            stop.set()
            wl.join(timeout=3)
            audio.MicStream = orig
            kinds = [i["type"] for i in asst.memory.recent()]
            self.assertIn("pergunta", kinds)
            self.assertEqual(asst.memory.recent()[0]["content"], "que horas são?")
        finally:
            audio.MicStream = orig
            srv.close()
            os.environ["ITACHI_CAPOEIRA_OLLAMA_URL"] = "http://127.0.0.1:9"
