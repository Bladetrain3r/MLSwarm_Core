#!/usr/bin/env python3
"""Tests for NapNorn's full-memory semantic focus wiring.

Deterministic fake embedder (no server); each test uses its own temp save_dir
so grid/brain files don't collide.

Run from the norns directory:

    python -m unittest discover -s tests
"""

import os
import random
import sys
import tempfile
import unittest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Napnorn_Backpack_Experimental import NapNorn

MARKERS = ["rain", "fire", "code", "sea", "bone"]
CORPUS = {
    "rain": ["rain rain rain soaks the wet moor", "the storm rain floods every ditch"],
    "fire": ["fire fire fire consumes the dry hall", "flame and fire scorch the roof"],
    "code": ["code code code compiles clean logic", "the function code returns a value"],
    "sea": ["sea sea sea swells against the hull", "salt sea spray over the deck"],
    "bone": ["bone bone bone white in the barrow", "a bone dry relic of the dead"],
}


def fake_embed(text):
    low = text.lower()
    return [low.count(m) + 0.01 for m in MARKERS]


def _fed_norn(name, embed_fn):
    norn = NapNorn(name, save_dir=tempfile.mkdtemp(), embed_fn=embed_fn)
    for lines in CORPUS.values():
        for line in lines:
            norn.perceive(line)
    return norn


class TestNornFocus(unittest.TestCase):
    def test_no_embedder_uses_grid_path(self):
        norn = _fed_norn("Plain", None)
        self.assertEqual(norn.babel.fragment_vectors, [])
        self.assertIsInstance(norn.think(), str)

    def test_full_memory_focus_hones_to_topic(self):
        norn = _fed_norn("Focus", fake_embed)
        self.assertEqual(len(norn.babel.fragment_vectors), len(norn.babel.memory))
        # Current topic = sea; neutralise grid blending for a clean read.
        norn.memory_fragments += ["sea sea salt swell hull deck"] * 3
        norn._active_grid_keywords = lambda: ""

        random.seed(11)
        hits = Counter()
        for _ in range(200):
            thought = norn._focused_think().lower()
            for m in MARKERS:
                if m in thought:
                    hits[m] += 1
        # "sea" should be the clear plurality across the whole memory.
        top = hits.most_common(1)[0][0]
        self.assertEqual(top, "sea")
        self.assertGreater(hits["sea"], sum(v for k, v in hits.items() if k != "sea"))

    def test_dead_embedder_falls_back_to_grid(self):
        norn = _fed_norn("Dead", lambda text: None)
        # Focus can't embed -> _focused_think returns via _grid_think, no raise.
        self.assertIsInstance(norn.think(), str)

    def test_brain_reload_realigns_vectors(self):
        norn = _fed_norn("Save", fake_embed)
        norn.save_brain()
        reborn = NapNorn("Save", save_dir=str(norn.save_dir), embed_fn=fake_embed)
        reborn.load_brain(os.path.join(str(norn.save_dir), "Save_brain.json"))
        self.assertEqual(len(reborn.babel.fragment_vectors), len(reborn.babel.memory))
        self.assertTrue(reborn.babel.fragment_vectors)


if __name__ == "__main__":
    unittest.main()
