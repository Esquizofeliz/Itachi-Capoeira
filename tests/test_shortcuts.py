"""Testes dos atalhos do desktop (gsettings simulado em memória)."""
import os
import re
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from itachi_capoeira import shortcuts as sc

LIST = "org.gnome.settings-daemon.plugins.media-keys"


class FakeGsettings:
    """Imita `gsettings get/set/reset` o bastante para os atalhos personalizados."""

    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.calls = []

    def __call__(self, cmd, capture_output=True, text=True, timeout=15):
        assert cmd[0] == "gsettings"
        op, schema, key, *rest = cmd[1:]
        self.calls.append(cmd)
        k = (schema, key)
        if op == "get":
            if k not in self.store:
                return SimpleNamespace(returncode=0, stdout="@as []\n" if key == "custom-keybindings" else "''\n", stderr="")
            v = self.store[k]
            if isinstance(v, list):
                return SimpleNamespace(returncode=0, stdout=("[" + ", ".join(f"'{x}'" for x in v) + "]") if v else "@as []", stderr="")
            return SimpleNamespace(returncode=0, stdout="'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'\n", stderr="")
        if op == "set":
            raw = rest[0]
            if raw.startswith("[") or raw.startswith("@as"):
                self.store[k] = re.findall(r"'([^']*)'", raw)
            else:
                self.store[k] = raw[1:-1].replace("\\'", "'").replace("\\\\", "\\")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if op == "reset":
            self.store.pop(k, None)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(cmd)


def cfg(**kw):
    base = dict(HOTKEY_SCREEN="<f9>", HOTKEY_VOICE="<f8>", HOTKEY_TALK="<f7>", HOTKEY_STOP="<f10>",
                AUTO_DESKTOP_SHORTCUTS=True)
    base.update(kw)
    return SimpleNamespace(**base)


GNOME_ENV = {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME", "XDG_SESSION_TYPE": "wayland"}


class ToGnome(unittest.TestCase):
    def test_conversions(self):
        self.assertEqual(sc.to_gnome("<f9>"), "F9")
        self.assertEqual(sc.to_gnome("<ctrl>+<print_screen>"), "<Ctrl>Print")
        self.assertEqual(sc.to_gnome("<cmd>+<shift>+J"), "<Super><Shift>j")
        self.assertEqual(sc.to_gnome("<ctrl>+<alt>+t"), "<Ctrl><Alt>t")

    def test_invalid(self):
        self.assertIsNone(sc.to_gnome(""))
        self.assertIsNone(sc.to_gnome("<banana>"))
        self.assertIsNone(sc.to_gnome("<f99>"))
        self.assertIsNone(sc.to_gnome("t+<ctrl>"))


class Install(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, GNOME_ENV)
        p.start()
        self.addCleanup(p.stop)

    def test_install_keeps_other_shortcuts_and_is_idempotent(self):
        other = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/"
        gs = FakeGsettings({(LIST, "custom-keybindings"): [other],
                            (f"{sc.SCHEMA_ITEM}:{other}", "name"): "Terminal",
                            (f"{sc.SCHEMA_ITEM}:{other}", "binding"): "F9"})   # conflita com F9
        ok, msg = sc.install(cfg(), gs)
        self.assertTrue(ok, msg)
        self.assertIn("Terminal", msg)                       # avisou do conflito
        paths = gs.store[(LIST, "custom-keybindings")]
        self.assertEqual(paths[0], other)                    # preservou o seu
        self.assertEqual(len(paths), 5)
        st = sc.status(gs)
        self.assertEqual(set(st), {"screen", "voice", "talk", "stop"})
        self.assertEqual(st["screen"]["binding"], "F9")
        self.assertTrue(st["talk"]["command"].endswith("trigger talk --start"))
        n = len(paths)
        ok, _ = sc.install(cfg(), gs)                        # de novo: não duplica
        self.assertEqual(len(gs.store[(LIST, "custom-keybindings")]), n)

    def test_command_with_spaces_roundtrips(self):
        gs = FakeGsettings()
        with mock.patch.object(sc, "launcher", return_value=sc.Path("/home/a b/it'achi/itachi-capoeira")):
            sc.install(cfg(), gs)
            self.assertEqual(sc.status(gs)["stop"]["command"], sc.command_for("stop"))

    def test_remove_only_ours(self):
        other = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/"
        gs = FakeGsettings({(LIST, "custom-keybindings"): [other]})
        sc.install(cfg(), gs)
        ok, _ = sc.remove(gs)
        self.assertTrue(ok)
        self.assertEqual(gs.store[(LIST, "custom-keybindings")], [other])
        self.assertEqual(sc.status(gs), {})

    def test_ensure_does_not_override_user_changed_key(self):
        gs = FakeGsettings()
        sc.install(cfg(), gs)
        path = sc.status(gs)["screen"]["path"]
        gs.store[(f"{sc.SCHEMA_ITEM}:{path}", "binding")] = "<Super>s"     # você mudou nas Configurações
        msg = sc.ensure(cfg(), gs)
        self.assertIn("já configurados", msg)
        self.assertEqual(sc.status(gs)["screen"]["binding"], "<Super>s")

    def test_ensure_recreates_missing(self):
        gs = FakeGsettings()
        msg = sc.ensure(cfg(), gs)
        self.assertIn("registrados", msg)
        self.assertEqual(len(sc.status(gs)), 4)

    def test_ensure_skips_on_x11_or_when_disabled(self):
        with mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "x11"}):
            self.assertIsNone(sc.ensure(cfg(), FakeGsettings()))
        self.assertIsNone(sc.ensure(cfg(AUTO_DESKTOP_SHORTCUTS=False), FakeGsettings()))

    def test_unsupported_desktop(self):
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}):
            ok, msg = sc.install(cfg(), FakeGsettings())
        self.assertFalse(ok)
        self.assertIn("trigger screen --start", msg)

    def test_invalid_key_is_skipped(self):
        gs = FakeGsettings()
        ok, msg = sc.install(cfg(HOTKEY_TALK="<banana>"), gs)
        self.assertTrue(ok)
        self.assertNotIn("talk", sc.status(gs))
        self.assertIn("HOTKEY_TALK", msg)


class Hotkeys(unittest.TestCase):
    def test_wayland_never_uses_pynput(self):
        from itachi_capoeira import hotkeys
        with mock.patch.object(hotkeys.sys, "platform", "linux"), \
                mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"}):
            self.assertIn("Wayland", hotkeys._session_warning())


if __name__ == "__main__":
    unittest.main()
