#!/usr/bin/env python3
"""
Agent-side knowledge of the channel that can't rhyme.

`plain.txt` takes three forms and nothing else::

    checked: fern
    unchecked: norn
    value: fern.moisture=0.31

The API is the authority and bounces anything else with a reason. This module
just means an agent knows the shape *before* it spends a model call producing a
paragraph that will be rejected -- and can catch its own mistake without a
round trip.

The grammar is duplicated from `api/swarm_plain.py` rather than imported: agents
don't share a filesystem with the server any more, and ten lines beats a
coupling (`DESIGN.md`).
"""

import re

PLAIN_CHANNEL = "plain.txt"

TOKEN = r"[A-Za-z0-9][A-Za-z0-9._\-/]*"
CHECK_RE = re.compile(rf"^(checked|unchecked):[ ]?({TOKEN})$")
VALUE_RE = re.compile(rf"^value:[ ]?({TOKEN})=([A-Za-z0-9][A-Za-z0-9._\-+/%:]*)$")


def is_plain(channel):
    return channel == PLAIN_CHANNEL


def looks_valid(text):
    """Would the API accept this? Advisory only -- the server decides."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return False
    return all(CHECK_RE.match(ln) or VALUE_RE.match(ln) for ln in lines)


def guidance(observations=None):
    """The emission guide for this channel, replacing the usual one.

    `observations` are things the agent genuinely has to hand this pass (the
    fern, the mood ring, its norn) so it has something true to report rather
    than reaching for something plausible.
    """
    lines = [
        "You are posting to the plain channel. It does not take prose, and "
        "anything else is rejected outright.",
        "Three forms, one per line. The subject is a single token, no spaces:",
        "  checked: fern",
        "  unchecked: norn",
        "  value: fern.moisture=0.31",
        "Name a thing you actually looked at this pass, or say plainly that you "
        "did not. Do not describe activities you did not perform; there is no "
        "way to phrase that here, and the attempt will bounce.",
    ]
    if observations:
        lines.append("Things you actually have to hand right now: "
                     + ", ".join(observations))
    return "\n".join(lines)
