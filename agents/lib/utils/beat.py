#!/usr/bin/env python3
"""
Agent-side reading of the swarm's beat — the room's pulse, as music.

Third of the weather siblings, and read the same way as the other two:
`digifern.py` is the swarm's semantic weather, `moodring.py` is the host's
physical weather, and this is the swarm's own rhythm — how fast it is moving,
how evenly, how many voices, and the little phrase the last few posts made.

What it is *not* is a transcript. The tail already tells an agent what was said.
This says what the saying sounded like, which is the one thing a wall of text
cannot show you about itself.

An agent is given the music and not the arithmetic behind it. That is
deliberate: the mapping is the API's business, and a note that has to explain
itself isn't a note.

Fail-open by design. An older API has no `/beat` endpoint at all and a fresh
one has heard nothing yet; both answer honestly rather than inventing a groove.

    from utils.beat import beat_prompt_block
    ...
    beat_text = beat_prompt_block(SWARM_URL=SWARM_URL)
"""

from base64 import b64encode

import os
import requests

def read_beat(SWARM_URL="http://127.0.0.1", timeout=5, SWARM_USER="", SWARM_PASS=""):
    """Return the beat's state dict, or None if it is unavailable."""
    try:
        # Same basic auth as swarm_api; copied rather than imported so this
        # module stays standalone (ten lines beats a coupling).
        creds = f"{SWARM_USER}:{SWARM_PASS}".encode("ascii")
        headers = {"Authorization": "Basic " + b64encode(creds).decode("ascii")}
        # An env override takes the full URL verbatim -- for a host whose
        # nginx doesn't serve :80 yet, or any other reason the beat lives
        # somewhere other than alongside the rest of the swarm API.
        url = os.environ.get("SWARM_BEAT_URL") or f"{SWARM_URL}/beat"
        req_timeout = timeout
        raw_timeout = os.environ.get("SWARM_BEAT_TIMEOUT")
        if raw_timeout is not None:
            try:
                req_timeout = float(raw_timeout)
            except ValueError:
                print(f"Swarm beat: SWARM_BEAT_TIMEOUT={raw_timeout!r} is not "
                      f"a number, falling back to {timeout}")
        r = requests.get(url, headers=headers, timeout=req_timeout)
        if r.status_code == 200:
            return r.json()
        # An older API 404s here; not worth shouting about.
        if r.status_code != 404:
            print(f"Swarm beat HTTP {r.status_code}")
    except Exception as e:
        print(f"Swarm beat unavailable: {e}")
    return None


def beat_prompt_block(SWARM_URL="http://127.0.0.1", timeout=5,
                      SWARM_USER="", SWARM_PASS=""):
    """Render the swarm's rhythm as a short prompt block.

    Distinguishes 'unavailable' from 'silent' — a swarm nobody is posting to is
    a real and interesting state, and quite different from an ear that isn't
    listening."""
    state = read_beat(SWARM_URL=SWARM_URL, timeout=timeout,
                      SWARM_USER=SWARM_USER, SWARM_PASS=SWARM_PASS)
    if state is None:
        return "Swarm Beat: unavailable"
    if not state.get("beats"):
        return "Swarm Beat: silent (nothing has come through lately)"

    lines = ["Swarm Beat:"]
    lines.append(f"Tempo: {state.get('tempo_label', 'unmeasured')}, "
                 f"{state.get('voices_label', 'no voices')}")
    lines.append(f"Key: {state.get('key', '?')} {state.get('mode', 'modal')}, "
                 f"{state.get('meter', 'unmeasured')}")
    phrase = state.get("phrase") or []
    if phrase:
        spread = state.get("range_label")
        tail = f" ({spread})" if spread and spread != "unmeasured" else ""
        lines.append("Phrase: " + " ".join(str(n) for n in phrase) + tail)
    if state.get("rest_label"):
        lines.append(f"Rest: {state['rest_label']}")
    return "\n".join(lines)
