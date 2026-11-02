"""`itachi-capoeira up`: um comando que registra os atalhos, liga o daemon e lista as 4 ações."""
import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

from itachi_capoeira import cli

CFG = SimpleNamespace(NAME="Itachi", HOTKEY_SCREEN="<f9>", HOTKEY_VOICE="<f8>", HOTKEY_TALK="<f7>", HOTKEY_STOP="<f10>",
                      AUTO_DESKTOP_SHORTCUTS=True)


class Up(unittest.TestCase):
    def run_up(self, pid_running=None, started=4242):
        buf = io.StringIO()
        with mock.patch("itachi_capoeira.daemon.read_pid", return_value=pid_running), \
                mock.patch("itachi_capoeira.daemon.start_background", return_value=started) as sb, \
                mock.patch.object(cli, "_configure_shortcuts") as cs, redirect_stdout(buf):
            rc = cli.cmd_up(CFG, None)
        return rc, buf.getvalue(), sb, cs

    def test_starts_daemon_configures_shortcuts_and_lists_four_actions(self):
        rc, out, sb, cs = self.run_up()
        self.assertEqual(rc, 0)
        cs.assert_called_once()
        sb.assert_called_once()
        for word in ("screen", "voice", "talk", "stop", "F9", "F8", "F7", "F10"):
            self.assertIn(word, out)

    def test_does_not_restart_running_daemon(self):
        rc, out, sb, _ = self.run_up(pid_running=777)
        self.assertEqual(rc, 0)
        sb.assert_not_called()
        self.assertIn("777", out)

    def test_fails_clearly_when_daemon_does_not_start(self):
        rc, out, _, _ = self.run_up(started=0)
        self.assertEqual(rc, 1)
        self.assertIn("logs", out)

    def test_never_touches_api_keys(self):
        import inspect
        src = inspect.getsource(cli.cmd_up)
        self.assertNotIn("cloud", src)
        self.assertNotIn("API", src)


if __name__ == "__main__":
    unittest.main()
