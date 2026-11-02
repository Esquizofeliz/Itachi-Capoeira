"""Síntese de voz: Kokoro (ONNX, local, pt-BR) com fallback para a voz nativa de cada sistema."""
from __future__ import annotations

import logging
import os
import ctypes.util
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable

import numpy as np

from . import audio
from .config import MODELS_DIR, Config

log = logging.getLogger("itachi_capoeira.tts")

KOKORO_DIR = MODELS_DIR / "kokoro"
KOKORO_FILES = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}
KOKORO_MIN_BYTES = {"kokoro-v1.0.onnx": 100_000_000, "voices-v1.0.bin": 5_000_000}


def _system_espeak_config(EspeakConfig):
    """Use the real system eSpeak NG on Linux instead of the wheel's build-time paths.

    Some espeakng-loader wheels bundle a library compiled with an absolute data
    directory from their CI runner. Supplying both paths explicitly avoids that
    invalid path and also avoids depending on the project's installation depth.
    """
    if not sys.platform.startswith("linux"):
        return None

    library_candidates = (
        Path("/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1"),
        Path("/lib/x86_64-linux-gnu/libespeak-ng.so.1"),
        Path("/usr/lib/aarch64-linux-gnu/libespeak-ng.so.1"),
        Path("/lib/aarch64-linux-gnu/libespeak-ng.so.1"),
        Path("/usr/lib64/libespeak-ng.so.1"),
        Path("/usr/lib/libespeak-ng.so.1"),
        Path("/usr/local/lib/libespeak-ng.so.1"),
    )
    lib_path = next((str(p) for p in library_candidates if p.is_file()), None)
    if not lib_path:
        lib_path = ctypes.util.find_library("espeak-ng")

    data_candidates = (
        Path("/usr/lib/x86_64-linux-gnu/espeak-ng-data"),
        Path("/usr/lib/aarch64-linux-gnu/espeak-ng-data"),
        Path("/usr/lib64/espeak-ng-data"),
        Path("/usr/lib/espeak-ng-data"),
        Path("/usr/share/espeak-ng-data"),
    )
    data_path = next((p for p in data_candidates if all((p / name).is_file()
                      for name in ("phontab", "phondata", "phonindex"))), None)

    # On Debian/Ubuntu, --version reports the exact compiled-in data directory.
    exe = shutil.which("espeak-ng")
    if exe:
        try:
            result = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=5, check=False)
            match = re.search(r"Data at:\s*(.+?)\s*$", (result.stdout or "") + "\n" + (result.stderr or ""), re.M)
            if match:
                reported = Path(match.group(1).strip())
                if all((reported / name).is_file() for name in ("phontab", "phondata", "phonindex")):
                    data_path = reported
        except (OSError, subprocess.SubprocessError):
            pass

    if not lib_path or not data_path:
        log.warning("eSpeak NG do sistema não encontrado com biblioteca e dados completos; usando configuração padrão do Kokoro.")
        return None

    return EspeakConfig(lib_path=lib_path, data_path=str(data_path))


# ---------------------------------------------------------------------- texto
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\u200d\ufe0f]+")


def clean_for_speech(text: str, max_chars: int = 900) -> str:
    """Remove markdown/emoji/código para que a fala soe natural e limita o tamanho."""
    t = text or ""
    t = re.sub(r"```.*?```", " (trecho de código omitido) ", t, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", " link ", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*•]\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*\d+[.)]\s+", "", t, flags=re.M)
    t = re.sub(r"[*_~>|]+", " ", t)
    t = _EMOJI.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_chars:
        cut = t[:max_chars]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        t = cut[: end + 1] if end > max_chars * 0.5 else cut.rsplit(" ", 1)[0] + "…"
    return t


def split_sentences(text: str, max_len: int = 300) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    out: list[str] = []
    for p in parts:
        while len(p) > max_len:
            cut = p.rfind(",", 0, max_len)
            cut = cut if cut > 40 else p.rfind(" ", 0, max_len)
            cut = cut if cut > 0 else max_len
            out.append(p[: cut + 1].strip())
            p = p[cut + 1:].strip()
        if p:
            out.append(p)
    return out


# ---------------------------------------------------------------------- download dos modelos Kokoro
def kokoro_paths() -> tuple[Path, Path]:
    return KOKORO_DIR / "kokoro-v1.0.onnx", KOKORO_DIR / "voices-v1.0.bin"


def kokoro_ready() -> bool:
    for name, minimum in KOKORO_MIN_BYTES.items():
        p = KOKORO_DIR / name
        if not p.exists() or p.stat().st_size < minimum:
            return False
    return True


def download_kokoro(progress: Callable[[str, int, int], None] | None = None) -> None:
    """Baixa os arquivos do Kokoro (releases oficiais do kokoro-onnx no GitHub)."""
    KOKORO_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in KOKORO_FILES.items():
        dest = KOKORO_DIR / name
        if dest.exists() and dest.stat().st_size >= KOKORO_MIN_BYTES[name]:
            continue
        part = dest.with_suffix(dest.suffix + ".part")
        req = urllib.request.Request(url, headers={"User-Agent": "itachi-capoeira"})
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(name, done, total)
        if part.stat().st_size < KOKORO_MIN_BYTES[name]:
            part.unlink(missing_ok=True)
            raise RuntimeError(f"Download incompleto de {name}")
        os.replace(part, dest)


# ---------------------------------------------------------------------- engines
class KokoroEngine:
    name = "kokoro"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._k = None
        self._lock = threading.Lock()
        self.failed = False          # travou/estourou o tempo nesta sessão: o Speaker passa a usar a voz do sistema

    def preload(self) -> None:
        """Carrega o modelo em segundo plano ao ligar o daemon, para a primeira fala não esperar."""
        t0 = time.time()
        try:
            with self._lock:
                self._load()
                self._k.create("ok", voice=self.cfg.VOICE, speed=float(self.cfg.KOKORO_SPEED), lang=self.cfg.KOKORO_LANG)
            log.info("🔊 Kokoro pronto em %.1fs", time.time() - t0)
        except Exception as e:  # noqa: BLE001
            self.failed = True
            log.warning("Kokoro não carregou (%s); usarei a voz do sistema.", e)

    def available(self) -> bool:
        if self.failed or not kokoro_ready():
            return False
        try:
            import kokoro_onnx  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False

    def _load(self):
        if self._k is None:
            from kokoro_onnx import EspeakConfig, Kokoro
            model, voices = kokoro_paths()
            espeak_config = _system_espeak_config(EspeakConfig)
            if espeak_config is not None:
                log.info("eSpeak NG do sistema: biblioteca=%s | dados=%s",
                         espeak_config.lib_path, espeak_config.data_path)
                self._k = Kokoro(str(model), str(voices), espeak_config=espeak_config)
            else:
                self._k = Kokoro(str(model), str(voices))
        return self._k

    def synth(self, text: str):
        with self._lock:
            k = self._load()
            samples, sr = k.create(text, voice=self.cfg.VOICE, speed=float(self.cfg.KOKORO_SPEED),
                                   lang=self.cfg.KOKORO_LANG)
        return np.asarray(samples, dtype=np.float32), int(sr)

    def speak(self, text: str, stop: threading.Event) -> bool:
        # Sintetiza a próxima frase enquanto a anterior toca (reduz a latência percebida).
        sentences = split_sentences(text)
        if not sentences:
            return True
        result: dict = {}

        def worker(i: int, s: str) -> None:
            try:
                result[i] = self.synth(s)
            except Exception as e:  # noqa: BLE001
                result[i] = e

        threads: dict[int, threading.Thread] = {}

        def launch(i: int) -> None:
            if i < len(sentences) and i not in threads:
                th = threading.Thread(target=worker, args=(i, sentences[i]), daemon=True)
                threads[i] = th
                th.start()

        launch(0)
        for i in range(len(sentences)):
            if stop.is_set():
                return False
            t0 = time.time()
            limit = max(5.0, float(getattr(self.cfg, "TTS_SYNTH_TIMEOUT", 45)))
            while threads[i].is_alive():
                threads[i].join(0.2)
                if stop.is_set():
                    return False
                if time.time() - t0 > limit:
                    self.failed = True
                    raise TimeoutError(f"Kokoro não sintetizou a frase {i + 1}/{len(sentences)} em {limit:.0f}s")
            log.info("🔊 Frase %d/%d pronta em %.1fs", i + 1, len(sentences), time.time() - t0)
            launch(i + 1)
            out = result.pop(i)
            if isinstance(out, Exception):
                raise out
            samples, sr = out
            if not audio.play_samples(samples, sr, stop, device=getattr(self.cfg, "AUDIO_OUT_DEVICE", ""),
                                      player=getattr(self.cfg, "AUDIO_PLAYER", "auto")):
                return False
        return True


class SystemEngine:
    """Voz nativa: SAPI (Windows), `say` (macOS), espeak-ng/spd-say (Linux). O texto vai por variável de ambiente
    — nunca interpolado em comando — para evitar injeção."""
    name = "system"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._proc: subprocess.Popen | None = None

    def _command(self) -> list[str] | None:
        if sys.platform == "win32":
            script = (
                "Add-Type -AssemblyName System.Speech;"
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                "try { $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::NotSet, "
                "[System.Speech.Synthesis.VoiceAge]::NotSet, 0, [System.Globalization.CultureInfo]::GetCultureInfo('pt-BR')) } catch {};"
                "$s.Speak($env:ITACHI_CAPOEIRA_TEXT)"
            )
            return ["powershell", "-NoProfile", "-Command", script]
        if sys.platform == "darwin":
            return ["sh", "-c", 'say -v Luciana "$ITACHI_CAPOEIRA_TEXT" 2>/dev/null || say "$ITACHI_CAPOEIRA_TEXT"']
        if shutil.which("espeak-ng"):
            return ["sh", "-c", 'espeak-ng -v pt-br -s 165 "$ITACHI_CAPOEIRA_TEXT"']
        if shutil.which("espeak"):
            return ["sh", "-c", 'espeak -v pt-br -s 165 "$ITACHI_CAPOEIRA_TEXT"']
        if shutil.which("spd-say"):
            return ["sh", "-c", 'spd-say -w -l pt-BR "$ITACHI_CAPOEIRA_TEXT"']
        return None

    def available(self) -> bool:
        return self._command() is not None

    def speak(self, text: str, stop: threading.Event) -> bool:
        cmd = self._command()
        if not cmd:
            return False
        env = dict(os.environ, ITACHI_CAPOEIRA_TEXT=text)
        self._proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        while self._proc.poll() is None:
            if stop.is_set():
                self._proc.terminate()
                return False
            stop.wait(0.05)
        if self._proc.returncode != 0:
            err = (self._proc.stderr.read() or b"").decode("utf-8", "replace").strip() if self._proc.stderr else ""
            log.warning("Voz do sistema falhou (código %s)%s", self._proc.returncode, f": {err[:200]}" if err else "")
        return self._proc.returncode == 0

    def terminate(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


class Speaker:
    """Escolhe o motor de voz disponível e fala com suporte a interrupção."""

    def __init__(self, cfg: Config, stop_event: threading.Event | None = None):
        self.cfg = cfg
        self.stop = stop_event or threading.Event()
        self.kokoro = KokoroEngine(cfg)
        self.system = SystemEngine(cfg)
        self._engine_name: str | None = None

    def engine(self):
        pref = str(self.cfg.TTS_ENGINE).lower()
        if pref == "off":
            return None
        if pref in ("auto", "kokoro") and self.kokoro.available():
            return self.kokoro
        if pref in ("auto", "system", "kokoro") and self.system.available():
            if pref == "kokoro":
                log.warning("Kokoro indisponível; usando a voz do sistema.")
            return self.system
        return None

    def speak(self, text: str) -> bool:
        clean = clean_for_speech(text, int(self.cfg.TTS_MAX_CHARS))
        if not clean:
            return False
        eng = self.engine()
        if eng is None:
            log.warning("Nenhum motor de voz disponível — rode 'itachi-capoeira setup' ou 'itachi-capoeira doctor'.")
            return False
        self._engine_name = eng.name
        log.info("🔊 Falando (%s, %d caracteres)...", eng.name, len(clean))
        try:
            ok = eng.speak(clean, self.stop)
            if not ok and not self.stop.is_set():
                log.warning("A fala não foi reproduzida (motor %s). Veja os avisos acima ou rode: itachi-capoeira say \"teste\"",
                            eng.name)
            return ok
        except Exception as e:  # noqa: BLE001
            log.error("Falha no motor %s: %s", eng.name, e)
            if eng is self.kokoro and self.system.available():
                log.info("Tentando a voz do sistema como alternativa.")
                return self.system.speak(clean, self.stop)
            if eng is self.kokoro:
                log.warning("Sem voz de reserva. No Linux: sudo apt install espeak-ng")
            return False

    def interrupt(self) -> None:
        self.stop.set()
        audio.stop_playback()
        self.system.terminate()
