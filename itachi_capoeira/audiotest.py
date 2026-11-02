"""Teste de voz: mostra em qual etapa a fala falha (síntese, saída de áudio ou reprodução)."""
from __future__ import annotations

import threading
import time

from . import audio
from .tts import Speaker

TEXT = "Teste de voz. Se você está me ouvindo, o áudio está funcionando."


def output_device_name(device=None) -> str | None:
    sd = audio.sounddevice_module()
    if sd is None:
        return None
    try:
        return str(sd.query_devices(audio._device_arg(device), "output")["name"])
    except Exception:  # noqa: BLE001
        return None


def run(cfg, speaker: Speaker | None = None, text: str = TEXT) -> dict:
    """Devolve {ok, engine, synth_s, play_s, device, sounddevice, hint}. Nunca levanta exceção."""
    res = {"ok": False, "engine": None, "synth_s": None, "play_s": None, "device": None,
           "sounddevice": audio.sounddevice_module() is not None, "hint": ""}
    res["device"] = output_device_name(getattr(cfg, "AUDIO_OUT_DEVICE", ""))
    sp = speaker or Speaker(cfg, threading.Event())
    eng = sp.engine()
    if eng is None:
        res["hint"] = "Nenhum motor de voz. Rode 'itachi-capoeira setup' ou, no Linux: sudo apt install espeak-ng"
        return res
    res["engine"] = eng.name
    try:
        if eng is sp.kokoro:                              # mede a síntese sozinha (é onde a voz costuma travar)
            t = time.time()
            sp.kokoro.synth("Olá.")
            res["synth_s"] = round(time.time() - t, 1)
        t = time.time()
        res["ok"] = bool(sp.speak(text))
        res["play_s"] = round(time.time() - t, 1)
    except Exception as e:  # noqa: BLE001
        res["hint"] = f"Erro no motor {eng.name}: {e}"
        return res
    if not res["sounddevice"] and not res["ok"]:
        res["hint"] = "sounddevice indisponível. No Linux: sudo apt install libportaudio2"
    elif not res["ok"]:
        res["hint"] = ("A fala não tocou. Tente AUDIO_PLAYER=\"system\" em config/persona.txt, "
                       "ou TTS_ENGINE=\"system\" (espeak-ng).")
    elif res["synth_s"] and res["synth_s"] > 10:
        res["hint"] = "Kokoro está lento nesta máquina; para resposta imediata use TTS_ENGINE=\"system\"."
    else:
        res["hint"] = "Se você não ouviu nada, a saída padrão está errada: ajuste AUDIO_OUT_DEVICE (python -m sounddevice)."
    return res


def format_report(r: dict) -> str:
    lines = [f"Motor de voz : {r['engine'] or '— nenhum'}",
             f"sounddevice  : {'ok' if r['sounddevice'] else 'INDISPONÍVEL'}",
             f"Saída de áudio: {r['device'] or 'não identificada'}"]
    if r["synth_s"] is not None:
        lines.append(f"Síntese Kokoro: {r['synth_s']} s (1ª frase curta)")
    if r["play_s"] is not None:
        lines.append(f"Fala completa: {r['play_s']} s → {'✅ reproduzida' if r['ok'] else '❌ NÃO reproduzida'}")
    if r["hint"]:
        lines.append("💡 " + r["hint"])
    return "\n".join(lines)
