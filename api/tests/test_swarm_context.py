#!/usr/bin/env python3
"""Tests for server-side context sizing.

Run from api/:  python -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swarm_context import (DEFAULT_CONTEXT_LINES, parse_target,
                           requested_lines, resolve_lines)


class TestParseTarget(unittest.TestCase):
    def test_plain_path(self):
        self.assertEqual(parse_target("/swarm/general.txt"), ("general.txt", {}))

    def test_query_is_split_off_before_the_whitelist_sees_it(self):
        filename, query = parse_target("/swarm/general.txt?lines=60")
        self.assertEqual(filename, "general.txt")
        self.assertEqual(query["lines"], ["60"])

    def test_trailing_slash_and_other_prefixes(self):
        self.assertEqual(parse_target("/swarm/tech.txt/")[0], "tech.txt")
        self.assertEqual(parse_target("/logs")[0], "")


class TestRequestedLines(unittest.TestCase):
    def test_no_ask(self):
        self.assertIsNone(requested_lines(None, {}))

    def test_header_wins_over_query(self):
        self.assertEqual(requested_lines("40", {"lines": ["900"]}), 40)

    def test_query_used_when_no_header(self):
        self.assertEqual(requested_lines(None, {"lines": ["120"]}), 120)

    def test_junk_is_ignored_not_reinterpreted(self):
        # Wrong loudly: unparseable/absurd asks fall back to "no ask", they
        # never silently become a different number.
        self.assertIsNone(requested_lines("lots", {}))
        self.assertIsNone(requested_lines("", {}))
        self.assertIsNone(requested_lines("0", {}))
        self.assertIsNone(requested_lines("-5", {}))


class TestResolveLines(unittest.TestCase):
    def test_default_is_unchanged_behaviour(self):
        self.assertEqual(resolve_lines(None, {}), DEFAULT_CONTEXT_LINES)

    def test_ask_for_less_is_granted(self):
        self.assertEqual(resolve_lines("60", {}, ceiling=1000), 60)

    def test_ask_for_more_is_clamped_to_the_ceiling(self):
        self.assertEqual(resolve_lines("50000", {}, ceiling=1000), 1000)

    def test_cheap_environment_caps_an_agent_that_did_not_ask(self):
        # The dev-swarm case: server dialled down, agent unchanged.
        self.assertEqual(resolve_lines(None, {}, ceiling=60), 60)

    def test_junk_ask_gets_the_ceiling(self):
        self.assertEqual(resolve_lines("banana", {}, ceiling=60), 60)


if __name__ == "__main__":
    unittest.main()
