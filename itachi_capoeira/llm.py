"""Cliente mínimo da API HTTP do Ollama (somente biblioteca padrão)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Iterable
from urllib.parse import urlparse


class OllamaError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _extract_error(body: str) -> str:
    try:
        data = json.loads(body)
        if isinstance(data, dict) and data.get("error"):
            return str(data["error"])
    except (ValueError, TypeError):
        pass
    return body.strip()[:300]


def is_local_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "::1", "0.0.0.0") or host.startswith("127.")


class Ollama:
    """Cliente do Ollama local ou da nuvem (https://ollama.com, com chave de API no cabeçalho Bearer)."""

    def __init__(self, url: str = "http://127.0.0.1:11434", timeout: float = 300, api_key: str = "",
                 cloud: bool | None = None):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.api_key = (api_key or "").strip()
        self.cloud = (not is_local_url(self.url)) if cloud is None else bool(cloud)
        # Local: ignora proxies do ambiente (proxies corporativos quebram localhost).
        # Nuvem: respeita os proxies do sistema, pois sai pela internet.
        self._opener = (urllib.request.build_opener() if self.cloud
                        else urllib.request.build_opener(urllib.request.ProxyHandler({})))

    @classmethod
    def from_config(cls, cfg, **kw) -> "Ollama":
        return cls(cfg.OLLAMA_URL, api_key=cfg.get("OLLAMA_API_KEY", ""), **kw)

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        # A chave só viaja por HTTPS, nunca em texto puro.
        if self.api_key and self.cloud and self.url.startswith("https://"):
            h["Authorization"] = "Bearer " + self.api_key
        return h

    def _cloud_error(self, status: int, msg: str) -> str:
        if not self.cloud:
            return msg
        if status == 401:
            return "Chave de API do Ollama ausente ou inválida. Rode: itachi-capoeira cloud setup"
        if status == 403:
            return (f"A nuvem do Ollama negou o acesso ({msg}). Esse modelo pode exigir plano pago; "
                    "troque com: itachi-capoeira cloud setup --chat-model OUTRO")
        if status == 429:
            return "Limite de uso do plano gratuito do Ollama atingido. Tente de novo mais tarde."
        return msg

    # ------------------------------------------------------------------ baixo nível
    def _open(self, path: str, payload: dict | None, timeout: float | None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            self.url + path, data=data, headers=self._headers(),
            method="POST" if data is not None else "GET",
        )
        try:
            return self._opener.open(req, timeout=timeout or self.timeout)
        except urllib.error.HTTPError as e:
            msg = self._cloud_error(e.code, _extract_error(e.read().decode("utf-8", "replace")))
            raise OllamaError(msg, status=e.code) from None
        except (urllib.error.URLError, OSError) as e:
            raise OllamaError(f"Ollama indisponível em {self.url} ({e})") from None

    def _json(self, path: str, payload: dict | None = None, timeout: float | None = None) -> dict:
        with self._open(path, payload, timeout) as r:
            raw = r.read().decode("utf-8", "replace")
        try:
            return json.loads(raw) if raw.strip() else {}
        except ValueError as e:
            raise OllamaError(f"Resposta inválida do Ollama: {raw[:200]!r}") from e

    # ------------------------------------------------------------------ status
    def alive(self, timeout: float = 3) -> bool:
        try:
            # Na nuvem usamos /api/tags (documentado); localmente, /api/version.
            self._json("/api/tags" if self.cloud else "/api/version", timeout=timeout if not self.cloud else max(timeout, 8))
            return True
        except OllamaError:
            return False

    def version(self) -> str:
        if self.cloud:
            self._json("/api/tags", timeout=10)
            return "nuvem"
        return str(self._json("/api/version", timeout=5).get("version", "?"))

    def list_models(self) -> list[str]:
        data = self._json("/api/tags", timeout=10)
        return [m.get("name", "") for m in data.get("models", [])]

    def has_model(self, name: str) -> bool:
        names = set(self.list_models())
        if name in names:
            return True
        return ":" not in name and f"{name}:latest" in names

    def running(self) -> list[dict]:
        """Modelos carregados na memória agora (/api/ps)."""
        if self.cloud:
            return []
        return self._json("/api/ps", timeout=10).get("models", [])

    # ------------------------------------------------------------------ geração
    def chat(
        self,
        model: str,
        messages: list[dict],
        *,
        images_b64: Iterable[str] | None = None,
        keep_alive: str | int | None = None,
        num_ctx: int | None = None,
        timeout: float | None = None,
    ) -> str:
        """Chat não-streaming. `images_b64` é anexado à última mensagem do usuário."""
        msgs = [dict(m) for m in messages]
        if images_b64:
            for m in reversed(msgs):
                if m.get("role") == "user":
                    m["images"] = list(images_b64)
                    break
        payload: dict = {"model": model, "messages": msgs, "stream": False, "think": False}
        if keep_alive is not None and not self.cloud:     # na nuvem o servidor cuida da memória
            payload["keep_alive"] = keep_alive
        if num_ctx and not self.cloud:
            payload["options"] = {"num_ctx": int(num_ctx)}
        try:
            data = self._json("/api/chat", payload, timeout=timeout)
        except OllamaError as e:
            # Modelos sem suporte a "think" podem rejeitar o campo: tenta de novo sem ele.
            if e.status == 400 and "think" in str(e).lower():
                payload.pop("think", None)
                data = self._json("/api/chat", payload, timeout=timeout)
            else:
                raise
        return str((data.get("message") or {}).get("content", "")).strip()

    def unload(self, model: str) -> None:
        if self.cloud:
            return
        try:
            self._json("/api/generate", {"model": model, "keep_alive": 0}, timeout=15)
        except OllamaError:
            pass

    def unload_all(self) -> list[str]:
        names = []
        try:
            for m in self.running():
                n = m.get("name") or m.get("model")
                if n:
                    self.unload(n)
                    names.append(n)
        except OllamaError:
            pass
        return names

    def pull(self, model: str, progress: Callable[[str, int, int], None] | None = None) -> None:
        """Baixa um modelo (stream NDJSON). progress(status, completed, total)."""
        if self.cloud:
            raise OllamaError("Modelos da nuvem não são baixados; escolha um com: itachi-capoeira cloud setup")
        with self._open("/api/pull", {"model": model, "stream": True}, timeout=3600) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("error"):
                    raise OllamaError(str(ev["error"]))
                if progress:
                    progress(str(ev.get("status", "")), int(ev.get("completed") or 0), int(ev.get("total") or 0))
