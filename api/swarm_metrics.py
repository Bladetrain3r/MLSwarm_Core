#!/usr/bin/env python3
"""
On-demand webserver metrics for the swarm API.

Records (timestamp, status_code) per response in a bounded deque and aggregates
on demand into a per-hour timeseries: request totals (rate/hour) and 2xx/4xx/5xx
counts. Emits CSV. With a stats-log path, a CSV snapshot is also written there
for longer retention than the in-memory window holds.

Stdlib only.
"""

import csv
import io
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone

_FIELDS = ["hour", "total", "2xx", "4xx", "5xx", "other"]


def status_class(code):
    if 200 <= code < 300:
        return "2xx"
    if 400 <= code < 500:
        return "4xx"
    if 500 <= code < 600:
        return "5xx"
    return "other"


def _now_epoch():
    return datetime.now(timezone.utc).timestamp()


class Metrics:
    def __init__(self, maxlen=10000, statslog=None):
        self._events = deque(maxlen=maxlen)  # (epoch_seconds, status_code)
        self._statslog = statslog
        self._lock = threading.Lock()

    def set_statslog(self, path):
        self._statslog = path

    def record(self, status_code, now=None):
        ts = now if now is not None else _now_epoch()
        with self._lock:
            self._events.append((ts, int(status_code)))

    def rate(self, window_seconds=60, now=None):
        """Requests seen in the last `window_seconds` (a simple current-rate)."""
        cutoff = (now if now is not None else _now_epoch()) - window_seconds
        with self._lock:
            return sum(1 for ts, _ in self._events if ts >= cutoff)

    def hourly(self):
        """Per-hour buckets sorted ascending; each a dict over _FIELDS."""
        buckets = defaultdict(lambda: {"total": 0, "2xx": 0, "4xx": 0, "5xx": 0, "other": 0})
        with self._lock:
            events = list(self._events)
        for ts, code in events:
            hour = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:00Z")
            bucket = buckets[hour]
            bucket["total"] += 1
            bucket[status_class(code)] += 1
        rows = []
        for hour in sorted(buckets):
            row = {"hour": hour}
            row.update(buckets[hour])
            rows.append(row)
        return rows

    def to_csv(self):
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=_FIELDS)
        writer.writeheader()
        for row in self.hourly():
            writer.writerow(row)
        return out.getvalue()

    def flush_to_log(self):
        """Write the current CSV snapshot to the stats-log file, if configured."""
        if not self._statslog:
            return
        try:
            with open(self._statslog, "w", encoding="utf-8", newline="") as f:
                f.write(self.to_csv())
        except OSError as e:
            print(f"[swarm_metrics] could not write {self._statslog}: {e}")
