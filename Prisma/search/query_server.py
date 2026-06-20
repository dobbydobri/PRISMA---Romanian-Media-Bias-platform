from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import numpy as np
import torch
from flask import Flask, jsonify, request
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL_NAME      = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-large")
DEVICE          = os.getenv("EMBED_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
USE_FP16        = os.getenv("EMBED_FP16", "1") == "1"
HOST            = os.getenv("HOST", "0.0.0.0")
PORT            = int(os.getenv("PORT", "8081"))
MAX_QUERY_CHARS = int(os.getenv("MAX_QUERY_CHARS", "512"))
LOG_LEVEL       = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("query_server")

# ---------------------------------------------------------------------------
# Model load (once, at import time — Flask app holds the reference)
# ---------------------------------------------------------------------------

log.info("Loading model %s on %s (fp16=%s)", MODEL_NAME, DEVICE, USE_FP16)
_load_t0 = time.perf_counter()
_model = SentenceTransformer(MODEL_NAME, device=DEVICE)
if USE_FP16 and DEVICE.startswith("cuda"):
    _model = _model.half()
_load_secs = time.perf_counter() - _load_t0
_dim = _model.get_sentence_embedding_dimension()
log.info("Model ready: dim=%d, load=%.2fs", _dim, _load_secs)

_inference_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)


def _embed_query_text(text: str) -> np.ndarray:
    prefixed = f"query: {text}"
    with _inference_lock:
        vec = _model.encode(
            prefixed,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    return vec.astype(np.float32, copy=False)


@app.get("/health")
def health() -> Any:
    return jsonify(
        {
            "status": "ok",
            "model":  MODEL_NAME,
            "device": str(_model.device),
            "dim":    _dim,
            "fp16":   USE_FP16 and DEVICE.startswith("cuda"),
        }
    )


@app.post("/embed_query")
def embed_query() -> Any:
    payload = request.get_json(silent=True) or {}
    text = payload.get("text")

    if not isinstance(text, str):
        return jsonify({"error": "field 'text' must be a string"}), 400

    text = text.strip()
    if not text:
        return jsonify({"error": "field 'text' must be non-empty"}), 400

    if len(text) > MAX_QUERY_CHARS:
        log.info("Truncating query from %d to %d chars", len(text), MAX_QUERY_CHARS)
        text = text[:MAX_QUERY_CHARS]

    t0 = time.perf_counter()
    try:
        vec = _embed_query_text(text)
    except Exception:
        log.exception("Embedding failed for query: %r", text[:80])
        return jsonify({"error": "embedding failed"}), 500
    encode_ms = (time.perf_counter() - t0) * 1000.0

    log.info("embed_query ok len=%d ms=%.1f", len(text), encode_ms)

    return jsonify(
        {
            "embedding":  vec.tolist(),
            "dim":        int(vec.shape[0]),
            "encode_ms":  round(encode_ms, 2),
        }
    )


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False, threaded=True)