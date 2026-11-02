"""Início automático com o login: XDG autostart/systemd (Linux), LaunchAgent (macOS), Agendador de Tarefas (Windows)."""
from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from .config import APP_DIR, LOG_DIR, ensure_dirs

LABEL = "com.itachicapoeira.assistant"


def _python() -> str:
    exe = Path(sys.executable)
    if sys.platform == "win32":
        pyw = exe.with_name("pythonw.exe")      # sem janela de console
        return str(pyw if pyw.exists() else exe)
    return str(exe)


def _xdg_path() -> Path:
    return Path.home() / ".config" / "autostart" / "itachi-capoeira.desktop"


def _systemd_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "itachi-capoeira.service"


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def desktop_entry() -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Itachi Capoeira\n"
        "Comment=Assistente de IA local com voz e visão\n"
        f"Exec=\"{sys.executable}\" -m itachi_capoeira run\n"
        f"Path={APP_DIR}\n"
        "Icon=audio-input-microphone\n"
        "Terminal=false\n"
        "Categories=Utility;Audio;\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def systemd_unit() -> str:
    return (
        "[Unit]\n"
        "Description=Itachi Capoeira — assistente de IA local\n"
        "After=graphical-session.target network.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={APP_DIR}\n"
        "ExecStartPre=-/usr/bin/env systemctl --user import-environment DISPLAY XAUTHORITY WAYLAND_DISPLAY\n"
        f"ExecStart={sys.executable} -m itachi_capoeira run\n"
        "Restart=on-failure\n"
        "RestartSec=5\n\n"
        "[Install]\n"
        "WantedBy=graphical-session.target\n"
    )


def enable(method: str = "auto") -> str:
    ensure_dirs()
    if sys.platform == "win32":
        cmd = f'"{_python()}" -m itachi_capoeira run'
        r = subprocess.run(
            ["schtasks", "/Create", "/TN", "ItachiCapoeira", "/TR", cmd, "/SC", "ONLOGON", "/RL", "LIMITED", "/F"],
            capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or r.stdout.strip())
        return "Tarefa 'ItachiCapoeira' criada no Agendador de Tarefas (inicia no login)."
    if sys.platform == "darwin":
        p = _plist_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        plist = {
            "Label": LABEL,
            "ProgramArguments": [sys.executable, "-m", "itachi_capoeira", "run"],
            "WorkingDirectory": str(APP_DIR),
            "EnvironmentVariables": {"PYTHONPATH": str(APP_DIR)},
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
            "StandardOutPath": str(LOG_DIR / "launchd.out.log"),
            "StandardErrorPath": str(LOG_DIR / "launchd.err.log"),
        }
        with open(p, "wb") as f:
            plistlib.dump(plist, f)
        subprocess.run(["launchctl", "unload", str(p)], capture_output=True)
        r = subprocess.run(["launchctl", "load", "-w", str(p)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip())
        return f"LaunchAgent instalado em {p}."
    # Linux
    use_systemd = method == "systemd"
    if use_systemd and shutil.which("systemctl"):
        p = _systemd_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(systemd_unit(), encoding="utf-8")
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        r = subprocess.run(["systemctl", "--user", "enable", "itachi-capoeira.service"], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip())
        return f"Serviço systemd de usuário instalado em {p}."
    p = _xdg_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(desktop_entry(), encoding="utf-8")
    # também cria o atalho no menu de aplicativos
    menu = Path.home() / ".local" / "share" / "applications" / "itachi-capoeira.desktop"
    menu.parent.mkdir(parents=True, exist_ok=True)
    menu.write_text(desktop_entry(), encoding="utf-8")
    return f"Autostart criado em {p} (inicia ao entrar na sessão gráfica)."


def disable(remove_menu_entry: bool = True) -> str:
    removed = []
    if sys.platform == "win32":
        r = subprocess.run(["schtasks", "/Delete", "/TN", "ItachiCapoeira", "/F"], capture_output=True, text=True)
        if r.returncode == 0:
            removed.append("tarefa agendada")
    elif sys.platform == "darwin":
        p = _plist_path()
        if p.exists():
            subprocess.run(["launchctl", "unload", str(p)], capture_output=True)
            p.unlink()
            removed.append(str(p))
    else:
        paths = [_xdg_path()]
        if remove_menu_entry:
            paths.append(Path.home() / ".local" / "share" / "applications" / "itachi-capoeira.desktop")
        for p in paths:
            if p.exists():
                p.unlink()
                removed.append(str(p))
        sp = _systemd_path()
        if sp.exists():
            if shutil.which("systemctl"):
                subprocess.run(["systemctl", "--user", "disable", "itachi-capoeira.service"], capture_output=True)
            sp.unlink()
            removed.append(str(sp))
    return "Removido: " + ", ".join(removed) if removed else "Nada para remover."


def status() -> str:
    if sys.platform == "win32":
        r = subprocess.run(["schtasks", "/Query", "/TN", "ItachiCapoeira"], capture_output=True, text=True)
        return "ativado (Agendador de Tarefas)" if r.returncode == 0 else "desativado"
    if sys.platform == "darwin":
        return "ativado (LaunchAgent)" if _plist_path().exists() else "desativado"
    if _systemd_path().exists():
        return "ativado (systemd --user)"
    return "ativado (XDG autostart)" if _xdg_path().exists() else "desativado"
