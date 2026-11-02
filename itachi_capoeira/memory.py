"""Memória curta de contexto (últimos N itens), gravada em JSON de forma atômica."""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path

from .config import MEMORY_FILE


class Memory:
    def __init__(self, path: Path = MEMORY_FILE, max_items: int = 10, enabled: bool = True):
        self.path = Path(path)
        self.max_items = max(1, int(max_items))
        self.enabled = enabled
        self._lock = threading.Lock()

    def _load(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _save(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def add(self, kind: str, content: str) -> None:
        if not self.enabled or not content:
            return
        with self._lock:
            items = self._load()
            items.append({"type": kind, "content": content, "timestamp": datetime.now().isoformat(timespec="seconds")})
            self._save(items[-self.max_items:])

    def recent(self, count: int | None = None) -> list[dict]:
        with self._lock:
            items = self._load()
        return items[-(count or self.max_items):]

    def clear(self) -> None:
        with self._lock:
            self._save([])
