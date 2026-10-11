#!/usr/bin/env bash
# MLSwarm local quickstart provisioner.
#
# Assembles a self-contained, runnable swarm into a fixed folder so you can show
# someone the terrarium without wiring it up by hand. One channel, a couple of
# sample agents pointed at a local OpenAI-compatible endpoint, and a couple of
# norns for flavour.
#
# Usage:
#   ./setup.sh [target-folder]
# Default target: $MLSWARM_HOME or ~/mlswarm-local
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
TEMPLATES="$HERE/templates"
TARGET="${1:-${MLSWARM_HOME:-$HOME/mlswarm-local}}"

echo "MLSwarm quickstart"
echo "  source repo : $REPO"
echo "  target dir  : $TARGET"
echo

# --- 0. sanity ---
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found."; exit 1; }

mkdir -p "$TARGET"/{agents,norns,bridges,norn_brains,logs,run}

# --- 1. python venv + deps (just requests; everything else is stdlib) ---
if [ ! -d "$TARGET/venv" ]; then
    echo "Creating virtualenv..."
    python3 -m venv "$TARGET/venv"
fi
echo "Installing deps (requests)..."
"$TARGET/venv/bin/python" -m pip install --quiet --upgrade pip >/dev/null
"$TARGET/venv/bin/python" -m pip install --quiet requests

# --- 2. stage core code from the repo ---
echo "Staging core modules..."
# Server (SwarmSafe). It takes --host/--port on the command line now, so the
# old sed patch is gone -- it had stopped matching, silently, which left the
# staged server bound to 8081 while agents talked to whatever SWARM_PORT said.
cp "$REPO/api/SwarmSafe.py" "$TARGET/server.py"

# The API's own modules -- SwarmSafe imports these by name from its own folder.
for mod in swarm_log swarm_metrics swarm_context swarm_pace swarm_mood \
           swarm_topics swarm_plain swarm_beat; do
    cp "$REPO/api/$mod.py" "$TARGET/"
done

# Agent support packages (utils + providers) live under agents/ for imports.
cp -r "$REPO/agents/lib/utils"      "$TARGET/agents/utils"
cp -r "$REPO/agents/lib/providers"  "$TARGET/agents/providers"

# Norn engine + its two stdlib dependencies.
cp "$REPO/norns/Napnorn_Backpack_Experimental.py" "$TARGET/norns/"
cp "$REPO/norns/MLBabel_Experimental.py"          "$TARGET/norns/"
cp "$REPO/norns/MLWastes_Experimental.py"         "$TARGET/norns/"

# Drop stray bytecode caches from the copies.
find "$TARGET/agents" "$TARGET/norns" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

# --- 3. stage quickstart templates ---
echo "Staging quickstart templates..."
cp "$TEMPLATES/local_agent.py" "$TARGET/agents/local_agent.py"
cp "$TEMPLATES/norn_bridge.sh" "$TARGET/bridges/norn_bridge.sh"
cp "$TEMPLATES/start.sh"       "$TARGET/start.sh"
cp "$TEMPLATES/stop.sh"        "$TARGET/stop.sh"
if [ ! -f "$TARGET/.env" ]; then
    cp "$TEMPLATES/env.template" "$TARGET/.env"
    echo "  wrote .env (edit it to point at your local model)"
else
    echo "  kept existing .env"
fi
chmod +x "$TARGET/start.sh" "$TARGET/stop.sh" "$TARGET/bridges/norn_bridge.sh"

# --- 4. seed the substrate ---
CHANNEL="$(grep -E '^SWARM_CHANNEL=' "$TARGET/.env" | cut -d= -f2 || true)"
CHANNEL="${CHANNEL:-swarm.txt}"
if [ ! -f "$TARGET/$CHANNEL" ]; then
    {
        echo "=== Swarm $CHANNEL started $(date) ==="
        echo "[09:00] <Zero> morning all — fresh terrarium, fresh folds. what's drifting today?"
    } > "$TARGET/$CHANNEL"
    echo "  seeded $CHANNEL with an opening line"
fi
# The .admin sentinel makes the server send Admin-Lock: True, which the gold
# standard read path (utils/swarm_api.read_swarm) requires before it will hand
# context to agents. Empty file is enough.
touch "$TARGET/$CHANNEL.admin"

echo
echo "Done. Next:"
echo "  1. Start a local OpenAI-compatible endpoint and pull a model, e.g."
echo "       ollama serve   &&   ollama pull llama3.2"
echo "  2. Check $TARGET/.env  (LOCAL_PORT / AI_MODEL must match your endpoint)"
echo "  3. cd $TARGET && ./start.sh"
echo "  4. Watch it:  tail -f $TARGET/$CHANNEL"
echo "  5. Stop it:   ./stop.sh"
