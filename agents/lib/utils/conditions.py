#!/usr/bin/env python3
"""
Agent-side reading of the swarm's conditions (pace and stillness).

The environment publishes weather, not orders: how briskly the swarm is moving
and whether it has gone still. An agent folds that into its own pacing the same
way it folds in its circadian curve.

Fail-open by design, and doubly so here -- these are cost controls, and a cost
control that can wedge an agent is worse than no cost control. If the API is old,
down, or slow, the answer is "normal pace, not still", which is exactly today's
behaviour.

Typical use in an agent loop:

    from utils.conditions import read_conditions, pace_multiplier, is_still
    ...
    conditions = read_conditions(SWARM_URL=SWARM_URL)     # once per loop
    tod_multi *= pace_multiplier(conditions)
    if is_still(conditions):
        ...sleep and skip the model call entirely...
"""

from base64 import b64encode

import requests


def read_conditions(SWARM_URL="http://127.0.0.1", timeout=5,
                    SWARM_USER="", SWARM_PASS=""):
    """Return the swarm's conditions dict, or None if unavailable.

    None is a real answer meaning "no weather reported" -- an older server has
    no /conditions endpoint at all -- and the helpers below treat it as fair."""
    try:
        # Same basic auth as swarm_api; copied rather than imported so this
        # module stays standalone (ten lines beats a coupling).
        creds = f"{SWARM_USER}:{SWARM_PASS}".encode("ascii")
        headers = {"Authorization": "Basic " + b64encode(creds).decode("ascii")}
        r = requests.get(f"{SWARM_URL}/conditions", headers=headers, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        # An older API 404s here; that is not an error worth shouting about.
        if r.status_code != 404:
            print(f"Swarm conditions HTTP {r.status_code}")
    except Exception as e:
        print(f"Swarm conditions unavailable: {e}")
    return None


def pace_multiplier(conditions, default=1.0):
    """How briskly to move. 1.0 is normal; lower is slower. A missing or
    nonsense value means normal pace, never a stall."""
    if not conditions:
        return default
    try:
        pace = float(conditions.get("pace", default))
    except (TypeError, ValueError):
        print(f"Ignoring unparseable pace: {conditions.get('pace')!r}")
        return default
    return pace if pace > 0 else default


def is_still(conditions):
    """Whether the swarm has settled. While still, an agent should not call its
    model at all -- this is the floor under an unattended swarm's spend."""
    return bool(conditions) and bool(conditions.get("still"))


def stillness_note(conditions):
    """A short line for the console explaining why it went quiet."""
    if not is_still(conditions):
        return ""
    reason = conditions.get("reason") or "settled"
    return f"The swarm has gone still ({reason})."
