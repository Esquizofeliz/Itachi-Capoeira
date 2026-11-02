"""Ollama sempre sem interface + comandos 'gráfico' e 'mobile' (com aliases -mobile / -gráfico)."""
import unittest
from types import SimpleNamespace
from unittest import mock

from itachi_capoeira import cli, health


class OllamaHeadless(unittest.TestCase):
    def run_start(self, platform):
        llm = mock.Mock(cloud=False)
        llm.alive.side_effect = [False, False, True]
        popen = mock.Mock()
        run = mock.Mock(return_value=SimpleNamespace(returncode=0))
        with mock.patch.object(health.sys, "platform", platform), \
                mock.patch.object(health.shutil, "which", side_effect=lambda n: "/x/ollama" if n == "ollama" else None), \
                mock.patch.object(health.subprocess, "Popen", popen), mock.patch.object(health.subprocess, "run", run), \
                mock.patch.object(health.time, "sleep"):
            health.start_ollama(llm, wait=2)
        return popen, run

    def test_never_opens_the_ollama_app_on_any_platform(self):
        for platform in ("darwin", "win32", "linux"):
            popen, run = self.run_start(platform)
            cmds = [c.args[0] for c in popen.call_args_list] + [c.args[0] for c in run.call_args_list]
            flat = " ".join(" ".join(map(str, c)) for c in cmds)
            self.assertNotIn("open", [c[0] for c in cmds], platform)
            self.assertNotIn("ollama app", flat, platform)
            self.assertNotIn("-a Ollama", flat, platform)
            self.assertIn("serve", [c.args[0][-1] for c in popen.call_args_list], platform)   # só o servidor

    def test_windows_server_has_no_window(self):
        popen, _ = self.run_start("win32")
        self.assertTrue(popen.call_args.kwargs["creationflags"] & 0x08000000)           # CREATE_NO_WINDOW


class Commands(unittest.TestCase):
    def parse(self, *argv):
        parser = cli.build_parser()
        return parser.parse_args(list(argv))

    def test_subcommands_exist(self):
        self.assertIs(self.parse("mobile").fn, cli.cmd_mobile)
        for name in ("grafico", "gráfico", "gui"):
            self.assertIs(self.parse(name).fn, cli.cmd_grafico)

    def test_gui_args(self):
        with mock.patch("itachi_capoeira.gui.main", return_value=0) as m:
            cli.cmd_grafico(None, SimpleNamespace(port=9000, no_browser=True))
            m.assert_called_with(["--port", "9000", "--no-browser"])
            cli.cmd_mobile(None, SimpleNamespace(port=8765))
            m.assert_called_with(["--port", "8765", "--usb", "--no-browser"])

    def test_dash_aliases(self):
        for typed, expected in (("-mobile", "mobile"), ("--mobile", "mobile"), ("-gráfico", "grafico"),
                                ("--grafico", "grafico"), ("gráfico", "grafico"), ("-GRÁFICO", "grafico")):
            self.assertEqual(cli.normalize_argv([typed, "--port", "9"]), [expected, "--port", "9"], typed)
        self.assertEqual(cli.normalize_argv(["trigger", "-mobile"]), ["trigger", "-mobile"])   # só o 1º argumento
        self.assertEqual(cli.normalize_argv([]), [])

    def test_main_runs_mobile_for_dash_form(self):
        with mock.patch("itachi_capoeira.gui.main", return_value=0) as m, \
                mock.patch.object(cli.config, "load", return_value=SimpleNamespace()):
            self.assertEqual(cli.main(["-mobile"]), 0)
        m.assert_called_with(["--port", "8765", "--usb", "--no-browser"])


if __name__ == "__main__":
    unittest.main()
