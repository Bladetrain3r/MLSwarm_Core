#!/usr/bin/env python3
"""
Server-side context sizing for the swarm API.

How much of a channel an agent hears is a property of the *environment*, not of
the agent. One dial on the server sets what everyone is served, so a cheap dev
swarm can run the same agent logic on a fraction of the tokens without editing
(or restarting) a single agent.

The dial is a **ceiling**. A request may ask for *fewer* lines -- a short-eared
agent, a cheap pass -- but never for more than the server is willing to serve.
A request that asks for nothing, or asks unintelligibly, gets the ceiling; that
is the historical 10k tail, so an older agent talking to a newer server sees no
change at all, and a newer agent talking to an older server just has its header
ignored and falls back to trimming client-side.

This is `SALIENCE.md` Stage 1 (fade) with the salience maths left out: a
smaller, fresher window served by the environment. The raw channel files stay
the deep-soil full history.

Stdlib only.
"""

from urllib.parse import urlsplit, parse_qs

# The historical tail size, and so the default ceiling: unchanged behaviour.
DEFAULT_CONTEXT_LINES = 10000

# How a request asks for less. Header for agents, query param for curl/browsers.
CONTEXT_HEADER = "Swarm-Context-Lines"
CONTEXT_PARAM = "lines"


def parse_target(path, prefix="/swarm/"):
    """Split a request path into (channel filename, query params).

    The query string is separated *before* the whitelist check so that
    `/swarm/general.txt?lines=60` still resolves to `general.txt` rather than
    falling through to a 404.
    """
    parts = urlsplit(path)
    filename = ""
    if parts.path.startswith(prefix):
        filename = parts.path[len(prefix):].strip("/")
    return filename, parse_qs(parts.query)


def requested_lines(header_value=None, query=None):
    """What this request asked for, or None if it didn't ask.

    Wrong loudly rather than creatively: an unparseable or non-positive value is
    logged and treated as "no request" (serve the ceiling), never quietly turned
    into some other number.
    """
    raw = header_value
    if raw is None and query:
        values = query.get(CONTEXT_PARAM)
        raw = values[0] if values else None
    if raw is None:
        return None

    try:
        asked = int(str(raw).strip())
    except (TypeError, ValueError):
        print(f"[context] ignoring unparseable {CONTEXT_HEADER}/{CONTEXT_PARAM}: {raw!r}")
        return None
    if asked <= 0:
        print(f"[context] ignoring non-positive context request: {asked}")
        return None
    return asked


def resolve_lines(header_value=None, query=None, ceiling=DEFAULT_CONTEXT_LINES):
    """How many lines to actually serve: the ask, clamped down to the ceiling."""
    asked = requested_lines(header_value, query)
    if asked is None:
        return ceiling
    return min(asked, ceiling)
