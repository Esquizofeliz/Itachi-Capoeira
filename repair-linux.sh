#!/usr/bin/env bash
# Repara as dependências de áudio, Kokoro ONNX e captura de tela no Linux.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY="$(command -v python3)"; fi
if [[ -z "${PY:-}" || ! -x "$PY" ]]; then
  echo "Python 3 não encontrado. Instale Python 3.12 e python3-venv." >&2
  exit 1
fi

echo "[1/3] Instalando a biblioteca PortAudio do sistema..."
if command -v apt-get >/dev/null 2>&1; then
  if dpkg-query -W -f='${Status}' libportaudio2 2>/dev/null | grep -q "install ok installed"; then
    echo "libportaudio2 já está instalado."
  elif [[ "$(id -u)" -eq 0 ]]; then
    apt-get update
    apt-get install -y libportaudio2
  elif command -v sudo >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y libportaudio2
  else
    echo "Instale manualmente: sudo apt install libportaudio2" >&2
    exit 1
  fi
else
  echo "Gerenciador apt não encontrado; instale PortAudio pela sua distribuição."
fi

echo "[2/3] Instalando/atualizando dependências Python no ambiente: $PY"
"$PY" -m pip install --upgrade pip wheel
"$PY" -m pip install --upgrade "sounddevice>=0.4.6" "mss>=9.0" "kokoro-onnx>=0.4.9" onnxruntime

echo "[3/3] Validando importações..."
"$PY" - <<'PY'
import importlib
for module in ("sounddevice", "mss", "kokoro_onnx", "onnxruntime"):
    try:
        m = importlib.import_module(module)
        print(f"OK {module}" + (f" {getattr(m, '__version__', '')}" if getattr(m, '__version__', None) else ""))
    except Exception as exc:
        print(f"FALHA {module}: {type(exc).__name__}: {exc}")
        raise
PY

echo
echo "Reparo concluído. Execute: itachi-capoeira doctor --deep"
