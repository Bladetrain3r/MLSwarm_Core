#!/usr/bin/env python3
"""Tests for MLBabel's optional semantic-focus fragment selection.

Uses a deterministic fake embedder (no embedding server needed): text maps to a
small vector counting a few marker words, so "near" and "far" fragments are
constructed on purpose and selection bias is checked statistically.

Run from the norns directory:

    python -m unittest discover -s tests
"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from MLBabel_Experimental import MLBabel

MARKERS = ["rain", "fire", "code"]


def fake_embed(text):
    """Vector = count of each marker word, plus a small base so nothing is zero."""
    low = text.lower()
    return [low.count(m) + 0.01 for m in MARKERS]


class TestNoEmbedder(unittest.TestCase):
    """With no embed_fn, behaviour must be exactly as before."""

    def test_no_vectors_cached(self):
        b = MLBabel(seed=1)
        b.consume("rain rain wet. fire fire hot. code code logic.")
        self.assertEqual(b.fragment_vectors, [])

    def test_weighted_index_returns_none(self):
        b = MLBabel(seed=1)
        b.consume("rain wet. fire hot.")
        b.set_focus("rain")  # no embedder -> focus stays None
        self.assertIsNone(b.focus_vector)
        self.assertIsNone(b._weighted_index())

    def test_choose_fragment_still_works(self):
        b = MLBabel(seed=1)
        b.consume("rain wet. fire hot.")
        self.assertIn(b._choose_fragment(), b.memory)


class TestEmbeddingCache(unittest.TestCase):
    def test_vectors_aligned(self):
        b = MLBabel(seed=1, embed_fn=fake_embed)
        b.consume("rain rain wet. fire fire hot. code code logic.")
        self.assertEqual(len(b.fragment_vectors), len(b.memory))
        self.assertTrue(all(v is not None for v in b.fragment_vectors))

    def test_rebuild_embeddings(self):
        b = MLBabel(seed=1, embed_fn=fake_embed)
        # Simulate a bulk load that bypasses consume() (like load_brain).
        b.memory = ["rain wet", "fire hot", "code logic"]
        b.rebuild_embeddings()
        self.assertEqual(len(b.fragment_vectors), 3)
        self.assertTrue(all(v is not None for v in b.fragment_vectors))

    def test_length_mismatch_falls_back(self):
        # Mimics oracle() appending to memory without vectors: guard -> uniform.
        b = MLBabel(seed=1, embed_fn=fake_embed)
        b.consume("rain wet. fire hot.")
        b.memory.append("code logic")  # now longer than fragment_vectors
        b.set_focus("rain")
        self.assertIsNone(b._weighted_index())


class TestFocusVector(unittest.TestCase):
    def test_set_focus_string(self):
        b = MLBabel(seed=1, embed_fn=fake_embed)
        b.set_focus("rain rain")
        self.assertEqual(b.focus_vector[0], 2.01)

    def test_set_focus_vector_direct(self):
        b = MLBabel(seed=1, embed_fn=fake_embed)
        b.set_focus([1.0, 0.0, 0.0])
        self.assertEqual(b.focus_vector, [1.0, 0.0, 0.0])

    def test_set_focus_none_clears(self):
        b = MLBabel(seed=1, embed_fn=fake_embed)
        b.set_focus("rain")
        b.set_focus(None)
        self.assertIsNone(b.focus_vector)


class TestFocusBias(unittest.TestCase):
    def _loaded(self, entropy):
        b = MLBabel(entropy=entropy, seed=7, embed_fn=fake_embed)
        b.memory = ["rain rain rain wet", "fire fire fire hot", "code code code logic"]
        b.rebuild_embeddings()
        return b

    def _sample_counts(self, b, n=3000):
        random.seed(123)
        counts = {"rain": 0, "fire": 0, "code": 0}
        for _ in range(n):
            frag = b._choose_fragment()
            counts[frag.split()[0]] += 1
        return counts

    def test_focus_biases_toward_topic(self):
        b = self._loaded(entropy=0.2)
        b.set_focus("rain water storm")
        counts = self._sample_counts(b)
        self.assertGreater(counts["rain"], counts["fire"])
        self.assertGreater(counts["rain"], counts["code"])

    def test_low_entropy_more_peaky_than_high(self):
        low = self._loaded(entropy=0.1)
        low.set_focus("rain water storm")
        high = self._loaded(entropy=0.95)
        high.set_focus("rain water storm")

        low_frac = self._sample_counts(low)["rain"] / 3000
        high_frac = self._sample_counts(high)["rain"] / 3000
        # Colder temperature (low entropy) concentrates more on the topic.
        self.assertGreater(low_frac, high_frac)

    def test_no_focus_is_roughly_uniform(self):
        b = self._loaded(entropy=0.5)  # focus never set
        counts = self._sample_counts(b)
        for name in ("rain", "fire", "code"):
            self.assertGreater(counts[name], 3000 * 0.25)  # each near 1/3


if __name__ == "__main__":
    unittest.main()
