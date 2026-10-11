#!/usr/bin/env python3
"""Tests for the channel that can't rhyme.

Run from api/:  python -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swarm_plain import MAX_LINES, MAX_TOKEN, validate, validate_line


class TestAccepted(unittest.TestCase):
    def test_the_three_forms(self):
        for line in ("checked: fern", "unchecked: norn", "value: fern.moisture=0.31"):
            self.assertTrue(validate(line)[0], line)

    def test_the_speaker_stamp_is_tolerated(self):
        # Agents post through send_to_swarm, which prefixes [time] <Nick>.
        self.assertTrue(validate("[13:45] <Agent_Bigz> checked: fern")[0])

    def test_several_lines(self):
        body = "checked: fern\nvalue: fern.moisture=damp\nunchecked: mood"
        self.assertTrue(validate(body)[0])

    def test_blank_lines_are_ignored(self):
        self.assertTrue(validate("checked: fern\n\n\nunchecked: norn\n")[0])

    def test_dotted_and_slashed_names(self):
        for line in ("value: swarm/general.lines=402", "checked: norn.Agent_Jungz"):
            self.assertTrue(validate(line)[0], line)

    def test_readings_may_be_words_or_numbers(self):
        for line in ("value: mood.warmth=searing", "value: mood.warmth=0.82",
                     "value: cpu.effort=41%"):
            self.assertTrue(validate(line)[0], line)


class TestBounced(unittest.TestCase):
    def test_prose_is_bounced(self):
        ok, reason = validate("[13:45] <Agent_Viz> The lattice hums at dusk")
        self.assertFalse(ok)
        self.assertIn("must start with", reason)

    def test_the_cosplay_case(self):
        # The actual thing the swarm complained about: the *form* of a report
        # with none of the substance. A length cap alone would let this through,
        # which is why the subject has to be a single token.
        ok, reason = validate("checked: the sensor integrity of the hydroponics array")
        self.assertFalse(ok)
        self.assertIn("single token", reason)

    def test_a_haiku_cannot_get_one_line_in(self):
        haiku = "the lattice hums soft\na coconut falls at dusk\nnobody checked it"
        self.assertFalse(validate(haiku)[0])

    def test_value_needs_a_reading(self):
        ok, reason = validate("value: fern.moisture")
        self.assertFalse(ok)
        self.assertIn("<name>=<reading>", reason)

    def test_unknown_verb(self):
        self.assertFalse(validate("observed: fern")[0])

    def test_empty_post(self):
        ok, reason = validate("   \n  \n")
        self.assertFalse(ok)
        self.assertIn("empty", reason)

    def test_line_cap(self):
        ok, reason = validate("\n".join(["checked: fern"] * (MAX_LINES + 1)))
        self.assertFalse(ok)
        self.assertIn("at most", reason)

    def test_token_length_cap(self):
        ok, reason = validate("checked: " + "a" * (MAX_TOKEN + 5))
        self.assertFalse(ok)
        self.assertIn("longer than", reason)

    def test_punctuation_that_carries_prose_is_refused(self):
        for line in ("checked: fern, mood", "checked: fern!", "value: a=b; c=d"):
            self.assertFalse(validate(line)[0], line)


class TestReasonsAreUseful(unittest.TestCase):
    def test_the_reason_names_the_line(self):
        ok, reason = validate("checked: fern\nthe lattice hums")
        self.assertFalse(ok)
        self.assertIn("line 2", reason)

    def test_the_reason_quotes_the_offending_text(self):
        ok, reason = validate_line("checked: two words here")
        self.assertFalse(ok)
        self.assertIn("two words here", reason)


if __name__ == "__main__":
    unittest.main()
