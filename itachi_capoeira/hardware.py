"""Detecção de GPU/VRAM/RAM e escolha automática do nível de modelos."""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

try:
    import psutil
except ImportError:  # psutil é dependência, mas o instalador usa este módulo antes de instalar tudo
    psutil = None


@dataclass
class GpuInfo:
    backend: str = "none"            # cuda | metal | rocm | none
    name: str = ""
    vram_total_mb: int = 0           # no Apple Silicon: estimativa da memória utilizável pela GPU
    vram_free_mb: int = 0
    note: str = ""


@dataclass
class Tier:
    key: str
    label: str
    chat_model: str
    vision_model: str
    whisper_model: str
    whisper_device: str              # auto | cpu
    min_vram_gb: float
    recommended_vram_gb: float
    extra: dict = field(default_factory=dict)


# Faixas de VRAM (valores aproximados, ver README). O Ollama completa com CPU/RAM se faltar VRAM,
# porém bem mais devagar — por isso o instalador escolhe o maior nível que cabe com folga.
TIERS: dict[str, Tier] = {
    "xl": Tier("xl", "Máxima qualidade (GPU grande)", "gemma4:26b", "gemma4:26b", "small", "auto", 20, 24),
    "m": Tier("m", "Equilibrado (recomendado)", "gemma4:e4b", "gemma4:e4b", "small", "auto", 6, 10),
    "s": Tier("s", "Econômico (GPU pequena)", "gemma4:e2b", "gemma4:e2b", "base", "cpu", 4, 6),
    "cpu": Tier("cpu", "Somente CPU (lento)", "gemma4:e2b", "gemma4:e2b", "base", "cpu", 0, 0),
}


def _run(cmd: list[str], timeout: int = 8) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def ram_total_gb() -> float:
    if psutil:
        return psutil.virtual_memory().total / 1024 ** 3
    if sys.platform == "darwin":
        out = _run(["sysctl", "-n", "hw.memsize"])
        return int(out) / 1024 ** 3 if out.isdigit() else 0.0
    return 0.0


def ram_available_gb() -> float:
    return psutil.virtual_memory().available / 1024 ** 3 if psutil else 0.0


def detect_gpu() -> GpuInfo:
    # NVIDIA (Windows e Linux)
    if shutil.which("nvidia-smi"):
        out = _run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"])
        if out:
            best = None
            for line in out.splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3 and parts[1].isdigit():
                    info = GpuInfo("cuda", parts[0], int(parts[1]), int(parts[2]) if parts[2].isdigit() else 0)
                    if best is None or info.vram_total_mb > best.vram_total_mb:
                        best = info
            if best:
                return best

    # Apple Silicon: memória unificada (o macOS reserva ~65% para a GPU por padrão)
    if sys.platform == "darwin":
        if platform.machine() == "arm64":
            total = ram_total_gb() * 1024
            chip = _run(["sysctl", "-n", "machdep.cpu.brand_string"]) or "Apple Silicon"
            usable = int(total * 0.65)
            return GpuInfo("metal", chip, usable, usable, "memória unificada (estimativa de 65% da RAM)")
        return GpuInfo("none", "", 0, 0, "Mac Intel: o Ollama roda só na CPU")

    # AMD no Linux (ROCm)
    if shutil.which("rocm-smi"):
        out = _run(["rocm-smi", "--showmeminfo", "vram", "--json"])
        try:
            import json
            data = json.loads(out)
            card = next(iter(data.values()))
            total = int(card.get("VRAM Total Memory (B)", 0)) // (1024 * 1024)
            used = int(card.get("VRAM Total Used Memory (B)", 0)) // (1024 * 1024)
            if total:
                return GpuInfo("rocm", "AMD GPU", total, max(total - used, 0))
        except (ValueError, StopIteration, TypeError):
            pass

    # Windows sem NVIDIA: só descobre o nome (AdapterRAM do Windows é limitado a 4 GB e não é confiável)
    if sys.platform == "win32":
        out = _run(["powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty Name)"])
        if out:
            return GpuInfo("none", out, 0, 0, "GPU sem suporte automático — rodará na CPU (use --tier para forçar)")

    return GpuInfo()


def pick_tier(gpu: GpuInfo, ram_gb: float) -> Tier:
    vram_gb = gpu.vram_total_mb / 1024
    if gpu.backend in ("cuda", "metal", "rocm"):
        if vram_gb >= 22:
            return TIERS["xl"]
        if vram_gb >= 8:
            return TIERS["m"]
        if vram_gb >= 4:
            return TIERS["s"]
    return TIERS["cpu"]


def describe(gpu: GpuInfo, ram_gb: float) -> str:
    if gpu.backend == "none":
        gpu_txt = f"sem GPU compatível{' (' + gpu.name + ')' if gpu.name else ''}"
    else:
        gpu_txt = f"{gpu.name} — {gpu.vram_total_mb / 1024:.1f} GB de VRAM ({gpu.backend})"
    return f"{gpu_txt}; RAM {ram_gb:.1f} GB"
