#!/usr/bin/env python3
"""Tests for the swarm's beat — the API's own hearing.

Run from api/:  python -m unittest discover -s tests
"""

import csv
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swarm_beat import (CEIL_BYTES, FLOOR_BYTES, MAX_WINDOW, MIN_WINDOW, SPAN,
                        Beat, degree_for, note_name, resolve_window,
                        voices_label)


def feed(beat, count, *, start=1000.0, gap=20.0, size=200, channel="swarm.txt",
         names=("A", "B", "C", "D"), shrink=0):
    """Post `count` messages, optionally shortening each one by `shrink` bytes."""
    for i in range(count):
        beat.record(channel, names[i % len(names)], max(1, size - i * shrink),
                    now=start + i * gap)
    return start + (count - 1) * gap


class TestPitch(unittest.TestCase):
    def test_short_posts_sit_above_long_ones(self):
        self.assertGreater(degree_for(20), degree_for(2000))

    def test_the_range_is_clamped_at_both_ends(self):
        # A 40kb paste is simply the lowest note, not an outlier that flattens
        # every other post in the window.
        self.assertEqual(degree_for(1), degree_for(FLOOR_BYTES))
        self.assertEqual(degree_for(40000), degree_for(CEIL_BYTES))
        self.assertEqual(degree_for(CEIL_BYTES), 0)
        self.assertEqual(degree_for(FLOOR_BYTES), SPAN - 1)

    def test_nonsense_lengths_do_not_raise(self):
        for value in (None, 0, -5):
            self.assertEqual(degree_for(value), SPAN - 1)

    def test_typical_posts_land_in_a_usable_octave(self):
        # Real swarm traffic is roughly 60..800 bytes; if that squashed into
        # one or two degrees the phrase would be a flat line.
        spread = {degree_for(n) for n in (60, 120, 250, 500, 800)}
        self.assertGreaterEqual(len(spread), 4)

    def test_a_degree_names_itself_in_key(self):
        self.assertEqual(note_name(0, root=2, mode="major"), "D2")
        self.assertEqual(note_name(7, root=2, mode="major"), "D3")
        # Third degree is what separates the modes.
        self.assertEqual(note_name(2, root=0, mode="major"), "E2")
        self.assertEqual(note_name(2, root=0, mode="minor"), "D#2")

    def test_naming_survives_a_degree_out_of_range(self):
        self.assertTrue(note_name(-4))
        self.assertTrue(note_name(999))


class TestSilence(unittest.TestCase):
    def test_an_unheard_swarm_says_so(self):
        state = Beat().snapshot(now=1000.0)
        self.assertEqual(state["beats"], 0)
        self.assertEqual(state["tempo_label"], "silent")
        self.assertIsNone(state["key"])
        self.assertIn("silent", Beat().render(now=1000.0))

    def test_events_older_than_the_window_fall_out_of_earshot(self):
        beat = Beat(window=100)
        beat.record("swarm.txt", "A", 200, now=1000.0)
        self.assertEqual(beat.snapshot(now=1050.0)["beats"], 1)
        self.assertEqual(beat.snapshot(now=1200.0)["beats"], 0)


class TestTempo(unittest.TestCase):
    def test_a_busy_window_reads_faster_than_a_quiet_one(self):
        quiet, busy = Beat(), Beat()
        feed(quiet, 4, gap=200.0)
        feed(busy, 120, gap=5.0)
        self.assertLess(quiet.snapshot(now=1900.0)["tempo"],
                        busy.snapshot(now=1600.0)["tempo"])

    def test_rate_stays_honest_when_the_buffer_wraps(self):
        # A fast swarm fills the deque; if the denominator stayed the full
        # window it would under-report exactly the swarms that are loudest.
        beat = Beat(window=900, maxlen=10)
        feed(beat, 40, gap=1.0)
        self.assertGreater(beat.snapshot(now=1040.0)["tempo"], 30)

    def test_rest_grows_with_the_silence(self):
        beat = Beat()
        last = feed(beat, 5)
        self.assertEqual(beat.snapshot(now=last + 10)["rest_label"], "no rest")
        self.assertEqual(beat.snapshot(now=last + 600)["rest_label"], "a long rest")


class TestMeter(unittest.TestCase):
    def test_cron_paced_posting_reads_steady(self):
        beat = Beat()
        feed(beat, 10, gap=30.0)
        self.assertEqual(beat.snapshot(now=1300.0)["meter"], "steady")

    def test_a_burst_after_a_lull_does_not(self):
        beat = Beat()
        beat.record("swarm.txt", "A", 200, now=1000.0)
        for i in range(8):
            beat.record("swarm.txt", "B", 200, now=1400.0 + i)
        self.assertNotEqual(beat.snapshot(now=1410.0)["meter"], "steady")

    def test_too_few_posts_to_claim_a_meter(self):
        beat = Beat()
        feed(beat, 2)
        self.assertEqual(beat.snapshot(now=1100.0)["meter"], "unmeasured")


class TestModeAndKey(unittest.TestCase):
    def test_quickening_into_short_posts_reads_major(self):
        beat = Beat()
        feed(beat, 16, size=900, shrink=50)
        self.assertEqual(beat.snapshot(now=1400.0)["mode"], "major")

    def test_settling_into_monologue_reads_minor(self):
        beat = Beat()
        feed(beat, 16, size=60, shrink=-50)
        self.assertEqual(beat.snapshot(now=1400.0)["mode"], "minor")

    def test_no_trend_is_modal_and_so_is_too_little_evidence(self):
        even = Beat()
        feed(even, 16, size=200)
        self.assertEqual(even.snapshot(now=1400.0)["mode"], "modal")
        sparse = Beat()
        feed(sparse, 3, size=200)
        self.assertEqual(sparse.snapshot(now=1100.0)["mode"], "modal")

    def test_the_busiest_channel_sets_the_key(self):
        beat = Beat()
        feed(beat, 8, channel="tech.txt")
        self.assertEqual(beat.snapshot(now=1200.0)["key"], "E")
        feed(beat, 20, start=1200.0, channel="gaming.txt")
        self.assertEqual(beat.snapshot(now=1700.0)["key"], "C")

    def test_an_unknown_channel_still_has_a_key(self):
        beat = Beat()
        feed(beat, 6, channel="not_a_channel.txt")
        self.assertEqual(beat.snapshot(now=1200.0)["key"], "C")

    def test_a_phrase_transposes_rather_than_going_out_of_tune(self):
        # Same posts, different busy channel -> same shape, new key.
        one, two = Beat(), Beat()
        feed(one, 8, channel="gaming.txt")     # C
        feed(two, 8, channel="swarm.txt")      # D
        first = one.snapshot(now=1200.0)["phrase"]
        second = two.snapshot(now=1200.0)["phrase"]
        self.assertEqual(len(first), len(second))
        self.assertNotEqual(first, second)


class TestVoices(unittest.TestCase):
    def test_distinct_posters_are_counted(self):
        beat = Beat()
        feed(beat, 9, names=("A", "B", "C"))
        state = beat.snapshot(now=1200.0)
        self.assertEqual(state["voices"], 3)
        self.assertEqual(state["voices_label"], "a trio")

    def test_labels_hold_at_both_ends(self):
        self.assertEqual(voices_label(0), "no voices")
        self.assertEqual(voices_label(1), "a solo")
        self.assertEqual(voices_label(6), "a small ensemble")
        self.assertEqual(voices_label(40), "a full ensemble")


class TestRender(unittest.TestCase):
    def test_the_block_carries_labels_and_no_arithmetic(self):
        beat = Beat()
        feed(beat, 12)
        text = beat.render(now=1300.0)
        self.assertIn("Swarm Beat:", text)
        self.assertIn("Tempo:", text)
        self.assertIn("Phrase:", text)
        # An agent is told the music, not the bytecount behind it.
        for leak in ("bytes", "200", "window"):
            self.assertNotIn(leak, text.lower())

    def test_missing_identity_does_not_break_the_ear(self):
        beat = Beat()
        beat.record(None, None, None, now=1000.0)
        self.assertEqual(beat.snapshot(now=1000.0)["voices"], 1)


class TestWindow(unittest.TestCase):
    def test_a_narrower_look_hears_less_of_the_same_memory(self):
        beat = Beat(window=900)
        feed(beat, 30, gap=20.0)          # spans 580s
        now = 1600.0
        self.assertEqual(beat.snapshot(now=now)["beats"], 30)
        self.assertLess(beat.snapshot(now=now, window=120)["beats"], 30)

    def test_the_hour_view_is_the_prototype_average(self):
        beat = Beat()
        feed(beat, 30, gap=100.0)         # spans 2900s, past the 900s default
        state = beat.snapshot(now=4000.0, window=3600)
        self.assertEqual(state["window_seconds"], 3600)
        self.assertEqual(state["beats"], 30)

    def test_asks_are_clamped_and_junk_falls_back(self):
        self.assertEqual(resolve_window(5), MIN_WINDOW)
        self.assertEqual(resolve_window(999999), MAX_WINDOW)
        self.assertEqual(resolve_window(1800), 1800)
        for junk in (None, "banana", "", 0, -30):
            self.assertEqual(resolve_window(junk, default=900), 900)


class TestRange(unittest.TestCase):
    def test_posts_of_one_length_sit_on_one_note(self):
        beat = Beat()
        feed(beat, 10, size=200)
        self.assertEqual(beat.snapshot(now=1300.0)["range_label"], "on one note")

    def test_mixed_lengths_spread_out(self):
        beat = Beat()
        for i, size in enumerate((20, 3000, 40, 2000, 25, 2500, 60, 1800)):
            beat.record("swarm.txt", "A", size, now=1000.0 + i * 10)
        state = beat.snapshot(now=1100.0)
        self.assertIn(state["range_label"], ("a wide range", "all over the register"))
        self.assertGreater(state["spread"], 4.5)

    def test_too_few_posts_to_claim_a_range(self):
        beat = Beat()
        feed(beat, 2)
        self.assertEqual(beat.snapshot(now=1100.0)["range_label"], "unmeasured")


class TestBeatLog(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "beats.csv")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_header_then_a_row_per_beat(self):
        beat = Beat(beatlog=self.path)
        beat.record("swarm.txt", "Agent_Bigz", 240, now=1000.0)
        beat.record("tech.txt", "Agent_Viz", 90, now=1010.0)
        rows = list(csv.reader(open(self.path)))
        self.assertEqual(rows[0], ["timestamp", "datetime", "channel", "poster",
                                   "bytes", "degree"])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][2:], ["swarm.txt", "Agent_Bigz", "240",
                                       str(degree_for(240))])

    def test_the_operator_gets_the_arithmetic_the_agents_do_not(self):
        beat = Beat(beatlog=self.path)
        beat.record("swarm.txt", "A", 512, now=1000.0)
        self.assertIn("512", open(self.path).read())
        self.assertNotIn("512", beat.render(now=1000.0))

    def test_a_comma_in_a_name_cannot_shift_a_column(self):
        beat = Beat(beatlog=self.path)
        beat.record("swarm.txt", "Bad,Name", 100, now=1000.0)
        rows = list(csv.reader(open(self.path)))
        self.assertEqual(len(rows[1]), 6)

    def test_an_unwritable_log_never_costs_a_post(self):
        beat = Beat(beatlog="/no/such/dir/beats.csv")
        beat.record("swarm.txt", "A", 100, now=1000.0)     # must not raise
        self.assertEqual(beat.snapshot(now=1000.0)["beats"], 1)


if __name__ == "__main__":
    unittest.main()
