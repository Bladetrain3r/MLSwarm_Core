#!/usr/bin/env python3
"""Tests for the norn `breed` operation.

Run from the norns directory:

    python -m unittest discover -s tests
"""

import json
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Napnorn_Backpack_Experimental as nb
from Napnorn_Backpack_Experimental import NapNorn, breed_norns


def _make_parent(name, lines, save_dir):
    norn = NapNorn(name, save_dir=save_dir)
    for line in lines:
        norn.perceive(line)
    norn.save_brain()
    return os.path.join(save_dir, f"{name}_brain.json")


class TestMutation(unittest.TestCase):
    def test_no_mutation_when_rate_zero(self):
        self.assertEqual(nb._mutate_fragment("one two three four", 0.0),
                         "one two three four")

    def test_mutation_changes_word_count(self):
        random.seed(1)
        out = nb._mutate_fragment("one two three four five", 1.0)
        self.assertNotEqual(len(out.split()), 5)  # dropped or duplicated a word

    def test_single_word_never_mutates(self):
        self.assertEqual(nb._mutate_fragment("solo", 1.0), "solo")

    def test_portmanteau(self):
        self.assertEqual(nb._portmanteau("Sparky", "Hamlet"), "Spalet")
        self.assertTrue(nb._portmanteau("", ""))  # non-empty fallback


class TestGridOsmosis(unittest.TestCase):
    def test_resize_dims_and_corners(self):
        src = [["a", "b"], ["c", "d"]]  # 2x2
        out = nb._resize_map(src, 4, 4)  # upscale
        self.assertEqual(len(out), 4)
        self.assertTrue(all(len(r) == 4 for r in out))
        self.assertEqual(out[0][0], "a")   # top-left preserved
        self.assertEqual(out[-1][-1], "d")  # bottom-right preserved

    def test_resize_ragged_and_empty(self):
        self.assertEqual(len(nb._resize_map([], 3, 2)), 2)      # empty -> filled base
        ragged = [["x"], ["y", "z", "w"]]
        out = nb._resize_map(ragged, 5, 4)
        self.assertTrue(all(len(r) == 5 for r in out))

    def test_blend_dims_and_source(self):
        a = [["A"] * 4 for _ in range(4)]
        b = [["B"] * 4 for _ in range(4)]
        random.seed(0)
        out = nb.blend_grid_maps(a, b, 6, 5)
        self.assertEqual(len(out), 5)
        self.assertTrue(all(len(r) == 6 for r in out))
        cells = {c for row in out for c in row}
        self.assertTrue(cells <= {"A", "B"})  # every cell came from a parent
        self.assertEqual(cells, {"A", "B"})   # and both are represented

    def test_breed_with_grid_osmosis_different_sizes(self):
        d = tempfile.mkdtemp()
        # Hand-crafted parents with DIFFERENT grid sizes.
        pa = os.path.join(d, "Pa_brain.json")
        pb = os.path.join(d, "Pb_brain.json")
        json.dump({"name": "Pa", "personality_entropy": 0.2, "memories": ["pa rain moor"],
                   "grid_state": {"map": [["#"] * 10 for _ in range(5)]},
                   "babel_memory": [], "babel_pairs": {}, "babel_word_freq": {}},
                  open(pa, "w"))
        json.dump({"name": "Pb", "personality_entropy": 0.3, "memories": ["pb fire hall"],
                   "grid_state": {"map": [["@"] * 20 for _ in range(8)]},
                   "babel_memory": [], "babel_pairs": {}, "babel_word_freq": {}},
                  open(pb, "w"))
        random.seed(1)
        child = breed_norns(pa, pb, "Kid", save_dir=d, n_memories=2,
                            mutation_rate=0.0, grid_osmosis=True)
        self.assertIsNotNone(child)
        cmap = child.grid.state["map"]
        # Child grid is its own size, not either parent's.
        self.assertEqual(len(cmap), child.grid.height)
        self.assertEqual(len(cmap[0]), child.grid.width)


class TestBreeding(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.a = _make_parent(
            "Alpha", ["alpha rain floods the moor", "alpha storm over water"], self.d)
        self.b = _make_parent(
            "Bravo", ["bravo fire burns the hall", "bravo flame and ember"], self.d)

    def test_child_created_with_mixed_memories(self):
        random.seed(5)
        child = breed_norns(self.a, self.b, "Child", save_dir=self.d,
                            n_memories=8, mutation_rate=0.0)
        self.assertIsNotNone(child)
        path = os.path.join(self.d, "Child_brain.json")
        self.assertTrue(os.path.exists(path))

        brain = json.load(open(path))
        joined = " ".join(brain["memories"]).lower()
        self.assertIn("alpha", joined)  # inherited from A
        self.assertIn("bravo", joined)  # inherited from B
        self.assertTrue(0.1 <= brain["personality_entropy"] <= 0.9)
        self.assertEqual(brain["thought_count"], 0)  # fresh birth

    def test_default_name_is_portmanteau(self):
        random.seed(1)
        child = breed_norns(self.a, self.b, save_dir=self.d, n_memories=4)
        self.assertEqual(child.name, "Alavo")

    def test_refuses_overwrite_without_force(self):
        random.seed(1)
        breed_norns(self.a, self.b, "Twin", save_dir=self.d, n_memories=4)
        # Second attempt without force returns None and leaves file intact.
        again = breed_norns(self.a, self.b, "Twin", save_dir=self.d, n_memories=4)
        self.assertIsNone(again)
        forced = breed_norns(self.a, self.b, "Twin", save_dir=self.d,
                            n_memories=4, force=True)
        self.assertIsNotNone(forced)

    def test_respects_memory_budget(self):
        random.seed(2)
        child = breed_norns(self.a, self.b, "Small", save_dir=self.d,
                            n_memories=2, mutation_rate=0.0)
        brain = json.load(open(os.path.join(self.d, "Small_brain.json")))
        # Parents have 2 raw lines each; a budget of 2 caps total inheritance.
        self.assertLessEqual(len(brain["memories"]), 2)


if __name__ == "__main__":
    unittest.main()
