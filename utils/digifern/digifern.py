#!/usr/bin/env python3
"""
DigiFern: shared semantic weather for MLSwarm.

A tiny local service. Every public swarm message is embedded, normalized, and
folded into one rolling fern vector. Fixed semantic axes project that vector
into visible properties (moisture, nutrition, vigor) alongside coherence and
motion. Agents read the state; the swarm API feeds it.

The visible call path stays flat and readable:

    HTTP request
    -> validate input
    -> request embedding
    -> update fern
    -> atomically write state
    -> return JSON

Usage:
    python digifern.py serve
    python digifern.py state
    python digifern.py influence "some text"
    python digifern.py reset [--force]
    python digifern.py check
"""

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import fern_core

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Environment variables that may override config (non-secret operational knobs).
ENV_OVERRIDES = {
    "DIGIFERN_HOST": "host",
    "DIGIFERN_PORT": "port",
    "DIGIFERN_EMBEDDING_URL": "embedding_url",
    "DIGIFERN_EMBEDDING_MODEL": "embedding_model",
    "DIGIFERN_STATE_FILE": "state_file",
}


class EmbeddingError(Exception):
    """The embedding endpoint was unreachable or returned something unusable."""


class PersistenceError(Exception):
    """State could not be written to disk."""


class RequestError(Exception):
    """The caller sent an invalid request (maps to HTTP 400)."""


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    required = [
        "host", "port", "embedding_url", "embedding_model", "state_file",
        "update_rate", "max_text_chars", "recent_event_limit", "axes",
    ]
    for key in required:
        if key not in cfg:
            raise ValueError(f"config missing required key: {key}")

    if not cfg["axes"]:
        raise ValueError("config defines no axes")
    for name, anchors in cfg["axes"].items():
        if "positive" not in anchors or "negative" not in anchors:
            raise ValueError(f"axis {name!r} needs positive and negative anchors")

    # Optional knobs with defaults.
    cfg.setdefault("max_body_bytes", 65536)
    cfg.setdefault("embedding_timeout", 30)
    cfg.setdefault("motion_sensitivity", 300)

    for env_key, cfg_key in ENV_OVERRIDES.items():
        if env_key in os.environ:
            cfg[cfg_key] = os.environ[env_key]
    cfg["port"] = int(cfg["port"])

    return cfg


def print_config(cfg):
    """Print the resolved configuration at startup. No credentials exist yet;
    if any are introduced later, exclude them here."""
    shown = {k: v for k, v in cfg.items() if k != "axes"}
    print("DigiFern resolved configuration:")
    for key in sorted(shown):
        print(f"  {key}: {shown[key]}")
    print(f"  axes: {', '.join(cfg['axes'].keys())}")


# --------------------------------------------------------------------------
# Embedding client
# --------------------------------------------------------------------------
def embed(text, url, model, timeout):
    """Request one embedding from the OpenAI-compatible endpoint and return it
    as a validated list of floats. Every failure mode raises EmbeddingError."""
    payload = json.dumps({"model": model, "input": text}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise EmbeddingError(f"embedding endpoint returned HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise EmbeddingError(f"embedding endpoint unreachable: {e.reason}") from e
    except OSError as e:
        raise EmbeddingError(f"embedding request failed: {e}") from e

    if status != 200:
        raise EmbeddingError(f"embedding endpoint returned HTTP {status}")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise EmbeddingError(f"embedding response was not valid JSON: {e}") from e

    if not isinstance(data, dict) or not data.get("data"):
        raise EmbeddingError("embedding response missing 'data'")
    first = data["data"][0]
    if not isinstance(first, dict) or "embedding" not in first:
        raise EmbeddingError("embedding response missing 'embedding'")
    try:
        return fern_core.validate_vector(first["embedding"])
    except fern_core.FernError as e:
        raise EmbeddingError(f"embedding vector invalid: {e}") from e


def build_axes(cfg):
    """Regenerate axis vectors from anchors at startup. Cheap for a few axes,
    and it means broken anchors, model, or endpoint fail visibly right away."""
    axes = {}
    dimensions = None
    for name, anchors in cfg["axes"].items():
        pos = embed(anchors["positive"], cfg["embedding_url"],
                    cfg["embedding_model"], cfg["embedding_timeout"])
        neg = embed(anchors["negative"], cfg["embedding_url"],
                    cfg["embedding_model"], cfg["embedding_timeout"])
        if dimensions is None:
            dimensions = len(pos)
        try:
            axes[name] = fern_core.build_axis(pos, neg)
        except fern_core.FernError as e:
            raise EmbeddingError(f"axis {name!r} could not be constructed: {e}") from e
    return axes, dimensions


# --------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------
def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


class FernService:
    """Holds the running state and serializes updates. One process, threaded
    HTTP server; a single lock guards the state and its persistence."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.model = cfg["embedding_model"]
        self.state_path = cfg["state_file"]
        self.lock = threading.Lock()
        self.axes, self.dimensions = build_axes(cfg)
        self.state = self._load_or_create_state()

    def _load_or_create_state(self):
        if os.path.exists(self.state_path):
            state = fern_core.load_state(
                self.state_path, model=self.model, dimensions=self.dimensions
            )
            return state
        state = fern_core.empty_state(self.model, self.cfg["update_rate"])
        fern_core.save_state(self.state_path, state)
        return state

    def influence(self, text, event_id=None):
        """Run text through the shared update path. Returns a dict with
        accepted / duplicate flags and the resulting visible values."""
        sensitivity = self.cfg["motion_sensitivity"]
        # Best-effort early duplicate check before the network round trip.
        with self.lock:
            if fern_core.is_duplicate(self.state, event_id):
                return {"accepted": False, "duplicate": True,
                        "state": _short_values(self.state, sensitivity)}

        embedding = embed(text, self.cfg["embedding_url"], self.model,
                          self.cfg["embedding_timeout"])
        try:
            fern_core.validate_vector(embedding, self.dimensions)
            unit = fern_core.normalize(embedding)
        except fern_core.FernError as e:
            # Malformed / unnormalizable embedding: the endpoint misbehaved.
            raise EmbeddingError(str(e)) from e

        with self.lock:
            state = self.state
            # Re-check under lock: a concurrent request may have landed the
            # same event id while we were embedding.
            if fern_core.is_duplicate(state, event_id):
                return {"accepted": False, "duplicate": True,
                        "state": _short_values(state, sensitivity)}

            new_vec, motion = fern_core.update_fern(
                state["vector"], unit, state["update_rate"]
            )
            state["vector"] = new_vec
            state["dimensions"] = self.dimensions
            state["model"] = self.model
            state["values"] = fern_core.project_values(new_vec, self.axes)
            state["coherence"] = fern_core.magnitude(new_vec)
            state["motion"] = motion
            state["influences"] += 1
            state["updated_at"] = now_iso()
            fern_core.remember_event(state, event_id, self.cfg["recent_event_limit"])

            try:
                fern_core.save_state(self.state_path, state)
            except OSError as e:
                raise PersistenceError(f"could not persist state: {e}") from e

            return {"accepted": True, "duplicate": False,
                    "state": _short_values(state, sensitivity)}

    def visible_state(self):
        with self.lock:
            return _visible_state(self.state, self.cfg["motion_sensitivity"])

    def health(self):
        return {"ok": True, "service": "digifern",
                "model": self.model, "dimensions": self.dimensions}


def _visible_state(state, motion_sensitivity):
    """Full /state payload: flat numeric values plus coherence/motion/meta.
    Raw motion stays authoritative; motion_label is an amplified reading.
    The rolling vector itself stays internal."""
    out = dict(state["values"])
    out["coherence"] = state["coherence"]
    out["motion"] = state["motion"]
    out["motion_label"] = fern_core.motion_label(
        fern_core.amplify_motion(state["motion"], motion_sensitivity)
    )
    out["influences"] = state["influences"]
    out["updated_at"] = state["updated_at"]
    return out


def _short_values(state, motion_sensitivity):
    """Compact values echoed in an /influence response."""
    out = dict(state["values"])
    out["coherence"] = state["coherence"]
    out["motion"] = state["motion"]
    out["motion_label"] = fern_core.motion_label(
        fern_core.amplify_motion(state["motion"], motion_sensitivity)
    )
    return out


# --------------------------------------------------------------------------
# HTTP API
# --------------------------------------------------------------------------
class DigiFernHandler(BaseHTTPRequestHandler):
    service = None  # set by serve()

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Route access logs to stderr, quietly.
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, self.service.health())
        elif self.path == "/state":
            self._send_json(200, self.service.visible_state())
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/influence":
            self._send_json(404, {"error": "not found"})
            return

        cfg = self.service.cfg
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._send_json(400, {"error": "invalid Content-Length"})
            return
        if length <= 0:
            self._send_json(400, {"error": "empty request body"})
            return
        if length > cfg["max_body_bytes"]:
            self._send_json(400, {"error": "request body too large"})
            return

        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, {"error": "body must be valid JSON"})
            return

        try:
            text, event_id = _parse_influence(body, cfg["max_text_chars"])
        except RequestError as e:
            self._send_json(400, {"error": str(e)})
            return

        try:
            result = self.service.influence(text, event_id=event_id)
        except EmbeddingError as e:
            sys.stderr.write(f"[influence] embedding failure: {e}\n")
            self._send_json(502, {"error": f"embedding failure: {e}"})
            return
        except PersistenceError as e:
            sys.stderr.write(f"[influence] persistence failure: {e}\n")
            self._send_json(500, {"error": f"persistence failure: {e}"})
            return

        self._send_json(200, result)


def _parse_influence(body, max_text_chars):
    if not isinstance(body, dict):
        raise RequestError("body must be a JSON object")
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        raise RequestError("field 'text' is required and must be non-empty")
    if len(text) > max_text_chars:
        raise RequestError(
            f"text exceeds {max_text_chars} character limit"
        )
    event_id = body.get("event_id")
    if event_id is not None and not isinstance(event_id, str):
        raise RequestError("field 'event_id' must be a string if present")
    return text, event_id


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def cmd_serve(cfg):
    print_config(cfg)
    service = FernService(cfg)
    DigiFernHandler.service = service
    print(f"DigiFern serving on http://{cfg['host']}:{cfg['port']} "
          f"({service.dimensions} dims, {service.state['influences']} influences so far)")
    httpd = ThreadingHTTPServer((cfg["host"], cfg["port"]), DigiFernHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nDigiFern shutting down.")
        httpd.shutdown()


def cmd_state(cfg):
    state = fern_core.load_state(cfg["state_file"])
    if state["influences"] == 0:
        print("DigiFern has no influences yet (empty state).")
        return
    for name, value in state["values"].items():
        print(f"{name}: {fern_core.label_for(name, value)} ({value:+.2f})")
    print(f"coherence: {state['coherence']:.2f}")
    mlabel = fern_core.motion_label(
        fern_core.amplify_motion(state["motion"], cfg["motion_sensitivity"])
    )
    print(f"motion: {mlabel} ({state['motion']:.3f})")
    print(f"influences: {state['influences']}")
    print(f"updated_at: {state['updated_at']}")


def cmd_influence(cfg, text):
    service = FernService(cfg)
    result = service.influence(text)
    print(json.dumps(result, indent=2))


def cmd_reset(cfg, force):
    path = cfg["state_file"]
    if os.path.exists(path) and not force:
        answer = input(f"Reset DigiFern state at {path}? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Reset cancelled.")
            return
    state = fern_core.empty_state(cfg["embedding_model"], cfg["update_rate"])
    fern_core.save_state(path, state)
    print(f"State reset: {path}")


def cmd_check(cfg):
    """Validate config, endpoint, dimensions, axes, and state compatibility.
    Makes no state changes."""
    print_config(cfg)
    print("-" * 40)
    try:
        axes, dimensions = build_axes(cfg)
    except EmbeddingError as e:
        print(f"FAIL: embedding / axis construction: {e}")
        return 1
    print(f"OK: embedding endpoint reachable, {dimensions} dimensions")
    print(f"OK: constructed {len(axes)} axes: {', '.join(axes)}")

    path = cfg["state_file"]
    if not os.path.exists(path):
        print(f"OK: no state file yet at {path} (will be created on first serve)")
        return 0
    try:
        state = fern_core.load_state(
            path, model=cfg["embedding_model"], dimensions=dimensions
        )
    except (fern_core.FernError, ValueError, OSError) as e:
        print(f"FAIL: state at {path} is incompatible: {e}")
        return 1
    print(f"OK: state at {path} compatible ({state['influences']} influences)")
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 1

    command = argv[0]
    config_path = os.environ.get("DIGIFERN_CONFIG", DEFAULT_CONFIG_PATH)
    try:
        cfg = load_config(config_path)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"Config error ({config_path}): {e}", file=sys.stderr)
        return 1

    if command == "serve":
        return cmd_serve(cfg) or 0
    if command == "state":
        try:
            cmd_state(cfg)
        except (fern_core.FernError, OSError, ValueError) as e:
            print(f"State error: {e}", file=sys.stderr)
            return 1
        return 0
    if command == "influence":
        if len(argv) < 2:
            print("usage: digifern.py influence \"some text\"", file=sys.stderr)
            return 1
        try:
            cmd_influence(cfg, argv[1])
        except (EmbeddingError, PersistenceError, fern_core.FernError) as e:
            print(f"Influence error: {e}", file=sys.stderr)
            return 1
        return 0
    if command == "reset":
        cmd_reset(cfg, force="--force" in argv[1:])
        return 0
    if command == "check":
        return cmd_check(cfg)

    print(f"Unknown command: {command}", file=sys.stderr)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
