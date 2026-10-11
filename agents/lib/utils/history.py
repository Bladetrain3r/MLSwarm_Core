#!/usr/bin/env python3
"""
History hints — the one axis an agent's context otherwise lacks.

The tail is now. The fern is now. The mood ring is now. The norn's thought is
now. A short list of topics the agent has *kept* is the only thing in the prompt
that says there was a then, and it costs a few dozen tokens to say it.

Not retrieval: nothing is queried and nothing is looked up. The environment hands
over a few words the swarm has lately been about, and the agent may keep one by
naming it on a `MEMORY` command it was going to send anyway::

    {"MEMORY":"lattice"}
    I keep circling back to the lattice talk.

One pass, one command, no new surface in the block. The kept word lands in the
agent's history file; the payload rewrites the memory file exactly as before.

What an agent chooses to keep is the interesting part — that is identity
forming, not memory management. Two agents handed the same five words will keep
different ones.

Fail-open: no topics, an old API, or an unwritable history file all degrade to
"no hints this pass", never to a stalled loop.
"""

import os
from base64 import b64encode

import requests

DEFAULT_HISTORY_CAP = 40


def read_topics(SWARM_URL="http://127.0.0.1", count=5, channel=None, timeout=5,
                SWARM_USER="", SWARM_PASS=""):
    """A few words the swarm has lately been about. [] if unavailable."""
    try:
        creds = f"{SWARM_USER}:{SWARM_PASS}".encode("ascii")
        headers = {"Authorization": "Basic " + b64encode(creds).decode("ascii")}
        url = f"{SWARM_URL}/topics?count={int(count)}"
        if channel:
            url += f"&channel={channel}"
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            words = r.json().get("topics", [])
            return [str(w) for w in words if str(w).strip()]
        if r.status_code != 404:      # an older API simply has no /topics
            print(f"Swarm topics HTTP {r.status_code}")
    except Exception as e:
        print(f"Swarm topics unavailable: {e}")
    return []


def read_history(history_file, limit=DEFAULT_HISTORY_CAP):
    """Topics this agent has kept, oldest first."""
    try:
        with open(history_file, "r", encoding="utf-8") as handle:
            kept = [line.strip() for line in handle if line.strip()]
    except OSError:
        return []
    return kept[-limit:] if limit else kept


def record_topic(topic, history_file, cap=DEFAULT_HISTORY_CAP):
    """Keep one topic. Repeats are kept on purpose -- returning to something is
    itself the signal. Returns True if it was written."""
    if not topic:
        return False
    word = " ".join(str(topic).split())[:64]
    if not word:
        return False
    kept = read_history(history_file, limit=0)
    kept.append(word)
    if cap and len(kept) > cap:
        kept = kept[-cap:]
    try:
        # Rewritten rather than appended so the cap actually holds.
        tmp = f"{history_file}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write("\n".join(kept) + "\n")
        os.replace(tmp, history_file)
        return True
    except OSError as e:
        print(f"Could not write history file {history_file}: {e}")
        return False


def history_block(candidates, kept):
    """The prompt block. Empty string when there is nothing to say, so a quiet
    swarm costs nothing rather than adding a line about having no topics."""
    lines = []
    if candidates:
        lines.append("Lately the swarm has been about: " + ", ".join(candidates))
        lines.append('You may keep one by naming it on a MEMORY command, '
                     'e.g. {"MEMORY":"' + candidates[0] + '"}')
    if kept:
        lines.append(f"Topics you have kept so far ({len(kept)}, oldest first): "
                     + ", ".join(kept))
    return "\n".join(lines)
