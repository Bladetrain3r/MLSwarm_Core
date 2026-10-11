#!/usr/bin/env python3
"""
Tiny OpenAI-compatible embedding client for the norns.

make_embedder() returns a callable(text) -> vector suitable for passing to
MLBabel(embed_fn=...) or NapNorn(embed_fn=...). It is fail-open by design:
any error (endpoint down, bad response, timeout) returns None, and every norn
selection path treats None as "no vector" and falls back to plain random. A
norn must keep thinking whether or not an embedding server is around.

Defaults target a local Ollama serving a tiny model (all-minilm, 384-dim) --
the same OpenAI-compatible shape DigiFern uses, just a smaller model:

    ollama pull all-minilm

Stdlib only; no dependency beyond urllib.
"""

import json
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:11434/v1/embeddings"
DEFAULT_MODEL = "all-minilm:latest"


def make_embedder(url=DEFAULT_URL, model=DEFAULT_MODEL, timeout=10):
    """Build a fail-open embedder. Returns callable(text) -> list[float] | None."""

    def _embed(text):
        if not text:
            return None
        payload = json.dumps({"model": model, "input": text}).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.getcode() != 200:
                    return None
                data = json.loads(resp.read().decode("utf-8"))
            vec = data["data"][0]["embedding"]
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError):
            return None
        if not isinstance(vec, list) or not vec:
            return None
        return vec

    return _embed
