"""Gravação (com detecção de fala) e reprodução de áudio, multiplataforma."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np

from .config import TMP_DIR

log = logging.getLogger("itachi_capoeira.audio")

SAMPLE_RATE = 16000  # taxa usada pelo Whisper


class AudioError(RuntimeError):
    pass


_sd = None
_sd_error: str | None = None


def sounddevice_module():
    """Importa sounddevice sob demanda; devolve None se PortAudio não estiver disponível."""
    global _sd, _sd_error
    if _sd is None and _sd_error is None:
        try:
            import sounddevice as sd  # noqa: WPS433
            _sd = sd
        except (ImportError, OSError) as e:
            _sd_error = str(e)
    return _sd


def sounddevice_error() -> str | None:
    sounddevice_module()
    return _sd_error


# ---------------------------------------------------------------------- VAD
class VAD:
    """Detector de fala por energia (RMS) com piso de ruído adaptativo.

    feed(frame) devolve um np.ndarray quando uma frase termina, senão None.
    """

    def __init__(self, sr: int = SAMPLE_RATE, frame_ms: int = 30, min_rms: float = 0.004, factor: float = 2.5,
                 silence_s: float = 1.2, start_frames: int = 3, max_s: float = 30.0, preroll_s: float = 0.35):
        self.sr = sr
        self.frame_len = int(sr * frame_ms / 1000)
        self.frame_s = frame_ms / 1000
        self.min_rms = min_rms
        self.factor = factor
        self.silence_frames = max(1, int(silence_s / self.frame_s))
        self.start_frames = start_frames
        self.max_frames = int(max_s / self.frame_s)
        self.preroll: deque = deque(maxlen=max(1, int(preroll_s / self.frame_s)))
        self.reset()

    def reset(self) -> None:
        self.noise = self.min_rms / self.factor
        self.in_speech = False
        self._loud = 0
        self._quiet = 0
        self._buf: list = []
        self.preroll.clear()

    @property
    def threshold(self) -> float:
        return max(self.min_rms, self.noise * self.factor)

    def feed(self, frame: np.ndarray):
        rms = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64)))) if len(frame) else 0.0
        loud = rms > self.threshold
        if not self.in_speech:
            if not loud:
                self.noise = 0.95 * self.noise + 0.05 * rms  # aprende o ruído de fundo
                self._loud = 0
                self.preroll.append(frame)
                return None
            self._loud += 1
            self.preroll.append(frame)
            if self._loud >= self.start_frames:
                self.in_speech = True
                self._buf = list(self.preroll)
                self._quiet = 0
            return None
        self._buf.append(frame)
        self._quiet = 0 if loud else self._quiet + 1
        if self._quiet >= self.silence_frames or len(self._buf) >= self.max_frames:
            utter = np.concatenate(self._buf)
            self.in_speech = False
            self._buf = []
            self._loud = self._quiet = 0
            self.preroll.clear()
            return utter
        return None

    def flush(self):
        """Devolve o que já foi captado (se estava falando) — usado ao parar manualmente."""
        if self.in_speech and self._buf:
            utter = np.concatenate(self._buf)
            self.in_speech = False
            self._buf = []
            return utter
        return None


def resample(x: np.ndarray, sr_in: int, sr_out: int = SAMPLE_RATE) -> np.ndarray:
    if sr_in == sr_out or len(x) == 0:
        return x.astype(np.float32, copy=False)
    n_out = int(round(len(x) * sr_out / sr_in))
    idx = np.linspace(0, len(x) - 1, n_out)
    return np.interp(idx, np.arange(len(x)), x).astype(np.float32)


# ---------------------------------------------------------------------- microfone
def _device_arg(device):
    if device in (None, ""):
        return None
    s = str(device)
    return int(s) if s.isdigit() else s


class MicStream:
    """Abre o microfone em 16 kHz (ou na taxa nativa, reamostrando) e entrega frames de 30 ms."""

    def __init__(self, device=None, frame_ms: int = 30):
        sd = sounddevice_module()
        if sd is None:
            raise AudioError(
                "Biblioteca de áudio indisponível (" + str(sounddevice_error()) + "). "
                "No Linux instale: sudo apt install libportaudio2")
        self.sd = sd
        self.frame_ms = frame_ms
        dev = _device_arg(device)
        try:
            self.sr_in = SAMPLE_RATE
            self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=dev,
                                         blocksize=int(SAMPLE_RATE * frame_ms / 1000))
        except Exception:
            try:
                info = sd.query_devices(dev, "input")
                self.sr_in = int(info["default_samplerate"])
                self.stream = sd.InputStream(samplerate=self.sr_in, channels=1, dtype="float32", device=dev,
                                             blocksize=int(self.sr_in * frame_ms / 1000))
            except Exception as e:
                raise AudioError(f"Não consegui abrir o microfone: {e}") from e
        self._block = int(self.sr_in * frame_ms / 1000)
        try:
            info = sd.query_devices(dev, "input")
            log.info("🎙️ Microfone: %s | entrada=%s | taxa=%s Hz", info.get("name", "desconhecido"),
                     "padrão" if dev is None else dev, self.sr_in)
        except Exception as e:  # noqa: BLE001
            log.warning("Não consegui identificar o microfone selecionado: %s", e)

    def __enter__(self):
        self.stream.start()
        return self

    def __exit__(self, *exc):
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:  # noqa: BLE001
            pass

    def read(self) -> np.ndarray:
        data, _overflow = self.stream.read(self._block)
        frame = data[:, 0] if data.ndim > 1 else data
        return resample(frame, self.sr_in) if self.sr_in != SAMPLE_RATE else frame


def record_command(device=None, max_seconds: float = 30, silence_seconds: float = 1.4,
                   no_speech_timeout: float = 7.0, stop_event: threading.Event | None = None,
                   interrupt_event: threading.Event | None = None):
    """Grava uma frase. Termina no silêncio, no limite de tempo ou quando stop_event for acionado.

    Devolve np.ndarray float32 (16 kHz) ou None se ninguém falou.
    """
    vad = VAD(silence_s=silence_seconds, max_s=max_seconds)
    start = time.time()
    peak_rms = 0.0
    with MicStream(device) as mic:
        while True:
            if interrupt_event is not None and interrupt_event.is_set():
                log.info("Gravação interrompida antes da transcrição.")
                return None
            frame = mic.read()
            rms = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64)))) if len(frame) else 0.0
            peak_rms = max(peak_rms, rms)
            utter = vad.feed(frame)
            if utter is not None:
                log.info("Áudio capturado: %.1fs | pico RMS=%.4f", len(utter) / SAMPLE_RATE, peak_rms)
                return utter
            if stop_event is not None and stop_event.is_set():
                utter = vad.flush()
                if utter is not None:
                    log.info("Gravação finalizada manualmente: %.1fs | pico RMS=%.4f",
                             len(utter) / SAMPLE_RATE, peak_rms)
                else:
                    log.warning("Gravação encerrada, mas nenhuma fala foi detectada (pico RMS=%.4f).", peak_rms)
                return utter
            if not vad.in_speech and time.time() - start > no_speech_timeout:
                log.warning("Nenhuma fala detectada em %.1fs (pico RMS=%.4f; limiar VAD=%.4f). "
                            "Verifique a entrada do microfone e o volume.",
                            no_speech_timeout, peak_rms, vad.threshold)
                return None
            if time.time() - start > max_seconds + no_speech_timeout:
                utter = vad.flush()
                if utter is None:
                    log.warning("Tempo máximo atingido sem fala detectável (pico RMS=%.4f).", peak_rms)
                return utter


# ---------------------------------------------------------------------- reprodução
_proc_lock = threading.Lock()
_proc: subprocess.Popen | None = None


def _write_wav(samples: np.ndarray, sr: int) -> Path:
    import soundfile as sf
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    path = TMP_DIR / f"play-{os.getpid()}-{int(time.time() * 1000)}.wav"
    sf.write(str(path), np.asarray(samples, dtype=np.float32), sr)
    return path


def _file_player_cmd(path: Path) -> list[str] | None:
    if sys.platform == "darwin":
        return ["afplay", str(path)] if shutil.which("afplay") else None
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-Command",
                "(New-Object System.Media.SoundPlayer $env:ITACHI_CAPOEIRA_WAV).PlaySync()"]
    for exe, args in (("paplay", []), ("aplay", ["-q"]), ("pw-play", []),
                      ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]), ("play", ["-q"])):
        if shutil.which(exe):
            return [exe, *args, str(path)]
    return None


def _play_with_file_player(samples: np.ndarray, sr: int, stop: threading.Event | None) -> bool:
    global _proc
    path = _write_wav(samples, sr)
    try:
        cmd = _file_player_cmd(path)
        if not cmd:
            log.warning("Nenhuma saída de áudio disponível (sounddevice e players do sistema falharam).")
            return False
        env = dict(os.environ, ITACHI_CAPOEIRA_WAV=str(path))
        with _proc_lock:
            _proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
            proc = _proc
        while proc.poll() is None:
            if stop is not None and stop.is_set():
                proc.terminate()
                return False
            time.sleep(0.05)
        if proc.returncode != 0:
            err = (proc.stderr.read() or b"").decode("utf-8", "replace").strip() if proc.stderr else ""
            log.warning("Player '%s' falhou (código %s)%s", cmd[0], proc.returncode, f": {err[:200]}" if err else "")
        return proc.returncode == 0
    finally:
        try:
            path.unlink()
        except OSError:
            pass


_out_logged = False


def _log_output_device(sd, device) -> None:
    """Registra uma vez em qual saída o som vai (a causa nº 1 de 'responde mas não fala')."""
    global _out_logged
    if _out_logged:
        return
    _out_logged = True
    try:
        info = sd.query_devices(_device_arg(device), "output")
        log.info("🔈 Saída de áudio: %s (%s)", info["name"], sd.query_hostapis(info["hostapi"])["name"])
    except Exception as e:  # noqa: BLE001
        log.warning("Não consegui identificar a saída de áudio padrão: %s", e)


def play_samples(samples: np.ndarray, sr: int, stop: threading.Event | None = None,
                 device=None, player: str = "auto") -> bool:
    """Toca amostras float32. Devolve False se interrompido ou sem saída de áudio.

    player: 'auto' (sounddevice, com player do sistema de reserva) | 'sounddevice' | 'system'."""
    samples = np.asarray(samples, dtype=np.float32)
    if samples.size == 0:
        return True
    player = str(player or "auto").lower()
    sd = sounddevice_module() if player != "system" else None
    if sd is not None:
        try:
            _log_output_device(sd, device)
            sd.play(samples, sr, device=_device_arg(device))
            stream = sd.get_stream()
            deadline = time.time() + len(samples) / sr + 2.0
            while stream.active and time.time() < deadline:
                if stop is not None and stop.is_set():
                    sd.stop()
                    return False
                time.sleep(0.03)
            sd.stop()
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("sounddevice falhou na reprodução (%s); tentando player do sistema", e)
            if player == "sounddevice":
                return False
    elif player == "sounddevice":
        log.warning("sounddevice indisponível (%s).", sounddevice_error())
        return False
    return _play_with_file_player(samples, sr, stop)


def stop_playback() -> None:
    sd = sounddevice_module()
    if sd is not None:
        try:
            sd.stop()
        except Exception:  # noqa: BLE001
            pass
    with _proc_lock:
        if _proc is not None and _proc.poll() is None:
            try:
                _proc.terminate()
            except OSError:
                pass


def beep(freq: float = 880, ms: int = 120, volume: float = 0.2, sr: int = 22050) -> None:
    """Sinal sonoro curto (início/fim de gravação). Falhas são ignoradas."""
    try:
        t = np.linspace(0, ms / 1000, int(sr * ms / 1000), endpoint=False)
        tone = (np.sin(2 * np.pi * freq * t) * volume).astype(np.float32)
        fade = np.minimum(1, np.minimum(t, t[::-1]) * 60)
        play_samples(tone * fade, sr)
    except Exception as e:  # noqa: BLE001
        log.debug("beep falhou: %s", e)


def list_devices() -> tuple[list[str], list[str]]:
    sd = sounddevice_module()
    ins, outs = [], []
    if sd is None:
        return ins, outs
    try:
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                ins.append(f"{i}: {d['name']}")
            if d.get("max_output_channels", 0) > 0:
                outs.append(f"{i}: {d['name']}")
    except Exception as e:  # noqa: BLE001
        log.debug("query_devices falhou: %s", e)
    return ins, outs
