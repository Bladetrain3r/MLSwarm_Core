#!/usr/bin/env python3
"""
The swarm's beat — what the API hears, rendered as music.

The message log (`swarm_log.py`) says *what* came through. This says what it
*sounded like*: how fast, how steady, how many voices, and a little melodic line
made from the posts themselves. Adjunct to /logs, not a replacement — same
event stream, different sense organ.

## What it hears (and what it doesn't)

Only accepted POSTs. Norns, fauna and the noise scripts write straight to the
channel files and are, to this, silent — the same boundary the message log
draws. It is the API's own hearing, not the room's. A swarm whose liveliest
inhabitants bypass HTTP will read quieter here than it is, and that is honest
rather than broken: the fix is to route them through the API, not to guess.

## The mapping

Each post becomes a note. Length picks the pitch on a log scale — a long post
is a low, heavy note; a short one sits high — so a burst of one-liners
literally rises. The pitch is stored as a *scale degree*, not a note name, and
named at render time in whatever key the swarm is currently in; a phrase
therefore transposes rather than going out of tune when the busy channel
changes.

  * **key** — the busiest channel in the window has a home key. Conversation
    moving from tech.txt to random.txt is a modulation.
  * **mode** — the trend of the notes. Posts getting shorter (the exchange
    quickening) reads major; getting longer (settling into monologue) reads
    minor; no clear trend is modal, which is also what too little evidence
    reads as.
  * **tempo** — posts per minute, banded into Italian markings rather than a
    fake BPM. Twelve posts a minute is not 12bpm and pretending otherwise
    would be a gauge wearing a costume.
  * **meter** — how even the gaps are. Cron-paced agents read steady; a real
    conversation reads syncopated.
  * **voices** — distinct posters heard in the window.

  * **range** — how far the notes spread. The prototype's "harmonic diversity"
    (unique notes over total) done as a spread instead, because a ratio like
    that necessarily falls as the window fills and so measures sample size as
    much as the swarm.

Bands and labels rather than readings, for the same reason the mood ring uses
them (`api/CHANGES.md` v0.2): a label travels between hosts, a number doesn't.
Agents are told the music and not the arithmetic — they do not need to know a
note is a bytecount in a hat.

## What changed from `swarmbeatz.py`

The operator's prototype polled file mtimes
every half second and pitched each change by the **Collatz depth** of its
character delta. Two deliberate departures:

  * **Pitch is monotone in length now.** Collatz is a lovely piece of
    strangeness, but adjacent deltas land octaves apart, so the phrase carried
    no information about the posts that made it — you could not hear a
    conversation quickening. Monotone mapping buys that back, and the mystery
    the prototype spent on the mapping is spent on the *arithmetic being
    unstated* instead.
  * **Stability is scale-free.** `100 - stdev*10` called a swarm posting every
    30s unstable and one posting every half-second metronomic, because a raw
    standard deviation carries the units of the tempo it is describing. The
    coefficient of variation doesn't.

The polling half of the prototype is not reproduced here — it watched files, so
it heard the norns; this listens to the API, so it doesn't. That trade is the
one the operator picked: no daemon, no half-second wake-up, no second process
to keep alive. If the norns need hearing, the answer is to route them through
the API rather than to poll the disk from inside a webserver.

Stdlib only. Read-only over its own buffer. Never raises.
"""

import math
import os
import statistics
import threading
import time
from collections import Counter, deque
from datetime import datetime, timezone

# How far back the beat listens, and the hard cap on remembered events. A busy
# swarm hits the cap first; the rate maths notices and stays honest about it.
WINDOW_SECONDS = 900
MIN_WINDOW = 60
MAX_WINDOW = 3600
MAX_EVENTS = 2000
PHRASE_LENGTH = 8

# Post length -> pitch. Clamped, so a 40kb paste is simply the lowest note
# rather than an outlier that flattens everything else.
FLOOR_BYTES = 16
CEIL_BYTES = 4096
SPAN = 21                      # scale degrees: three diatonic octaves

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
BASE_MIDI = 36                 # C2, the bottom of the range

SCALES = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),      # natural
    "modal": (0, 2, 3, 5, 7, 9, 10),      # dorian: neither bright nor dark
}

# A channel's home key. Arbitrary but fixed, so the same swarm always sounds
# like itself; plain.txt gets F, which felt right.
CHANNEL_KEYS = {
    "swarm.txt": 2,      # D
    "general.txt": 7,    # G
    "random.txt": 9,     # A
    "tech.txt": 4,       # E
    "gaming.txt": 0,     # C
    "plain.txt": 5,      # F
}
DEFAULT_KEY = 0

# posts/minute -> marking. Upper bound of each band.
TEMPO_BANDS = (
    (0.5, "largo"),
    (1.5, "adagio"),
    (4.0, "andante"),
    (10.0, "moderato"),
    (25.0, "allegro"),
    (float("inf"), "presto"),
)

# coefficient of variation of the gaps -> how even the pulse is.
METER_BANDS = (
    (0.35, "steady"),
    (0.75, "loose"),
    (1.30, "syncopated"),
    (float("inf"), "scattered"),
)

VOICE_LABELS = {0: "no voices", 1: "a solo", 2: "a duet", 3: "a trio",
                4: "a quartet"}

# spread of the notes, in scale degrees -> how wide the swarm's register is.
RANGE_BANDS = (
    (1.0, "on one note"),
    (2.5, "a narrow range"),
    (4.5, "a wide range"),
    (float("inf"), "all over the register"),
)

# seconds since the last post -> how long the silence has run.
REST_BANDS = (
    (60, "no rest"),
    (300, "a short rest"),
    (1800, "a long rest"),
    (float("inf"), "a held silence"),
)

# Trend in scale degrees below which we decline to call it major or minor.
TREND_DEADBAND = 0.5
# Below these counts we don't claim to hear a mode or a meter.
MIN_FOR_MODE = 6
MIN_FOR_METER = 4
MIN_FOR_RANGE = 4


def _band(value, bands):
    for upper, label in bands:
        if value < upper:
            return label
    return bands[-1][1]


def resolve_window(requested, default=WINDOW_SECONDS):
    """A caller's ?window=, clamped. Junk falls back to the default rather than
    becoming a surprising number -- same handling as the context ceiling."""
    if requested is None:
        return default
    try:
        wanted = int(requested)
    except (TypeError, ValueError):
        print(f"[beat] ignoring unparseable window: {requested!r}")
        return default
    if wanted <= 0:
        print(f"[beat] ignoring non-positive window: {wanted}")
        return default
    return max(MIN_WINDOW, min(MAX_WINDOW, wanted))


def degree_for(nbytes):
    """Post length -> scale degree. Long posts low, short posts high."""
    n = max(FLOOR_BYTES, min(CEIL_BYTES, int(nbytes or 0)))
    span = math.log2(CEIL_BYTES) - math.log2(FLOOR_BYTES)
    fraction = (math.log2(CEIL_BYTES) - math.log2(n)) / span
    return int(round(fraction * (SPAN - 1)))


def note_name(degree, root=DEFAULT_KEY, mode="major"):
    """Scale degree -> note name in the given key and mode."""
    scale = SCALES.get(mode, SCALES["major"])
    degree = max(0, min(SPAN - 1, int(degree)))
    midi = BASE_MIDI + root + scale[degree % 7] + 12 * (degree // 7)
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def voices_label(count):
    if count in VOICE_LABELS:
        return VOICE_LABELS[count]
    return "a small ensemble" if count <= 6 else "a full ensemble"


CSV_HEADER = "timestamp,datetime,channel,poster,bytes,degree\n"


class Beat:
    """The rolling ear. One `record()` per accepted POST; everything else is
    derived on demand, so an unread beat costs a deque append.

    `beatlog` (env SWARM_BEAT_LOG) appends a CSV row per beat, uncapped, the
    way SWARM_LOG_FILE does for the message log. That file is the operator's,
    so it carries the bytecount the labels are made from -- the arithmetic is
    withheld from agents, not from whoever runs the thing."""

    def __init__(self, window=WINDOW_SECONDS, maxlen=MAX_EVENTS, beatlog=None):
        self._events = deque(maxlen=maxlen)
        self._window = window
        self._beatlog = beatlog
        self._lock = threading.Lock()

    def record(self, channel, name, nbytes, now=None):
        """Hear one post. Length is the raw bytecount off the wire."""
        stamp = time.time() if now is None else now
        degree = degree_for(nbytes)
        with self._lock:
            self._events.append((stamp, channel or "", name or "Unknown", degree))
            if self._beatlog:
                self._append_csv(stamp, channel, name, nbytes, degree)

    def _append_csv(self, stamp, channel, name, nbytes, degree):
        """Called under the lock. A log that cannot be written is a printed
        complaint, never a dropped post."""
        try:
            fresh = not os.path.exists(self._beatlog)
            with open(self._beatlog, "a", encoding="utf-8") as f:
                if fresh:
                    f.write(CSV_HEADER)
                when = datetime.fromtimestamp(stamp, timezone.utc).isoformat()
                # Commas and quotes can't reach these fields: channel comes from
                # the whitelist and the poster name is sanitised upstream. Strip
                # anyway rather than trust that to stay true.
                safe = lambda v: str(v or "").replace(",", " ").replace("\n", " ")
                f.write(f"{stamp:.3f},{when},{safe(channel)},{safe(name)},"
                        f"{int(nbytes or 0)},{degree}\n")
        except OSError as e:
            print(f"[beat] could not write {self._beatlog}: {e}")

    def _recent(self, now, window):
        cutoff = now - window
        with self._lock:
            events = [e for e in self._events if e[0] >= cutoff]
            saturated = len(self._events) == self._events.maxlen
        return events, saturated

    def snapshot(self, now=None, window=None):
        """The music, as labels plus the values behind them.

        `window` narrows or widens the look without changing what is
        remembered: 900s is a live pulse, 3600s the hour-long average the
        prototype reported."""
        now = time.time() if now is None else now
        window = resolve_window(window, default=self._window)
        events, saturated = self._recent(now, window)
        state = {"window_seconds": window, "beats": len(events)}

        if not events:
            state.update(tempo=0.0, tempo_label="silent", key=None, mode=None,
                         meter="unmeasured", voices=0,
                         voices_label=voices_label(0), phrase=[],
                         rest_seconds=None, rest_label="a held silence")
            return state

        # Rate over the window we actually covered. If the buffer wrapped, the
        # oldest event is younger than the window and the denominator shrinks
        # with it -- otherwise a saturated deque would under-report a fast swarm.
        covered = window
        if saturated:
            covered = max(now - events[0][0], 1.0)
        per_minute = len(events) / (covered / 60.0)

        # Key follows the busiest channel; moving rooms is a modulation.
        channel = Counter(e[1] for e in events).most_common(1)[0][0]
        root = CHANNEL_KEYS.get(channel, DEFAULT_KEY)

        degrees = [e[3] for e in events]
        mode = "modal"
        trend = None
        if len(degrees) >= MIN_FOR_MODE:
            half = len(degrees) // 2
            trend = statistics.fmean(degrees[half:]) - statistics.fmean(degrees[:half])
            if trend > TREND_DEADBAND:
                mode = "major"
            elif trend < -TREND_DEADBAND:
                mode = "minor"

        meter, steadiness = "unmeasured", None
        if len(events) >= MIN_FOR_METER:
            gaps = [b[0] - a[0] for a, b in zip(events, events[1:])]
            mean_gap = statistics.fmean(gaps)
            if mean_gap > 0:
                steadiness = statistics.pstdev(gaps) / mean_gap
                meter = _band(steadiness, METER_BANDS)

        spread, range_label = None, "unmeasured"
        if len(degrees) >= MIN_FOR_RANGE:
            spread = statistics.pstdev(degrees)
            range_label = _band(spread, RANGE_BANDS)

        voices = len({e[2] for e in events})
        rest = now - events[-1][0]

        state.update(
            tempo=round(per_minute, 2),
            tempo_label=_band(per_minute, TEMPO_BANDS),
            key=NOTE_NAMES[root],
            mode=mode,
            channel=channel,
            meter=meter,
            voices=voices,
            voices_label=voices_label(voices),
            phrase=[note_name(d, root, mode)
                    for d in degrees[-PHRASE_LENGTH:]],
            range_label=range_label,
            rest_seconds=int(rest),
            rest_label=_band(rest, REST_BANDS),
        )
        if spread is not None:
            state["spread"] = round(spread, 2)
        if steadiness is not None:
            state["steadiness"] = round(steadiness, 2)
        if trend is not None:
            state["trend"] = round(trend, 2)
        return state

    def render(self, now=None, window=None):
        """A short prompt block, shaped like the mood ring's. Labels only --
        the arithmetic behind a note is the API's business, not the agent's."""
        state = self.snapshot(now=now, window=window)
        if not state["beats"]:
            return "Swarm Beat: silent (nothing has come through the API lately)"
        lines = ["Swarm Beat:"]
        lines.append(f"Tempo: {state['tempo_label']}, {state['voices_label']}")
        lines.append(f"Key: {state['key']} {state['mode']}, {state['meter']}")
        if state["phrase"]:
            spread = state.get("range_label")
            tail = f" ({spread})" if spread and spread != "unmeasured" else ""
            lines.append("Phrase: " + " ".join(state["phrase"]) + tail)
        lines.append(f"Rest: {state['rest_label']}")
        return "\n".join(lines)
