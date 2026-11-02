"""O instalador não deve deixar o Itachi iniciar com a sessão por padrão."""
import unittest
from types import SimpleNamespace
from unittest import mock

import install


class AutostartDefault(unittest.TestCase):
    def test_default_disables_autostart(self):
        calls = []
        proc = SimpleNamespace(returncode=0, stdout="Nada para remover.", stderr="")
        with mock.patch.object(install, "ARGS", SimpleNamespace(autostart=False), create=True), \
             mock.patch.object(install.subprocess, "run", side_effect=lambda *a, **k: (calls.append(a[0]) or proc)), \
             mock.patch.object(install, "info") as info, mock.patch.object(install, "warn"), mock.patch.object(install, "ok"):
            install.setup_autostart()
        self.assertEqual(calls[0][-2:], ["autostart", "disable"])
        info.assert_called_once()

    def test_only_explicit_flag_enables_autostart(self):
        calls = []
        proc = SimpleNamespace(returncode=0, stdout="enabled", stderr="")
        with mock.patch.object(install, "ARGS", SimpleNamespace(autostart=True), create=True), \
             mock.patch.object(install.subprocess, "run", side_effect=lambda *a, **k: (calls.append(a[0]) or proc)), \
             mock.patch.object(install, "ok") as ok, mock.patch.object(install, "warn"), mock.patch.object(install, "info"):
            install.setup_autostart()
        self.assertEqual(calls[0][-2:], ["autostart", "enable"])
        ok.assert_called_once_with("enabled")


if __name__ == "__main__":
    unittest.main()
