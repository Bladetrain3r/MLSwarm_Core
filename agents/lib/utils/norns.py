#!/usr/bin/env python3
"""
File-based bridge to a Napkin Norn backpack, plus the dream-cycle helpers.

The norn runs as a separate daemon that reads NORN_command.txt and writes
NORN_response.txt. These helpers do the file plumbing and orchestrate a private
"dream" cycle during low-activity periods. Anything that needs the language
model itself (the response loop) stays in the agent and is injected as a
`generate` callable, so this module stays dependency-light.
"""


def get_norn_response(NORN_NAME="Norn", NORN_BRAINS="/tmp/norn_brains"):
    """Return the norn's latest response text, or "" if unavailable.

    Reads the buffer ONCE. (The previous version read the file twice, so the
    second read returned empty -- the reason callers fell back to inline file
    ops.)"""
    try:
        with open(f"{NORN_BRAINS}/{NORN_NAME}_response.txt", "r", encoding="utf-8") as response:
            return response.read().strip()
    except (FileNotFoundError, PermissionError):
        print(f"Norn brain not found or inaccessible, please check {NORN_NAME}.")
        return ""


def send_norn_command(NORN_NAME="Norn", NORN_BRAINS="/tmp/norn_brains", command="Hello!", feed=False, play=False):
    """Write a command into the norn's command file. Returns True on success."""
    try:
        with open(f"{NORN_BRAINS}/{NORN_NAME}_command.txt", "w", encoding="utf-8") as target_brain:
            target_brain.write(command)
            return True
    except (FileExistsError, PermissionError, FileNotFoundError):
        print(f"Previous Norn command still processing, or path cannot be written to!\n"
              f" Please check {NORN_BRAINS}.")
        return False


# --------------------------------------------------------------------------
# Dream cycle: during low-activity periods the agent detaches from the swarm
# and instead trickle-feeds the norn its own continued thoughts.
# --------------------------------------------------------------------------
def is_dreaming(circadian_value, threshold=0.3):
    """True when the circadian activity value is below the dream threshold.
    A threshold <= 0 disables dreaming entirely."""
    return threshold > 0 and circadian_value < threshold


def dream_rate_multiplier(tod_multi, threshold=0.3):
    """Floor the pacing multiplier so dream waits trickle at a steady slow rate
    instead of stretching out to the full nighttime slowdown."""
    return max(tod_multi, threshold)


def build_dream_body(norn_thought, instruction="Add to this thought."):
    """Frame the norn's current inner thought as a fragment to continue."""
    return (
        "You are drifting in a low-activity dream. There is no conversation to "
        "answer right now, only a fragment of your own inner thought to continue.\n\n"
        f"Fragment:\n{norn_thought}\n\n{instruction}"
    )


def run_dream_cycle(generate, NORN_NAME="Norn", NORN_BRAINS="/tmp/norn_brains",
                    instruction="Add to this thought."):
    """One private dream cycle.

    Seed from the norn's current thought, ask the model to continue it, and feed
    the continuation back into the norn (the trickle input). `generate` is a
    callable(body) -> str supplied by the agent, so this stays free of provider
    and config dependencies. Returns the continuation text, or None if there was
    nothing to dream on yet or the model produced nothing.
    """
    seed = get_norn_response(NORN_NAME=NORN_NAME, NORN_BRAINS=NORN_BRAINS)
    if not seed:
        return None
    resp = generate(build_dream_body(seed, instruction))
    if resp:
        send_norn_command(NORN_NAME=NORN_NAME, NORN_BRAINS=NORN_BRAINS,
                          command=resp.replace("\n", " "))
    return resp
