"""Escuta contínua (opcional): VAD por energia + Whisper para detectar a palavra de ativação."""
from __future__ import annotations

import difflib
import logging
import re
import threading
import unicodedata

from . import audio
from .assistant import Assistant, Busy

log = logging.getLogger("itachi_capoeira.wake")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s]", " ", s)


def match_wake_word(text: str, wake_words: list[str], threshold: float = 0.8) -> tuple[bool, str]:
    """Procura uma das palavras (com tolerância a erros do Whisper, ex.: 'jarvi', 'járvis').

    Devolve (achou, resto_da_frase_depois_da_palavra).
    """
    words = _norm(text).split()
    targets = [_norm(w).strip() for w in wake_words if w.strip()]
    for i, w in enumerate(words):
        for t in targets:
            if t and (w == t or difflib.SequenceMatcher(None, w, t).ratio() >= threshold):
                # reconstrói o resto a partir do texto original (mantém acentos/pontuação)
                original = text.split()
                rest = " ".join(original[i + 1:]).lstrip(" ,.:;!?-")
                return True, rest
    return False, ""


class WakeListener(threading.Thread):
    def __init__(self, assistant: Assistant, stop: threading.Event):
        super().__init__(name="wake-listener", daemon=True)
        self.a = assistant
        self.stop_event = stop

    def run(self) -> None:
        cfg = self.a.cfg
        words = cfg.wake_words or [cfg.NAME.lower()]
        log.info("👂 Escuta ativa — diga: %s", ", ".join(words))
        while not self.stop_event.is_set():
            try:
                self._loop(words)
            except audio.AudioError as e:
                log.error("Escuta contínua parou: %s", e)
                return
            except Exception as e:  # noqa: BLE001
                log.error("Erro na escuta contínua: %s — tentando de novo em 5s", e)
                self.stop_event.wait(5)

    def _loop(self, words: list[str]) -> None:
        cfg = self.a.cfg
        vad = audio.VAD(silence_s=0.8, max_s=8.0)
        with audio.MicStream(cfg.MIC_DEVICE) as mic:
            while not self.stop_event.is_set():
                frame = mic.read()
                if self.a.busy:           # enquanto fala/processa, ignora o microfone (evita ouvir a si mesmo)
                    vad.reset()
                    continue
                utter = vad.feed(frame)
                if utter is None or len(utter) < audio.SAMPLE_RATE * 0.4:
                    continue
                text = self.a.stt.transcribe(utter)
                if not text:
                    continue
                found, rest = match_wake_word(text, words)
                log.debug("ouvi: %r (ativação=%s)", text, found)
                if not found:
                    continue
                log.info("✨ Palavra de ativação detectada: %r", text)
                vad.reset()
                try:
                    threading.Thread(target=self._handle, args=(rest,), daemon=True).start()
                except Busy:
                    pass

    def _handle(self, rest: str) -> None:
        try:
            self.a.converse(rest if len(rest) > 2 else None)
        except Busy:
            pass
        except Exception as e:  # noqa: BLE001
            log.error("Falha ao atender: %s", e)
