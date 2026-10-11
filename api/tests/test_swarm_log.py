#!/usr/bin/env python3
"""Tests for the swarm message log + identity resolution.

Run from api/:  python -m unittest discover -s tests
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import swarm_log
from swarm_log import MessageLog, resolve_identity


class TestIdentity(unittest.TestCase):
    def test_header_trusted(self):
        self.assertEqual(resolve_identity("Agent_Jungz", "whatever"), ("Agent_Jungz", True))

    def test_header_wins_over_body(self):
        self.assertEqual(resolve_identity("Real_Name", "<Faked> hi"), ("Real_Name", True))

    def test_body_nick_uncertain(self):
        self.assertEqual(resolve_identity(None, "[12:00] <Gem_In_Eye> hello"),
                         ("Gem_In_Eye", False))

    def test_no_identity(self):
        self.assertEqual(resolve_identity(None, "just some text"), ("Unknown", False))

    def test_nick_regex_alnum_underscore_only(self):
        # Punctuation/spaces inside brackets shouldn't match a nick.
        self.assertEqual(resolve_identity(None, "<not a nick!> text"), ("Unknown", False))
        self.assertEqual(resolve_identity(None, "<Norn_7> text"), ("Norn_7", False))


class TestMessageLog(unittest.TestCase):
    def test_format_certain_vs_uncertain(self):
        log = MessageLog(maxlen=10)
        certain = log.record("general.txt", "Jungz", True, "hi there", now=0)
        uncertain = log.record("general.txt", "Gem_In_Eye", False, "boo", now=0)
        self.assertIn("[general.txt] <Jungz> hi there", certain)
        self.assertIn("<Gem_In_Eye> (Uncertain) boo", uncertain)
        self.assertTrue(certain.startswith("1970-01-01T00:00:00Z"))

    def test_collapses_newlines_and_truncates(self):
        log = MessageLog()
        line = log.record("t", "X", True, "a\nb\n\nc", now=0)
        self.assertIn("<X> a b c", line)
        long_line = log.record("t", "X", True, "y" * 900, now=0)
        self.assertIn("…", long_line)

    def test_cap_is_bounded(self):
        log = MessageLog(maxlen=3)
        for i in range(5):
            log.record("t", "X", True, f"msg{i}", now=0)
        recent = log.recent()
        self.assertEqual(len(recent), 3)
        self.assertIn("msg4", recent[-1])
        self.assertNotIn("msg0", "".join(recent))

    def test_file_append(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "log.txt")
            log = MessageLog(logfile=path)
            log.record("t", "X", True, "one", now=0)
            log.record("t", "Y", False, "two", now=0)
            with open(path) as f:
                lines = f.read().strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertIn("<Y> (Uncertain) two", lines[1])


if __name__ == "__main__":
    unittest.main()
