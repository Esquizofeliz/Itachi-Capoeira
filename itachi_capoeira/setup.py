"""itachi-capoeira setup — detecta o hardware, escolhe os modelos e baixa tudo (Ollama, Kokoro, Whisper)."""
from __future__ import annotations

import sys
import time

from . import hardware, tts
from .config import LOCAL_FILE, Config, write_local
from .health import start_ollama
from .llm import Ollama, OllamaError


def _bar(label: str, done: int, total: int, state: dict) -> None:
    now = time.time()
    if now - state.get("t", 0) < 0.5 and done != total:
        return
    state["t"] = now
    if total:
        pct = done * 100 // total
        sys.stdout.write(f"\r   {label[:34]:<34} {pct:3d}%  {done / 1024 ** 2:8.0f}/{total / 1024 ** 2:.0f} MB")
    else:
        sys.stdout.write(f"\r   {label[:60]:<60}")
    sys.stdout.flush()


def run(cfg: Config, tier_key: str | None = None, skip_models: bool = False, skip_tts: bool = False,
        skip_whisper: bool = False) -> int:
    problems = 0
    print("\n⚙️  Itachi Capoeira setup\n")

    # 1) Hardware → nível
    gpu = hardware.detect_gpu()
    ram = hardware.ram_total_gb()
    print("🖥️  Hardware:", hardware.describe(gpu, ram))
    if gpu.note:
        print("   ", gpu.note)
    llm = Ollama.from_config(cfg)
    cloud_mode = llm.cloud
    if cloud_mode:
        print("☁️  Modo nuvem ativo: modelos de conversa/visão ficam como estão (veja: itachi-capoeira cloud status).")
        skip_models = True
    tier = hardware.TIERS[tier_key] if tier_key else hardware.pick_tier(gpu, ram)
    print(f"🎚️  Nível escolhido: {tier.label}  →  {tier.chat_model}  (VRAM mínima ≈ {tier.min_vram_gb:g} GB)")
    if tier.key == "cpu":
        print("   ⚠️  Sem GPU compatível: vai funcionar, porém bem mais devagar (respostas em dezenas de segundos).")
    if ram < 8 and tier.key in ("cpu", "s"):
        print(f"   ⚠️  Só {ram:.1f} GB de RAM: pode faltar memória para os modelos.")
    chosen = {"WHISPER_MODEL": tier.whisper_model, "WHISPER_DEVICE": tier.whisper_device}
    if not cloud_mode:
        chosen.update({"CHAT_MODEL": tier.chat_model, "VISION_MODEL": tier.vision_model})
    write_local(chosen)
    print(f"💾 Gravado em {LOCAL_FILE.name}\n")
    cfg._v.update(chosen)

    # 2) Modelos do Ollama
    if skip_models:
        print("⏭️  Download de modelos do Ollama ignorado" + (" (modo nuvem)." if cloud_mode else " (--skip-models)."))
    else:
        print("🤖 Ollama...")
        if not start_ollama(llm, wait=30):
            print("   ❌ O Ollama não está acessível. Instale em https://ollama.com/download, abra-o e rode de novo:")
            print("      itachi-capoeira setup")
            problems += 1
        else:
            for model in dict.fromkeys([tier.chat_model, tier.vision_model]):
                if llm.has_model(model):
                    print(f"   ✅ {model} já instalado")
                    continue
                print(f"   ⬇️  Baixando {model} (pode levar vários minutos)...")
                state: dict = {}
                try:
                    llm.pull(model, lambda s, d, t: _bar(s, d, t, state))
                    print(f"\n   ✅ {model} pronto")
                except OllamaError as e:
                    print(f"\n   ❌ Falha ao baixar {model}: {e}")
                    problems += 1

    # 3) Kokoro TTS
    if skip_tts:
        print("⏭️  Kokoro ignorado (--skip-tts).")
    else:
        print("🔊 Kokoro TTS...")
        if tts.kokoro_ready():
            print("   ✅ modelos já baixados")
        else:
            state = {}
            try:
                tts.download_kokoro(lambda n, d, t: _bar(n, d, t, state))
                print("\n   ✅ Kokoro baixado")
            except Exception as e:  # noqa: BLE001
                print(f"\n   ❌ Falha no download do Kokoro: {e}")
                print("      (o Itachi Capoeira usará a voz do sistema até você rodar 'itachi-capoeira setup' de novo)")
                problems += 1

    # 4) Whisper
    if skip_whisper:
        print("⏭️  Whisper ignorado (--skip-whisper).")
    else:
        print(f"🎤 Whisper '{tier.whisper_model}'...")
        try:
            from .stt import Transcriber
            t = Transcriber(cfg)
            t.preload()
            print(f"   ✅ pronto ({t.device})")
        except Exception as e:  # noqa: BLE001
            print(f"   ❌ Não consegui carregar o Whisper agora: {str(e)[:200]}")
            print("      Ele tenta baixar de novo no primeiro uso de voz; verifique sua conexão/Hugging Face.")
            problems += 1

    print()
    if problems:
        print(f"⚠️  Setup terminou com {problems} pendência(s). Rode 'itachi-capoeira doctor' para ver o que falta.")
    else:
        print("🎉 Setup completo! Rode: itachi-capoeira start")
    return 1 if problems else 0
