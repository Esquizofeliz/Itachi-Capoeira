"""Saúde do sistema: reinicia/libera o Ollama quando preciso e monitora disco, GPU e containers."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import psutil

from .config import Config
from .llm import Ollama
from .screen import notify_desktop

log = logging.getLogger("itachi_capoeira.health")


def start_ollama(llm: Ollama, wait: int = 30) -> bool:
    """Tenta iniciar o Ollama de forma portátil e espera ele responder."""
    if llm.alive():
        return True
    if llm.cloud:        # nuvem: não há servidor local para iniciar
        return False
    exe = shutil.which("ollama")
    if not exe:
        for c in (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
                  Path("/Applications/Ollama.app/Contents/Resources/ollama"),
                  Path("/opt/homebrew/bin/ollama"), Path("/usr/local/bin/ollama")):
            if c.exists():
                exe = str(c)
                break
    # Nunca abrimos o app/janela do Ollama (nem 'open -a Ollama', nem 'ollama app.exe'): só o servidor, sem interface.
    if not exe and sys.platform in ("darwin", "win32"):
        log.warning("Não achei o executável do Ollama. Instale em https://ollama.com/download e rode: itachi-capoeira setup")
    try:
        if sys.platform not in ("darwin", "win32"):
            r = subprocess.run(["systemctl", "--user", "start", "ollama"], capture_output=True, timeout=10)
            if r.returncode != 0 and shutil.which("systemctl"):
                subprocess.run(["systemctl", "start", "ollama"], capture_output=True, timeout=10)
        if not llm.alive() and exe:
            kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
            if sys.platform == "win32":
                kwargs["creationflags"] = 0x00000008 | 0x08000000
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen([exe, "serve"], **kwargs)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("Não consegui iniciar o Ollama automaticamente: %s", e)
        return False
    for _ in range(wait):
        if llm.alive():
            return True
        time.sleep(1)
    return llm.alive()


def check_ollama(cfg: Config, llm: Ollama | None = None) -> dict:
    """Equivalente ao antigo ollama-health.sh, porém portátil. Devolve um resumo do que fez."""
    llm = llm or Ollama.from_config(cfg)
    if llm.cloud:        # nuvem: RAM/VRAM local não importam; só confere se está acessível
        ok = llm.alive()
        log.info("Health: nuvem do Ollama %s", "acessível" if ok else "INACESSÍVEL (internet/chave?)")
        return {"action": "none" if ok else "failed", "cloud": True}
    vm = psutil.virtual_memory()
    free_gb = vm.available / 1024 ** 3
    summary = {"ram_percent": vm.percent, "free_gb": round(free_gb, 1), "action": "none"}
    log.info("Health: RAM %.0f%% (%.1f GB livres)", vm.percent, free_gb)
    if not llm.alive():
        log.warning("Ollama não responde — tentando iniciar...")
        summary["action"] = "started" if start_ollama(llm) else "failed"
        return summary
    if vm.percent >= cfg.HEALTH_RAM_PERCENT or free_gb < cfg.HEALTH_MIN_FREE_RAM_GB:
        names = llm.unload_all()
        summary["action"] = "unloaded"
        summary["models"] = names
        log.warning("RAM crítica: modelos descarregados: %s", ", ".join(names) or "(nenhum carregado)")
    return summary


# ---------------------------------------------------------------------- monitor proativo
def _disk_path(cfg: Config) -> str:
    if cfg.DISK_PATH:
        return cfg.DISK_PATH
    return str(Path.home().anchor or Path.home())


def gpu_temperature() -> int | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=8).stdout.strip().splitlines()
        return int(out[0]) if out and out[0].strip().isdigit() else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def proactive_checks(cfg: Config) -> list[str]:
    """Devolve a lista de alertas (vazia = tudo certo)."""
    alerts: list[str] = []
    if shutil.which("docker"):
        try:
            out = subprocess.run(["docker", "ps", "--format", "{{.Names}}", "--filter", "status=restarting"],
                                 capture_output=True, text=True, timeout=10).stdout.split()
            if out:
                alerts.append("Container com problemas: " + ", ".join(out))
        except (OSError, subprocess.SubprocessError):
            pass
    temp = gpu_temperature()
    if temp is not None and temp > cfg.GPU_TEMP_LIMIT:
        alerts.append(f"GPU em {temp} graus Celsius — considere verificar a refrigeração")
    try:
        du = shutil.disk_usage(_disk_path(cfg))
        pct = du.used / du.total * 100
        if pct > cfg.DISK_LIMIT_PERCENT:
            alerts.append(f"Disco em {pct:.0f} por cento — faça uma limpeza")
    except OSError:
        pass
    return alerts


def notify_alerts(cfg: Config, speaker, alerts: list[str]) -> None:
    for msg in alerts:
        log.warning("⚠️  %s", msg)
        notify_desktop(cfg.NAME, msg)
        if cfg.NOTIFY_ON_ERRORS:
            speaker.speak(f"{cfg.NAME}. {msg}")
