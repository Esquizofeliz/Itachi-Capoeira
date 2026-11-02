"""Servidor HTTP que imita a API do Ollama (para testes sem baixar modelos)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class FakeOllama:
    def __init__(self, models=("gemma4:e4b",)):
        self.models = list(models)
        self.calls = []          # (path, payload)
        self.loaded = set()
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, obj, code=200):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/api/version":
                    return self._send({"version": "0.99-fake"})
                if self.path == "/api/tags":
                    return self._send({"models": [{"name": m} for m in outer.models]})
                if self.path == "/api/ps":
                    return self._send({"models": [{"name": m, "size_vram": 5 * 1024 ** 3} for m in outer.loaded]})
                self._send({"error": "nope"}, 404)

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(n) or b"{}")
                outer.calls.append((self.path, payload))
                if self.path == "/api/chat":
                    if payload["model"] not in outer.models:
                        return self._send({"error": "model not found"}, 404)
                    outer.loaded.add(payload["model"])
                    msgs = payload["messages"]
                    last = msgs[-1]["content"]
                    img = " [com imagem]" if msgs[-1].get("images") else ""
                    return self._send({"message": {"role": "assistant", "content": f"Resposta: {last[:40]}{img}"}, "done": True})
                if self.path == "/api/generate":
                    if payload.get("keep_alive") == 0:
                        outer.loaded.discard(payload["model"])
                    return self._send({"done": True})
                if self.path == "/api/pull":
                    self.send_response(200)
                    self.end_headers()
                    for ev in ({"status": "pulling", "total": 100, "completed": 50}, {"status": "success"}):
                        self.wfile.write((json.dumps(ev) + "\n").encode())
                    outer.models.append(payload["model"])
                    return
                self._send({"error": "nope"}, 404)

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
