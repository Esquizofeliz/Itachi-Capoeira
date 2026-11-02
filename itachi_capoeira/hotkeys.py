"""Atalhos globais (pynput). Em ambientes sem suporte (Wayland, sem permissão no macOS) avisa e segue sem eles."""
from __future__ import annotations

import logging
import os
import sys
from typing import Callable

log = logging.getLogger("itachi_capoeira.hotkeys")


def _session_warning() -> str | None:
    if sys.platform.startswith("linux"):
        if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            return ("Sessão Wayland: o pynput só enxerga teclas em janelas XWayland, então não é usado. "
                    "Os atalhos globais vêm do desktop ('itachi-capoeira shortcuts install').")
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            return "Sem ambiente gráfico (DISPLAY ausente): atalhos desativados."
    return None


class HotkeyManager:
    def __init__(self, mapping: dict[str, Callable[[], None]]):
        self.mapping = mapping
        self.listener = None

    def start(self) -> bool:
        warn = _session_warning()
        if warn:
            log.warning(warn)
            return False
        try:
            from pynput import keyboard
        except Exception as e:  # noqa: BLE001
            log.warning("pynput indisponível (%s): atalhos desativados.", e)
            return False
        valid: dict[str, Callable[[], None]] = {}
        for combo, fn in self.mapping.items():
            if not combo:
                continue
            try:
                keyboard.HotKey.parse(combo)
                valid[combo] = fn
            except Exception as e:  # noqa: BLE001
                log.warning("Atalho inválido %r (%s) — ignorado.", combo, e)
        if not valid:
            return False
        try:
            self.listener = keyboard.GlobalHotKeys(valid)
            self.listener.start()
        except Exception as e:  # noqa: BLE001
            log.warning("Não consegui registrar atalhos globais: %s", e)
            return False
        if sys.platform == "darwin":
            log.info("macOS: se os atalhos não responderem, conceda 'Monitoramento de Entrada' e 'Acessibilidade' "
                     "ao Terminal/Python em Ajustes do Sistema > Privacidade e Segurança.")
        return True

    def stop(self) -> None:
        if self.listener is not None:
            try:
                self.listener.stop()
            except Exception:  # noqa: BLE001
                pass
            self.listener = None
