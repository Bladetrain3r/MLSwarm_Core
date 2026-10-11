#!/usr/bin/env python3
"""
The swarm's mood ring — the host's own physical rhythm, rendered as weather.

Takes a frond from DigiFern: an unbounded stream of numbers becomes a handful of
labelled bands, and the creatures perceive it rather than reading gauges. The
fern is the swarm's semantic weather; this is its physical weather. Same shape of
output on purpose, so an agent reads both the same way.

Non-numeric by design (`api/CHANGES.md` v0.2): "the silicon hums in normal
warmth", never "Temp: 47C". Labels travel between hosts; readings don't.

## The rhythm part

Lifted from a K-SOM server-monitor prototype, minus the parts that cost more than
they returned. That prototype gave every *process* an oscillator on a
self-organising map -- hundreds of them, an O(threads x grid) search per cycle,
and (the fatal bit) no coupling between the oscillators whose synchrony it was
trying to measure. Kuramoto with no coupling term is just independent clocks
drifting apart, so its "coherence" could only ever fall.

What survives is the good idea at a fraction of the cost: a handful of
oscillators, **one per metric stream** rather than one per process, genuinely
coupled to each other. Six oscillators need no numpy and no SOM -- the whole
update is a dozen lines of `math` -- and they yield the two numbers that were
wanted all along:

  * **coherence** -- are the machine's systems moving together or pulling apart?
    High when everything rises and falls as one (a single big job); low when CPU
    thrashes while the disk sits idle (many small unrelated things).
  * **tempo** -- how fast the whole thing is breathing.

## Sources

Read straight from `/proc` and `/sys` so the substrate keeps its stdlib-only
rule (`DESIGN.md`). Every source is optional: a missing one drops its axis and
says so, rather than substituting a plausible number.

Stdlib only. Read-only. Never raises.
"""

import math
import time
from collections import deque
from pathlib import Path

# Bands mirror utils/digifern/fern_core.py so both weathers read alike.
AXIS_LABELS = {
    "effort": ["still", "stirring", "working", "straining", "labouring"],
    "saturation": ["empty", "roomy", "balanced", "crowded", "saturated"],
    "warmth": ["cold", "cool", "warm", "hot", "searing"],
    "churn": ["quiet", "trickling", "flowing", "busy", "flooded"],
}
TEMPO_LABELS = ["becalmed", "slow", "steady", "brisk", "racing"]

# How long a reading is averaged over before it counts as weather rather than a
# spike -- v0.2 asks for 3-5 minutes.
WINDOW_SECONDS = 240

# Kuramoto coupling. Strong enough that related systems pull together, weak
# enough that genuinely divergent ones stay apart.
#
# Tuning note: two oscillators lock when the coupling exceeds their frequency
# gap. With FREQ_GAIN at 2.0 the gap ran 0..2.0 against a coupling of 0.6, so
# the threshold sat near the very bottom of the range -- almost everything was
# unlocked, and ordinary sampling noise flipped it in and out. A gain of 1.2
# puts the transition in the middle, where it separates "these systems are
# doing the same thing" from "these are not" instead of tracking jitter.
#
# The coupling then has to come down to match. Measured against two synthetic
# hosts -- one whose systems rise and fall together, one with a pegged CPU
# beside an idle disk -- coupling 0.6 separates them by 0.06 (i.e. not at all,
# everything locks), while 0.10-0.15 separates them by ~0.3. Below the locking
# threshold the order parameter *beats* as phases drift past one another, which
# is real dynamics rather than noise, but it is not weather: the reported value
# is averaged over the window like every other axis.
COUPLING = 0.12
BASE_FREQ = 0.20      # radians/sec for a perfectly idle stream
FREQ_GAIN = 1.2       # how far a fully-busy stream outruns an idle one

# Integration step for the phase update. The phase advance is freq*dt, so with
# freq up to ~1.4 rad/s a single Euler step over a 5s poll gap would swing a
# phase most of the way round the circle -- the trajectory is then aliasing
# noise, not dynamics, and coherence jumps about accordingly. Substep instead.
SUBSTEP = 0.05

# A stream ticks fast because it is *high* or because it is *moving*. Both
# matter: a pegged CPU is not becalmed just because it is steadily pegged, and
# a stream swinging wildly around a low mean is not resting either. Dropping the
# level term makes every steady state look identical and pins coherence at 1.
LEVEL_WEIGHT = 0.6
RATE_WEIGHT = 0.4

# How hard a new sample pulls the frequency-driving value. Low, because this is
# weather: the axis labels are averaged over minutes and the physics underneath
# them should be too.
SMOOTHING = 0.25


def band_index(value):
    """Five bands over 0..1. Mirrors the fern's banding, shifted to a
    unipolar scale (the fern's axes run -1..1, these run 0..1)."""
    if value < 0.20:
        return 0
    if value < 0.40:
        return 1
    if value < 0.60:
        return 2
    if value < 0.80:
        return 3
    return 4


def label_for(axis, value):
    return AXIS_LABELS[axis][band_index(value)]


# --------------------------------------------------------------------------
# Sources. Each returns a raw number or None; None means "no such sense here".
# --------------------------------------------------------------------------

def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def cpu_times():
    """(busy, total) jiffies from /proc/stat, or None."""
    text = _read("/proc/stat")
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("cpu "):
            try:
                fields = [int(f) for f in line.split()[1:]]
            except ValueError:
                return None
            if len(fields) < 4:
                return None
            idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
            total = sum(fields)
            return total - idle, total
    return None


def memory_used():
    """Fraction of memory in use, or None."""
    text = _read("/proc/meminfo")
    if not text:
        return None
    values = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        try:
            values[key] = int(rest.split()[0])
        except (IndexError, ValueError):
            continue
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total:
        return None
    if available is None:
        available = values.get("MemFree", 0) + values.get("Cached", 0)
    return max(0.0, min(1.0, 1.0 - available / total))


def temperature():
    """Hottest thermal zone in degrees C, or None where there are no sensors."""
    hottest = None
    try:
        zones = sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp"))
    except OSError:
        return None
    for zone in zones:
        raw = _read(zone)
        if not raw:
            continue
        try:
            celsius = int(raw.strip()) / 1000.0
        except ValueError:
            continue
        # Some zones report nonsense; ignore obviously wrong readings rather
        # than letting one bad sensor set the swarm's mood.
        if 0 < celsius < 150 and (hottest is None or celsius > hottest):
            hottest = celsius
    return hottest


def io_bytes():
    """(disk sectors, network bytes) counters, or None each."""
    disk = net = None
    text = _read("/proc/diskstats")
    if text:
        total = 0
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 10 and not parts[2].startswith(("loop", "ram")):
                try:
                    total += int(parts[5]) + int(parts[9])   # sectors r + w
                except ValueError:
                    continue
        disk = total
    text = _read("/proc/net/dev")
    if text:
        total = 0
        for line in text.splitlines()[2:]:
            _, _, rest = line.partition(":")
            parts = rest.split()
            if len(parts) >= 9:
                try:
                    total += int(parts[0]) + int(parts[8])   # rx + tx bytes
                except ValueError:
                    continue
        net = total
    return disk, net


class Oscillator:
    """One metric stream, carrying a phase. Its natural frequency rises with how
    fast the metric is moving -- a stream that is changing quickly ticks fast."""

    def __init__(self, name):
        self.name = name
        self.phase = 0.0
        self.freq = BASE_FREQ
        self.level = deque()      # (timestamp, value) inside the window
        self.smooth = None        # EMA of the level, drives the frequency
        self.smooth_rate = 0.0    # EMA of the rate of change

    def observe(self, value, rate, now, window=WINDOW_SECONDS):
        self.level.append((now, value))
        cutoff = now - window
        while self.level and self.level[0][0] < cutoff:
            self.level.popleft()
        # Smooth before driving the physics. The displayed axis was already
        # averaged over the window while the frequency reacted to the raw
        # sample, so the labels sat still while coherence thrashed underneath
        # them -- one busy instant was enough to unlock the whole ring.
        self.smooth = value if self.smooth is None else \
            self.smooth + SMOOTHING * (value - self.smooth)
        self.smooth_rate += SMOOTHING * (abs(rate) - self.smooth_rate)
        drive = (LEVEL_WEIGHT * min(1.0, abs(self.smooth))
                 + RATE_WEIGHT * min(1.0, self.smooth_rate))
        self.freq = BASE_FREQ + FREQ_GAIN * min(1.0, drive)

    def mean(self):
        if not self.level:
            return 0.0
        return sum(v for _, v in self.level) / len(self.level)


class MoodRing:
    """Samples the host, couples the oscillators, renders the weather."""

    def __init__(self, window_seconds=WINDOW_SECONDS, coupling=COUPLING):
        self.window_seconds = window_seconds
        self.coupling = coupling
        self.oscillators = {}
        self._coherence = deque()  # (timestamp, order parameter) in the window
        self._prev = {}           # raw counters from the last sample
        self._last_sample = None
        self.samples = 0

    # -- sampling ---------------------------------------------------------
    def _rate(self, key, value, dt, scale):
        """Change per second of a monotonic counter, normalised to 0..1."""
        previous = self._prev.get(key)
        self._prev[key] = value
        if previous is None or dt <= 0 or value < previous:
            return 0.0            # first sample, or the counter wrapped
        return min(1.0, (value - previous) / dt / scale)

    def sample(self, now=None):
        """Take one reading. Cheap: a few small file reads, no sleeping, no
        process walk. Safe to call on demand from a request handler."""
        now = time.time() if now is None else now
        dt = 0.0 if self._last_sample is None else now - self._last_sample
        self._last_sample = now
        readings = {}

        times = cpu_times()
        if times:
            busy, total = times
            prev = self._prev.get("_cpu")
            self._prev["_cpu"] = (busy, total)
            if prev and total > prev[1]:
                readings["effort"] = (busy - prev[0]) / (total - prev[1]), None
            elif prev is None:
                readings["effort"] = (0.0, None)

        used = memory_used()
        if used is not None:
            readings["saturation"] = (used, None)

        celsius = temperature()
        if celsius is not None:
            # 30C cold .. 90C searing, the band range v0.2 asks for.
            readings["warmth"] = (max(0.0, min(1.0, (celsius - 30.0) / 60.0)), celsius)

        disk, net = io_bytes()
        churn = []
        if disk is not None:
            churn.append(self._rate("_disk", disk, dt, scale=20000))     # sectors/s
        if net is not None:
            churn.append(self._rate("_net", net, dt, scale=5_000_000))   # bytes/s
        if churn:
            readings["churn"] = (sum(churn) / len(churn), None)

        for name, (value, _raw) in readings.items():
            osc = self.oscillators.get(name)
            if osc is None:
                osc = self.oscillators[name] = Oscillator(name)
                # Spread starting phases so a fresh ring isn't spuriously
                # coherent before it has seen anything.
                osc.phase = (len(self.oscillators) * 2.0 * math.pi) / 6.0
            previous = osc.level[-1][1] if osc.level else value
            rate = abs(value - previous) / dt if dt > 0 else 0.0
            osc.observe(value, rate, now, self.window_seconds)

        if dt > 0:
            self._advance(dt)
        instant = self.coherence()
        if instant is not None:
            self._coherence.append((now, instant))
            cutoff = now - self.window_seconds
            while self._coherence and self._coherence[0][0] < cutoff:
                self._coherence.popleft()
        self.samples += 1
        return readings

    # -- dynamics ---------------------------------------------------------
    def _advance(self, dt):
        """Kuramoto: each oscillator is pulled toward the others.

        This is the coupling the prototype was missing. Without it the phases
        are independent clocks and coherence measures nothing but how far their
        frequencies have drifted apart.
        """
        oscs = list(self.oscillators.values())
        if len(oscs) < 2:
            return
        elapsed = min(dt, 5.0)    # a long gap between polls isn't a long night
        steps = max(1, int(elapsed / SUBSTEP))
        step = elapsed / steps
        two_pi = 2 * math.pi
        for _ in range(steps):
            phases = [o.phase for o in oscs]
            for i, osc in enumerate(oscs):
                pull = sum(math.sin(phases[j] - phases[i])
                           for j in range(len(oscs)) if j != i) / (len(oscs) - 1)
                osc.phase = (osc.phase + (osc.freq + self.coupling * pull) * step) % two_pi

    def coherence(self):
        """Kuramoto order parameter: 1.0 = every system moving as one,
        0.0 = all pulling in different directions."""
        oscs = list(self.oscillators.values())
        if not oscs:
            return None
        total = sum(complex(math.cos(o.phase), math.sin(o.phase)) for o in oscs)
        return abs(total) / len(oscs)

    def settled_coherence(self):
        """Coherence as weather: the order parameter averaged over the window.

        `coherence()` is the instantaneous value and is what the physics and the
        tests care about. Below the locking threshold it oscillates as phases
        beat against each other, so reporting it raw makes the mood ring look
        like it is flickering when the machine is simply doing two unrelated
        things at once."""
        if not self._coherence:
            return self.coherence()
        return sum(v for _, v in self._coherence) / len(self._coherence)

    def tempo(self):
        """Mean oscillator frequency, normalised to 0..1."""
        oscs = list(self.oscillators.values())
        if not oscs:
            return None
        mean = sum(o.freq for o in oscs) / len(oscs)
        return max(0.0, min(1.0, (mean - BASE_FREQ) / FREQ_GAIN))

    # -- rendering --------------------------------------------------------
    def snapshot(self):
        """The weather, as labels plus the values behind them."""
        state = {"senses": sorted(self.oscillators), "samples": self.samples}
        for axis in AXIS_LABELS:
            osc = self.oscillators.get(axis)
            if osc is None:
                continue          # no such sense on this host; say nothing
            value = osc.mean()
            state[axis] = round(value, 3)
            state[f"{axis}_label"] = label_for(axis, value)
        coherence = self.settled_coherence()
        if coherence is not None:
            state["coherence"] = round(coherence, 3)
        tempo = self.tempo()
        if tempo is not None:
            state["tempo"] = round(tempo, 3)
            state["tempo_label"] = TEMPO_LABELS[band_index(tempo)]
        return state

    def render(self):
        """A short prompt block, shaped like the fern's so agents read both the
        same way. Says so plainly when a host has no senses to report."""
        state = self.snapshot()
        if not state["senses"]:
            return "Swarm Mood: unavailable (no readable sensors on this host)"
        lines = ["Swarm Mood:"]
        for axis in AXIS_LABELS:
            if axis in state:
                lines.append(f"{axis.capitalize()}: {state[f'{axis}_label']} ({state[axis]:.2f})")
        if "coherence" in state:
            lines.append(f"Coherence: {state['coherence']:.2f}")
        if "tempo" in state:
            lines.append(f"Tempo: {state['tempo_label']} ({state['tempo']:.2f})")
        return "\n".join(lines)
