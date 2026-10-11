#!/usr/bin/env python3
"""Tests for swarm conditions: pace and stillness.

Run from api/:  python -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swarm_pace import Conditions, is_human_post, to_headers


class TestIsHumanPost(unittest.TestCase):
    def test_truthy_forms(self):
        for value in ("true", "True", "TRUE", " yes ", "1"):
            self.assertTrue(is_human_post(value), value)

    def test_falsy_forms(self):
        for value in (None, "", "false", "0", "no", "agent"):
            self.assertFalse(is_human_post(value), value)


class TestDefaultsAreInert(unittest.TestCase):
    def test_a_swarm_with_no_limits_never_settles(self):
        c = Conditions(started=0)
        for _ in range(1000):
            c.record_post(human=False, now=0)
        state = c.snapshot(now=10 ** 9)   # decades later, still chattering
        self.assertFalse(state["still"])
        self.assertIsNone(state["reason"])
        self.assertEqual(state["pace"], 1.0)


class TestStillAfter(unittest.TestCase):
    def test_settles_once_nobody_is_around(self):
        c = Conditions(still_after=600, started=0)
        self.assertFalse(c.snapshot(now=599)["still"])
        state = c.snapshot(now=600)
        self.assertTrue(state["still"])
        self.assertEqual(state["reason"], "no human present")

    def test_a_human_stirs_it_again(self):
        c = Conditions(still_after=600, started=0)
        self.assertTrue(c.snapshot(now=900)["still"])
        c.record_post(human=True, now=900)
        self.assertFalse(c.snapshot(now=900)["still"])
        self.assertEqual(c.snapshot(now=900)["seconds_since_human"], 0)

    def test_agent_posts_do_not_stir_it(self):
        c = Conditions(still_after=600, started=0)
        c.record_post(human=False, now=700)
        self.assertTrue(c.snapshot(now=700)["still"])


class TestStillPosts(unittest.TestCase):
    def test_chatter_budget_runs_out(self):
        c = Conditions(still_posts=3, started=0)
        for _ in range(2):
            c.record_post(human=False, now=0)
        self.assertFalse(c.snapshot(now=0)["still"])
        c.record_post(human=False, now=0)
        state = c.snapshot(now=0)
        self.assertTrue(state["still"])
        self.assertEqual(state["reason"], "post budget spent")

    def test_a_human_refills_the_budget(self):
        c = Conditions(still_posts=2, started=0)
        c.record_post(human=False, now=0)
        c.record_post(human=False, now=0)
        self.assertTrue(c.snapshot(now=0)["still"])
        c.record_post(human=True, now=0)
        self.assertFalse(c.snapshot(now=0)["still"])
        self.assertEqual(c.snapshot(now=0)["posts_since_human"], 0)

    def test_whichever_limit_trips_first_wins(self):
        c = Conditions(still_after=600, still_posts=2, started=0)
        c.record_post(human=False, now=10)
        c.record_post(human=False, now=20)
        self.assertEqual(c.snapshot(now=20)["reason"], "post budget spent")


class TestSnapshotShape(unittest.TestCase):
    def test_starts_awake_not_silent(self):
        # Server start counts as the last stir, so a fresh swarm runs and then
        # settles rather than booting into silence.
        c = Conditions(still_after=600, still_posts=1)
        self.assertFalse(c.snapshot()["still"])

    def test_context_lines_included_when_given(self):
        state = Conditions(started=0).snapshot(now=0, context_lines=60)
        self.assertEqual(state["context_lines"], 60)
        self.assertNotIn("context_lines", Conditions(started=0).snapshot(now=0))

    def test_headers(self):
        c = Conditions(pace=0.25, still_after=10, started=0)
        self.assertEqual(to_headers(c.snapshot(now=0)),
                         [("Swarm-Pace", "0.25"), ("Swarm-Stillness", "False")])
        self.assertEqual(to_headers(c.snapshot(now=99))[1],
                         ("Swarm-Stillness", "True"))


if __name__ == "__main__":
    unittest.main()
