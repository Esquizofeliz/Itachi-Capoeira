"""Daemon do Itachi Capoeira: atalhos globais, monitor proativo, health check, escuta contínua e gatilhos externos."""
from __future__ import annotations

import logging
import logging.handlers
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from . import __version__
from .assistant import Assistant, Busy
from .config import APP_DIR, LOG_DIR, PIDFILE, RUN_DIR, Config, ensure_dirs
from .health import check_ollama, notify_alerts, proactive_checks, start_ollama
from .hotkeys import HotkeyManager

log = logging.getLogger("itachi_capoeira")

TRIGGERS = ("screen", "voice", "talk", "stop")


# ---------------------------------------------------------------------- logging
def setup_logging(console: bool = True, level: int = logging.INFO) -> None:
    ensure_dirs()
    root = logging.getLogger("itachi_capoeira")
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = logging.Formatter("[%(asctime)s] [%(name)s] %(message)s", "%H:%M:%S")
    fh = logging.handlers.RotatingFileHandler(LOG_DIR / "itachi-capoeira.log", maxBytes=1_000_000, backupCount=5,
                                              encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if console and sys.stdout is not None:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        root.addHandler(ch)
    root.propagate = False


# ---------------------------------------------------------------------- pid
def read_pid() -> int | None:
    try:
        pid = int(PIDFILE.read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    if psutil.pid_exists(pid):
        try:
            cmd = " ".join(psutil.Process(pid).cmdline())
        except psutil.Error:
            return None
        if "itachi_capoeira" in cmd:
            return pid
    return None


def trigger_path(name: str) -> Path:
    return RUN_DIR / f"trigger-{name}"


def send_trigger(name: str) -> None:
    ensure_dirs()
    trigger_path(name).write_text(str(time.time()))


# ---------------------------------------------------------------------- daemon
class Daemon:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.assistant = Assistant(cfg)
        self.stop_event = threading.Event()
        self.hotkeys: HotkeyManager | None = None

    # -- jobs
    def _run_job(self, name: str, fn) -> None:
        def target():
            try:
                fn()
            except Busy:
                log.info("Ocupado — ignorando '%s'.", name)
            except Exception as e:  # noqa: BLE001
                log.error("Falha em '%s': %s", name, e)
                if self.cfg.NOTIFY_ON_ERRORS:
                    try:
                        self.assistant.speaker.speak(f"Tive um problema: {str(e)[:120]}")
                    except Exception:  # noqa: BLE001
                        pass
        threading.Thread(target=target, name=f"job-{name}", daemon=True).start()

    def on_screen(self) -> None:
        self._run_job("screen", lambda: self.assistant.describe_screen())

    def on_voice(self) -> None:
        a = self.assistant
        if a.recording:           # segundo toque = parar de gravar
            a.stop_listening()
            return
        self._run_job("voice", a.dictate)

    def on_talk(self) -> None:
        a = self.assistant
        if a.recording:
            a.stop_listening()
            return
        self._run_job("talk", a.converse)

    def on_stop(self) -> None:
        self.assistant.interrupt()

    def dispatch(self, name: str) -> None:
        {"screen": self.on_screen, "voice": self.on_voice, "talk": self.on_talk, "stop": self.on_stop}[name]()

    # -- loops
    def _watch_triggers(self) -> None:
        while not self.stop_event.wait(0.4):
            for name in TRIGGERS:
                p = trigger_path(name)
                if p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        continue
                    log.info("Gatilho externo: %s", name)
                    self.dispatch(name)

    def _health_loop(self) -> None:
        interval = max(1, int(self.cfg.HEALTH_INTERVAL_MINUTES)) * 60
        while not self.stop_event.wait(interval):
            try:
                check_ollama(self.cfg, self.assistant.llm)
            except Exception as e:  # noqa: BLE001
                log.error("Health check falhou: %s", e)

    def _proactive_loop(self) -> None:
        interval = max(1, int(self.cfg.PROACTIVE_INTERVAL_MINUTES)) * 60
        log.info("👁️  Monitor proativo ativo (a cada %d min)", interval // 60)
        while not self.stop_event.wait(interval):
            try:
                alerts = proactive_checks(self.cfg)
                if alerts:
                    notify_alerts(self.cfg, self.assistant.speaker, alerts)
                else:
                    log.info("Monitor proativo: tudo OK")
            except Exception as e:  # noqa: BLE001
                log.error("Monitor proativo falhou: %s", e)

    # -- ciclo de vida
    def run(self) -> int:
        cfg = self.cfg
        existing = read_pid()
        if existing and existing != os.getpid():
            log.error("O Itachi Capoeira já está rodando (PID %d).", existing)
            return 1
        PIDFILE.write_text(str(os.getpid()))
        log.info("═" * 56)
        log.info("🤖 %s v%s — iniciando (%s)", cfg.NAME, __version__, sys.platform)
        log.info("Modelos: chat=%s | visão=%s | whisper=%s", cfg.CHAT_MODEL, cfg.VISION_MODEL, cfg.WHISPER_MODEL)

        if self.assistant.llm.cloud:
            log.info("☁️  Modo nuvem: %s | conversa=%s | visão=%s", cfg.OLLAMA_URL, cfg.CHAT_MODEL, cfg.VISION_MODEL)
            if not self.assistant.llm.alive():
                log.warning("Nuvem do Ollama inacessível (internet/chave?). Veja: itachi-capoeira cloud status")
        elif not start_ollama(self.assistant.llm, wait=20):
            log.warning("Ollama não está respondendo. Instale/inicie o Ollama; tentarei de novo a cada uso.")

        def _sig(*_a):
            self.stop_event.set()
        signal.signal(signal.SIGINT, _sig)
        signal.signal(signal.SIGTERM, _sig)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, _sig)

        mapping = {cfg.HOTKEY_VOICE: self.on_voice, cfg.HOTKEY_SCREEN: self.on_screen,
                   cfg.HOTKEY_TALK: self.on_talk, cfg.HOTKEY_STOP: self.on_stop}
        self.hotkeys = HotkeyManager(mapping)
        if self.hotkeys.start():
            log.info("⌨️  Atalhos: voz→colar=%s | tela=%s | conversa=%s | parar=%s",
                     cfg.HOTKEY_VOICE, cfg.HOTKEY_SCREEN, cfg.HOTKEY_TALK, cfg.HOTKEY_STOP)
        else:
            msg = None
            try:
                from . import shortcuts
                msg = shortcuts.ensure(cfg)
            except Exception as e:  # noqa: BLE001
                log.warning("Atalhos do desktop falharam: %s", e)
            if msg:
                for line in msg.splitlines():
                    log.info("⌨️  %s", line)
            else:
                log.info("⌨️  Sem atalhos globais. Use: itachi-capoeira trigger screen|voice|talk|stop")

        threading.Thread(target=self._watch_triggers, name="triggers", daemon=True).start()
        threading.Thread(target=self._health_loop, name="health", daemon=True).start()
        if cfg.PROACTIVE_MODE:
            threading.Thread(target=self._proactive_loop, name="proactive", daemon=True).start()
        sp = self.assistant.speaker
        if str(cfg.TTS_ENGINE).lower() in ("auto", "kokoro") and sp.kokoro.available():
            threading.Thread(target=sp.kokoro.preload, name="kokoro-preload", daemon=True).start()
        if cfg.WAKE_WORD_ENABLED:
            from .wake import WakeListener
            WakeListener(self.assistant, self.stop_event).start()

        log.info("✅ %s ONLINE", cfg.NAME)
        log.info("═" * 56)
        try:
            while not self.stop_event.wait(0.5):
                pass
        finally:
            log.info("🛑 Encerrando %s...", cfg.NAME)
            self.assistant.interrupt()
            if self.hotkeys:
                self.hotkeys.stop()
            try:
                PIDFILE.unlink()
            except OSError:
                pass
            log.info("✅ Encerrado")
        return 0


# ---------------------------------------------------------------------- controle (start/stop/status)
def start_background() -> int:
    """Inicia o daemon desacoplado do terminal. Devolve o PID."""
    pid = read_pid()
    if pid:
        print(f"Já está rodando (PID {pid}).")
        return pid
    ensure_dirs()
    out = open(LOG_DIR / "daemon-stdout.log", "ab")
    cmd = [sys.executable, "-m", "itachi_capoeira", "run"]
    env = dict(os.environ, PYTHONPATH=str(APP_DIR) + os.pathsep + os.environ.get("PYTHONPATH", ""),
               PYTHONIOENCODING="utf-8")
    kwargs: dict = {"cwd": str(APP_DIR), "stdout": out, "stderr": out, "stdin": subprocess.DEVNULL, "env": env}
    if sys.platform == "win32":
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        if pyw.exists():
            cmd[0] = str(pyw)
        kwargs["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED | NEW_GROUP | NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)
    for _ in range(40):          # espera até 8 s o PID aparecer
        time.sleep(0.2)
        if read_pid():
            return proc.pid
        if proc.poll() is not None:
            break
    print("O daemon não subiu. Veja:", LOG_DIR / "daemon-stdout.log")
    return 0


def stop_background(timeout: float = 8.0) -> bool:
    pid = read_pid()
    if not pid:
        return False
    try:
        p = psutil.Process(pid)
        if sys.platform == "win32":
            p.terminate()
        else:
            p.send_signal(signal.SIGTERM)
        p.wait(timeout)
    except psutil.TimeoutExpired:
        p.kill()
    except psutil.Error:
        pass
    try:
        PIDFILE.unlink()
    except OSError:
        pass
    return True
