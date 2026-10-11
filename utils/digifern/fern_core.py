#!/usr/bin/env python3
"""
DigiFern core: pure vector math, fern updates, labels, and state persistence.

This module deliberately knows nothing about HTTP or embedding servers. It
operates on plain Python lists of floats so it can be tested without a running
model. Axis vectors (which DO come from embeddings) are passed in from outside.

Everything that can go wrong here fails loudly with FernError rather than
silently substituting a value.
"""

import json
import math
import os

STATE_VERSION = 1

# Five-band thresholds shared by every axis. The numeric value stays
# authoritative; labels are presentation sugar over these bands.
#   -1.00 .. -0.60   band 0
#   -0.60 .. -0.20   band 1
#   -0.20 ..  0.20   band 2
#    0.20 ..  0.60   band 3
#    0.60 ..  1.00   band 4
AXIS_LABELS = {
    "moisture": ["parched", "dry", "balanced", "damp", "saturated"],
    "nutrition": ["starved", "depleted", "balanced", "nourished", "abundant"],
    "vigor": ["dormant", "weak", "steady", "lively", "vigorous"],
}
GENERIC_LABELS = [
    "strongly negative",
    "mildly negative",
    "neutral",
    "mildly positive",
    "strongly positive",
]


class FernError(Exception):
    """Raised when a vector, axis, or state is invalid."""


# --------------------------------------------------------------------------
# Vector operations
# --------------------------------------------------------------------------
def validate_vector(vec, expected_dim=None):
    """Return vec as a list of floats, or raise FernError if it is not a
    clean, finite, non-empty numeric vector of the expected dimension."""
    if not isinstance(vec, (list, tuple)):
        raise FernError(f"vector must be a list, got {type(vec).__name__}")
    if len(vec) == 0:
        raise FernError("vector is empty")
    out = []
    for i, x in enumerate(vec):
        # bool is a subclass of int; reject it explicitly.
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise FernError(f"vector element {i} is not numeric: {x!r}")
        xf = float(x)
        if math.isnan(xf) or math.isinf(xf):
            raise FernError(f"vector element {i} is not finite: {x!r}")
        out.append(xf)
    if expected_dim is not None and len(out) != expected_dim:
        raise FernError(
            f"vector dimension {len(out)} does not match expected {expected_dim}"
        )
    return out


def magnitude(vec):
    return math.sqrt(sum(x * x for x in vec))


def normalize(vec):
    """Return the unit vector. A zero-length vector cannot be normalized."""
    m = magnitude(vec)
    if m == 0.0:
        raise FernError("cannot normalize a zero-length vector")
    return [x / m for x in vec]


def dot(a, b):
    if len(a) != len(b):
        raise FernError(f"dimension mismatch in dot: {len(a)} vs {len(b)}")
    return sum(x * y for x, y in zip(a, b))


# --------------------------------------------------------------------------
# Semantic axes
# --------------------------------------------------------------------------
def build_axis(positive_vec, negative_vec):
    """axis = normalize(positive - negative), from the two anchor embeddings.

    Raises if the anchors have different dimensions or embed to the same point
    (a zero difference cannot be normalized, so the axis is undefined)."""
    if len(positive_vec) != len(negative_vec):
        raise FernError(
            f"axis anchor dimension mismatch: "
            f"{len(positive_vec)} vs {len(negative_vec)}"
        )
    diff = [p - n for p, n in zip(positive_vec, negative_vec)]
    try:
        return normalize(diff)
    except FernError:
        raise FernError("axis anchors are identical; axis is undefined")


def project_values(vector, axes):
    """Project the rolling vector onto each named axis. Combines direction and
    coherence naturally: opposed messages shrink the vector toward zero."""
    return {name: dot(vector, axis_vec) for name, axis_vec in axes.items()}


# --------------------------------------------------------------------------
# Fern update math
# --------------------------------------------------------------------------
def update_fern(current_vector, message_unit, update_rate):
    """Fold a normalized message vector into the rolling fern vector.

    Returns (new_vector, motion). The first accepted influence adopts the
    message vector wholesale and has motion 0.0."""
    if current_vector is None:
        return list(message_unit), 0.0
    if len(current_vector) != len(message_unit):
        raise FernError(
            f"dimension mismatch in update: "
            f"{len(current_vector)} vs {len(message_unit)}"
        )
    a = update_rate
    new_vec = [(1.0 - a) * s + a * e for s, e in zip(current_vector, message_unit)]
    return new_vec, compute_motion(current_vector, new_vec)


def compute_motion(old_vec, new_vec):
    """Directional change from old to new: 0.0 = no change, 1.0 = reversal.

    If either direction is undefined (zero-length), motion is 0.0."""
    try:
        old_dir = normalize(old_vec)
        new_dir = normalize(new_vec)
    except FernError:
        return 0.0
    cosine = max(-1.0, min(1.0, dot(old_dir, new_dir)))
    return (1.0 - cosine) / 2.0


# --------------------------------------------------------------------------
# Labels
# --------------------------------------------------------------------------
def band_index(value):
    if value < -0.60:
        return 0
    if value < -0.20:
        return 1
    if value < 0.20:
        return 2
    if value < 0.60:
        return 3
    return 4


def label_for(axis_name, value):
    """Deterministic label for an axis value. Falls back to generic
    positive/negative wording for axes without a bespoke label set."""
    labels = AXIS_LABELS.get(axis_name, GENERIC_LABELS)
    return labels[band_index(value)]


# Raw motion is tiny at slow update rates (a single sharp message barely turns a
# coherent fern), so a "wind speed" sensitivity curve amplifies it for display.
# The raw value stays authoritative; this is presentation only.
MOTION_LABELS = ["still", "stirring", "breezy", "gusting", "turbulent"]


def amplify_motion(motion, sensitivity):
    """Map raw motion through a saturating curve: 1 - exp(-sensitivity * motion).

    Larger sensitivity makes small shoves more visible; the output still
    saturates toward 1.0 for a genuine reversal. A sensitivity of None or <= 0
    disables amplification and returns the raw value unchanged."""
    if sensitivity is None or sensitivity <= 0:
        return motion
    return 1.0 - math.exp(-sensitivity * motion)


def motion_label(amplified):
    """Wind-scale label for an already-amplified motion value in [0, 1]."""
    if amplified < 0.10:
        return MOTION_LABELS[0]
    if amplified < 0.30:
        return MOTION_LABELS[1]
    if amplified < 0.50:
        return MOTION_LABELS[2]
    if amplified < 0.75:
        return MOTION_LABELS[3]
    return MOTION_LABELS[4]


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------
STATE_KEYS = (
    "version",
    "model",
    "dimensions",
    "update_rate",
    "vector",
    "values",
    "coherence",
    "motion",
    "influences",
    "updated_at",
    "recent_event_ids",
)


def empty_state(model, update_rate, dimensions=None):
    """A fresh, valid, uninfluenced state. Dimensions bind on first influence
    so a reset can run without contacting the embedding server."""
    return {
        "version": STATE_VERSION,
        "model": model,
        "dimensions": dimensions,
        "update_rate": update_rate,
        "vector": None,
        "values": {},
        "coherence": 0.0,
        "motion": 0.0,
        "influences": 0,
        "updated_at": None,
        "recent_event_ids": [],
    }


def validate_state(state, model=None, dimensions=None):
    """Check structural validity and, if a vector is stored, compatibility with
    the running model and dimensions. An uninfluenced state (vector None) is
    always compatible: it holds no vector to reinterpret."""
    if not isinstance(state, dict):
        raise FernError("state must be a JSON object")
    for key in STATE_KEYS:
        if key not in state:
            raise FernError(f"state missing required key: {key}")
    if state["version"] != STATE_VERSION:
        raise FernError(
            f"state version {state['version']} != expected {STATE_VERSION}; "
            f"reset or migrate explicitly"
        )
    if not isinstance(state["recent_event_ids"], list):
        raise FernError("recent_event_ids must be a list")
    if state["vector"] is not None:
        if model is not None and state["model"] != model:
            raise FernError(
                f"state model {state['model']!r} != configured {model!r}; "
                f"reset or migrate explicitly"
            )
        if dimensions is not None and state["dimensions"] != dimensions:
            raise FernError(
                f"state dimensions {state['dimensions']} != configured "
                f"{dimensions}; reset or migrate explicitly"
            )
        validate_vector(state["vector"], state["dimensions"])
    return state


def load_state(path, model=None, dimensions=None):
    """Load and validate state. Raises on missing file or malformed JSON so a
    corrupt state never gets silently reinterpreted."""
    with open(path, "r", encoding="utf-8") as f:
        state = json.load(f)
    return validate_state(state, model=model, dimensions=dimensions)


def save_state(path, state):
    """Atomically persist state: write a temp file, flush+fsync, then replace.
    A crash leaves either the old or the new state, never half a document."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# Duplicate-event tracking
# --------------------------------------------------------------------------
def is_duplicate(state, event_id):
    return event_id is not None and event_id in state["recent_event_ids"]


def remember_event(state, event_id, limit):
    """Append an event id to the bounded recent list, trimming the oldest."""
    if event_id is None:
        return
    ids = state["recent_event_ids"]
    ids.append(event_id)
    if len(ids) > limit:
        del ids[: len(ids) - limit]
