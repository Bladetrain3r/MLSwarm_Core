#!/usr/bin/env python3
"""Reads agents/lib/VERSION so version drift across the agent fleet is
greppable from process output (ticket c530b5af, per-folder consolidation).

Every Gold chassis lands on agents/lib via SWARM_LIB/PYTHONPATH at runtime;
this makes the resolved lib's version cheap to check without diffing files
across per-agent folders.
"""

import os

_VERSION_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION"
)


def lib_version():
    """Return the shared lib's version string (e.g. "lib-1").

    Fail-open: never raises. Returns "unknown" if VERSION is missing or
    unreadable -- a missing version line should never block an agent from
    starting."""
    try:
        with open(_VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "unknown"
