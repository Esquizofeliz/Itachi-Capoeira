"""Interface de linha de comando: itachi-capoeira <comando>."""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from . import __version__, autostart, config
from .config import LOG_DIR, MEMORY_FILE


def _utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # emojis no console do Windows
        except (AttributeError, ValueError):
            pass


def _assistant(cfg, console: bool = True):
    from .assistant import Assistant
    from .daemon import setup_logging
    setup_logging(console=console)
    return Assistant(cfg)


def cmd_run(cfg, _a) -> int:
    from .daemon import Daemon, setup_logging
    setup_logging(console=True)
    return Daemon(cfg).run()


def cmd_start(cfg, _a) -> int:
    from .daemon import read_pid, start_background
    _configure_shortcuts(cfg)
    if read_pid():
        print(f"{cfg.NAME} já está rodando (PID {read_pid()}).")
        return 0
    pid = start_background()
    if pid:
        print(f"✅ {cfg.NAME} iniciado em segundo plano. Veja: itachi-capoeira status | itachi-capoeira logs")
        return 0
    return 1 if not read_pid() else 0


def cmd_stop(cfg, _a) -> int:
    from .daemon import stop_background
    print("🛑 Parado." if stop_background() else "Não estava rodando.")
    return 0


def cmd_restart(cfg, a) -> int:
    from .daemon import stop_background
    stop_background()
    time.sleep(1)
    return cmd_start(cfg, a)


def cmd_status(cfg, _a) -> int:
    from .daemon import read_pid
    pid = read_pid()
    print(f"{cfg.NAME} ONLINE (PID {pid})" if pid else f"{cfg.NAME} OFFLINE")
    print("Início automático:", autostart.status())
    return 0 if pid else 3


def cmd_logs(cfg, _a) -> int:
    path = LOG_DIR / "itachi-capoeira.log"
    if not path.exists():
        print("Ainda não há logs.")
        return 0
    print(f"📜 {path}  (Ctrl+C para sair)\n")
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()[-30:]
        sys.stdout.write("".join(lines))
        try:
            while True:
                line = f.readline()
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                else:
                    time.sleep(0.4)
        except KeyboardInterrupt:
            pass
    return 0


def cmd_screen(cfg, a) -> int:
    asst = _assistant(cfg)
    reply = asst.describe_screen(" ".join(a.question) or None, speak=not a.no_speak)
    if a.no_speak:
        print(reply)
    return 0


def cmd_voice(cfg, a) -> int:
    asst = _assistant(cfg)
    text = asst.dictate(paste=False if a.no_paste else None)
    if text:
        print(text)
    return 0 if text else 1


def cmd_talk(cfg, a) -> int:
    _assistant(cfg).converse()
    return 0


def cmd_ask(cfg, a) -> int:
    reply = _assistant(cfg).ask(" ".join(a.text), speak=not a.no_speak)
    if a.no_speak:
        print(reply)
    return 0


def cmd_say(cfg, a) -> int:
    ok = _assistant(cfg).say(" ".join(a.text))
    return 0 if ok else 1


def _configure_shortcuts(cfg) -> None:
    """Registra os atalhos globais do desktop (Wayland/GNOME) se ainda não existirem. Silencioso quando não se aplica."""
    from . import shortcuts
    try:
        msg = shortcuts.ensure(cfg)
    except Exception as e:  # noqa: BLE001
        msg = f"Atalhos do desktop falharam: {e}"
    if msg:
        print("⌨️ ", msg)


def cmd_grafico(cfg, a) -> int:
    """Interface gráfica no navegador (o Ollama continua sem janela)."""
    from . import gui
    return gui.main(["--port", str(a.port)] + (["--no-browser"] if a.no_browser else []))


def cmd_mobile(cfg, a) -> int:
    """Extensão do celular: liga o servidor local + o cabo USB (adb reverse) e abre a página no celular."""
    from . import gui
    print("📱 Modo celular: conecte o cabo USB, ative a 'Depuração USB' e aceite a permissão no celular.")
    print(f"   Se não abrir sozinho, no celular acesse: http://localhost:{a.port}/mobile/\n")
    return gui.main(["--port", str(a.port), "--usb", "--no-browser"])


def cmd_audiotest(cfg, _a) -> int:
    from . import audiotest
    print("🔊 Testando a voz (você deve ouvir uma frase)...\n")
    r = audiotest.run(cfg)
    print(audiotest.format_report(r))
    return 0 if r["ok"] else 1


def cmd_up(cfg, _a) -> int:
    """Um comando só: registra os atalhos, liga o daemon e confirma as 4 ações (screen, voice, talk, stop)."""
    from . import shortcuts
    from .daemon import read_pid, start_background
    _configure_shortcuts(cfg)
    pid = read_pid() or start_background()
    if not pid:
        print("❌ O daemon não subiu. Veja: itachi-capoeira logs")
        return 1
    print(f"✅ {cfg.NAME} ligado (PID {pid}). Ações prontas:\n")
    bound: dict[str, str] = {}
    if shortcuts.is_wayland():
        try:
            bound = {n: d["binding"] for n, d in shortcuts.status().items()}
        except Exception:  # noqa: BLE001
            pass
    for name, key, title in shortcuts.ACTIONS:
        k = bound.get(name) or str(getattr(cfg, key, "")).replace("<", "").replace(">", "").upper() or "—"
        print(f"   {k:<10} {name:<7} {title.split(': ', 1)[-1]}")
    print("\n   Teste sem teclado:  itachi-capoeira trigger screen|voice|talk|stop")
    return 0


def cmd_trigger(cfg, a) -> int:
    from .daemon import read_pid, send_trigger, start_background
    if not a.name:                      # sem ação: configura os atalhos e mostra como usar
        from . import shortcuts
        if shortcuts.is_wayland() or shortcuts.desktop_supported():
            ok, msg = shortcuts.install(cfg)
            print(msg)
        print("\nUso: itachi-capoeira trigger screen|voice|talk|stop [--start]")
        return 0
    if not read_pid():
        if a.name == "stop":
            return 0                         # nada para interromper
        if not getattr(a, "start", False):
            print("O Itachi Capoeira não está rodando. Inicie com: itachi-capoeira start")
            return 1
        if not start_background():           # --start: liga o daemon e depois envia o gatilho
            return 1
    send_trigger(a.name)
    print(f"Gatilho '{a.name}' enviado.")
    return 0


def cmd_shortcuts(cfg, a) -> int:
    from . import shortcuts
    try:
        if a.action == "install":
            ok, msg = shortcuts.install(cfg)
        elif a.action == "remove":
            ok, msg = shortcuts.remove()
        else:
            ok, why = shortcuts.available()
            if not ok:
                print(why)
                return 1
            st = shortcuts.status()
            print(f"Sessão: {os.environ.get('XDG_SESSION_TYPE', '?')} | desktop: {os.environ.get('XDG_CURRENT_DESKTOP', '?')}")
            if not st:
                print("Nenhum atalho do Itachi Capoeira registrado. Rode: itachi-capoeira shortcuts install")
                return 1
            for n, d in sorted(st.items()):
                print(f"   {d['binding']:<12} → {n}")
            return 0
    except Exception as e:  # noqa: BLE001
        print("❌", e)
        return 1
    print(msg)
    return 0 if ok else 1


def cmd_memory(cfg, _a) -> int:
    from .memory import Memory
    items = Memory(MEMORY_FILE, cfg.MEMORY_MAX_ITEMS).recent()
    if not items:
        print("(memória vazia)")
    for it in items:
        print(f"[{it['type']}] {str(it['content'])[:160]}")
    return 0


def cmd_clear_memory(cfg, _a) -> int:
    from .memory import Memory
    Memory(MEMORY_FILE, cfg.MEMORY_MAX_ITEMS).clear()
    print("Memória limpa.")
    return 0


def cmd_health(cfg, _a) -> int:
    from .daemon import setup_logging
    from .health import check_ollama, proactive_checks
    setup_logging(console=True)
    print(check_ollama(cfg))
    alerts = proactive_checks(cfg)
    print("Alertas:", alerts or "nenhum")
    return 0


def cmd_doctor(cfg, a) -> int:
    from . import doctor
    return doctor.run(cfg, deep=a.deep)


def cmd_setup(cfg, a) -> int:
    from . import setup
    code = setup.run(cfg, a.tier, a.skip_models, a.skip_tts, a.skip_whisper)
    _configure_shortcuts(cfg)
    return code


def cmd_cloud(cfg, a) -> int:
    from . import cloud
    if a.action == "setup":
        return cloud.enable(cfg, a.key, a.chat_model, a.vision_model)
    if a.action == "off":
        return cloud.disable(cfg)
    return cloud.status(cfg)


def cmd_autostart(cfg, a) -> int:
    try:
        if a.action == "enable":
            print(autostart.enable("systemd" if a.systemd else "auto"))
        elif a.action == "disable":
            print(autostart.disable())
        else:
            print("Início automático:", autostart.status())
    except Exception as e:  # noqa: BLE001
        print("❌", e)
        return 1
    return 0


def cmd_config(cfg, _a) -> int:
    for k, v in sorted(cfg.as_dict(mask_secrets=True).items()):
        print(f"{k}={v}")
    return 0


def cmd_demo(cfg, a) -> int:
    """Pipeline completo, etapa por etapa: hardware → modelos → visão → raciocínio → voz."""
    from . import hardware, screen
    from .llm import Ollama, OllamaError
    asst = _assistant(cfg)
    ok = True

    def stage(n, title):
        print(f"\n[{n}/5] {title}")

    stage(1, "Hardware")
    gpu = hardware.detect_gpu()
    print("   ", hardware.describe(gpu, hardware.ram_total_gb()))

    stage(2, "Modelos")
    llm: Ollama = asst.llm
    if not llm.alive():
        print("    ❌ Ollama não está rodando.")
        return 1
    for m in dict.fromkeys([cfg.CHAT_MODEL, cfg.VISION_MODEL]):
        has = llm.has_model(m)
        print(f"    {'✅' if has else '❌'} {m}")
        ok &= has
    if not ok:
        print("    Rode: itachi-capoeira setup")
        return 1

    stage(3, "Visão (captura da tela)")
    try:
        jpeg = screen.capture_jpeg(int(cfg.SCREENSHOT_MAX_PX), int(cfg.SCREEN_MONITOR))
        print(f"    ✅ captura de {len(jpeg) // 1024} KB")
        desc = llm.chat(cfg.VISION_MODEL, [{"role": "user", "content": "Descreva esta tela em uma frase, em português."}],
                        images_b64=[screen.to_b64(jpeg)], num_ctx=cfg.NUM_CTX, timeout=300)
        print("    👁️ ", desc or "(sem resposta)")
        ok &= bool(desc)
    except Exception as e:  # noqa: BLE001
        print("    ❌", e)
        ok = False

    stage(4, "Raciocínio")
    try:
        reply = asst.answer("Apresente-se em duas frases curtas e diga que o teste de demonstração está funcionando.")
        print("    🧠", reply)
        ok &= bool(reply)
    except OllamaError as e:
        print("    ❌", e)
        return 1

    stage(5, "Voz")
    if a.no_speak:
        print("    ⏭️  ignorado (--no-speak)")
    else:
        spoke = asst.say(reply)
        print("    ✅ falou" if spoke else "    ⚠️  não consegui tocar o áudio (veja 'itachi-capoeira doctor')")
    print("\n🎉 Demo concluída!" if ok else "\n⚠️  Demo terminou com problemas.")
    return 0 if ok else 1


def cmd_test(cfg, _a) -> int:
    import unittest
    from .config import APP_DIR
    suite = unittest.defaultTestLoader.discover(str(APP_DIR / "tests"), top_level_dir=str(APP_DIR))
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if res.wasSuccessful() else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="itachi-capoeira", description=f"Itachi Capoeira v{__version__}")
    sub = p.add_subparsers(dest="cmd")

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        return sp

    add("run", cmd_run, "roda em primeiro plano (útil para depurar)")
    add("start", cmd_start, "inicia em segundo plano")
    add("stop", cmd_stop, "para o Itachi Capoeira")
    add("restart", cmd_restart, "reinicia")
    add("status", cmd_status, "mostra se está rodando")
    add("logs", cmd_logs, "acompanha o log em tempo real")
    sp = add("screen", cmd_screen, "captura a tela e o Itachi Capoeira descreve/fala (pergunta opcional)")
    sp.add_argument("question", nargs="*")
    sp.add_argument("--no-speak", action="store_true", help="só imprime, sem falar")
    sp = add("voice", cmd_voice, "grava sua voz → transcreve → copia (e cola)")
    sp.add_argument("--no-paste", action="store_true")
    add("talk", cmd_talk, "conversa por voz (você fala, ele responde falando)")
    sp = add("ask", cmd_ask, "pergunta por texto")
    sp.add_argument("text", nargs="+")
    sp.add_argument("--no-speak", action="store_true")
    sp = add("say", cmd_say, "fala um texto")
    sp.add_argument("text", nargs="+")
    sp = sub.add_parser("grafico", aliases=["gráfico", "gui"], help="abre a interface gráfica no navegador")
    sp.set_defaults(fn=cmd_grafico)
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--no-browser", action="store_true", help="não abre o navegador")
    sp = add("mobile", cmd_mobile, "extensão do celular por USB (abre a página no celular)")
    sp.add_argument("--port", type=int, default=8765)
    add("audiotest", cmd_audiotest, "testa a voz e mostra em qual etapa ela falha (síntese, saída ou player)")
    add("up", cmd_up, "liga tudo de uma vez: atalhos globais + daemon (screen, voice, talk, stop)")
    sp = add("trigger", cmd_trigger, "aciona uma função do Itachi Capoeira em execução (para atalhos do Wayland etc.)")
    sp.add_argument("name", nargs="?", choices=["screen", "voice", "talk", "stop"],
                    help="ação; sem ela, só configura os atalhos globais do desktop")
    sp.add_argument("--start", action="store_true", help="se o daemon não estiver rodando, liga antes de enviar")
    sp = add("shortcuts", cmd_shortcuts, "atalhos globais pelo desktop (GNOME/Wayland): install | remove | status")
    sp.add_argument("action", choices=["install", "remove", "status"], nargs="?", default="status")
    add("memory", cmd_memory, "mostra a memória recente")
    add("clear-memory", cmd_clear_memory, "limpa a memória")
    add("health", cmd_health, "verifica Ollama/RAM/GPU/disco agora")
    sp = add("doctor", cmd_doctor, "diagnóstico completo do ambiente")
    sp.add_argument("--deep", action="store_true", help="também testa LLM, voz e captura de tela de verdade")
    sp = add("setup", cmd_setup, "escolhe modelos pela sua VRAM e baixa tudo")
    sp.add_argument("--tier", choices=["xl", "m", "s", "cpu"], help="força um nível de modelos")
    sp.add_argument("--skip-models", action="store_true")
    sp.add_argument("--skip-tts", action="store_true")
    sp.add_argument("--skip-whisper", action="store_true")
    sp = add("autostart", cmd_autostart, "liga/desliga o início automático com o sistema")
    sp.add_argument("action", choices=["enable", "disable", "status"])
    sp.add_argument("--systemd", action="store_true", help="Linux: usa systemd --user em vez de XDG autostart")
    sp = add("cloud", cmd_cloud, "usa a nuvem do Ollama (plano gratuito, com chave de API): setup | status | off")
    sp.add_argument("action", choices=["setup", "status", "off"], nargs="?", default="status")
    sp.add_argument("--key", help="chave de API (evite: fica no histórico do shell; deixe o programa perguntar)")
    sp.add_argument("--chat-model", help="modelo de conversa (nome da nuvem, ex.: gpt-oss:120b)")
    sp.add_argument("--vision-model", help="modelo que descreve a tela")
    add("config", cmd_config, "mostra a configuração efetiva")
    sp = add("demo", cmd_demo, "demonstração completa: hardware → modelos → visão → raciocínio → voz")
    sp.add_argument("--no-speak", action="store_true")
    add("test", cmd_test, "roda os testes automatizados")
    return p


def normalize_argv(argv: list[str]) -> list[str]:
    """Aceita também as formas '-mobile', '--mobile', '-gráfico', '--grafico' como o subcomando."""
    argv = list(argv)
    if argv and argv[0].lstrip("-").lower() in ("mobile", "grafico", "gráfico"):
        argv[0] = argv[0].lstrip("-").lower().replace("á", "a")
    return argv


def main(argv: list[str] | None = None) -> int:
    _utf8()
    parser = build_parser()
    args = parser.parse_args(normalize_argv(sys.argv[1:] if argv is None else argv))
    if not getattr(args, "fn", None):
        parser.print_help()
        return 0
    cfg = config.load()
    try:
        return int(args.fn(cfg, args) or 0)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001
        from .assistant import Busy
        from .llm import OllamaError
        if isinstance(e, (OllamaError, Busy)):
            print(f"❌ {e}")
            return 1
        logging.getLogger("itachi_capoeira").exception("Erro inesperado")
        print(f"❌ Erro: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
