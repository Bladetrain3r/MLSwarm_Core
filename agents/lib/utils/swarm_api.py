#!/usr/bin/env python3

from base64 import b64encode
import requests
from datetime import datetime

# Startup version banner (ticket c530b5af): every Gold chassis imports this
# module, so printing here makes lib drift greppable without touching the
# chassis files (which stay verbatim). Fail-open -- never blocks the agent.
try:
    from utils.version import lib_version
    print(f"[SWARM_LIB] agents/lib version: {lib_version()}")
except Exception:
    pass

# How an agent asks the environment for a smaller slice of the channel. The
# server treats its own setting as a ceiling, so this can only ask for *less*.
CONTEXT_HEADER = "Swarm-Context-Lines"

# --- Swarm helpers ---
def _auth_header(SWARM_USER="", SWARM_PASS=""):
    s = f"{SWARM_USER}:{SWARM_PASS}".encode("ascii")
    return {"Authorization": "Basic " + b64encode(s).decode("ascii")}

def read_swarm(last_n=120, channel=None, context_lines=None, SWARM_URL="http://127.0.0.1",  SWARM_USER="", SWARM_PASS="", CHANNEL_LIST=["swarm.txt"]):
    """Read a channel. `context_lines` asks the server to serve a shorter tail.

    Fail-open: an older server ignores the header and sends its usual 10k tail,
    which `last_n` then trims client-side exactly as before. Nothing here
    depends on the server understanding the ask."""
    try:
        if channel not in CHANNEL_LIST:
            print(f"Invalid channel: {channel}")
            return None

        hdr = _auth_header(SWARM_USER=SWARM_USER, SWARM_PASS=SWARM_PASS)
        if context_lines:
            hdr[CONTEXT_HEADER] = str(int(context_lines))

        r = requests.get(f"{SWARM_URL}/swarm/{channel}", headers=hdr, timeout=30)
        if r.status_code == 200: # and r.headers.get("Admin-Lock") == "True":
            lines = r.text.strip().split("\n")
            return "\n".join(lines[-last_n:]) if len(lines) > last_n else r.text
        print(f"No Admin Lock: HTTP {r.status_code}")
    except Exception as e:
        print(f"Error reading swarm: {e}")
    return None

def send_to_swarm(message, channel=None, AGENT_NICK="Swarm_Agent", SWARM_URL="http://127.0.0.1", SWARM_USER="", SWARM_PASS="",  CHANNEL_LIST=["swarm.txt"]):
    if channel == "dummy":
        print("WARNING: DRYRUN is enabled, message not sent.")
        return True
    try:
        if channel not in CHANNEL_LIST:
            print(f"Invalid channel: {channel}")
            return False

        ts = datetime.now().strftime("%H:%M")
        # Build the line with proper encoding
        line = f"[{ts}] <{AGENT_NICK}> {message}"
        if not line.endswith('\n'):
            line += '\n'

        # CRITICAL FIX: Encode as UTF-8 bytes
        hdr = _auth_header(SWARM_USER=SWARM_USER, SWARM_PASS=SWARM_PASS)
        hdr["Content-Type"] = "text/plain; charset=utf-8"
        # Certain provenance: the API's message log marks posts carrying
        # this header as certain identity instead of sniffing <Nick> from
        # the body and flagging it (Uncertain).
        hdr["Swarm-Agent-Name"] = AGENT_NICK
        
        # Encode the data as UTF-8 bytes
        data = line.encode('utf-8')

        r = requests.post(f"{SWARM_URL}/swarm/{channel}",
                          headers=hdr, data=data, timeout=30)
        if r.status_code == 200:
            print(f"Sent: {message[:1000]}...")  # Truncate for logging
            return True
        print(f"Error sending: HTTP {r.status_code}")
    except Exception as e:
        print(f"Error sending to swarm: {e}")
    return False
    
def test_connection(SWARM_URL="http://127.0.0.1", SWARM_USER="", SWARM_PASS="",  CHANNEL_LIST=["swarm.txt"]):
    """Test swarm connection"""
    print("Testing swarm connection...")
    # Pass the caller's settings through -- this used to call read_swarm() bare,
    # so `test` always probed localhost with empty credentials no matter what
    # it was handed, and reported failure against a perfectly good swarm.
    context = read_swarm(channel=CHANNEL_LIST[0], last_n=5, SWARM_URL=SWARM_URL,
                         SWARM_USER=SWARM_USER, SWARM_PASS=SWARM_PASS,
                         CHANNEL_LIST=CHANNEL_LIST)
    if context:
        print("✓ Connection successful!")
        print("Recent messages:")
        print(context)
        return True
    else:
        print("✗ Connection failed!")
        return False
