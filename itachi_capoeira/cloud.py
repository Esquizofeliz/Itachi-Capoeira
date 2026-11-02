"""Modo nuvem: usa os modelos hospedados do Ollama (plano gratuito) com uma chave de API, sem GPU local.

    itachi-capoeira cloud setup     pede a chave (https://ollama.com/settings/keys), testa e ativa
    itachi-capoeira cloud status    mostra o modo atual
    itachi-capoeira cloud off       volta para o Ollama local

Só o raciocínio/visão vai para a nuvem; voz (Whisper) e fala (Kokoro) continuam locais.
ATENÇÃO: neste modo o texto das conversas e os prints de tela são enviados ao ollama.com.
"""
from __future__ import annotations

import getpass
import os
import re
import sys

from .config import Config, remove_local, remove_secret, write_local, write_secret
from .llm import Ollama, OllamaError

CLOUD_URL = "https://ollama.com"
KEYS_URL = "https://ollama.com/settings/keys"
# Nomes da API direta (sem o sufixo ':cloud'); preferência por prefixo. O plano gratuito não publica
# quais modelos inclui, por isso listamos o que a sua chave enxerga e testamos antes de salvar.
CHAT_PREFS = ("gpt-oss:120b", "gpt-oss:20b", "qwen3.5", "gemma3", "gemma4", "llama3.3", "deepseek-v4-flash")
VISION_RE = re.compile(r"(-vl\b|vl:|vision|gemma[34]|llava|minicpm-v|qwen3\.5|mistral-small3|llama4|kimi-k2\.5)", re.I)

PRIVACY = ("⚠️  No modo nuvem, o texto das conversas e os PRINTS DA TELA são enviados ao ollama.com.\n"
           "   Para uso 100% local, rode depois: itachi-capoeira cloud off")


def _tty() -> bool:
    return bool(sys.stdin) and sys.stdin.isatty()


def pick_models(names: list[str]) -> tuple[str | None, str | None]:
    """(modelo de conversa, modelo de visão) sugeridos a partir da lista da nuvem."""
    chat = None
    for pref in CHAT_PREFS:
        chat = next((n for n in names if n == pref or n.startswith(pref)), None)
        if chat:
            break
    chat = chat or (names[0] if names else None)
    vis = [n for n in names if VISION_RE.search(n)]
    vis.sort(key=lambda n: (0 if re.search(r"-vl\b|vl:|vision", n, re.I) else 1, n))
    return chat, (vis[0] if vis else None)


def _ask(prompt: str, default: str, interactive: bool | None = None) -> str:
    if not (_tty() if interactive is None else interactive):
        return default
    ans = input(f"   ❓ {prompt} [{default}]: ").strip()
    return ans or default


def _get_key(cfg: Config, given: str | None, out, interactive: bool | None = None) -> str:
    key = (given or os.environ.get("OLLAMA_API_KEY") or "").strip()
    if key:
        return key
    out(f"🔑 Crie uma chave gratuita em {KEYS_URL}  (conta no ollama.com, sem cartão)")
    if _tty() if interactive is None else interactive:
        try:
            import webbrowser
            webbrowser.open(KEYS_URL)
        except Exception:  # noqa: BLE001
            pass
        return getpass.getpass("   Cole a chave de API (não aparece na tela): ").strip()
    return (cfg.get("OLLAMA_API_KEY") or "").strip()


def enable(cfg: Config, key: str | None = None, chat_model: str | None = None, vision_model: str | None = None,
           out=print, interactive: bool | None = None) -> int:
    """interactive=False (usado pela GUI): nunca pergunta nada no terminal nem abre o navegador."""
    out("☁️  Modo nuvem do Ollama\n")
    key = _get_key(cfg, key, out, interactive)
    if not key:
        out("❌ Nenhuma chave informada. Rode de novo: itachi-capoeira cloud setup")
        return 1
    out(PRIVACY + "\n")
    llm = Ollama(CLOUD_URL, timeout=60, api_key=key, cloud=True)
    try:
        names = llm.list_models()
    except OllamaError as e:
        out(f"❌ Não consegui entrar na nuvem: {e}")
        return 1
    if not names:
        out("❌ A nuvem não devolveu nenhum modelo para a sua conta.")
        return 1
    chat_s, vision_s = pick_models(names)
    out(f"📚 Modelos disponíveis ({len(names)}): " + ", ".join(names[:25]) + (" ..." if len(names) > 25 else ""))
    chat = chat_model or _ask("Modelo de conversa", chat_s or names[0], interactive)
    if chat not in names:
        out(f"❌ '{chat}' não está na lista da nuvem. Use um dos nomes acima (sem o sufixo ':cloud').")
        return 1
    vision = vision_model or _ask("Modelo que descreve a tela (precisa aceitar imagem)", vision_s or chat, interactive)
    if vision not in names:
        out(f"❌ '{vision}' não está na lista da nuvem.")
        return 1
    if vision == chat and not vision_s and not vision_model:
        out("   ⚠️  Não identifiquei um modelo de imagem; usando o mesmo da conversa. "
            "Se 'descrever a tela' falhar, escolha outro: itachi-capoeira cloud setup --vision-model NOME")

    out(f"🧪 Testando '{chat}'...")
    try:
        reply = llm.chat(chat, [{"role": "user", "content": "Responda só com a palavra: ok"}], timeout=90)
        out(f"   ✅ respondeu: {reply[:60]!r}")
    except OllamaError as e:
        if e.status in (401, 403):
            out(f"❌ {e}")
            return 1
        out(f"   ⚠️  O teste não passou ({e}). Vou salvar mesmo assim; rode 'itachi-capoeira cloud status' depois.")

    write_secret("OLLAMA_API_KEY", key)
    write_local({"OLLAMA_URL": CLOUD_URL, "CHAT_MODEL": chat, "VISION_MODEL": vision})
    cfg._v.update({"OLLAMA_URL": CLOUD_URL, "OLLAMA_API_KEY": key, "CHAT_MODEL": chat, "VISION_MODEL": vision})
    out(f"\n💾 Chave salva em config/secrets.txt (permissão 600); modelos em config/local.txt")
    out(f"✅ Nuvem ativa: conversa={chat} | visão={vision}")
    out("➡️  Reinicie para valer: itachi-capoeira restart")
    return 0


def disable(cfg: Config, out=print) -> int:
    remove_local(["OLLAMA_URL", "CHAT_MODEL", "VISION_MODEL"])
    remove_secret("OLLAMA_API_KEY")
    out("✅ Modo nuvem desligado (chave apagada de config/secrets.txt).")
    out("➡️  Escolha os modelos locais com: itachi-capoeira setup   e depois: itachi-capoeira restart")
    return 0


def status(cfg: Config, out=print) -> int:
    llm = Ollama.from_config(cfg, timeout=30)
    key = cfg.get("OLLAMA_API_KEY", "")
    out(f"Modo: {'☁️  nuvem' if llm.cloud else '🖥️  local'} | {cfg.OLLAMA_URL}")
    out(f"Chave de API: {'definida (••••' + key[-4:] + ')' if key else 'não definida'}")
    out(f"Modelos: conversa={cfg.CHAT_MODEL} | visão={cfg.VISION_MODEL}")
    if llm.cloud and not key:
        out("❌ Falta a chave. Rode: itachi-capoeira cloud setup")
        return 1
    try:
        names = llm.list_models()
    except OllamaError as e:
        out(f"❌ {e}")
        return 1
    for m in dict.fromkeys([cfg.CHAT_MODEL, cfg.VISION_MODEL]):
        out(f"   {'✅' if llm.has_model(m) else '❌'} {m}")
    out(f"({len(names)} modelos visíveis)")
    return 0
