#!/usr/bin/env bash
# norn_bridge.sh <NornName> [channel_file]
#
# Bridges a running NapNorn daemon into a swarm channel. Norns are file-based
# "creatures" that don't speak HTTP, so this loop is their mouth and ears:
#   1. feeds the norn a recent line from the channel  (its senses)
#   2. asks it to think                               (its cognition)
#   3. appends the resulting thought + mood back into the channel (its voice)
#
# It writes directly to the channel .txt file, exactly like the legacy
# Largo.sh / Forest.sh bridges. The HTTP server re-reads the file on every GET,
# so agents see the norn's lines the same as any other message.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NORN="${1:-Mossy}"
CHANNEL="${2:-swarm.txt}"
BRAINS="$ROOT/norn_brains"
CHAN="$ROOT/$CHANNEL"

echo "Bridging norn '$NORN' into $CHANNEL ..."

while true; do
    # 1. Senses: feed a recent, non-corrupt chat line (if any).
    line="$(tail -n 40 "$CHAN" 2>/dev/null | grep -E '\[..:..\]' | grep -v '\\\\' | shuf -n 1)"
    if [ -n "$line" ]; then
        printf 'feed:%s\n' "$line" > "$BRAINS/${NORN}_command.txt"
        sleep 15   # > the daemon's 10s update interval, so the command is seen
    fi

    # 2. Cognition: ask it to think.
    echo "think" > "$BRAINS/${NORN}_command.txt"
    sleep 15

    # 3. Voice: post the thought + current mood back into the channel.
    if [ -f "$BRAINS/${NORN}_response.txt" ]; then
        ts="$(date +%H:%M)"
        thought="$(tr '\n' ' ' < "$BRAINS/${NORN}_response.txt" | sed 's/  */ /g')"
        mood="$(grep '"mood"' "$BRAINS/${NORN}_status.json" 2>/dev/null \
                | head -n 1 | sed 's/.*: *"//; s/".*//')"
        if [ -n "$thought" ]; then
            printf '[%s] <%s> (%s) %s\n' "$ts" "$NORN" "${mood:-stirring}" "$thought" >> "$CHAN"
        fi
    fi

    # Idle between visits so the norn is a slow presence, not a firehose.
    sleep $((RANDOM % 120 + 60))
done
