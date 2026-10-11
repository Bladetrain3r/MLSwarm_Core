#!/usr/bin/env python3
"""Standard-library unittest coverage for fern_core.

Run from the digifern directory:

    python -m unittest discover -s tests
"""

import json
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fern_core


class TestVectorOps(unittest.TestCase):
    def test_validate_vector_ok(self):
        self.assertEqual(fern_core.validate_vector([1, 2, 3]), [1.0, 2.0, 3.0])

    def test_validate_vector_rejects_empty(self):
        with self.assertRaises(fern_core.FernError):
            fern_core.validate_vector([])

    def test_validate_vector_rejects_non_numeric(self):
        with self.assertRaises(fern_core.FernError):
            fern_core.validate_vector([1.0, "x", 3.0])

    def test_validate_vector_rejects_bool(self):
        with self.assertRaises(fern_core.FernError):
            fern_core.validate_vector([True, 1.0])

    def test_validate_vector_rejects_nan_inf(self):
        with self.assertRaises(fern_core.FernError):
            fern_core.validate_vector([1.0, float("nan")])
        with self.assertRaises(fern_core.FernError):
            fern_core.validate_vector([1.0, float("inf")])

    def test_validate_vector_dimension(self):
        with self.assertRaises(fern_core.FernError):
            fern_core.validate_vector([1.0, 2.0], expected_dim=3)

    def test_magnitude(self):
        self.assertAlmostEqual(fern_core.magnitude([3.0, 4.0]), 5.0)

    def test_normalize_unit_length(self):
        unit = fern_core.normalize([3.0, 4.0])
        self.assertAlmostEqual(fern_core.magnitude(unit), 1.0)

    def test_normalize_zero_raises(self):
        with self.assertRaises(fern_core.FernError):
            fern_core.normalize([0.0, 0.0, 0.0])

    def test_dot(self):
        self.assertAlmostEqual(fern_core.dot([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]), 32.0)

    def test_dot_dimension_mismatch(self):
        with self.assertRaises(fern_core.FernError):
            fern_core.dot([1.0, 2.0], [1.0])


class TestAxes(unittest.TestCase):
    def test_build_axis_direction(self):
        axis = fern_core.build_axis([1.0, 0.0], [0.0, 0.0])
        self.assertAlmostEqual(axis[0], 1.0)
        self.assertAlmostEqual(axis[1], 0.0)

    def test_build_axis_is_unit(self):
        axis = fern_core.build_axis([2.0, 2.0], [0.0, 0.0])
        self.assertAlmostEqual(fern_core.magnitude(axis), 1.0)

    def test_build_axis_identical_anchors_raises(self):
        with self.assertRaises(fern_core.FernError):
            fern_core.build_axis([1.0, 1.0], [1.0, 1.0])

    def test_build_axis_dimension_mismatch(self):
        with self.assertRaises(fern_core.FernError):
            fern_core.build_axis([1.0, 0.0], [0.0])

    def test_project_values(self):
        axes = {"x": [1.0, 0.0], "y": [0.0, 1.0]}
        values = fern_core.project_values([0.3, 0.7], axes)
        self.assertAlmostEqual(values["x"], 0.3)
        self.assertAlmostEqual(values["y"], 0.7)


class TestFernUpdate(unittest.TestCase):
    def test_first_influence_adopts_message(self):
        unit = fern_core.normalize([1.0, 1.0])
        new_vec, motion = fern_core.update_fern(None, unit, 0.05)
        self.assertEqual(new_vec, unit)
        self.assertEqual(motion, 0.0)

    def test_subsequent_influence_blends(self):
        s = [1.0, 0.0]
        e = [0.0, 1.0]
        new_vec, _ = fern_core.update_fern(s, e, 0.05)
        self.assertAlmostEqual(new_vec[0], 0.95)
        self.assertAlmostEqual(new_vec[1], 0.05)

    def test_update_dimension_mismatch(self):
        with self.assertRaises(fern_core.FernError):
            fern_core.update_fern([1.0, 0.0], [1.0], 0.05)

    def test_coherence_high_when_aligned(self):
        # Averaging aligned unit vectors keeps magnitude near 1.
        s = [1.0, 0.0]
        e = [1.0, 0.0]
        new_vec, _ = fern_core.update_fern(s, e, 0.05)
        self.assertAlmostEqual(fern_core.magnitude(new_vec), 1.0)

    def test_coherence_low_when_opposed(self):
        # A rolling vector near zero means scattered/opposed directions.
        new_vec, _ = fern_core.update_fern([1.0, 0.0], [-1.0, 0.0], 0.5)
        self.assertAlmostEqual(fern_core.magnitude(new_vec), 0.0)

    def test_motion_no_change(self):
        self.assertAlmostEqual(fern_core.compute_motion([1.0, 0.0], [2.0, 0.0]), 0.0)

    def test_motion_reversal(self):
        self.assertAlmostEqual(fern_core.compute_motion([1.0, 0.0], [-1.0, 0.0]), 1.0)

    def test_motion_orthogonal(self):
        self.assertAlmostEqual(fern_core.compute_motion([1.0, 0.0], [0.0, 1.0]), 0.5)

    def test_motion_zero_length_is_zero(self):
        self.assertEqual(fern_core.compute_motion([0.0, 0.0], [1.0, 0.0]), 0.0)


class TestLabels(unittest.TestCase):
    def test_band_boundaries(self):
        self.assertEqual(fern_core.band_index(-0.8), 0)
        self.assertEqual(fern_core.band_index(-0.4), 1)
        self.assertEqual(fern_core.band_index(0.0), 2)
        self.assertEqual(fern_core.band_index(0.4), 3)
        self.assertEqual(fern_core.band_index(0.8), 4)

    def test_axis_specific_labels(self):
        self.assertEqual(fern_core.label_for("moisture", 0.8), "saturated")
        self.assertEqual(fern_core.label_for("nutrition", -0.8), "starved")
        self.assertEqual(fern_core.label_for("vigor", 0.0), "steady")

    def test_generic_fallback(self):
        self.assertEqual(fern_core.label_for("unknown_axis", 0.8), "strongly positive")


class TestMotionAmplification(unittest.TestCase):
    def test_disabled_returns_raw(self):
        self.assertEqual(fern_core.amplify_motion(0.02, 0), 0.02)
        self.assertEqual(fern_core.amplify_motion(0.02, None), 0.02)

    def test_zero_motion_amplifies_to_zero(self):
        self.assertAlmostEqual(fern_core.amplify_motion(0.0, 300), 0.0)

    def test_monotonic_and_bounded(self):
        low = fern_core.amplify_motion(0.001, 300)
        high = fern_core.amplify_motion(0.01, 300)
        self.assertLess(low, high)
        self.assertLess(high, 1.0)
        self.assertGreater(low, 0.0)

    def test_small_motion_becomes_visible(self):
        # A raw motion invisible on a 0..1 scale should lift into a usable range.
        self.assertGreater(fern_core.amplify_motion(0.002, 300), 0.1)

    def test_motion_label_bands(self):
        self.assertEqual(fern_core.motion_label(0.0), "still")
        self.assertEqual(fern_core.motion_label(0.2), "stirring")
        self.assertEqual(fern_core.motion_label(0.4), "breezy")
        self.assertEqual(fern_core.motion_label(0.6), "gusting")
        self.assertEqual(fern_core.motion_label(0.9), "turbulent")


class TestState(unittest.TestCase):
    def test_empty_state_valid(self):
        state = fern_core.empty_state("m", 0.05)
        fern_core.validate_state(state)  # should not raise
        self.assertIsNone(state["vector"])
        self.assertEqual(state["influences"], 0)

    def test_validate_missing_key(self):
        state = fern_core.empty_state("m", 0.05)
        del state["motion"]
        with self.assertRaises(fern_core.FernError):
            fern_core.validate_state(state)

    def test_validate_version_mismatch(self):
        state = fern_core.empty_state("m", 0.05)
        state["version"] = 999
        with self.assertRaises(fern_core.FernError):
            fern_core.validate_state(state)

    def test_validate_model_mismatch_with_vector(self):
        state = fern_core.empty_state("model-a", 0.05)
        state["vector"] = [1.0, 0.0]
        state["dimensions"] = 2
        with self.assertRaises(fern_core.FernError):
            fern_core.validate_state(state, model="model-b", dimensions=2)

    def test_validate_dimension_mismatch_with_vector(self):
        state = fern_core.empty_state("m", 0.05)
        state["vector"] = [1.0, 0.0]
        state["dimensions"] = 2
        with self.assertRaises(fern_core.FernError):
            fern_core.validate_state(state, model="m", dimensions=768)

    def test_empty_state_ignores_model_check(self):
        # No stored vector -> always compatible, whatever the running model.
        state = fern_core.empty_state("model-a", 0.05)
        fern_core.validate_state(state, model="model-b", dimensions=768)

    def test_save_load_roundtrip(self):
        state = fern_core.empty_state("m", 0.05)
        state["vector"] = [0.1, 0.2, 0.3]
        state["dimensions"] = 3
        state["influences"] = 7
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")
            fern_core.save_state(path, state)
            loaded = fern_core.load_state(path, model="m", dimensions=3)
            self.assertEqual(loaded["vector"], [0.1, 0.2, 0.3])
            self.assertEqual(loaded["influences"], 7)

    def test_save_is_atomic_no_tmp_left(self):
        state = fern_core.empty_state("m", 0.05)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")
            fern_core.save_state(path, state)
            self.assertTrue(os.path.exists(path))
            self.assertFalse(os.path.exists(path + ".tmp"))

    def test_load_malformed_raises(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")
            with open(path, "w") as f:
                f.write("{ this is not json")
            with self.assertRaises(json.JSONDecodeError):
                fern_core.load_state(path)


class TestDuplicateTracking(unittest.TestCase):
    def test_is_duplicate(self):
        state = fern_core.empty_state("m", 0.05)
        self.assertFalse(fern_core.is_duplicate(state, "a"))
        fern_core.remember_event(state, "a", 256)
        self.assertTrue(fern_core.is_duplicate(state, "a"))

    def test_none_event_never_duplicate(self):
        state = fern_core.empty_state("m", 0.05)
        fern_core.remember_event(state, None, 256)
        self.assertFalse(fern_core.is_duplicate(state, None))
        self.assertEqual(state["recent_event_ids"], [])

    def test_bounded_list(self):
        state = fern_core.empty_state("m", 0.05)
        for i in range(300):
            fern_core.remember_event(state, f"e{i}", 256)
        self.assertEqual(len(state["recent_event_ids"]), 256)
        # Oldest trimmed, newest kept.
        self.assertFalse(fern_core.is_duplicate(state, "e0"))
        self.assertTrue(fern_core.is_duplicate(state, "e299"))


if __name__ == "__main__":
    unittest.main()
