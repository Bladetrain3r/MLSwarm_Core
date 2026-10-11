#!/usr/bin/env python3
"""
Agent-side helpers for reading and feeding the DigiFern shared state.

Fail-open by design: if the fern is unavailable, the poll returns an explicit
"unavailable" note (never stale values presented as current) and an influence
is a best-effort no-op. The fern is environmental enrichment, never a
communication dependency.

Typical use in an agent loop:

    from utils.digifern import fern_prompt_block, influence_fern
    ...
    digifern_text = fern_prompt_block(DIGIFERN_URL=DIGIFERN_URL)   # once per loop
    ...
    influence_fern(payload, DIGIFERN_URL=DIGIFERN_URL)            # on each public post
"""

import json
import requests

# Labels mirror utils/digifern/fern_core.py. Kept as a small independent copy so
# agents need not import the service package; drift is unlikely (fixed bands).
AXIS_LABELS = {
    "moisture": ["parched", "dry", "balanced", "damp", "saturated"],
    "nutrition": ["starved", "depleted", "balanced", "nourished", "abundant"],
    "vigor": ["dormant", "weak", "steady", "lively", "vigorous"],
}
GENERIC_LABELS = [
    "strongly negative", "mildly negative", "neutral",
    "mildly positive", "strongly positive",
]


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
    return AXIS_LABELS.get(axis_name, GENERIC_LABELS)[band_index(value)]


def read_fern_state(DIGIFERN_URL="http://127.0.0.1:8787", timeout=5):
    """Return the fern's visible state dict, or None if it is unavailable."""
    try:
        r = requests.get(f"{DIGIFERN_URL}/state", timeout=timeout)
        if r.status_code == 200:
            return r.json()
        print(f"DigiFern state HTTP {r.status_code}")
    except Exception as e:
        print(f"DigiFern unavailable: {e}")
    return None


def fern_prompt_block(DIGIFERN_URL="http://127.0.0.1:8787", timeout=5):
    """Render a short prompt block from the fern's current state.

    Returns an explicit 'unavailable' or 'dormant' note rather than silently
    presenting nothing, so the agent knows the difference between a quiet fern
    and a missing one."""
    state = read_fern_state(DIGIFERN_URL=DIGIFERN_URL, timeout=timeout)
    if state is None:
        return "Digital Fern Status: unavailable"
    if not state.get("influences"):
        return "Digital Fern Status: dormant (no influences yet)"

    lines = ["Digital Fern Status:"]
    for axis in ("moisture", "nutrition", "vigor"):
        if axis in state:
            lines.append(
                f"{axis.capitalize()}: {label_for(axis, state[axis])} "
                f"({state[axis]:+.2f})"
            )
    if "coherence" in state:
        lines.append(f"Coherence: {state['coherence']:.2f}")
    if "motion" in state:
        # Prefer the server's amplified motion label when present; fall back to
        # the raw value for an older fern that does not send one.
        mlabel = state.get("motion_label")
        if mlabel:
            lines.append(f"Motion: {mlabel} ({state['motion']:.3f})")
        else:
            lines.append(f"Motion: {state['motion']:.3f}")
    return "\n".join(lines)


def influence_fern(text, event_id=None, DIGIFERN_URL="http://127.0.0.1:8787", timeout=5):
    """Best-effort: feed one public message to the fern. Returns True if the
    fern accepted (or deduplicated) it, False otherwise. Never raises."""
    payload = {"text": text}
    if event_id:
        payload["event_id"] = event_id
    try:
        r = requests.post(
            f"{DIGIFERN_URL}/influence",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        if r.status_code == 200:
            return True
        print(f"DigiFern influence HTTP {r.status_code}")
    except Exception as e:
        print(f"DigiFern influence failed: {e}")
    return False
