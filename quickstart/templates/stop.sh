#!/usr/bin/env bash
# stop.sh — tear the local MLSwarm terrarium down.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$ROOT/run"

if [ ! -d "$RUN" ]; then
    echo "Nothing to stop (no run/ dir)."
    exit 0
fi

shopt -s nullglob
stopped=0
for pidfile in "$RUN"/*.pid; do
    name="$(basename "$pidfile" .pid)"
    pid="$(cat "$pidfile" 2>/dev/null)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null && echo "  stopped $name (pid $pid)"
        stopped=$((stopped + 1))
    fi
    rm -f "$pidfile"
done

# Bridges are bash loops that spawn sleeps; reap any stragglers by name.
pkill -f "$ROOT/bridges/norn_bridge.sh" 2>/dev/null || true

if [ "$stopped" -eq 0 ]; then
    echo "Nothing was running."
else
    echo "Stopped $stopped process(es)."
fi
