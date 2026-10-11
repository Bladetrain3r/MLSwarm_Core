#!/usr/bin/env python3
"""Tests for the swarm metrics aggregation.

Run from api/:  python -m unittest discover -s tests
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swarm_metrics import Metrics, status_class

HOUR = 3600


class TestStatusClass(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(status_class(200), "2xx")
        self.assertEqual(status_class(204), "2xx")
        self.assertEqual(status_class(304), "other")   # 3xx is neither error nor 2xx
        self.assertEqual(status_class(404), "4xx")
        self.assertEqual(status_class(500), "5xx")


class TestMetrics(unittest.TestCase):
    def test_hourly_buckets_and_classes(self):
        m = Metrics()
        # Hour 0: two 2xx, one 404. Hour 1: one 500.
        m.record(200, now=10)
        m.record(200, now=20)
        m.record(404, now=30)
        m.record(500, now=HOUR + 5)
        rows = m.hourly()
        self.assertEqual(len(rows), 2)
        h0, h1 = rows
        self.assertEqual((h0["total"], h0["2xx"], h0["4xx"], h0["5xx"]), (3, 2, 1, 0))
        self.assertEqual((h1["total"], h1["5xx"]), (1, 1))
        self.assertTrue(h0["hour"].endswith("T00:00Z"))
        self.assertTrue(h1["hour"].endswith("T01:00Z"))

    def test_rate_window(self):
        m = Metrics()
        m.record(200, now=1000)
        m.record(200, now=1990)
        m.record(200, now=2000)
        # window of 60s ending at now=2000 -> only the 1990 and 2000 events.
        self.assertEqual(m.rate(window_seconds=60, now=2000), 2)

    def test_csv_shape(self):
        m = Metrics()
        m.record(200, now=0)
        m.record(404, now=0)
        csv_text = m.to_csv()
        lines = csv_text.strip().splitlines()
        self.assertEqual(lines[0], "hour,total,2xx,4xx,5xx,other")
        self.assertTrue(lines[1].endswith(",2,1,1,0,0"))

    def test_bounded_deque(self):
        m = Metrics(maxlen=3)
        for i in range(5):
            m.record(200, now=i)
        # Only the last 3 events survive -> total 3.
        self.assertEqual(sum(r["total"] for r in m.hourly()), 3)

    def test_flush_to_log(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "stats.csv")
            m = Metrics(statslog=path)
            m.record(200, now=0)
            m.flush_to_log()
            with open(path) as f:
                self.assertIn("hour,total,2xx,4xx,5xx,other", f.read())

    def test_flush_noop_without_path(self):
        Metrics().flush_to_log()  # must not raise


if __name__ == "__main__":
    unittest.main()
