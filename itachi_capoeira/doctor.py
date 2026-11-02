"""itachi-capoeira doctor — verifica tudo que o Itachi Capoeira precisa e diz exatamente o que falta."""
from __future__ import annotations

import os
import platform
import shutil
import sys
import time

from . import audio, autostart, hardware, screen
from .config import APP_DIR, LOCAL_FILE, Config
from .llm import Ollama, OllamaError
from .tts import KokoroEngine, SystemEngine, kokoro_paths, kokoro_ready

OK, WARN, FAIL = "OK", "AVISO", "FALHA"
_ICON = {OK: "✅", WARN: "⚠️ ", FAIL: "❌"}


class Report:
    def __init__(self):
        self.rows: list[tuple[str, str, str]] = []

    def add(self, level: str, name: str, detail: str = "") -> None:
        self.rows.append((level, name, detail))
        print(f"{_ICON[level]} {name}" + (f" — {detail}" if detail else ""), flush=True)

    @property
    def failures(self) -> int:
        return sum(1 for r in self.rows if r[0] == FAIL)

    @property
    def warnings(self) -> int:
        return sum(1 for r in self.rows if r[0] == WARN)


def run(cfg: Config, deep: bool = False) -> int:
    rep = Report()
    print(f"\n🩺 Itachi Capoeira doctor — {platform.system()} {platform.release()} ({platform.machine()})\n")

    # --- Python / projeto
    v = sys.version_info
    rep.add(OK if v >= (3, 10) else FAIL, "Python", f"{v.major}.{v.minor}.{v.micro}")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    rep.add(OK if in_venv else WARN, "Ambiente virtual", "ativo" if in_venv else "não está usando .venv (rode via itachi-capoeira)")
    rep.add(OK if LOCAL_FILE.exists() else WARN, "Configuração de hardware (config/local.txt)",
            "presente" if LOCAL_FILE.exists() else "ausente — rode: itachi-capoeira setup")

    # --- Hardware
    gpu = hardware.detect_gpu()
    ram = hardware.ram_total_gb()
    rep.add(OK if gpu.backend != "none" else WARN, "GPU / VRAM", hardware.describe(gpu, ram) +
            (f" [{gpu.note}]" if gpu.note else ""))
    tier = hardware.pick_tier(gpu, ram)
    rep.add(OK, "Nível de modelos recomendado", f"{tier.label}: {tier.chat_model}")
    if gpu.backend == "none" and ram < 8:
        rep.add(WARN, "RAM", "menos de 8 GB: modelos locais ficarão muito lentos")
    if sys.platform.startswith("linux"):
        sess = os.environ.get("XDG_SESSION_TYPE", "desconhecida")
        rep.add(OK if sess != "wayland" else WARN, "Sessão gráfica", sess +
                (" — atalhos globais via desktop: 'itachi-capoeira shortcuts install'" if sess == "wayland" else ""))

    # --- Ollama
    llm = Ollama.from_config(cfg, timeout=30)
    if llm.alive():
        try:
            rep.add(OK, "Ollama", (f"nuvem em {cfg.OLLAMA_URL}" if llm.cloud else f"v{llm.version()} em {cfg.OLLAMA_URL}"))
            for m in dict.fromkeys([cfg.CHAT_MODEL, cfg.VISION_MODEL]):
                if llm.has_model(m):
                    rep.add(OK, f"Modelo {m}", "instalado")
                else:
                    rep.add(FAIL, f"Modelo {m}", "ausente na nuvem — rode: itachi-capoeira cloud setup" if llm.cloud
                            else f"ausente — rode: itachi-capoeira setup  (ou: ollama pull {m})")
            loaded = llm.running()
            if loaded:
                info = ", ".join(f"{x.get('name')} ({x.get('size_vram', 0) / 1024 ** 3:.1f} GB na GPU)" for x in loaded)
                rep.add(OK, "Carregados agora", info)
        except OllamaError as e:
            rep.add(FAIL, "Ollama", str(e))
    else:
        rep.add(FAIL, "Ollama", (f"nuvem inacessível em {cfg.OLLAMA_URL} — internet ou chave? (itachi-capoeira cloud status)"
                                 if llm.cloud else
                                 f"não responde em {cfg.OLLAMA_URL} — instale em https://ollama.com/download e abra-o"))

    # --- TTS
    if kokoro_ready():
        k = KokoroEngine(cfg)
        if k.available():
            rep.add(OK, "Kokoro TTS", "modelo + biblioteca prontos")
        else:
            try:
                import kokoro_onnx  # noqa: F401
                detail = "biblioteca importada, mas o motor não ficou disponível; verifique os arquivos do modelo"
            except Exception as e:  # noqa: BLE001
                detail = f"falha ao importar kokoro_onnx: {type(e).__name__}: {e}"
            rep.add(FAIL, "Kokoro TTS", detail + " — repare com: ./repair-linux.sh")
    else:
        rep.add(WARN, "Kokoro TTS", f"modelo ausente em {kokoro_paths()[0].parent} — rode: itachi-capoeira setup")
    sysv = SystemEngine(cfg)
    rep.add(OK if sysv.available() else WARN, "Voz do sistema (reserva)",
            "disponível" if sysv.available() else "indisponível (no Linux: sudo apt install espeak-ng)")

    # --- STT
    try:
        import faster_whisper  # noqa: F401
        from .stt import WHISPER_DIR, cuda_available
        cached = WHISPER_DIR.exists() and any(WHISPER_DIR.iterdir())
        rep.add(OK, "Faster-Whisper", f"instalado; modelo '{cfg.WHISPER_MODEL}' " +
                ("em cache" if cached else "será baixado no primeiro uso") +
                f"; CUDA {'sim' if cuda_available() else 'não (usará CPU)'}")
    except Exception as e:  # noqa: BLE001
        rep.add(FAIL, "Faster-Whisper", f"não importa: {e}")

    # --- Áudio
    ins, outs = audio.list_devices()
    err = audio.sounddevice_error()
    if err:
        rep.add(FAIL, "Áudio (PortAudio)", err +
                " — execute ./repair-linux.sh (ou: pip install sounddevice; sudo apt install libportaudio2)")
    else:
        rep.add(OK if ins else WARN, "Microfone", f"{len(ins)} dispositivo(s)" + (f"; ex.: {ins[0]}" if ins else
                " — nenhum encontrado"))
        rep.add(OK if outs else WARN, "Alto-falantes", f"{len(outs)} dispositivo(s)" + (f"; ex.: {outs[0]}" if outs else
                " — nenhum encontrado (usarei players do sistema)"))

    # --- Tela / clipboard / atalhos
    try:
        import mss  # noqa: F401
        if deep:
            jpg = screen.capture_jpeg(800, int(cfg.SCREEN_MONITOR))
            rep.add(OK, "Captura de tela", f"funcionou ({len(jpg) // 1024} KB)")
        else:
            rep.add(OK, "Captura de tela (mss)", "instalado (teste real: doctor --deep)")
    except Exception as e:  # noqa: BLE001
        rep.add(FAIL, "Captura de tela", str(e) + " — execute ./repair-linux.sh (instala mss)")

    if sys.platform.startswith("linux"):
        tools = [t for t in ("wl-copy", "xclip", "xsel") if shutil.which(t)]
        rep.add(OK if tools else WARN, "Área de transferência", ", ".join(tools) if tools else
                "instale xclip (X11) ou wl-clipboard (Wayland)")
    else:
        rep.add(OK, "Área de transferência", "nativa do sistema")

    try:
        from pynput import keyboard  # noqa: F401
        rep.add(OK, "Atalhos globais (pynput)", "instalado" + (" — conceda permissão de Acessibilidade/Monitoramento "
                "de Entrada no macOS" if sys.platform == "darwin" else ""))
    except Exception as e:  # noqa: BLE001
        first = str(e).strip().splitlines()[0][:110] if str(e).strip() else type(e).__name__
        rep.add(WARN, "Atalhos globais (pynput)", f"indisponível aqui ({first}); use 'itachi-capoeira trigger'")

    rep.add(OK, "Início automático", autostart.status())

    # --- Testes reais (opcional)
    if deep:
        print("\n— Testes reais —")
        try:
            t0 = time.time()
            out = llm.chat(cfg.CHAT_MODEL, [{"role": "user", "content": "Responda apenas: OK"}],
                           num_ctx=cfg.NUM_CTX, timeout=180)
            rep.add(OK if out else FAIL, "Resposta do LLM", f"{out[:60]!r} em {time.time() - t0:.1f}s")
        except OllamaError as e:
            rep.add(FAIL, "Resposta do LLM", str(e))
        try:
            from .tts import Speaker
            sp = Speaker(cfg)
            eng = sp.engine()
            if eng is None:
                rep.add(FAIL, "Síntese de voz", "nenhum motor disponível")
            elif eng.name == "kokoro":
                t0 = time.time()
                samples, sr = eng.synth("Olá! Teste de voz do assistente.")
                rep.add(OK, "Síntese de voz (Kokoro)", f"{len(samples) / sr:.1f}s de áudio gerados em {time.time() - t0:.1f}s")
            else:
                rep.add(OK, "Síntese de voz", f"motor: {eng.name}")
        except Exception as e:  # noqa: BLE001
            rep.add(FAIL, "Síntese de voz", str(e))

    print()
    if rep.failures:
        print(f"❌ {rep.failures} problema(s) a resolver, {rep.warnings} aviso(s).")
    elif rep.warnings:
        print(f"✅ Funcional, com {rep.warnings} aviso(s) acima.")
    else:
        print("✅ Tudo certo! Rode: itachi-capoeira start")
    print(f"   Pasta do projeto: {APP_DIR}\n")
    return 1 if rep.failures else 0
