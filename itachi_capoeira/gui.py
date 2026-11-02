"""Itachi Capoeira — interface gráfica web local (inspirada no projeto Jarvis) + ponte do celular por USB.

Uso:  itachi-capoeira-gui [--port 8765] [--no-browser] [--usb]      (ou: python -m itachi_capoeira.gui)
  --usb  liga o celular Android por cabo (adb reverse) e abre o assistente de mesa nele.
Escuta apenas em 127.0.0.1. Nada sai da sua máquina (o celular acessa o PC pelo cabo USB).
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import wave
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import numpy as np
import psutil

from . import __version__, audio, hardware, screen, tts
from .assistant import Assistant, Busy
from .config import APP_DIR, LOG_DIR, MODELS_DIR, load
from .daemon import TRIGGERS, read_pid, send_trigger
from .health import gpu_temperature, start_ollama
from .llm import OllamaError
from .wake import match_wake_word

log = logging.getLogger("itachi_capoeira.gui")
GUI_DIR = APP_DIR / "gui"
MOBILE_DIR = APP_DIR / "mobile"
HTML = GUI_DIR / "Itachi-capoeira.html"
MOBILE_HTML = MOBILE_DIR / "Itachi.html"
LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".svg": "image/svg+xml"}
MAX_AUDIO_BYTES = 12 * 1024 * 1024      # ~6 min de WAV 16 kHz mono


def wav_to_samples(raw: bytes) -> np.ndarray:
    """WAV PCM 16 bits (qualquer taxa/canais) → float32 mono a 16 kHz (taxa do Whisper)."""
    try:
        with wave.open(io.BytesIO(raw)) as w:
            if w.getsampwidth() != 2:
                raise ValueError("o áudio precisa ser WAV PCM de 16 bits")
            sr, ch, frames = w.getframerate(), w.getnchannels(), w.readframes(w.getnframes())
    except (wave.Error, EOFError) as e:
        raise ValueError(f"áudio inválido: {e}") from e
    x = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x[: len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
    return audio.resample(x, sr, audio.SAMPLE_RATE) if sr != audio.SAMPLE_RATE else x


def samples_to_wav(x: np.ndarray, sr: int) -> bytes:
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()


def usb_connect(port: int, open_phone: bool = True) -> tuple[bool, str]:
    """Liga o celular Android por cabo: `adb reverse` deixa o celular acessar localhost:PORTA do PC."""
    adb = shutil.which("adb")
    if not adb:
        return False, "adb não encontrado. Instale o Android Platform-Tools e coloque o 'adb' no PATH."
    try:
        out = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=15).stdout
        ready = [ln.split("\t")[0] for ln in out.splitlines()[1:] if ln.strip().endswith("\tdevice")]
        if not ready:
            return False, ("Nenhum celular autorizado. Conecte o cabo USB, ative a 'Depuração USB' "
                           "(Opções do desenvolvedor) e aceite a permissão na tela do celular.")
        serial = ready[0]
        r = subprocess.run([adb, "-s", serial, "reverse", f"tcp:{port}", f"tcp:{port}"],
                           capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return False, "Falha no 'adb reverse': " + (r.stderr or r.stdout).strip()
        if open_phone:
            subprocess.run([adb, "-s", serial, "shell", "am", "start", "-a", "android.intent.action.VIEW",
                            "-d", f"http://localhost:{port}/mobile/"], capture_output=True, text=True, timeout=15)
        return True, f"Celular {serial} conectado por USB. Abra http://localhost:{port}/mobile/ nele."
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"Erro ao falar com o adb: {e}"


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.a = Assistant(cfg)
        self.jobs: dict[str, dict] = {}
        self.stt_ready = False
        self._hw = (0.0, None, None)
        self._sys: tuple[float, dict | None] = (0.0, None)

    # ------------------------------------------------------------ hardware (cache de 3 s: chama nvidia-smi)
    def hw(self):
        t, gpu, temp = self._hw
        if time.time() - t > 3 or gpu is None:
            gpu = hardware.detect_gpu()
            temp = gpu_temperature()
            self._hw = (time.time(), gpu, temp)
        return gpu, temp

    # ------------------------------------------------------------ modelos
    def specs(self):
        c = self.cfg
        same = c.VISION_MODEL == c.CHAT_MODEL
        out = [("chat", "Chat + Visão · " + c.CHAT_MODEL if same else "Chat · " + c.CHAT_MODEL,
                "LLM principal (Ollama). Entende texto e imagem." if same else "LLM de texto (Ollama).", "llm", c.CHAT_MODEL)]
        if not same:
            out.append(("vision", "Visão · " + c.VISION_MODEL, "Modelo de visão (Ollama).", "llm", c.VISION_MODEL))
        out.append(("whisper", f"Faster-Whisper ({c.WHISPER_MODEL})", "Voz → texto, off-line. Baixa no 1º uso se não pré-carregado.", "stt", c.WHISPER_MODEL))
        out.append(("kokoro", "Kokoro TTS (voz pt-BR)", "Texto → voz via ONNX, roda na CPU.", "tts", "kokoro"))
        return out

    def models(self, tags: dict, running: set):
        res = []
        for mid, label, desc, kind, name in self.specs():
            m = {"id": mid, "label": label, "desc": desc, "kind": kind, "name": name, "installed": False,
                 "loaded": False, "size_gb": None, "job": self.jobs.get(mid)}
            if kind == "llm":
                hit = tags.get(name) or tags.get(name + ":latest")
                m["installed"] = bool(hit)
                m["size_gb"] = round(hit["size"] / 1024 ** 3, 2) if hit and hit.get("size") else None
                m["loaded"] = name in running or name + ":latest" in running
            elif kind == "tts":
                m["installed"] = tts.kokoro_ready()
                if tts.KOKORO_DIR.exists():
                    m["size_gb"] = round(sum(f.stat().st_size for f in tts.KOKORO_DIR.glob("*") if f.is_file()) / 1024 ** 3, 2)
            else:
                m["installed"] = self.stt_ready
            res.append(m)
        return res

    def status(self) -> dict:
        llm = self.a.llm
        alive = llm.alive()
        tags, running = {}, set()
        if alive:
            try:
                tags = {m["name"]: m for m in llm._json("/api/tags", timeout=10).get("models", [])}
                running = {m.get("name") or m.get("model") for m in llm.running()}
            except OllamaError:
                pass
        gpu, temp = self.hw()
        vm = psutil.virtual_memory()
        du = shutil.disk_usage(MODELS_DIR if MODELS_DIR.exists() else APP_DIR)
        models = self.models(tags, running)
        return {
            "name": self.cfg.NAME, "version": __version__, "ollama": alive, "daemon_pid": read_pid(),
            "busy": self.a.busy, "recording": self.a.recording,
            "cpu": psutil.cpu_percent(), "ram": {"percent": vm.percent, "total_gb": round(vm.total / 1024 ** 3, 1)},
            "gpu": {"backend": gpu.backend, "name": gpu.name, "total_mb": gpu.vram_total_mb, "free_mb": gpu.vram_free_mb,
                    "temp": temp, "temp_limit": self.cfg.GPU_TEMP_LIMIT},
            "models": models, "models_gb": round(sum(m["size_gb"] or 0 for m in models), 2),
            "disk_free_gb": round(du.free / 1024 ** 3, 1),
            "hotkeys": {"screen": self.cfg.HOTKEY_SCREEN, "voice": self.cfg.HOTKEY_VOICE,
                        "talk": self.cfg.HOTKEY_TALK, "stop": self.cfg.HOTKEY_STOP},
            "memory": len(self.a.memory.recent()), "tts": self.cfg.TTS_ENGINE, "cloud": llm.cloud,
        }

    # ------------------------------------------------------------ sistema: atalhos globais, nuvem e voz
    def _rebuild_llm(self) -> None:
        from .llm import Ollama
        self.a.llm = Ollama.from_config(self.cfg, timeout=self.cfg.LLM_TIMEOUT)
        self._sys = (0.0, None)

    def system_info(self, fresh: bool = False) -> dict:
        from . import shortcuts
        t, cached = self._sys
        if cached and not fresh and time.time() - t < 8:
            return {**cached, "job": self.jobs.get("audiotest")}
        cfg = self.cfg
        key = str(cfg.get("OLLAMA_API_KEY", "") or "")
        sc = {"supported": False, "bindings": {}, "registered": False}
        if shortcuts.is_wayland():
            ok, _why = shortcuts.available()
            sc["supported"] = ok
            if ok:
                try:
                    sc["bindings"] = {n: d["binding"] for n, d in shortcuts.status().items()}
                    sc["registered"] = len(sc["bindings"]) >= 4
                except Exception as e:  # noqa: BLE001
                    log.warning("Atalhos do desktop: %s", e)
        info = {
            "session": os.environ.get("XDG_SESSION_TYPE", "") or sys.platform,
            "desktop": os.environ.get("XDG_CURRENT_DESKTOP", ""),
            "wayland": shortcuts.is_wayland(),
            "shortcuts": sc,
            "cloud": {"on": self.a.llm.cloud, "url": cfg.OLLAMA_URL, "key": bool(key), "key_tail": key[-4:] if key else "",
                      "chat": cfg.CHAT_MODEL, "vision": cfg.VISION_MODEL},
            "audio": {"engine": str(cfg.TTS_ENGINE), "player": str(cfg.AUDIO_PLAYER),
                      "out": str(cfg.AUDIO_OUT_DEVICE) or "padrão"},
            "daemon_pid": read_pid(),
        }
        self._sys = (time.time(), info)
        return {**info, "job": self.jobs.get("audiotest")}

    def system_action(self, action: str, d: dict) -> dict:
        from . import audiotest, cloud, shortcuts
        from .config import load as reload_cfg
        from .daemon import start_background, stop_background
        cfg = self.cfg
        msg: list[str] = []
        if action == "up":                               # atalhos + daemon, igual a 'itachi-capoeira up'
            m = shortcuts.ensure(cfg)
            if m:
                msg.append(m)
            pid = read_pid() or start_background()
            msg.append(f"Daemon ligado (PID {pid})." if pid else "O daemon não subiu — veja os logs.")
            ok = bool(pid)
        elif action in ("shortcuts_install", "shortcuts_remove"):
            ok, m = shortcuts.install(cfg) if action == "shortcuts_install" else shortcuts.remove()
            msg.append(m)
        elif action == "restart_daemon":
            stop_background()
            time.sleep(1)
            pid = start_background()
            ok = bool(pid)
            msg.append(f"Daemon reiniciado (PID {pid})." if pid else "O daemon não subiu — veja os logs.")
        elif action == "audiotest":
            def f(job):
                r = audiotest.run(cfg, self.a.speaker)
                job.update(result=r, msg=r["hint"] or ("Reproduzida." if r["ok"] else "Não reproduzida."))
            self.start_job("audiotest", f)
            return {"ok": True, "started": True}
        elif action == "cloud_enable":
            rc = cloud.enable(cfg, key=str(d.get("key", "")).strip() or None, chat_model=d.get("chat") or None,
                              vision_model=d.get("vision") or None, out=msg.append, interactive=False)
            ok = rc == 0
            if ok:
                self._rebuild_llm()
                msg.append("Reinicie o daemon para valer nos atalhos." if read_pid() else "")
        elif action == "cloud_off":
            ok = cloud.disable(cfg, out=msg.append) == 0
            fresh = reload_cfg()
            cfg._v.clear()
            cfg._v.update(fresh._v)
            self._rebuild_llm()
        else:
            raise ValueError("ação inválida")
        self._sys = (0.0, None)
        return {"ok": ok, "message": "\n".join(m for m in msg if m)}

    # ------------------------------------------------------------ jobs em segundo plano
    def start_job(self, mid: str, fn) -> None:
        cur = self.jobs.get(mid)
        if cur and cur["state"] == "running":
            return
        job = self.jobs[mid] = {"state": "running", "pct": 0, "msg": ""}

        def run():
            try:
                fn(job)
                job.update(state="done", pct=100)
                log.info("✅ %s concluído", mid)
            except Exception as e:  # noqa: BLE001
                job.update(state="error", msg=str(e)[:200])
                log.error("Falha em %s: %s", mid, e)
        threading.Thread(target=run, name=f"gui-{mid}", daemon=True).start()

    def model_action(self, action: str, mid: str | None) -> None:
        cfg, llm = self.cfg, self.a.llm
        if action == "unload_all":
            log.info("🧹 VRAM liberada: %s", ", ".join(llm.unload_all()) or "(nada carregado)")
            return
        specs = {s[0]: s for s in self.specs()}
        if action == "pull_all":
            for k in specs:
                if k != "whisper" or not self.stt_ready:
                    self.model_action("pull", k)
            return
        if mid not in specs:
            raise ValueError("modelo desconhecido")
        _, _, _, kind, name = specs[mid]

        def progress(job, done, total, msg):
            job.update(msg=msg, pct=done * 100 // total if total else job["pct"])

        if action == "pull" and kind == "llm":
            def f(job):
                if not start_ollama(llm, wait=20):
                    raise OllamaError("Ollama não está rodando.")
                if not llm.has_model(name):
                    llm.pull(name, lambda s, d, t: progress(job, d, t, s))
            self.start_job(mid, f)
        elif action == "pull" and kind == "tts":
            if not tts.kokoro_ready():
                self.start_job(mid, lambda job: tts.download_kokoro(lambda n, d, t: progress(job, d, t, n)))
        elif action == "pull" and kind == "stt":
            def f(job):
                self.a.stt.preload()
                self.stt_ready = True
            self.start_job(mid, f)
        elif action == "load" and kind == "llm":
            if llm.cloud:
                raise ValueError("Na nuvem não há o que carregar na VRAM.")
            self.start_job(mid, lambda job: llm._json("/api/generate", {"model": name, "keep_alive": cfg.OLLAMA_KEEP_ALIVE}, timeout=300))
        elif action == "unload" and kind == "llm":
            llm.unload(name)
        else:
            raise ValueError("ação inválida")

    # ------------------------------------------------------------ interação
    def trigger(self, name: str) -> str:
        """Com o daemon rodando, usa o mesmo gatilho dos atalhos; senão executa aqui mesmo."""
        if read_pid():
            send_trigger(name)
            return "daemon"
        a = self.a
        if name == "stop":
            a.interrupt()
        elif name in ("voice", "talk") and a.recording:
            a.stop_listening()
        else:
            fn = {"screen": a.describe_screen, "voice": a.dictate, "talk": a.converse}[name]

            def run():
                try:
                    fn()
                except Busy:
                    log.info("Ocupado — ignorando '%s'.", name)
                except Exception as e:  # noqa: BLE001
                    log.error("Falha em '%s': %s", name, e)
            threading.Thread(target=run, name=f"gui-{name}", daemon=True).start()
        return "local"

    def vision(self, question: str, image_b64: str | None) -> dict:
        a, cfg = self.a, self.cfg
        a._begin()
        try:
            a._ensure_llm(cfg.VISION_MODEL)
            if not image_b64:
                image_b64 = screen.to_b64(screen.capture_jpeg(int(cfg.SCREENSHOT_MAX_PX), int(cfg.SCREEN_MONITOR)))
            ask = question.strip() or "Descreva esta imagem em português, de forma breve. Transcreva textos importantes."
            reply = a.llm.chat(cfg.VISION_MODEL, a._messages(ask), images_b64=[image_b64],
                               keep_alive=cfg.OLLAMA_KEEP_ALIVE, num_ctx=cfg.NUM_CTX)
            a.memory.add("tela", reply)
            return {"reply": reply, "image": image_b64, "question": ask}
        finally:
            a._end()

    # ------------------------------------------------------------ celular (microfone + áudio por USB)
    def mobile_info(self) -> dict:
        pref = str(self.cfg.TTS_ENGINE).lower()
        return {"ok": True, "name": self.cfg.NAME, "version": __version__, "busy": self.a.busy,
                "ollama": self.a.llm.alive(), "tts": pref, "wake_word": bool(self.cfg.WAKE_WORD_ENABLED),
                "cloud": self.a.llm.cloud, "daemon": bool(read_pid())}

    def _tts_payload(self, reply: str) -> dict:
        """Áudio da resposta para o celular tocar: WAV (Kokoro) ou, na falta dele, o texto para a voz do próprio celular."""
        cfg, sp = self.cfg, self.a.speaker
        clean = tts.clean_for_speech(reply, int(cfg.TTS_MAX_CHARS))
        if str(cfg.TTS_ENGINE).lower() == "off" or not clean:
            return {"audio": None, "speak": ""}
        if str(cfg.TTS_ENGINE).lower() in ("auto", "kokoro") and sp.kokoro.available():
            try:
                parts, sr = [], 24000
                for sentence in tts.split_sentences(clean):
                    x, sr = sp.kokoro.synth(sentence)
                    parts.append(x)
                if parts:
                    return {"audio": base64.b64encode(samples_to_wav(np.concatenate(parts), sr)).decode("ascii"), "speak": ""}
            except Exception as e:  # noqa: BLE001
                log.warning("Kokoro falhou para o celular (%s); usando a voz do celular.", e)
        return {"audio": None, "speak": clean}

    def mobile_voice(self, raw: bytes) -> dict:
        """Frase gravada no celular → Whisper → (palavra de ativação) → LLM → voz de volta para o celular."""
        samples = wav_to_samples(raw)
        out = {"text": "", "reply": "", "audio": None, "speak": ""}
        if len(samples) < audio.SAMPLE_RATE * 0.3:
            return out
        a, cfg = self.a, self.cfg
        a._begin()
        try:
            text = a.stt.transcribe(samples)
            out["text"] = text
            if not text:
                return out
            if cfg.WAKE_WORD_ENABLED:
                found, rest = match_wake_word(text, cfg.wake_words)
                if not found:
                    return out                      # ninguém chamou o assistente: ignora
                text = rest or "Estou ouvindo."
                if not rest:
                    out["reply"] = text
                    out.update(self._tts_payload(text))
                    return out
            log.info("📱 Celular: %s", text)
            reply = a.answer(text)
            log.info("🧠 %s: %s", cfg.NAME, reply)
            out["reply"] = reply
            out.update(self._tts_payload(reply))
            return out
        finally:
            a._end()

    def script(self) -> str:
        c = self.cfg
        names = " ".join(dict.fromkeys([c.CHAT_MODEL, c.VISION_MODEL]))
        return (f"# {c.NAME} · comandos úteis (modelos atuais: chat={c.CHAT_MODEL} | visão={c.VISION_MODEL} | whisper={c.WHISPER_MODEL})\n"
                "itachi-capoeira up                              # liga TUDO: atalhos globais (F7-F10) + daemon\n"
                "itachi-capoeira start | stop | restart | status | logs\n"
                "itachi-capoeira audiotest                        # testa a voz e mostra onde ela falha\n"
                "itachi-capoeira shortcuts install | status       # atalhos globais do desktop (Wayland/GNOME)\n"
                "itachi-capoeira cloud setup | status | off       # nuvem do Ollama (plano gratuito, chave de API)\n"
                "itachi-capoeira setup [--tier xl|m|s|cpu]      # escolhe e baixa os modelos pela sua VRAM\n"
                "itachi-capoeira screen \"o que significa esse erro?\"\n"
                "itachi-capoeira ask \"me explique o que é Docker\"\n"
                "itachi-capoeira doctor --deep\n"
                f"ollama pull {names}                  # alternativa direta pelo Ollama\n\n"
                "# Python\n"
                "from itachi_capoeira import config\nfrom itachi_capoeira.assistant import Assistant\n"
                "a = Assistant(config.load())\nprint(a.answer(\"Olá!\"))\n\n"
                f"# Atalhos: tela={c.HOTKEY_SCREEN} voz={c.HOTKEY_VOICE} conversa={c.HOTKEY_TALK} parar={c.HOTKEY_STOP} (config/persona.txt)\n")

    def logs(self, n: int = 40) -> list[str]:
        lines: list[str] = []
        for f in ("itachi-capoeira.log", "itachi-gui.log"):
            try:
                lines += Path(LOG_DIR / f).read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
            except OSError:
                pass
        return sorted(lines, key=lambda s: s[:10])[-n:]


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _local(self) -> bool:
            host = self.headers.get("Host", "").rsplit(":", 1)[0]
            origin = self.headers.get("Origin")
            ok_origin = origin is None or any(origin.split("://", 1)[-1].rsplit(":", 1)[0] == h for h in LOCAL_HOSTS)
            return host in LOCAL_HOSTS and ok_origin     # barra DNS-rebinding / CSRF de outros sites

        def _send(self, obj, code=200, ctype="application/json; charset=utf-8"):
            body = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _redirect(self, to: str):
            self.send_response(302)
            self.send_header("Location", to)
            self.send_header("Content-Length", "0")
            self.end_headers()

        @staticmethod
        def _static_file(path: str) -> tuple[Path, str] | None:
            """Só imagens, sem subpastas: /mobile/<arq> vem de mobile/, /<arq> vem de gui/."""
            folder, name = (MOBILE_DIR, path[len("/mobile/"):]) if path.startswith("/mobile/") else (GUI_DIR, path[1:])
            name = unquote(name)
            f = folder / name
            if not name or "/" in name or "\\" in name or name.startswith("."):
                return None
            ctype = IMAGE_TYPES.get(f.suffix.lower())
            return (f, ctype) if ctype and f.is_file() else None

        def do_GET(self):
            if not self._local():
                return self._send({"error": "acesso negado"}, 403)
            path = self.path.split("?")[0]
            try:
                if path in ("/", "/index.html"):
                    return self._send(HTML.read_bytes(), ctype="text/html; charset=utf-8")
                if path == "/mobile":
                    return self._redirect("/mobile/")
                if path in ("/mobile/", "/mobile/index.html", "/mobile/Itachi.html"):
                    return self._send(MOBILE_HTML.read_bytes(), ctype="text/html; charset=utf-8")
                if path == "/api/mobile/ping":
                    return self._send(app.mobile_info())
                static = self._static_file(path)
                if static:
                    return self._send(static[0].read_bytes(), ctype=static[1])
                if path == "/api/status":
                    return self._send(app.status())
                if path == "/api/logs":
                    return self._send({"lines": app.logs()})
                if path == "/api/system":
                    return self._send(app.system_info())
                if path == "/api/script":
                    return self._send({"text": app.script()})
            except OSError as e:
                return self._send({"error": str(e)}, 500)
            self._send({"error": "não encontrado"}, 404)

        def do_POST(self):
            if not self._local():
                return self._send({"error": "acesso negado"}, 403)
            try:
                n = int(self.headers.get("Content-Length", 0))
                if n > MAX_AUDIO_BYTES:
                    return self._send({"error": "corpo grande demais"}, 413)
                body = self.rfile.read(n)
                if self.path.split("?")[0] == "/api/mobile/voice":
                    return self._send(app.mobile_voice(body))
                d = json.loads(body or b"{}")
                p = self.path
                if p == "/api/ask":
                    text = str(d.get("text", "")).strip()
                    if not text:
                        raise ValueError("texto vazio")
                    return self._send({"reply": app.a.ask(text, speak=bool(d.get("speak")))})
                if p == "/api/trigger" and d.get("name") in TRIGGERS:
                    return self._send({"via": app.trigger(d["name"])})
                if p == "/api/models":
                    app.model_action(str(d.get("action")), d.get("id"))
                    return self._send({"ok": True})
                if p == "/api/vision":
                    return self._send(app.vision(str(d.get("question", "")), d.get("image")))
                if p == "/api/system":
                    return self._send(app.system_action(str(d.get("action", "")), d))
                if p == "/api/memory/clear":
                    app.a.memory.clear()
                    return self._send({"ok": True})
                self._send({"error": "não encontrado"}, 404)
            except Busy as e:
                self._send({"error": str(e)}, 409)
            except OllamaError as e:
                self._send({"error": str(e)}, 502)
            except (ValueError, KeyError) as e:
                self._send({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                log.exception("Erro na API")
                self._send({"error": str(e)}, 500)
    return H


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="itachi-capoeira-gui", description="Interface gráfica local do Itachi Capoeira")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--usb", action="store_true", help="conecta o celular Android por cabo e abre o assistente de mesa nele")
    args = ap.parse_args(argv)
    cfg = load()
    root = logging.getLogger("itachi_capoeira")
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] [%(name)s] %(message)s", "%H:%M:%S")
    for h in (logging.FileHandler(LOG_DIR / "itachi-gui.log", encoding="utf-8"), logging.StreamHandler()):
        h.setFormatter(fmt)
        root.addHandler(h)
    root.propagate = False
    if not HTML.exists():
        print("Arquivo não encontrado:", HTML)
        return 1
    try:
        app = App(cfg)
        srv = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(app))
    except OSError as e:
        print(f"Não consegui abrir a porta {args.port}: {e}. Use --port OUTRA.")
        return 1
    url = f"http://127.0.0.1:{args.port}/"
    log.info("🈶 Itachi Capoeira em %s (Ctrl+C para sair)", url)
    try:                     # Wayland/GNOME: registra F7–F10 no desktop (o daemon só liga com 'start')
        from . import shortcuts
        msg = shortcuts.ensure(cfg)
        if msg:
            log.info("⌨️  %s", msg.splitlines()[0])
    except Exception as e:  # noqa: BLE001
        log.warning("Atalhos do desktop: %s", e)
    if not app.a.llm.cloud:        # Ollama local em segundo plano, SEM abrir a interface/janela do Ollama
        threading.Thread(target=lambda: start_ollama(app.a.llm, wait=20), daemon=True, name="ollama-headless").start()
    if args.usb:
        ok, msg = usb_connect(args.port)
        log.info("%s %s", "📱" if ok else "⚠️ ", msg)
    else:
        log.info("📱 Celular por USB: rode com --usb (ou: adb reverse tcp:%d tcp:%d) e abra http://localhost:%d/mobile/", args.port, args.port, args.port)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
