#!/usr/bin/env bash
# Itachi Capoeira — instalador para Linux e macOS.
# Uso:  bash install.sh [--yes] [--tier xl|m|s|cpu] [--autostart] [--skip-models] ...
# (todas as opções são repassadas ao install.py; veja: python3 install.py --help)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

find_python() {
  for c in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
      command -v "$c"; return 0
    fi
  done
  return 1
}

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

PY="$(find_python || true)"
if [ -z "$PY" ]; then
  echo "🐍 Python 3.10+ não encontrado — tentando instalar..."
  case "$(uname -s)" in
    Darwin)
      command -v brew >/dev/null 2>&1 || { echo "Instale o Python 3.12 em https://www.python.org/downloads/ (ou o Homebrew: https://brew.sh) e rode de novo."; exit 1; }
      brew install python@3.12 ;;
    Linux)
      if   command -v apt-get >/dev/null 2>&1; then $SUDO apt-get update -qq && $SUDO apt-get install -y python3 python3-venv python3-pip
      elif command -v dnf     >/dev/null 2>&1; then $SUDO dnf install -y python3 python3-pip
      elif command -v pacman  >/dev/null 2>&1; then $SUDO pacman -S --needed --noconfirm python python-pip
      elif command -v zypper  >/dev/null 2>&1; then $SUDO zypper --non-interactive install python3 python3-pip
      else echo "Instale o Python 3.10+ manualmente e rode de novo."; exit 1; fi ;;
  esac
  PY="$(find_python)" || { echo "Não consegui instalar o Python."; exit 1; }
fi

# Debian/Ubuntu separam o módulo venv em outro pacote
if ! "$PY" -c 'import venv, ensurepip' >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    echo "📦 Instalando python3-venv..."
    $SUDO apt-get update -qq && $SUDO apt-get install -y python3-venv python3-pip
  fi
fi

exec "$PY" install.py "$@"
