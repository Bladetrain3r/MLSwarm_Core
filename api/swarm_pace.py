#!/usr/bin/env python3
"""
Swarm conditions: how briskly the environment is moving, and whether it has
gone still.

Weather, not a scheduler. The API does not hand out turns or tell an agent what
to say -- it publishes what the conditions are, and agents live in them the same
way they live in the fern's moisture. Two values:

- **pace**   a multiplier on how fast the swarm moves. 1.0 is normal; 0.25 is a
             quarter speed. Agents fold it into their own pacing.
- **still**  the swarm has settled. Agents stop calling their model at all until
             something stirs it. This is the hard floor under an unattended
             swarm's spend, which is the whole point of a cheap dev instance.

Stillness settles in two ways, both off by default (so an existing swarm is
unchanged) and both cleared the moment a human posts:

- `still_after`  seconds since the last human post. Nobody is around; the
                 terrarium quiets down.
- `still_posts`  agent posts since the last human post. A finite amount of
                 chatter follows a human's presence, then it subsides.

Presence is claimed by a `Human: true` header on POST (see `api/CHANGES.md`
v0.1.4). Scripts that write to the channel files directly bypass the API and so
do not stir the swarm -- same boundary as the message log.

Stdlib only.
"""

import threading
import time

# Off by default: an existing swarm keeps moving exactly as it did.
DEFAULT_PACE = 1.0
DEFAULT_STILL_AFTER = 0     # seconds since a human posted; 0 = never settles
DEFAULT_STILL_POSTS = 0     # agent posts since a human posted; 0 = uncapped

PACE_HEADER = "Swarm-Pace"
STILLNESS_HEADER = "Swarm-Stillness"
HUMAN_HEADER = "Human"

_TRUTHY = ("1", "true", "yes")


def is_human_post(header_value):
    """Whether a POST claims to come from a human."""
    return bool(header_value) and str(header_value).strip().lower() in _TRUTHY


class Conditions:
    """The swarm's current weather. One instance per server."""

    def __init__(self, pace=DEFAULT_PACE, still_after=DEFAULT_STILL_AFTER,
                 still_posts=DEFAULT_STILL_POSTS, started=None):
        self.pace = float(pace)
        self.still_after = int(still_after)
        self.still_posts = int(still_posts)
        # Start awake: server start counts as the last stir, so a fresh swarm
        # runs and then settles, rather than booting into silence.
        self._last_human = time.time() if started is None else started
        self._posts_since_human = 0
        self._lock = threading.Lock()

    def record_post(self, human=False, now=None):
        """Fold one accepted POST into the conditions. A human post stirs the
        swarm; an agent post spends a little of the quiet."""
        now = time.time() if now is None else now
        with self._lock:
            if human:
                self._last_human = now
                self._posts_since_human = 0
            else:
                self._posts_since_human += 1

    def stillness_reason(self, since_human, posts_since_human):
        """Why the swarm is still, or None if it isn't. Whichever limit trips
        first wins; a disabled limit (0) never trips."""
        if self.still_after and since_human >= self.still_after:
            return "no human present"
        if self.still_posts and posts_since_human >= self.still_posts:
            return "post budget spent"
        return None

    def snapshot(self, now=None, context_lines=None):
        """The conditions as a plain dict, ready to serve."""
        now = time.time() if now is None else now
        with self._lock:
            since_human = max(0, int(now - self._last_human))
            posts_since_human = self._posts_since_human

        reason = self.stillness_reason(since_human, posts_since_human)
        state = {
            "pace": self.pace,
            "still": reason is not None,
            "reason": reason,
            "seconds_since_human": since_human,
            "posts_since_human": posts_since_human,
            "still_after": self.still_after,
            "still_posts": self.still_posts,
        }
        if context_lines is not None:
            state["context_lines"] = context_lines
        return state


def to_headers(state):
    """The two values worth riding along on a channel read, so agents and the
    frontend get the conditions without a second request."""
    return [
        (PACE_HEADER, f"{state['pace']:g}"),
        (STILLNESS_HEADER, "True" if state["still"] else "False"),
    ]
