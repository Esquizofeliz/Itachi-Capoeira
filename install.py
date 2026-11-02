#!/usr/bin/env python3
"""Instalador do Itachi Capoeira — Windows, macOS e Linux, em um único comando.

    Linux/macOS:  bash install.sh
    Windows:      install.bat          (ou: python install.py)

O que ele faz (tudo idempotente — pode rodar de novo sem medo):
  1. confere o Python;                          5. instala o Ollama (se faltar);
  2. instala dependências do sistema (Linux);   6. escolhe os modelos pela sua VRAM e baixa tudo;
  3. cria o ambiente virtual (.venv);           7. cria o comando 'itachi-capoeira' e (opcional) o início automático;
  4. instala as bibliotecas Python;             8. roda o diagnóstico final.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")
OLLAMA_URL = "http://127.0.0.1:11434"

ARGS: argparse.Namespace


# ---------------------------------------------------------------------- saída
def _enc() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def step(n: int, total: int, title: str) -> None:
    print(f"\n[{n}/{total}] {title}", flush=True)


def ok(msg: str) -> None:
    print(f"   ✅ {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"   ⚠️  {msg}", flush=True)


def info(msg: str) -> None:
    print(f"   {msg}", flush=True)


def fail(msg: str, code: int = 1):
    print(f"\n❌ {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


def confirm(question: str, default: bool = True) -> bool:
    if ARGS.yes or not sys.stdin or not sys.stdin.isatty():
        return default
    suffix = " [S/n] " if default else " [s/N] "
    ans = input(f"   ❓ {question}{suffix}").strip().lower()
    if not ans:
        return default
    return ans in ("s", "sim", "y", "yes")


def run(cmd: list[str], check: bool = True, quiet: bool = False, **kw) -> subprocess.CompletedProcess:
    kw.setdefault("text", True)
    if quiet:
        kw.update(stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        return subprocess.run(cmd, check=check, **kw)
    except FileNotFoundError:
        if check:
            raise
        return subprocess.CompletedProcess(cmd, 127, "", "")


def ollama_alive() -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(OLLAMA_URL + "/api/version", timeout=3):
            return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------- 1. Python
def check_python() -> None:
    v = sys.version_info
    ok(f"Python {v.major}.{v.minor}.{v.micro} em {sys.executable}")
    if v < (3, 10):
        fail("É preciso Python 3.10 ou mais novo. Baixe em https://www.python.org/downloads/")
    if v >= (3, 14):
        warn("Python 3.14+ ainda pode não ter pacotes prontos (onnxruntime/ctranslate2). Se falhar, use o 3.12.")


# ---------------------------------------------------------------------- 2. dependências do sistema
LINUX_PKGS = {
    "apt": ["libportaudio2", "libsndfile1", "xclip", "wl-clipboard", "espeak-ng", "libnotify-bin", "curl", "zstd"],
    "dnf": ["portaudio", "libsndfile", "xclip", "wl-clipboard", "espeak-ng", "libnotify", "curl", "zstd"],
    "pacman": ["portaudio", "libsndfile", "xclip", "wl-clipboard", "espeak-ng", "libnotify", "curl", "zstd"],
    "zypper": ["portaudio", "libsndfile1", "xclip", "wl-clipboard", "espeak-ng", "libnotify-tools", "curl", "zstd"],
}


def _sudo() -> list[str]:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return []
    return ["sudo"] if shutil.which("sudo") else []


def system_deps() -> None:
    if ARGS.skip_system_deps:
        info("ignorado (--skip-system-deps)")
        return
    if IS_WIN:
        ok("Windows: nada a instalar (PortAudio já vem nos pacotes Python)")
        return
    if IS_MAC:
        ok("macOS: nada a instalar (PortAudio já vem nos pacotes Python)")
        if not shutil.which("brew"):
            info("Dica: o Homebrew (https://brew.sh) facilita instalar o Ollama automaticamente.")
        return
    mgr = next((m for m in LINUX_PKGS if shutil.which(m if m != "apt" else "apt-get")), None)
    if not mgr:
        warn("Gerenciador de pacotes não reconhecido. Instale manualmente: PortAudio, libsndfile, xclip "
             "(ou wl-clipboard), espeak-ng.")
        return
    pkgs = LINUX_PKGS[mgr]
    sudo = _sudo()
    if sudo and not confirm(f"Instalar pacotes do sistema com sudo ({', '.join(pkgs)})?"):
        warn("Pulado. Se algo falhar depois, rode: itachi-capoeira doctor")
        return
    if mgr == "apt":
        run(sudo + ["apt-get", "update", "-qq"], check=False, quiet=True)
        cmd = sudo + ["apt-get", "install", "-y", "-qq", "-o", "Dpkg::Use-Pty=0", *pkgs]
    elif mgr == "dnf":
        cmd = sudo + ["dnf", "install", "-y", *pkgs]
    elif mgr == "pacman":
        cmd = sudo + ["pacman", "-S", "--needed", "--noconfirm", *pkgs]
    else:
        cmd = sudo + ["zypper", "--non-interactive", "install", *pkgs]
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    info("instalando (pode pedir sua senha de administrador)...")
    r = run(cmd, check=False, quiet=not sudo, env=env) if not sudo else run(cmd, check=False, env=env)
    if r.returncode == 0:
        ok("pacotes do sistema instalados")
        return
    # tenta um a um para não perder tudo por causa de um pacote que não existe na sua distro
    warn("Instalação em lote falhou; tentando pacote por pacote...")
    missing = []
    for p in pkgs:
        one = cmd[:-len(pkgs)] + [p]
        if run(one, check=False, quiet=True).returncode != 0:
            missing.append(p)
    if missing:
        warn("Não consegui instalar: " + ", ".join(missing) + " (alguns são opcionais; veja 'itachi-capoeira doctor')")
    else:
        ok("pacotes do sistema instalados")


# ---------------------------------------------------------------------- 3 e 4. venv + pip
def has_nvidia() -> bool:
    if not shutil.which("nvidia-smi"):
        return False
    r = run(["nvidia-smi", "-L"], check=False, quiet=True)
    return r.returncode == 0 and "GPU" in (r.stdout or "")


def make_venv() -> None:
    if ARGS.reinstall and VENV.exists():
        info("recriando .venv (--reinstall)")
        shutil.rmtree(VENV, ignore_errors=True)
    if VENV_PY.exists():
        ok(".venv já existe")
        return
    r = run([sys.executable, "-m", "venv", str(VENV)], check=False, quiet=True)
    if r.returncode != 0 or not VENV_PY.exists():
        msg = (r.stdout or "").strip()
        hint = ""
        if IS_LINUX:
            hint = "\n   No Debian/Ubuntu: sudo apt install python3-venv python3-pip"
        fail(f"Não consegui criar o ambiente virtual.\n{msg[-400:]}{hint}")
    ok(f"ambiente virtual criado em {VENV}")


def pip_install() -> None:
    pip = [str(VENV_PY), "-m", "pip"]
    run(pip + ["install", "--upgrade", "pip", "wheel", "-q", "--disable-pip-version-check"], check=False, quiet=True)
    info("Instalando bibliotecas (pode levar alguns minutos na primeira vez)...")
    r = run(pip + ["install", "-r", str(ROOT / "requirements.txt"), "--disable-pip-version-check",
                   "--progress-bar", "off", "-q"], check=False)
    if r.returncode != 0:
        fail("Falha ao instalar as dependências Python. Veja a mensagem acima.\n"
             "   Se o erro citar onnxruntime/ctranslate2, use o Python 3.12 (https://www.python.org/downloads/).")
    ok("bibliotecas principais instaladas")

    # atalhos globais (opcional)
    if IS_LINUX:
        r = run(pip + ["install", "--no-deps", "pynput", "six", "python-xlib", "-q", "--disable-pip-version-check"],
                check=False, quiet=True)
    else:
        r = run(pip + ["install", "-r", str(ROOT / "requirements-hotkeys.txt"), "-q", "--disable-pip-version-check"],
                check=False, quiet=True)
    if r.returncode == 0:
        ok("atalhos globais (pynput) instalados")
    else:
        warn("Atalhos globais indisponíveis — o Itachi Capoeira funciona igual via 'itachi-capoeira trigger ...'.")

    # CUDA para o Whisper
    if not ARGS.no_cuda and (IS_LINUX or IS_WIN) and platform.machine().lower() in ("x86_64", "amd64") and has_nvidia():
        info("GPU NVIDIA detectada: instalando bibliotecas CUDA para o Whisper (~1 GB)...")
        r = run(pip + ["install", "-r", str(ROOT / "requirements-cuda.txt"), "-q", "--disable-pip-version-check"],
                check=False, quiet=True)
        if r.returncode == 0:
            ok("CUDA para o Whisper instalado")
        else:
            warn("Não consegui instalar o CUDA via pip; o Whisper usará a CPU (o resto continua usando a GPU).")


# ---------------------------------------------------------------------- 5. Ollama
def _find_ollama() -> str | None:
    exe = shutil.which("ollama")
    if exe:
        return exe
    candidates = []
    if IS_WIN:
        candidates.append(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe")
    if IS_MAC:
        candidates += [Path("/Applications/Ollama.app/Contents/Resources/ollama"),
                       Path.home() / "Applications/Ollama.app/Contents/Resources/ollama",
                       Path("/opt/homebrew/bin/ollama"), Path("/usr/local/bin/ollama")]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "itachi-capoeira-installer"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def install_ollama() -> None:
    if ARGS.no_ollama:
        info("ignorado (--no-ollama)")
        return
    exe = _find_ollama()
    if exe:
        ok(f"Ollama já instalado ({exe})")
    else:
        if not confirm("O Ollama (motor dos modelos de IA) não está instalado. Instalar agora?"):
            warn("Sem o Ollama o Itachi Capoeira não consegue pensar. Instale em https://ollama.com/download")
            return
        try:
            if IS_LINUX:
                script = Path(tempfile.gettempdir()) / "ollama-install.sh"
                _download("https://ollama.com/install.sh", script)
                run(["sh", str(script)])
            elif IS_MAC:
                if shutil.which("brew"):
                    run(["brew", "install", "ollama"])
                else:
                    z = Path(tempfile.gettempdir()) / "Ollama-darwin.zip"
                    _download("https://ollama.com/download/Ollama-darwin.zip", z)
                    dest = Path.home() / "Applications"
                    dest.mkdir(exist_ok=True)
                    run(["unzip", "-q", "-o", str(z), "-d", str(dest)])   # sem abrir o app: usamos só o 'ollama serve'

            elif IS_WIN:
                if shutil.which("winget"):
                    r = run(["winget", "install", "--id", "Ollama.Ollama", "-e", "--silent",
                             "--accept-package-agreements", "--accept-source-agreements"], check=False)
                    if r.returncode != 0:
                        raise RuntimeError("winget falhou")
                else:
                    setup = Path(tempfile.gettempdir()) / "OllamaSetup.exe"
                    _download("https://ollama.com/download/OllamaSetup.exe", setup)
                    run([str(setup), "/SILENT"])
        except Exception as e:  # noqa: BLE001
            warn(f"Instalação automática do Ollama falhou ({e}). Instale manualmente: https://ollama.com/download")
            return
        exe = _find_ollama()
        if not exe:
            warn("Ollama instalado, mas ainda não achei o executável (abra um novo terminal e rode o instalador de novo).")
            return
        ok("Ollama instalado")
        if IS_WIN:      # o instalador do Windows abre o app/janela do Ollama sozinho: fechamos (o servidor sobe sem janela)
            subprocess.run(["taskkill", "/IM", "ollama app.exe"], capture_output=True)

    if not ollama_alive():
        info("Iniciando o servidor do Ollama...")
        try:
            if IS_LINUX and shutil.which("systemctl"):
                run(["systemctl", "start", "ollama"], check=False, quiet=True)
            if not ollama_alive() and exe:
                kw: dict = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                if IS_WIN:
                    kw["creationflags"] = 0x00000008 | 0x08000000
                else:
                    kw["start_new_session"] = True
                subprocess.Popen([exe, "serve"], **kw)
        except OSError as e:
            warn(f"Não consegui iniciar o Ollama sozinho: {e}")
        for _ in range(30):
            if ollama_alive():
                break
            time.sleep(1)
    if ollama_alive():
        ok("servidor do Ollama respondendo")
    else:
        warn("O Ollama não respondeu. Rode 'ollama serve' (sem janela) e depois: itachi-capoeira setup")


# ---------------------------------------------------------------------- 6. setup dos modelos
def run_setup() -> int:
    cmd = [str(VENV_PY), "-m", "itachi_capoeira", "setup"]
    if ARGS.tier:
        cmd += ["--tier", ARGS.tier]
    for flag in ("skip_models", "skip_tts", "skip_whisper"):
        if getattr(ARGS, flag):
            cmd.append("--" + flag.replace("_", "-"))
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")
    return subprocess.run(cmd, cwd=str(ROOT), env=env).returncode


# ---------------------------------------------------------------------- 7. comando e autostart
def make_launcher() -> None:
    if IS_WIN:
        ok(f"use:  {ROOT / 'itachi-capoeira.cmd'}   (dica: adicione a pasta do projeto ao PATH)")
        return
    (ROOT / "itachi-capoeira").chmod(0o755)
    bindir = Path.home() / ".local" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    link = bindir / "itachi-capoeira"
    try:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(ROOT / "itachi-capoeira")
        ok(f"comando 'itachi-capoeira' criado em {link}")
        if str(bindir) not in os.environ.get("PATH", "").split(os.pathsep):
            warn(f"Adicione {bindir} ao PATH (ex.: echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.bashrc) "
                 f"ou use {ROOT / 'itachi-capoeira'}")
    except OSError as e:
        warn(f"Não consegui criar o link ({e}); use {ROOT / 'itachi-capoeira'}")


def setup_cloud() -> None:
    """Opcional: usa a nuvem do Ollama (plano gratuito) com chave de API, em vez de modelos locais."""
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")
    r = subprocess.run([str(VENV_PY), "-m", "itachi_capoeira", "cloud", "setup"], cwd=str(ROOT), env=env)
    if r.returncode != 0:
        warn("Nuvem não configurada. Quando tiver a chave (https://ollama.com/settings/keys), rode: "
             "itachi-capoeira cloud setup")


def setup_shortcuts() -> None:
    """Linux/Wayland: o pynput não captura teclas globais; registra F7-F10 como atalhos do desktop."""
    if not IS_LINUX or os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland":
        return
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")
    r = subprocess.run([str(VENV_PY), "-m", "itachi_capoeira", "shortcuts", "install"], cwd=str(ROOT), env=env,
                       capture_output=True, text=True)
    (ok if r.returncode == 0 else warn)((r.stdout or r.stderr).strip())


def setup_autostart() -> None:
    """Por padrão, remove o início automático; só ativa com --autostart explícito."""
    action = "enable" if ARGS.autostart else "disable"
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    r = subprocess.run([str(VENV_PY), "-m", "itachi_capoeira", "autostart", action], cwd=str(ROOT), env=env,
                       capture_output=True, text=True)
    message = (r.stdout or r.stderr).strip()
    if r.returncode == 0:
        if ARGS.autostart:
            ok(message)
        else:
            info("Início automático desativado por padrão. " + message)
    else:
        warn(message or "Não foi possível ajustar o início automático.")


# ---------------------------------------------------------------------- main
def main() -> int:
    global ARGS
    _enc()
    ap = argparse.ArgumentParser(description="Instalador do Itachi Capoeira")
    ap.add_argument("-y", "--yes", action="store_true", help="responde 'sim' a tudo (sem perguntas)")
    ap.add_argument("--no-ollama", action="store_true", help="não instala/inicia o Ollama")
    ap.add_argument("--skip-system-deps", action="store_true", help="não instala pacotes do sistema (Linux)")
    ap.add_argument("--skip-models", action="store_true", help="não baixa os modelos do Ollama")
    ap.add_argument("--skip-tts", action="store_true", help="não baixa o Kokoro")
    ap.add_argument("--skip-whisper", action="store_true", help="não pré-baixa o Whisper")
    ap.add_argument("--tier", choices=["xl", "m", "s", "cpu"], help="força o nível de modelos (padrão: automático)")
    ap.add_argument("--cloud", action="store_true",
                    help="usa a nuvem do Ollama (plano gratuito, pede a chave de API) em vez de baixar modelos")
    ap.add_argument("--no-cuda", action="store_true", help="não instala as bibliotecas CUDA do pip")
    ap.add_argument("--autostart", action="store_true", help="liga o início automático")
    ap.add_argument("--no-autostart", action="store_true", help="mantém o início automático desativado (padrão)")
    ap.add_argument("--reinstall", action="store_true", help="recria o .venv do zero")
    ARGS = ap.parse_args()

    print("═" * 60)
    print("🤖 ITACHI CAPOEIRA — INSTALADOR")
    print(f"   {platform.system()} {platform.release()} · {platform.machine()} · {ROOT}")
    print("═" * 60)

    total = 7
    step(1, total, "Verificando o Python")
    check_python()
    step(2, total, "Dependências do sistema")
    system_deps()
    step(3, total, "Ambiente virtual (.venv)")
    make_venv()
    step(4, total, "Bibliotecas Python")
    pip_install()
    use_cloud = ARGS.cloud            # nuvem só se você pedir (--cloud); por padrão tudo local, sem chave de API
    if use_cloud:
        ARGS.skip_models = True
    step(5, total, "Ollama (motor dos modelos de IA)")
    if use_cloud:
        info("modo nuvem: não é preciso instalar o Ollama nem baixar modelos")
    else:
        install_ollama()
    step(6, total, "Escolha de modelos pela sua VRAM e downloads")
    code = run_setup()
    if use_cloud:
        setup_cloud()
    step(7, total, "Comando 'itachi-capoeira' e início automático")
    make_launcher()
    setup_shortcuts()
    setup_autostart()

    print("\n" + "─" * 60)
    print("🩺 Verificação final")
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")
    d = subprocess.run([str(VENV_PY), "-m", "itachi_capoeira", "doctor"], cwd=str(ROOT), env=env).returncode

    ctl = "itachi-capoeira.cmd" if IS_WIN else "itachi-capoeira"
    print("═" * 60)
    print("🎉 INSTALAÇÃO CONCLUÍDA!" if (code == 0 and d == 0) else "⚠️  INSTALAÇÃO CONCLUÍDA COM PENDÊNCIAS (veja acima)")
    print(f"""
COMO USAR
   {ctl} gráfico    → abre a interface gráfica     |  {ctl} mobile → extensão do celular (USB)
   {ctl} up         → liga TUDO: atalhos globais (F7/F8/F9/F10) + daemon, com um comando só
   {ctl} start      → só liga o Itachi Capoeira em segundo plano
   {ctl} demo       → testa tudo (hardware → visão → raciocínio → voz)
   {ctl} doctor     → diagnóstico  |  {ctl} --help → todos os comandos

ATALHOS (com o Itachi Capoeira ligado)
   F8  voz → texto → colar     F9  Itachi Capoeira descreve a tela
   F7  conversa por voz        F10 interrompe
""")
    print("═" * 60)
    return 0 if (code == 0 and d == 0) else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
