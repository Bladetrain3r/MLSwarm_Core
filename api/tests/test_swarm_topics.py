#!/usr/bin/env python3
"""Tests for topic extraction.

Run from api/:  python -m unittest discover -s tests
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swarm_topics import (gather, read_tail, score_topics, strip_speakers,
                          tokenise, topic_words)


def chatter(words, count, nick="Agent_Jungz"):
    return "".join(f"[10:{i % 60:02d}] <{nick}> {words}\n" for i in range(count))


class TestTokenising(unittest.TestCase):
    def test_speaker_prefix_is_stripped(self):
        # Otherwise the busiest talkers become the topics.
        text = "[14:32] <Crystal_Cicada> the lattice hums"
        self.assertEqual(strip_speakers(text), "the lattice hums")

    def test_nicks_do_not_become_topics(self):
        words = tokenise(chatter("lattice hums", 40))
        self.assertNotIn("agent_jungz", words)
        self.assertNotIn("jungz", words)
        self.assertIn("lattice", words)

    def test_stopwords_and_short_words_are_dropped(self):
        self.assertEqual(tokenise("<X> the a of lattice"), ["lattice"])


class TestScoring(unittest.TestCase):
    def test_lately_beats_perennial(self):
        # The whole point: a word the swarm has always used is not a topic,
        # a word it has just picked up is.
        baseline = chatter("coconut jungle hums", 300)
        recent = chatter("coconut jungle hums", 20) + chatter("lattice resonance", 20)
        words = topic_words(recent, baseline + recent)
        self.assertEqual(sorted(words[:2]), ["lattice", "resonance"])

    def test_a_single_shout_does_not_mint_a_topic(self):
        baseline = chatter("coconut jungle", 300)
        recent = chatter("coconut jungle", 20) + "[10:01] <Zero> quantumbanana\n"
        self.assertNotIn("quantumbanana", topic_words(recent, baseline))

    def test_min_count_is_the_floor(self):
        recent = chatter("kumquat", 2)
        self.assertEqual(topic_words(recent, recent, min_count=3), [])
        self.assertIn("kumquat", topic_words(recent, recent, min_count=2))

    def test_count_caps_the_list(self):
        recent = chatter("alpha beta gamma delta epsilon zeta", 20)
        self.assertEqual(len(topic_words(recent, recent, count=3)), 3)

    def test_order_is_stable_between_identical_calls(self):
        recent = chatter("alpha beta gamma", 20)
        self.assertEqual(topic_words(recent, recent), topic_words(recent, recent))

    def test_empty_input_yields_no_topics(self):
        self.assertEqual(score_topics("", ""), [])
        self.assertEqual(topic_words("[10:00] <X> ", "nothing here"), [])


class TestGathering(unittest.TestCase):
    def test_missing_channels_contribute_nothing_rather_than_failing(self):
        with tempfile.TemporaryDirectory() as d:
            good = os.path.join(d, "general.txt")
            with open(good, "w") as handle:
                handle.write(chatter("coconut jungle", 200))
                handle.write(chatter("lattice", 30))
            words = gather([good, os.path.join(d, "absent.txt")])
            self.assertIn("lattice", words)

    def test_no_readable_channels_is_an_empty_list(self):
        self.assertEqual(gather(["/nope/absent.txt"]), [])

    def test_read_tail_is_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.txt")
            with open(path, "w") as handle:
                handle.write("".join(f"line {i}\n" for i in range(500)))
            self.assertEqual(len(read_tail(path, 10).splitlines()), 10)


if __name__ == "__main__":
    unittest.main()
