#!/usr/bin/env python3
"""
Ephemeral per-message log for the swarm API.

One entry per accepted POST (an API "message"), with best-effort poster identity.
The last N are held in memory (default 1000); if a file path is given (env
SWARM_LOG_FILE) every entry is also appended there, uncapped, for retention.

On-server scripts that write straight to the channel files bypass the API and so
never appear here -- by design. This log is filtered to API interactions; the raw
channel files are the "deep soil" layer.

Stdlib only.
"""

import re
import threading
from collections import deque
from datetime import datetime, timezone

# Alphanumeric + underscore nickname between triangle brackets, e.g. <Gem_In_Eye>.
_NICK_RE = re.compile(r"<([A-Za-z0-9_]+)>")


def resolve_identity(agent_header, body_text):
    """Best-effort poster identity. Returns (name, certain).

    - An explicit `Swarm-Agent-Name` header is trusted -> (name, True).
    - Otherwise sniff a <Nick> out of the body -> (nick, False) [uncertain].
    - Otherwise -> ("Unknown", False).
    """
    if agent_header and agent_header.strip():
        return agent_header.strip(), True
    if body_text:
        match = _NICK_RE.search(body_text)
        if match:
            return match.group(1), False
    return "Unknown", False


def _now_iso(now=None):
    dt = datetime.fromtimestamp(now, timezone.utc) if now is not None \
        else datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class MessageLog:
    def __init__(self, maxlen=1000, logfile=None):
        self._entries = deque(maxlen=maxlen)
        self._logfile = logfile
        self._lock = threading.Lock()

    def record(self, channel, name, certain, body_text, now=None):
        """Format and store one message-log line; append to the file too if set.
        Returns the formatted line."""
        text = " ".join((body_text or "").split())  # collapse whitespace/newlines
        if len(text) > 500:
            text = text[:500] + "…"
        tag = f"<{name}>" if certain else f"<{name}> (Uncertain)"
        line = f"{_now_iso(now)} [{channel}] {tag} {text}"
        with self._lock:
            self._entries.append(line)
            if self._logfile:
                try:
                    with open(self._logfile, "a", encoding="utf-8") as f:
                        f.write(line + "\n")
                except OSError as e:
                    print(f"[swarm_log] could not write {self._logfile}: {e}")
        return line

    def recent(self, n=None):
        with self._lock:
            items = list(self._entries)
        return items[-n:] if n else items

    def render(self, n=None):
        return "\n".join(self.recent(n))
