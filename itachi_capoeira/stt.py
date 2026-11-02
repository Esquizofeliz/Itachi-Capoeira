"""Transcrição de voz com faster-whisper (CPU ou GPU NVIDIA), com fallback automático para CPU."""
from __future__ import annotations

import glob
import logging
import os
import site
import sys
import threading

import numpy as np

from .config import MODELS_DIR, Config

log = logging.getLogger("itachi_capoeira.stt")
WHISPER_DIR = MODELS_DIR / "whisper"

_cuda_preloaded = False


def _preload_cuda_libs() -> None:
    """Faz o faster-whisper achar as libs CUDA instaladas via pip (nvidia-cublas-cu12 / nvidia-cudnn-cu12)."""
    global _cuda_preloaded
    if _cuda_preloaded:
        return
    _cuda_preloaded = True
    roots = list(site.getsitepackages()) + [site.getusersitepackages()]
    try:
        if sys.platform == "win32":
            for root in roots:
                for sub in ("cublas", "cudnn"):
                    d = os.path.join(root, "nvidia", sub, "bin")
                    if os.path.isdir(d):
                        os.add_dll_directory(d)
                        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        elif sys.platform.startswith("linux"):
            import ctypes
            for root in roots:
                for pattern in ("nvidia/cublas/lib/libcublasLt.so*", "nvidia/cublas/lib/libcublas.so*",
                                "nvidia/cudnn/lib/libcudnn.so*"):
                    for lib in sorted(glob.glob(os.path.join(root, pattern))):
                        try:
                            ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
                        except OSError as e:
                            log.debug("Falha ao pré-carregar %s: %s", lib, e)
    except Exception as e:  # noqa: BLE001
        log.debug("preload CUDA: %s", e)


def cuda_available() -> bool:
    try:
        _preload_cuda_libs()
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001
        return False


class Transcriber:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._model = None
        self._device = None
        self._lock = threading.Lock()

    @property
    def device(self) -> str | None:
        return self._device

    def _build(self, device: str):
        from faster_whisper import WhisperModel
        compute = str(self.cfg.WHISPER_COMPUTE)
        if compute == "auto":
            compute = "float16" if device == "cuda" else "int8"
        WHISPER_DIR.mkdir(parents=True, exist_ok=True)
        log.info("Carregando Whisper '%s' em %s (%s)...", self.cfg.WHISPER_MODEL, device, compute)
        return WhisperModel(str(self.cfg.WHISPER_MODEL), device=device, compute_type=compute,
                            download_root=str(WHISPER_DIR))

    def load(self):
        with self._lock:
            if self._model is not None:
                return self._model
            want = str(self.cfg.WHISPER_DEVICE).lower()
            device = "cuda" if (want in ("auto", "cuda") and cuda_available()) else "cpu"
            try:
                self._model = self._build(device)
                self._device = device
            except Exception as e:  # noqa: BLE001
                if device == "cuda":
                    log.warning("Whisper na GPU falhou (%s); usando CPU.", e)
                    self._model = self._build("cpu")
                    self._device = "cpu"
                else:
                    raise
            return self._model

    def _run(self, audio: np.ndarray, language: str | None) -> str:
        model = self.load()
        segments, _info = model.transcribe(audio.astype(np.float32), language=language, vad_filter=True,
                                           beam_size=5, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip()

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> str:
        language = language or self.cfg.language_short
        if audio is None or len(audio) < 1600:   # < 0,1 s
            return ""
        try:
            return self._run(audio, language)
        except Exception as e:  # noqa: BLE001
            if self._device == "cuda":
                log.warning("Erro do Whisper na GPU (%s); recarregando na CPU.", e)
                with self._lock:
                    self._model = self._build("cpu")
                    self._device = "cpu"
                return self._run(audio, language)
            raise

    def preload(self) -> None:
        """Baixa/abre o modelo agora (usado pelo 'setup')."""
        self.load()
