"""Configuração: caminhos, valores padrão e leitura de config/persona.txt (+ local.txt + variáveis ITACHI_CAPOEIRA_*)."""
from __future__ import annotations

import os
import re
from pathlib import Path

APP_DIR = Path(os.environ.get("ITACHI_CAPOEIRA_APP_DIR") or Path(__file__).resolve().parent.parent)
DATA_DIR = Path(os.environ.get("ITACHI_CAPOEIRA_HOME") or (APP_DIR / "data"))
CONFIG_DIR = APP_DIR / "config"
LOG_DIR = DATA_DIR / "logs"
MODELS_DIR = DATA_DIR / "models"
RUN_DIR = DATA_DIR / "run"
TMP_DIR = DATA_DIR / "tmp"
MEMORY_FILE = DATA_DIR / "memory.json"
PIDFILE = RUN_DIR / "itachi-capoeira.pid"

PERSONA_FILE = CONFIG_DIR / "persona.txt"   # personalidade (editável pelo usuário)
LOCAL_FILE = CONFIG_DIR / "local.txt"       # gerado pelo instalador (modelos escolhidos p/ seu hardware)
SECRETS_FILE = CONFIG_DIR / "secrets.txt"   # chaves de API (permissão 600, fora do git): OLLAMA_API_KEY


def ensure_dirs() -> None:
    for d in (DATA_DIR, LOG_DIR, MODELS_DIR, RUN_DIR, TMP_DIR, CONFIG_DIR):
        d.mkdir(parents=True, exist_ok=True)


DEFAULTS: dict = {
    # --- Persona ---
    "NAME": "Itachi Capoeira",
    "VOICE": "pm_santa",          # vozes pt-BR do Kokoro: pm_santa, pm_alex, pf_dora
    "LANGUAGE": "pt-BR",
    "HUMOR": 60,
    "FORMALITY": 40,
    "ENTHUSIASM": 70,
    "PATIENCE": 90,
    "SHORT_RESPONSES": False,
    "USE_TECHNICAL_TERMS": True,
    "EXPLAIN_WHILE_DOING": True,
    "PROACTIVE_MODE": True,
    "PROACTIVE_INTERVAL_MINUTES": 30,
    "NOTIFY_ON_ERRORS": True,
    "NOTIFY_ON_COMPLETIONS": True,
    "MEMORY_ENABLED": True,
    "MEMORY_MAX_ITEMS": 10,
    # --- Modelos (o instalador ajusta conforme sua VRAM em config/local.txt) ---
    "OLLAMA_URL": "http://127.0.0.1:11434",   # nuvem: https://ollama.com (use: itachi-capoeira cloud setup)
    "OLLAMA_API_KEY": "",                     # só para a nuvem; fica em config/secrets.txt (ou env OLLAMA_API_KEY)
    "CHAT_MODEL": "gemma4:e4b",
    "VISION_MODEL": "gemma4:e4b",   # pode ser outro (ex.: llava). Se igual ao CHAT_MODEL, usa 1 chamada só.
    "LOW_VRAM_MODE": False,         # descarrega um modelo antes de carregar o outro (útil com 2 modelos distintos)
    "NUM_CTX": 4096,                # contexto menor = menos VRAM
    "OLLAMA_KEEP_ALIVE": "10m",
    "LLM_TIMEOUT": 300,
    "SCREENSHOT_MAX_PX": 1600,
    "SCREEN_MONITOR": 1,            # 1 = monitor principal, 0 = todos juntos
    # --- Voz ---
    "WHISPER_MODEL": "small",
    "WHISPER_DEVICE": "auto",       # auto | cpu | cuda
    "WHISPER_COMPUTE": "auto",      # auto | int8 | float16 ...
    "TTS_ENGINE": "auto",           # auto | kokoro | system | off
    "KOKORO_LANG": "pt-br",
    "KOKORO_SPEED": 1.0,
    "TTS_MAX_CHARS": 900,
    "TTS_SYNTH_TIMEOUT": 45,        # s: se o Kokoro não sintetizar uma frase nesse tempo, usa a voz do sistema
    "MIC_DEVICE": "",               # vazio = padrão do sistema (ou número/nome do dispositivo)
    "AUDIO_OUT_DEVICE": "",         # saída de áudio: vazio = padrão (ou número/nome; veja: python -m sounddevice)
    "AUDIO_PLAYER": "auto",         # auto | sounddevice | system (system = paplay/pw-play/aplay: toca no que o desktop usa)
    "MAX_RECORD_SECONDS": 30,
    "SILENCE_SECONDS": 1.4,
    "CORRECT_GRAMMAR": True,
    "AUTO_PASTE": True,
    # --- Teclas de atalho (formato pynput) ---
    "HOTKEY_VOICE": "<f8>",         # gravar -> transcrever -> colar (aperte de novo para parar)
    "HOTKEY_SCREEN": "<f9>",        # print da tela -> Itachi Capoeira descreve e fala
    "HOTKEY_TALK": "<f7>",          # conversa por voz (você fala, Itachi Capoeira responde falando)
    "HOTKEY_STOP": "<f10>",         # interrompe fala/processamento
    "AUTO_DESKTOP_SHORTCUTS": True, # Wayland/GNOME: o daemon registra as teclas acima como atalhos do desktop
    # --- Palavra de ativação (opcional, mantém o microfone ouvindo) ---
    "WAKE_WORD_ENABLED": False,
    "WAKE_WORDS": "itachi",         # lista separada por vírgula (aceita variações)
    # --- Saúde / monitor ---
    "HEALTH_INTERVAL_MINUTES": 15,
    "HEALTH_RAM_PERCENT": 85,
    "HEALTH_MIN_FREE_RAM_GB": 2,
    "DISK_PATH": "",                # vazio = unidade do usuário
    "GPU_TEMP_LIMIT": 80,
    "DISK_LIMIT_PERCENT": 90,
}


def _parse_value(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    if raw[0] in "\"'":
        q = raw[0]
        end = raw.find(q, 1)
        return raw[1:end] if end != -1 else raw[1:]
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip()


def parse_file(path: Path) -> dict:
    """Lê arquivos KEY=VALUE (compatível com o persona.txt original, sem executar nada)."""
    out: dict = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip().upper()
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            out[key] = _parse_value(val)
    return out


def _coerce(key: str, raw):
    default = DEFAULTS.get(key)
    if isinstance(default, bool):
        return str(raw).strip().lower() in ("1", "true", "yes", "sim", "on")
    if isinstance(default, int):
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default
    return str(raw)


class Config:
    def __init__(self, values: dict | None = None):
        merged = dict(DEFAULTS)
        for src in (parse_file(PERSONA_FILE), parse_file(LOCAL_FILE), parse_file(SECRETS_FILE)):
            for k, v in src.items():
                merged[k] = _coerce(k, v)
        for k in DEFAULTS:
            env = os.environ.get("ITACHI_CAPOEIRA_" + k)
            if env is not None:
                merged[k] = _coerce(k, env)
        if not merged.get("OLLAMA_API_KEY") and os.environ.get("OLLAMA_API_KEY"):
            merged["OLLAMA_API_KEY"] = os.environ["OLLAMA_API_KEY"].strip()
        if values:
            merged.update(values)
        self._v = merged

    def __getattr__(self, item):
        try:
            return self.__dict__["_v"][item]
        except KeyError:
            raise AttributeError(item) from None

    def get(self, key, default=None):
        return self._v.get(key, default)

    def as_dict(self, mask_secrets: bool = False) -> dict:
        d = dict(self._v)
        if mask_secrets and d.get("OLLAMA_API_KEY"):
            d["OLLAMA_API_KEY"] = "••••" + str(d["OLLAMA_API_KEY"])[-4:]
        return d

    @property
    def language_short(self) -> str:
        return (self.LANGUAGE or "pt").split("-")[0].lower()

    @property
    def wake_words(self) -> list[str]:
        return [w.strip().lower() for w in str(self.WAKE_WORDS).split(",") if w.strip()]


def load() -> Config:
    ensure_dirs()
    return Config()


def write_local(values: dict) -> None:
    """Grava/atualiza config/local.txt preservando chaves já existentes."""
    ensure_dirs()
    current = parse_file(LOCAL_FILE)
    current.update({k: str(v) for k, v in values.items()})
    lines = ["# Gerado por 'itachi-capoeira setup' — ajustes de modelos para o seu hardware.",
             "# Pode editar à vontade; rode 'itachi-capoeira setup' para recalcular."]
    for k, v in current.items():
        lines.append(f'{k}="{v}"')
    LOCAL_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def remove_local(keys) -> None:
    """Remove chaves de config/local.txt (ex.: ao voltar do modo nuvem para o local)."""
    current = parse_file(LOCAL_FILE)
    for k in keys:
        current.pop(k.upper(), None)
    lines = ["# Gerado por 'itachi-capoeira setup' — ajustes de modelos para o seu hardware.",
             "# Pode editar à vontade; rode 'itachi-capoeira setup' para recalcular."]
    lines += [f'{k}="{v}"' for k, v in current.items()]
    LOCAL_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_secrets(values: dict) -> None:
    ensure_dirs()
    if not values:
        try:
            SECRETS_FILE.unlink()
        except OSError:
            pass
        return
    body = "# Segredos (não compartilhe, não suba no git).\n" + "".join(f'{k}="{v}"\n' for k, v in values.items())
    fd = os.open(SECRETS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body)
    try:
        os.chmod(SECRETS_FILE, 0o600)
    except OSError:
        pass


def write_secret(key: str, value: str) -> None:
    """Grava/atualiza config/secrets.txt com permissão 600 (só o seu usuário lê)."""
    current = parse_file(SECRETS_FILE)
    current[key.upper()] = value
    _write_secrets(current)


def remove_secret(key: str) -> None:
    current = parse_file(SECRETS_FILE)
    if current.pop(key.upper(), None) is not None:
        _write_secrets(current)
