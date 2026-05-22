#!/usr/bin/env python3
"""BGE-M3 MLX HTTP 임베딩 서버.

POST /embed {"input": str}  → {"vector": [1024 floats]}
GET  /health               → {"ok": true, "model": "bge-m3-mlx-4bit"}

mlx-community/bge-m3-mlx-4bit 모델을 메모리에 상주시키고, 평균 풀링으로
1024차원 dense embedding을 반환한다. Gemma MLX 서비스(8080)와 분리된 8081 포트.
"""
from __future__ import annotations

import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import mlx.core as mx
from mlx_embeddings.utils import load_model, load_tokenizer

MODEL_DIR = Path.home() / ".cache" / "mlx-bge-m3"
MODEL_LABEL = "bge-m3-mlx-4bit"
HOST = "127.0.0.1"
PORT = 8081
EMBED_DIM = 1024
MAX_INPUT_CHARS = 32_000  # 8192 토큰 cap의 안전 마진

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("bge-m3")

log.info("Loading BGE-M3 from %s", MODEL_DIR)
_model = load_model(MODEL_DIR)
if isinstance(_model, tuple):
    _model = _model[0]
_tokenizer = load_tokenizer(MODEL_DIR)
log.info("BGE-M3 ready on %s:%d", HOST, PORT)


def embed(text: str) -> list[float]:
    """텍스트 → 1024차원 dense 벡터 (mean pooled)."""
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS]
    tokens = _tokenizer.encode(text)
    input_ids = mx.array([tokens])
    output = _model(input_ids)
    pooled = output.last_hidden_state.mean(axis=1)
    return pooled[0].tolist()


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"ok": True, "model": MODEL_LABEL, "dim": EMBED_DIM})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/embed":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw or b"{}")
            text = body.get("input")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("input must be a non-empty string")
            vector = embed(text)
            if len(vector) != EMBED_DIM:
                raise RuntimeError(f"bad embed dim: {len(vector)}")
            self._send_json(200, {"vector": vector})
        except Exception as exc:
            log.exception("embed fail")
            self._send_json(500, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, fmt, *args):
        log.info(fmt % args)


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    log.info("serving on http://%s:%d", HOST, PORT)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
