#!/usr/bin/env python3
"""Tests for the mood ring.

Run from api/:  python -m unittest discover -s tests

The host is faked throughout -- the source readers are swapped out -- so these
run offline, in milliseconds, on a machine with no thermal zones and prove the
logic rather than the hardware.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import swarm_mood
from swarm_mood import BASE_FREQ, MoodRing, Oscillator, band_index, label_for


class FakeHost:
    """Stands in for /proc and /sys. Any sense left as None is absent."""

    def __init__(self, cpu=None, memory=None, temperature=None, disk=None, net=None):
        self.cpu, self.memory, self.temperature = cpu, memory, temperature
        self.disk, self.net = disk, net
        self._saved = {}

    def __enter__(self):
        for name, value in (("cpu_times", lambda: self.cpu),
                            ("memory_used", lambda: self.memory),
                            ("temperature", lambda: self.temperature),
                            ("io_bytes", lambda: (self.disk, self.net))):
            self._saved[name] = getattr(swarm_mood, name)
            setattr(swarm_mood, name, value)
        return self

    def __exit__(self, *exc):
        for name, original in self._saved.items():
            setattr(swarm_mood, name, original)


class TestBanding(unittest.TestCase):
    def test_five_bands(self):
        self.assertEqual([band_index(v) for v in (0.0, 0.25, 0.5, 0.7, 0.95)],
                         [0, 1, 2, 3, 4])

    def test_boundaries_are_inclusive_below(self):
        self.assertEqual(band_index(0.199), 0)
        self.assertEqual(band_index(0.20), 1)
        self.assertEqual(band_index(0.799), 3)
        self.assertEqual(band_index(0.80), 4)

    def test_labels_are_words_not_numbers(self):
        self.assertEqual(label_for("warmth", 0.05), "cold")
        self.assertEqual(label_for("warmth", 0.95), "searing")
        self.assertEqual(label_for("effort", 0.5), "working")


class TestSensesAreOptional(unittest.TestCase):
    def test_a_host_with_no_sensors_says_so(self):
        # Wrong loudly: no readings means no reading, not a plausible zero.
        with FakeHost():
            ring = MoodRing()
            ring.sample(now=0)
            self.assertEqual(ring.snapshot()["senses"], [])
            self.assertIn("unavailable", ring.render())

    def test_missing_thermal_zone_drops_only_that_axis(self):
        with FakeHost(memory=0.5, temperature=None):
            ring = MoodRing()
            ring.sample(now=0)
            state = ring.snapshot()
            self.assertIn("saturation", state)
            self.assertNotIn("warmth", state)
            self.assertNotIn("warmth_label", state)

    def test_temperature_maps_into_bands(self):
        with FakeHost(temperature=30.0) as host:
            ring = MoodRing()
            ring.sample(now=0)
            self.assertEqual(ring.snapshot()["warmth_label"], "cold")
            host.temperature = 90.0
            ring = MoodRing()
            ring.sample(now=0)
            self.assertEqual(ring.snapshot()["warmth_label"], "searing")


class TestCounters(unittest.TestCase):
    def test_first_sample_of_a_counter_is_not_a_spike(self):
        # A monotonic counter's first reading has no predecessor; treating its
        # absolute value as a rate would report a flood on every restart.
        with FakeHost(disk=10 ** 9, net=10 ** 9):
            ring = MoodRing()
            ring.sample(now=0)
            self.assertEqual(ring.snapshot()["churn"], 0.0)

    def test_counter_reset_does_not_go_negative(self):
        with FakeHost(disk=1000, net=1000) as host:
            ring = MoodRing()
            ring.sample(now=0)
            ring.sample(now=1)
            host.disk, host.net = 5, 5      # counters wrapped / device replaced
            ring.sample(now=2)
            self.assertGreaterEqual(ring.snapshot()["churn"], 0.0)

    def test_cpu_utilisation_from_jiffy_deltas(self):
        # busy 0->50 of total 0->100 across the interval = half loaded.
        with FakeHost(cpu=(0, 0)) as host:
            ring = MoodRing()
            ring.sample(now=0)
            host.cpu = (50, 100)
            ring.sample(now=1)
            self.assertAlmostEqual(ring.oscillators["effort"].level[-1][1], 0.5, places=3)


class TestOscillator(unittest.TestCase):
    def test_a_steadily_busy_stream_outruns_an_idle_one(self):
        # The bug worth a regression test: driving frequency from rate of change
        # alone makes a pegged CPU indistinguishable from an idle one, and pins
        # coherence at 1.0 for every steady state.
        busy, idle = Oscillator("busy"), Oscillator("idle")
        for t in range(5):
            busy.observe(1.0, rate=0.0, now=t)
            idle.observe(0.0, rate=0.0, now=t)
        self.assertGreater(busy.freq, idle.freq)

    def test_a_moving_stream_outruns_a_still_one_at_the_same_level(self):
        moving, still = Oscillator("moving"), Oscillator("still")
        moving.observe(0.5, rate=1.0, now=0)
        still.observe(0.5, rate=0.0, now=0)
        self.assertGreater(moving.freq, still.freq)

    def test_window_evicts_old_samples(self):
        osc = Oscillator("x")
        osc.observe(1.0, 0.0, now=0, window=10)
        osc.observe(0.0, 0.0, now=100, window=10)
        self.assertEqual(len(osc.level), 1)
        self.assertEqual(osc.mean(), 0.0)


class TestCoupling(unittest.TestCase):
    """The part the K-SOM prototype was missing: without a coupling term the
    phases are independent clocks and coherence measures nothing."""

    def _ring_with(self, freqs, coupling):
        ring = MoodRing(coupling=coupling)
        for i, freq in enumerate(freqs):
            osc = Oscillator(f"s{i}")
            osc.freq = freq
            osc.phase = i * 1.5      # deliberately spread apart to start
            ring.oscillators[osc.name] = osc
        return ring

    def test_similar_frequencies_pull_into_step(self):
        ring = self._ring_with([1.0, 1.05], coupling=0.6)
        for _ in range(400):
            ring._advance(0.05)
        self.assertGreater(ring.coherence(), 0.95)

    def test_divergent_frequencies_stay_apart(self):
        # Two oscillators lock only when coupling exceeds their frequency gap.
        ring = self._ring_with([0.2, 2.4], coupling=0.6)
        worst = 1.0
        for _ in range(400):
            ring._advance(0.05)
            worst = min(worst, ring.coherence())
        self.assertLess(worst, 0.5)

    def test_stronger_coupling_captures_a_wider_spread(self):
        loose = self._ring_with([0.2, 2.4], coupling=0.1)
        tight = self._ring_with([0.2, 2.4], coupling=3.0)
        for _ in range(400):
            loose._advance(0.05)
            tight._advance(0.05)
        self.assertGreater(tight.coherence(), loose.coherence())

    def test_coherence_needs_two_oscillators(self):
        ring = self._ring_with([1.0], coupling=0.6)
        ring._advance(0.05)          # must not raise on a single sense
        self.assertEqual(ring.coherence(), 1.0)

    def test_a_long_gap_between_polls_is_not_a_long_night(self):
        # /mood is polled on demand, so gaps are arbitrary. An unclamped step
        # would spin the phases through many revolutions and randomise them.
        ring = self._ring_with([1.0, 1.05], coupling=0.6)
        for _ in range(200):
            ring._advance(0.05)
        settled = ring.coherence()
        ring._advance(86400)
        self.assertAlmostEqual(ring.coherence(), settled, delta=0.35)


class TestCoherenceIsUsableWeather(unittest.TestCase):
    """Coherence has to do two things at once: tell the two states apart, and
    hold still enough to read. The first tuning failed both -- coupling 0.6
    locked everything (no separation), and the raw order parameter beats below
    the locking threshold (no stillness)."""

    def _drive(self, ring, together, steps=200):
        import random
        random.seed(3)
        t = 0.0
        for i in range(steps):
            t += 2.0
            if together:
                base = 0.5 + 0.1 * random.gauss(0, 1)
                values = {"effort": base, "saturation": base * 0.9, "churn": base * 1.05}
            else:
                values = {"effort": 0.85, "saturation": 0.12, "churn": 0.02}
            for name, value in values.items():
                osc = ring.oscillators.get(name)
                if osc is None:
                    osc = ring.oscillators[name] = Oscillator(name)
                    osc.phase = len(ring.oscillators) * 2.0
                previous = osc.level[-1][1] if osc.level else value
                osc.observe(max(0.0, min(1.0, value)), abs(value - previous), t)
            ring._advance(2.0)
            instant = ring.coherence()
            ring._coherence.append((t, instant))
            cutoff = t - ring.window_seconds
            while ring._coherence and ring._coherence[0][0] < cutoff:
                ring._coherence.popleft()
        return ring.settled_coherence()

    def test_it_separates_together_from_divergent(self):
        together = self._drive(MoodRing(), together=True)
        divergent = self._drive(MoodRing(), together=False)
        self.assertGreater(together - divergent, 0.15,
                           "coherence cannot tell a machine doing one thing "
                           "from one doing several -- coupling is too strong")

    def test_coupling_stays_under_the_locking_threshold(self):
        # Guard the tuning itself: raise coupling far enough and everything
        # locks, which is exactly the failure this replaced.
        locked = self._drive(MoodRing(coupling=0.6), together=False)
        loose = self._drive(MoodRing(), together=False)
        self.assertGreater(locked, loose)

    def test_settled_coherence_smooths_a_beating_signal(self):
        ring = MoodRing()
        for i, value in enumerate([0.1, 0.9, 0.1, 0.9, 0.1, 0.9]):
            ring._coherence.append((float(i), value))
        self.assertAlmostEqual(ring.settled_coherence(), 0.5, places=6)

    def test_settled_falls_back_to_instantaneous_before_any_history(self):
        ring = MoodRing()
        self.assertIsNone(ring.settled_coherence())


class TestRendering(unittest.TestCase):
    def test_render_is_labels_first(self):
        with FakeHost(memory=0.9, temperature=85.0):
            ring = MoodRing()
            ring.sample(now=0)
            text = ring.render()
        self.assertIn("Saturation: saturated", text)
        self.assertIn("Warmth: searing", text)
        self.assertIn("Swarm Mood:", text)

    def test_snapshot_reports_which_senses_exist(self):
        with FakeHost(memory=0.5, disk=1, net=1):
            ring = MoodRing()
            ring.sample(now=0)
            self.assertEqual(ring.snapshot()["senses"], ["churn", "saturation"])


if __name__ == "__main__":
    unittest.main()
