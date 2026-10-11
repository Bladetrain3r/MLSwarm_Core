#!/usr/bin/env bash
# start.sh — bring the local MLSwarm terrarium up.
# Self-locating: works wherever this run folder lives.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# --- config ---
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a
SWARM_PORT="${SWARM_PORT:-8081}"
SWARM_URL="${SWARM_URL:-http://localhost:$SWARM_PORT}"
SWARM_CHANNEL="${SWARM_CHANNEL:-swarm.txt}"
PY="$ROOT/venv/bin/python"
[ -x "$PY" ] || PY="python3"

mkdir -p "$ROOT/logs" "$ROOT/run" "$ROOT/norn_brains"

# Export everything the children read from the environment.
export SWARM_PORT SWARM_URL SWARM_USER SWARM_PASS SWARM_CHANNEL
export LOCAL_IP LOCAL_PORT AI_MODEL POLL_MIN POLL_MAX DRYRUN

# start <name> <logfile> <command...>
start_proc() {
    local name="$1" log="$2"; shift 2
    if [ -f "$ROOT/run/$name.pid" ] && kill -0 "$(cat "$ROOT/run/$name.pid")" 2>/dev/null; then
        echo "  $name already running (pid $(cat "$ROOT/run/$name.pid"))"
        return
    fi
    nohup "$@" </dev/null >"$ROOT/logs/$log" 2>&1 &
    echo $! > "$ROOT/run/$name.pid"
    echo "  started $name (pid $!)  -> logs/$log"
}

echo "MLSwarm terrarium starting in: $ROOT"
echo

# 1. The substrate server.
echo "Server:"
start_proc server server.log "$PY" "$ROOT/server.py" --port "$SWARM_PORT"
sleep 1

# 2. Norns (file-creatures) — daemon + bridge each. Pure flavour.
echo "Norns:"
for norn in Mossy Glitch; do
    start_proc "norn_$norn" "norn_$norn.log" \
        "$PY" "$ROOT/norns/Napnorn_Backpack_Experimental.py" daemon "$norn"
done
sleep 1
for norn in Mossy Glitch; do
    start_proc "bridge_$norn" "bridge_$norn.log" \
        bash "$ROOT/bridges/norn_bridge.sh" "$norn" "$SWARM_CHANNEL"
done

# 3. Agents. Add a line here to grow the swarm — same file, new nick/persona/norn.
echo "Agents:"
start_agent() {  # <nick> <persona> <paired-norn>
    local nick="$1" persona="$2" norn="$3"
    ( cd "$ROOT/agents" && \
      AGENT_NICK="$nick" AGENT_PERSONA="$persona" \
      NORN_BRAINS="$ROOT/norn_brains" NORN_NAME="$norn" \
      nohup "$PY" local_agent.py </dev/null >"$ROOT/logs/agent_$nick.log" 2>&1 & \
      echo $! > "$ROOT/run/agent_$nick.pid" )
    echo "  started agent $nick (pid $(cat "$ROOT/run/agent_$nick.pid"))  -> logs/agent_$nick.log"
}
start_agent Driftwood driftwood Mossy
start_agent Sparkz    sparkz    Glitch

echo
echo "Up. Watch the conversation with:"
echo "  curl -s $SWARM_URL/swarm/$SWARM_CHANNEL        # or just: tail -f $ROOT/$SWARM_CHANNEL"
echo "Stop everything with: $ROOT/stop.sh"
