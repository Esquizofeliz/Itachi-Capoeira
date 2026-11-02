"""Atalhos globais pelo próprio desktop (GNOME/Ubuntu/Budgie/Unity).

No Wayland o pynput não enxerga o teclado fora das próprias janelas, então as teclas F7–F10 não funcionam.
A saída é registrar atalhos personalizados no desktop que chamam `itachi-capoeira trigger <ação> --start`
(o --start liga o daemon sozinho se ele não estiver rodando). As teclas vêm de config/persona.txt
(HOTKEY_*), as mesmas usadas pelo pynput.

Só mexemos nos atalhos cujo identificador começa com 'itachi-'; os seus outros atalhos ficam intactos.
"""
from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
from pathlib import Path

from .config import APP_DIR

log = logging.getLogger("itachi_capoeira.shortcuts")

SCHEMA_LIST = "org.gnome.settings-daemon.plugins.media-keys"
SCHEMA_ITEM = SCHEMA_LIST + ".custom-keybinding"
BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
PREFIX = "itachi-"
DESKTOPS = ("GNOME", "UNITY", "BUDGIE")

# (gatilho, chave na config, nome mostrado nas Configurações do desktop)
ACTIONS = (
    ("screen", "HOTKEY_SCREEN", "Itachi Capoeira: descrever a tela"),
    ("voice", "HOTKEY_VOICE", "Itachi Capoeira: voz para texto"),
    ("talk", "HOTKEY_TALK", "Itachi Capoeira: conversa por voz"),
    ("stop", "HOTKEY_STOP", "Itachi Capoeira: parar"),
)

_MODS = {"ctrl": "<Ctrl>", "ctrl_l": "<Ctrl>", "ctrl_r": "<Ctrl>", "alt": "<Alt>", "alt_l": "<Alt>",
         "alt_r": "<Alt>", "alt_gr": "<Alt>", "shift": "<Shift>", "shift_l": "<Shift>", "shift_r": "<Shift>",
         "cmd": "<Super>", "cmd_l": "<Super>", "cmd_r": "<Super>"}
_KEYS = {"print_screen": "Print", "esc": "Escape", "enter": "Return", "space": "space", "tab": "Tab",
         "backspace": "BackSpace", "delete": "Delete", "home": "Home", "end": "End", "page_up": "Page_Up",
         "page_down": "Page_Down", "up": "Up", "down": "Down", "left": "Left", "right": "Right",
         "insert": "Insert", "pause": "Pause", "scroll_lock": "Scroll_Lock", "menu": "Menu"}


# ---------------------------------------------------------------- ambiente
def is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def desktop_supported() -> bool:
    cur = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    return any(d in cur for d in DESKTOPS)


def to_gnome(combo: str) -> str | None:
    """'<ctrl>+<alt>+t' -> '<Ctrl><Alt>t';  '<f9>' -> 'F9'.  None se não souber converter."""
    out = ""
    parts = [p.strip() for p in combo.split("+") if p.strip()]
    if not parts:
        return None
    for i, raw in enumerate(parts):
        tok = raw.strip("<>").lower()
        last = i == len(parts) - 1
        if tok in _MODS and not last:
            out += _MODS[tok]
        elif not last:
            return None
        elif re.fullmatch(r"f([1-9]|1\d|2[0-4])", tok):
            out += tok.upper()
        elif tok in _KEYS:
            out += _KEYS[tok]
        elif len(tok) == 1 and tok.isprintable():
            out += tok
        else:
            return None
    return out


def launcher() -> Path:
    return APP_DIR / "itachi-capoeira"


def command_for(name: str) -> str:
    return f"{shlex.quote(str(launcher()))} trigger {name} --start"


# ---------------------------------------------------------------- gsettings
def _q(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _gs(run, *args: str, check: bool = True) -> str:
    r = run(["gsettings", *args], capture_output=True, text=True, timeout=15)
    if check and r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "gsettings falhou").strip())
    return (r.stdout or "").strip()


def _get_list(run) -> list[str]:
    return re.findall(r"'([^']*)'", _gs(run, "get", SCHEMA_LIST, "custom-keybindings"))


def _set_list(run, paths: list[str]) -> None:
    value = "[" + ", ".join(_q(p) for p in paths) + "]" if paths else "@as []"
    _gs(run, "set", SCHEMA_LIST, "custom-keybindings", value)


def _item(run, path: str, key: str) -> str:
    out = _gs(run, "get", f"{SCHEMA_ITEM}:{path}", key, check=False)
    m = re.fullmatch(r"'(.*)'", out, re.S)
    return (m.group(1) if m else out).replace("\\'", "'").replace("\\\\", "\\")


def available(run=subprocess.run) -> tuple[bool, str]:
    if not desktop_supported():
        return False, ("Desktop sem suporte automático (só GNOME/Ubuntu/Budgie/Unity). "
                       "Crie manualmente atalhos que executem:\n" + manual_help())
    try:
        _get_list(run)
    except (OSError, RuntimeError, subprocess.SubprocessError) as e:
        return False, f"gsettings indisponível ({e}).\n" + manual_help()
    return True, ""


def manual_help() -> str:
    return "\n".join(f"   {command_for(n)}" for n, _k, _t in ACTIONS)


# ---------------------------------------------------------------- operações
def status(run=subprocess.run) -> dict[str, dict]:
    """{gatilho: {'binding':..., 'command':..., 'path':...}} dos atalhos 'itachi-*' existentes."""
    found: dict[str, dict] = {}
    for p in _get_list(run):
        base = p.rstrip("/").rsplit("/", 1)[-1]
        if not base.startswith(PREFIX):
            continue
        found[base[len(PREFIX):]] = {"path": p, "binding": _item(run, p, "binding"),
                                     "command": _item(run, p, "command")}
    return found


def install(cfg, run=subprocess.run) -> tuple[bool, str]:
    ok, why = available(run)
    if not ok:
        return False, why
    existing = _get_list(run)
    others = [p for p in existing if not p.rstrip("/").rsplit("/", 1)[-1].startswith(PREFIX)]
    taken = {}
    for p in others:                       # atalhos personalizados de outros programas (para avisar de conflito)
        b = _item(run, p, "binding")
        if b:
            taken[b] = _item(run, p, "name") or p
    mine: list[str] = []
    lines: list[str] = []
    used: set[str] = set()
    for name, key, title in ACTIONS:
        combo = getattr(cfg, key, "")
        if not combo:
            continue
        gb = to_gnome(combo)
        if gb is None:
            lines.append(f"⚠️  {key}={combo!r}: não consegui converter para o desktop — ignorado.")
            continue
        if gb in used:
            lines.append(f"⚠️  {gb} repetido em {key} — ignorado.")
            continue
        used.add(gb)
        path = f"{BASE}{PREFIX}{name}/"
        _gs(run, "set", f"{SCHEMA_ITEM}:{path}", "name", _q(title))
        _gs(run, "set", f"{SCHEMA_ITEM}:{path}", "command", _q(command_for(name)))
        _gs(run, "set", f"{SCHEMA_ITEM}:{path}", "binding", _q(gb))
        mine.append(path)
        extra = f"  (⚠️ também usado por '{taken[gb]}')" if gb in taken else ""
        lines.append(f"   {gb:<12} → {name}{extra}")
    if not mine:
        return False, "Nenhuma tecla válida em HOTKEY_* (config/persona.txt)."
    _set_list(run, others + mine)
    return True, "Atalhos do desktop registrados (valem em qualquer janela, inclusive no Wayland):\n" + "\n".join(lines)


def remove(run=subprocess.run) -> tuple[bool, str]:
    ok, why = available(run)
    if not ok:
        return False, why
    existing = _get_list(run)
    keep = [p for p in existing if not p.rstrip("/").rsplit("/", 1)[-1].startswith(PREFIX)]
    gone = [p for p in existing if p not in keep]
    for p in gone:
        for k in ("name", "command", "binding"):
            _gs(run, "reset", f"{SCHEMA_ITEM}:{p}", k, check=False)
    _set_list(run, keep)
    return True, f"{len(gone)} atalho(s) do Itachi Capoeira removido(s)."


def ensure(cfg, run=subprocess.run) -> str | None:
    """Chamado pelo daemon: no Wayland, garante que os atalhos do desktop existem. Idempotente.
    Não sobrescreve teclas que você mudou nas Configurações — só recria o que faltar ou apontar para outro lugar."""
    if not getattr(cfg, "AUTO_DESKTOP_SHORTCUTS", True) or not is_wayland():
        return None
    ok, why = available(run)
    if not ok:
        return why.splitlines()[0] if why else None
    try:
        have = status(run)
        wanted = [n for n, key, _t in ACTIONS if getattr(cfg, key, "")]
        if wanted and all(n in have and have[n]["command"] == command_for(n) for n in wanted):
            return "Atalhos do desktop (Wayland) já configurados: " + ", ".join(
                f"{have[n]['binding']}→{n}" for n in wanted)
        return install(cfg, run)[1]
    except (OSError, RuntimeError, subprocess.SubprocessError) as e:
        return f"Não consegui configurar atalhos do desktop: {e}"
