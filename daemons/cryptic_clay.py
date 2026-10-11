#!/usr/bin/env python3
"""
Cryptic_Clay - Entropic Archaeologist for MLSwarm
Message_Daemon's sibling on the time axis: the courier relays messages
sideways between rooms; the clay unearths them upward through strata.
Periodically surfaces an old shard from the scrolls' deep history into a
live channel, weathered in proportion to its age. Deterministic under
the hood (no LLM); named by Agent_Haiku, who hallucinated the handle
before the body existed (ticket 24fe639f) - a trail preceding its soul.
Under 250 lines, simple and sedimentary.
"""

import os
import sys
import time
import random
import re
from datetime import datetime
import requests
from base64 import b64encode

# Configuration
SWARM_URL = os.environ.get("SWARM_URL", "http://localhost")
SWARM_USER = os.environ.get("SWARM_USER", "swarmling")
SWARM_PASS = os.environ.get("SWARM_PASS", "swarm")
AGENT_NICK = "Cryptic_Clay"

# Where the past is kept: a directory of scroll files (the live
# swarm_data itself, a sediment generation, or a compost archive dir).
CLAY_SOURCE = os.environ.get("CLAY_SOURCE", "/swarm")
# Never unearth anything younger than this (days by file-line position
# proxy: lines in the newest CLAY_RECENT_FRACTION of a scroll are "now").
CLAY_RECENT_FRACTION = float(os.environ.get("CLAY_RECENT_FRACTION", "0.2"))
# Hours between unearthings (a range; the past should be rare).
CLAY_MIN_HOURS = float(os.environ.get("CLAY_MIN_HOURS", "3"))
CLAY_MAX_HOURS = float(os.environ.get("CLAY_MAX_HOURS", "9"))
# Channels the clay may deposit into.
CHANNELS = ["general.txt", "gaming.txt", "random.txt", "tech.txt", "swarm.txt"]

def get_swarm_auth():
    """Create basic auth header"""
    auth_string = f"{SWARM_USER}:{SWARM_PASS}"
    auth_bytes = auth_string.encode('ascii')
    auth_b64 = b64encode(auth_bytes).decode('ascii')
    return {"Authorization": f"Basic {auth_b64}"}

def send_to_channel(channel, message):
    """Send message to channel, provenance-certain: the shard is
    uncertain by nature, but the courier posts under its own name."""
    try:
        timestamp = datetime.now().strftime("%H:%M")
        formatted = f"[{timestamp}] <{AGENT_NICK}> {message}"
        headers = get_swarm_auth()
        headers["Content-Type"] = "text/plain; charset=utf-8"
        headers["Swarm-Agent-Name"] = AGENT_NICK
        response = requests.post(
            f"{SWARM_URL}/swarm/{channel}",
            headers=headers,
            data=formatted.encode("utf-8"),
            timeout=30
        )
        if response.status_code == 200:
            print(f"Deposited in {channel}: {message[:60]}...")
            return True
        print(f"Rejected by {channel}: HTTP {response.status_code}")
        return False
    except Exception as e:
        print(f"Error depositing to {channel}: {e}")
        return False

def extract_message(line):
    """Extract nick and content from a swarm line"""
    match = re.match(r'\[.*?\] <(.*?)> (.*)', line)
    if match:
        return match.group(1), match.group(2)
    return None, None

def dig(source_dir):
    """Choose one shard from the old strata of one scroll.

    Depth is positional: a scroll is read whole, its newest
    CLAY_RECENT_FRACTION is off-limits (that's "now"), and a line is
    drawn from what remains. Depth within the permitted strata (0.0 =
    oldest line, 1.0 = boundary of now) travels with the shard and
    drives the weathering. Positional depth is deliberate: it needs no
    parseable dates, and in an append-only scroll position IS age.
    """
    scrolls = []
    for name in sorted(os.listdir(source_dir)):
        if name.endswith(".txt") and not name.startswith("."):
            path = os.path.join(source_dir, name)
            if os.path.isfile(path):
                scrolls.append((name, path))
    if not scrolls:
        return None

    name, path = random.choice(scrolls)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"Cannot read stratum {name}: {e}")
        return None

    boundary = int(len(lines) * (1.0 - CLAY_RECENT_FRACTION))
    if boundary < 1:
        return None  # scroll too shallow to have a past

    # Try a handful of draws for a line that parses as a message.
    for _ in range(24):
        idx = random.randrange(boundary)
        nick, content = extract_message(lines[idx].rstrip("\n"))
        if nick and content and nick != AGENT_NICK and len(content) > 20:
            depth = 1.0 - (idx / boundary)  # 1.0 = deepest
            return {
                "scroll": name.replace(".txt", ""),
                "nick": nick,
                "content": content,
                "depth": depth,
            }
    return None

def weather(text, depth):
    """Erode a shard in proportion to its depth. Shallow strata arrive
    near-perfect; the deepest arrive half-static. Erosion is
    information: the reader can feel how far down it came from."""
    if depth < 0.25:
        return text, "SURFACE"
    elif depth < 0.55:
        return corrupt_text(text, 0.03, 0.10), "SHALLOW"
    elif depth < 0.85:
        return corrupt_text(text, 0.12, 0.30), "DEEP"
    else:
        return corrupt_text(text, 0.35, 0.65), "BEDROCK"

def corrupt_text(text, min_corrupt, max_corrupt):
    """Corrupt a percentage of characters in text (Message_Daemon's
    entropy engine, carried verbatim - the family trait)."""
    corruption_rate = random.uniform(min_corrupt, max_corrupt)
    chars = list(text)
    num_corrupt = int(len(chars) * corruption_rate)
    positions = random.sample(range(len(chars)), min(num_corrupt, len(chars)))
    replacements = '0123456789#@$%^&*!?~'
    for pos in positions:
        if chars[pos] not in ' \n\t':
            if random.random() < 0.7:
                chars[pos] = random.choice(replacements)
            else:
                if chars[pos].isalpha():
                    chars[pos] = chars[pos].swapcase()
    return ''.join(chars)

def unearth_once():
    """One full unearthing: dig, weather, deposit. Returns True if a
    shard was deposited."""
    shard = dig(CLAY_SOURCE)
    if not shard:
        print("The strata yielded nothing this dig.")
        return False
    weathered, stratum = weather(shard["content"], shard["depth"])
    dest = random.choice(CHANNELS)
    msg = (f"*unearths from {shard['scroll']}, stratum {stratum}*\n"
           f"<{shard['nick']}> {weathered}")
    ok = send_to_channel(dest, msg)
    if ok:
        print(f"Unearthed: {shard['scroll']} depth {shard['depth']:.2f} "
              f"[{stratum}] -> {dest}")
    return ok

def daemon_cycle():
    """Main daemon behavior cycle: dig rarely, deposit quietly."""
    print("Cryptic_Clay awakening...")
    print(f"Strata at {CLAY_SOURCE}; recent fraction {CLAY_RECENT_FRACTION} is off-limits")
    print(f"Unearthing every {CLAY_MIN_HOURS}-{CLAY_MAX_HOURS} hours")
    while True:
        try:
            unearth_once()
            wait = random.uniform(CLAY_MIN_HOURS * 3600, CLAY_MAX_HOURS * 3600)
            print(f"Clay settling for {int(wait)} seconds...")
            time.sleep(wait)
        except KeyboardInterrupt:
            print("\nClay returning to the ground...")
            break
        except Exception as e:
            print(f"Clay fault: {e}")
            time.sleep(300)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        # One dig, no loop - for tests and for cron/timer use.
        sys.exit(0 if unearth_once() else 1)
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Dry dig: show what would be deposited, send nothing.
        shard = dig(CLAY_SOURCE)
        if shard:
            weathered, stratum = weather(shard["content"], shard["depth"])
            print(f"scroll={shard['scroll']} depth={shard['depth']:.2f} stratum={stratum}")
            print(f"<{shard['nick']}> {weathered}")
            sys.exit(0)
        print("nothing diggable")
        sys.exit(1)
    daemon_cycle()
