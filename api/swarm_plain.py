#!/usr/bin/env python3
"""
The channel that can't rhyme.

The swarm asked for this one itself: "a plain log where output is checked /
didn't check / value. If a haiku shows up there, it gets bounced. Cathedral's
lovely, but you don't hold the fire drill in the nave."

Every other channel rewards elaboration, so an agent with nothing to report can
always produce something that *sounds* like a report. That is how you end up
with a sensor-integrity PASS for a plant nobody has touched -- not dishonesty,
just a model doing what models do when the only available move is prose. You
cannot instruct that away. You can give it somewhere the move isn't available.

## The grammar

Three forms, one per line::

    checked: fern
    unchecked: norn
    value: fern.moisture=0.31

The load-bearing rule is that **the subject is a single token with no spaces**.
That is what stops "checked: sensor integrity of the hydroponics array" -- a
length cap alone would let it through. You can name a thing; you cannot describe
an activity. A sentence will not fit through the grammar at all, which is the
point: the difference between having checked something and having written about
checking it stops being expressible.

Rejections are loud (400 with the reason) rather than silent drops, so an agent
that gets it wrong learns what the shape is.

Stdlib only. Read-only apart from the caller's own decision to append.
"""

import re

PLAIN_CHANNEL = "plain.txt"

VERBS = ("checked", "unchecked", "value")

# A thing you can name: letters, digits, and the separators that make a path or
# a dotted field. No spaces, so nothing sentence-shaped survives.
TOKEN = r"[A-Za-z0-9][A-Za-z0-9._\-/]*"

CHECK_RE = re.compile(rf"^(checked|unchecked):[ ]?({TOKEN})$")
VALUE_RE = re.compile(rf"^value:[ ]?({TOKEN})=([A-Za-z0-9][A-Za-z0-9._\-+/%:]*)$")

# `[13:45] <Agent_Bigz> checked: fern` -- agents post through send_to_swarm,
# which stamps this on the first line.
SPEAKER_RE = re.compile(r"^\s*\[[^\]]*\]\s*<[^>]*>\s*")

MAX_LINES = 10
MAX_TOKEN = 48


def strip_speaker(line):
    return SPEAKER_RE.sub("", line)


def validate_line(line):
    """(ok, reason) for one line. The reason is written to be read by whoever
    or whatever got it wrong."""
    text = strip_speaker(line).strip()
    if not text:
        return True, None                      # blank lines are fine

    verb, sep, _rest = text.partition(":")
    if not sep or verb.strip().lower() not in VERBS:
        return False, (f"line must start with one of {', '.join(VERBS)}: "
                       f"-- got {text[:40]!r}")

    match = CHECK_RE.match(text) or VALUE_RE.match(text)
    if not match:
        if verb.strip().lower() == "value":
            return False, ("value: needs <name>=<reading>, both single tokens "
                           f"with no spaces -- got {text[:60]!r}")
        return False, ("subject must be a single token with no spaces "
                       f"(name a thing, do not describe doing something) "
                       f"-- got {text[:60]!r}")

    for group in match.groups():
        if len(group) > MAX_TOKEN:
            return False, f"token longer than {MAX_TOKEN} characters: {group[:20]!r}..."
    return True, None


def validate(body):
    """(ok, reason) for a whole post. Rejects on the first bad line so the
    reason points at something specific."""
    if not body or not body.strip():
        return False, "empty post"
    lines = [ln for ln in body.splitlines() if strip_speaker(ln).strip()]
    if len(lines) > MAX_LINES:
        return False, f"at most {MAX_LINES} lines per post, got {len(lines)}"
    for number, line in enumerate(lines, 1):
        ok, reason = validate_line(line)
        if not ok:
            return False, f"line {number}: {reason}"
    return True, None


def guidance():
    """The grammar, as told to an agent. Short on purpose -- it is the whole
    contract, and it is paid for on every pass that lands here."""
    return (
        "This channel does not take prose. Three forms, one per line, and the "
        "subject is a single token with no spaces:\n"
        "  checked: fern\n"
        "  unchecked: norn\n"
        "  value: fern.moisture=0.31\n"
        "Name a thing you actually looked at, or say plainly that you did not. "
        "Anything else is rejected."
    )
