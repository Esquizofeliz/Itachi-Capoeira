"""Captura de tela (mss, com fallback para ferramentas do sistema) e área de transferência."""
from __future__ import annotations

import base64
import io
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time

log = logging.getLogger("itachi_capoeira.screen")


class ScreenError(RuntimeError):
    pass


def _prepare(img, max_px: int) -> bytes:
    from PIL import Image
    img = img.convert("RGB")
    if max(img.size) > max_px:
        img.thumbnail((max_px, max_px), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _grab_mss(monitor: int):
    import mss
    from PIL import Image
    with mss.mss() as sct:
        mons = sct.monitors
        idx = monitor if 0 <= monitor < len(mons) else (1 if len(mons) > 1 else 0)
        raw = sct.grab(mons[idx])
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def _grab_cli():
    from PIL import Image
    out = os.path.join(tempfile.gettempdir(), f"itachi-capoeira-shot-{os.getpid()}-{int(time.time() * 1000)}.png")
    candidates: list[list[str]] = []
    if sys.platform == "darwin":
        candidates.append(["screencapture", "-x", out])
    elif sys.platform.startswith("linux"):
        if os.environ.get("WAYLAND_DISPLAY"):
            candidates += [["grim", out], ["gnome-screenshot", "-f", out], ["spectacle", "-b", "-n", "-o", out]]
        candidates += [["scrot", "-o", out], ["gnome-screenshot", "-f", out], ["import", "-window", "root", out]]
    for cmd in candidates:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=15)
                if os.path.getsize(out) > 0:
                    img = Image.open(out)
                    img.load()
                    return img
            except (OSError, subprocess.SubprocessError):
                continue
            finally:
                try:
                    os.unlink(out)
                except OSError:
                    pass
    raise ScreenError("Nenhum método de captura de tela funcionou.")


def capture_jpeg(max_px: int = 1600, monitor: int = 1) -> bytes:
    try:
        img = _grab_mss(monitor)
    except Exception as e:  # noqa: BLE001
        log.debug("mss falhou (%s); tentando ferramentas do sistema", e)
        try:
            img = _grab_cli()
        except ScreenError as e2:
            hint = ""
            if sys.platform == "darwin":
                hint = " No macOS, conceda 'Gravação de Tela' ao Terminal/Python em Ajustes do Sistema > Privacidade."
            elif os.environ.get("WAYLAND_DISPLAY"):
                hint = " No Wayland instale 'grim' (ou use uma sessão X11)."
            raise ScreenError(f"{e2}{hint}") from e
    return _prepare(img, max_px)


def to_b64(jpeg: bytes) -> str:
    return base64.b64encode(jpeg).decode("ascii")


# ---------------------------------------------------------------------- clipboard
def set_clipboard(text: str) -> bool:
    """Copia texto. Para Windows usa variável de ambiente (sem interpolar em comando)."""
    try:
        if sys.platform == "win32":
            env = dict(os.environ, ITACHI_CAPOEIRA_TEXT=text)
            r = subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $env:ITACHI_CAPOEIRA_TEXT"],
                               env=env, capture_output=True, timeout=10)
            return r.returncode == 0
        if sys.platform == "darwin":
            return subprocess.run(["pbcopy"], input=text.encode("utf-8"), timeout=10).returncode == 0
        cmds = []
        if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
            cmds.append(["wl-copy"])
        if shutil.which("xclip"):
            cmds.append(["xclip", "-selection", "clipboard"])
        if shutil.which("xsel"):
            cmds.append(["xsel", "--clipboard", "--input"])
        if shutil.which("wl-copy") and ["wl-copy"] not in cmds:
            cmds.append(["wl-copy"])
        for cmd in cmds:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                p.stdin.write(text.encode("utf-8"))
                p.stdin.close()
                p.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                # xclip/xsel ficam vivos servindo a seleção: isso é normal
                pass
            if p.poll() in (None, 0):
                return True
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("Falha ao copiar para a área de transferência: %s", e)
    return False


def paste_keystroke() -> bool:
    """Envia Ctrl+V (Cmd+V no macOS) para a janela ativa."""
    try:
        from pynput.keyboard import Controller, Key
        kb = Controller()
        mod = Key.cmd if sys.platform == "darwin" else Key.ctrl
        time.sleep(0.15)
        with kb.pressed(mod):
            kb.press("v")
            kb.release("v")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("Não consegui colar automaticamente (%s). O texto está na área de transferência: use Ctrl+V.", e)
        return False


def notify_desktop(title: str, message: str) -> None:
    """Notificação visual nativa (silenciosa se a ferramenta não existir)."""
    try:
        if sys.platform == "darwin":
            script = 'display notification (system attribute "ITACHI_CAPOEIRA_MSG") with title (system attribute "ITACHI_CAPOEIRA_TITLE")'
            subprocess.run(["osascript", "-e", script], env=dict(os.environ, ITACHI_CAPOEIRA_MSG=message, ITACHI_CAPOEIRA_TITLE=title),
                           capture_output=True, timeout=5)
        elif sys.platform.startswith("linux") and shutil.which("notify-send"):
            subprocess.run(["notify-send", title, message], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass
