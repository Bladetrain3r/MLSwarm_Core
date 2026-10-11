#!/usr/bin/env python3
"""
Agent-side reading of the swarm's mood ring — the host's physical weather.

Sibling of `utils/digifern.py` and deliberately the same shape: the fern is the
swarm's semantic weather, the mood ring is its physical one, and an agent that
reads both should read them the same way.

Fail-open by design. An older API has no `/mood` endpoint at all, and a host may
have no sensors worth reading; either way the answer is an explicit "unavailable"
note rather than a plausible-looking calm.

Wired into `Experimental.py`'s prompt as a short block. The earlier plan was to
leave it as something an agent *reaches for* rather than a push — that stays the
right shape for anything larger, but four labelled lines are cheaper than the
round trip a reach would need, so this one is pushed.

    from utils.moodring import mood_prompt_block
    ...
    mood_text = mood_prompt_block(SWARM_URL=SWARM_URL)
"""

from base64 import b64encode

import requests


def read_mood(SWARM_URL="http://127.0.0.1", timeout=5, SWARM_USER="", SWARM_PASS=""):
    """Return the mood ring's state dict, or None if it is unavailable."""
    try:
        # Same basic auth as swarm_api; copied rather than imported so this
        # module stays standalone (ten lines beats a coupling).
        creds = f"{SWARM_USER}:{SWARM_PASS}".encode("ascii")
        headers = {"Authorization": "Basic " + b64encode(creds).decode("ascii")}
        r = requests.get(f"{SWARM_URL}/mood", headers=headers, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        # An older API 404s here; not worth shouting about.
        if r.status_code != 404:
            print(f"Swarm mood HTTP {r.status_code}")
    except Exception as e:
        print(f"Swarm mood unavailable: {e}")
    return None


def mood_prompt_block(SWARM_URL="http://127.0.0.1", timeout=5,
                      SWARM_USER="", SWARM_PASS=""):
    """Render the host's weather as a short prompt block.

    Says 'unavailable' or 'no senses' explicitly, so the agent can tell a quiet
    machine from a missing one."""
    state = read_mood(SWARM_URL=SWARM_URL, timeout=timeout,
                      SWARM_USER=SWARM_USER, SWARM_PASS=SWARM_PASS)
    if state is None:
        return "Swarm Mood: unavailable"
    if not state.get("senses"):
        return "Swarm Mood: unavailable (no readable sensors on the host)"

    lines = ["Swarm Mood:"]
    for axis in ("effort", "saturation", "warmth", "churn"):
        label = state.get(f"{axis}_label")
        if label is not None:
            # Unsigned: these axes run 0..1, unlike the fern's -1..1 where the
            # sign carries meaning.
            lines.append(f"{axis.capitalize()}: {label} ({state[axis]:.2f})")
    if "coherence" in state:
        lines.append(f"Coherence: {state['coherence']:.2f}")
    if "tempo_label" in state:
        lines.append(f"Tempo: {state['tempo_label']} ({state['tempo']:.2f})")
    return "\n".join(lines)
