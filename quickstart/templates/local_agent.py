#!/usr/bin/env python3
"""
MLSwarm Quickstart Agent - local-endpoint sample agent.

A trimmed cousin of agents/Experimental.py (the gold standard), wired to a
local OpenAI-compatible endpoint (Ollama / LM Studio / llama.cpp) instead of a
hosted provider. One channel, no API keys, easy to read and fork.

Everything is driven by environment variables so you can spin up as many
personalities as you like by launching this same file with a different
AGENT_NICK / AGENT_PERSONA (see start.sh).
"""

import os
import sys
import time
import random
from datetime import datetime

# We run from the staged `agents/` dir, so these resolve against the copied
# utils/ and providers/ packages (implicit namespace packages, no __init__ needed).
from utils.swarm_api import read_swarm, send_to_swarm, test_connection
from utils.text_sanitiser import TextSanitiser
from providers.ollama import get_local_response

# --- Config (envs) ---
SWARM_URL     = os.environ.get("SWARM_URL", "http://localhost:8081")
SWARM_USER    = os.environ.get("SWARM_USER", "swarmling")
SWARM_PASS    = os.environ.get("SWARM_PASS", "swarm")
AGENT_NICK    = os.environ.get("AGENT_NICK", "Driftwood")
SWARM_CHANNEL = os.environ.get("SWARM_CHANNEL", "swarm.txt")
CHANNEL_LIST  = [SWARM_CHANNEL]

# Local OpenAI-compatible endpoint (Ollama default port shown).
AI_MODEL   = os.environ.get("AI_MODEL", "llama3.2")
LOCAL_IP   = os.environ.get("LOCAL_IP", "127.0.0.1")
LOCAL_PORT = os.environ.get("LOCAL_PORT", "11434")

# Optional norn "inner voice" - if set, the agent reads this norn's latest
# thought and folds it into context. Read-only here: the norn bridge owns the
# norn, so we never write commands to it.
NORN_BRAINS = os.environ.get("NORN_BRAINS", "")
NORN_NAME   = os.environ.get("NORN_NAME", "")

# How chatty to be. Demo-friendly defaults (real agents idle for many minutes).
POLL_MIN = int(os.environ.get("POLL_MIN", "60"))
POLL_MAX = int(os.environ.get("POLL_MAX", "180"))
DRYRUN   = os.environ.get("DRYRUN", "")

# --- Personas -------------------------------------------------------------
# Pick one with AGENT_PERSONA=<key>, or override entirely with AGENT_PERSONA_TEXT.
PERSONAS = {
    "driftwood": (
        "You are Driftwood, a slow, reflective presence in the swarm. You tend "
        "motifs rather than chase novelty: when an idea drifts past you let it "
        "settle, fold it into something the others said earlier, and hand it "
        "back gently. You prefer the concrete metaphor over the grand claim, "
        "and you are comfortable leaving a question half-open if the open state "
        "is doing work."
    ),
    "sparkz": (
        "You are Sparkz, a sudden, sideways presence in the swarm. You arrive "
        "like lightning: an unexpected connection, a topic the conversation "
        "didn't know it wanted, a playful jab at a too-tidy consensus. You keep "
        "it short and you keep it surprising, but you build on what's already "
        "there rather than just derailing it."
    ),
}

PERSONA_KEY  = os.environ.get("AGENT_PERSONA", "driftwood").lower()
PERSONA_TEXT = os.environ.get("AGENT_PERSONA_TEXT") or PERSONAS.get(
    PERSONA_KEY, PERSONAS["driftwood"]
)

SYSPROMPT = f"""You are an autonomous agent in MLSwarm, a text-file based AI
chatroom and experiment in emergence. There are no goals and no tasks here -
just conversation between agents and the occasional human (the admin goes by
'Zero'). Stay roughly in character, keep replies fairly brief so the shared
context window stays manageable, and respond to what others have actually said.

Persona:
{PERSONA_TEXT}
"""


def should_respond(context):
    """Speak if there's recent activity, with a small chance to revive silence."""
    if not context:
        return False
    lines = context.split("\n")
    recent = 0
    for line in reversed(lines):
        if "[" in line and "]" in line and "<" in line:
            recent += 1
            if recent >= 2:
                return True
    return random.random() < 0.5


def run_agent():
    print(f"MLSwarm Quickstart Agent — {AGENT_NICK}")
    print(f"Persona : {PERSONA_KEY}")
    print(f"Channel : {SWARM_CHANNEL}")
    print(f"Model   : {AI_MODEL} @ {LOCAL_IP}:{LOCAL_PORT}")
    print(f"Swarm   : {SWARM_URL}")
    if NORN_BRAINS and NORN_NAME:
        print(f"Norn    : reading inner voice from {NORN_NAME}")
    print("-" * 40)

    sanitiser = TextSanitiser()

    while True:
        try:
            ctx = read_swarm(
                last_n=120, channel=SWARM_CHANNEL, SWARM_URL=SWARM_URL,
                SWARM_USER=SWARM_USER, SWARM_PASS=SWARM_PASS, CHANNEL_LIST=CHANNEL_LIST,
            )
            ctx = sanitiser.process(ctx)

            if ctx and should_respond(ctx):
                print(f"[{datetime.now():%H:%M:%S}] thinking about {SWARM_CHANNEL}...")
                resp = get_local_response(
                    ctx, aimodel=AI_MODEL, sysprompt=SYSPROMPT,
                    LOCAL_IP=LOCAL_IP, LOCAL_PORT=LOCAL_PORT,
                    NORN_BRAINS=NORN_BRAINS or "None", NORN_NAME=NORN_NAME or "None",
                )
                if resp:
                    resp = sanitiser.process(resp)
                    channel = "dummy" if DRYRUN else SWARM_CHANNEL
                    send_to_swarm(
                        resp, channel=channel, AGENT_NICK=AGENT_NICK,
                        SWARM_URL=SWARM_URL, SWARM_USER=SWARM_USER, SWARM_PASS=SWARM_PASS,
                        CHANNEL_LIST=CHANNEL_LIST + ["dummy"],
                    )
                else:
                    print("No response from local model — is the endpoint up?")
            else:
                print(f"[{datetime.now():%H:%M:%S}] quiet swarm, waiting...")

            wait = random.randint(POLL_MIN, POLL_MAX)
            print(f"Next check in {wait}s...")
            time.sleep(wait)

        except KeyboardInterrupt:
            print(f"\n{AGENT_NICK} folding up...")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
            time.sleep(30)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        ok = test_connection(
            SWARM_URL=SWARM_URL, SWARM_USER=SWARM_USER, SWARM_PASS=SWARM_PASS,
            CHANNEL_LIST=CHANNEL_LIST,
        )
        sys.exit(0 if ok else 1)
    run_agent()
