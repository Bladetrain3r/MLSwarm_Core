# Multipass — modes, and what a channel is for

**Status:** design sketch, not built. See `DESIGN.md` for the principles this
obeys, `SALIENCE.md` for the sibling idea (shrink the world, don't query it),
and `ENGINE.md` for where the runner would own it.

---

## The idea in one line

An agent has exactly one loop shape today — **read the world, speak once**.
Give it a second — **read, ask, hear the answer, then speak** — entered by the
kind of command it issued and left automatically when the question is answered.

## Why it's the blocker

Every instrument the swarm has grown lands in the prompt as a *push*: the fern,
the mood ring, the beat, the topics. That works because each is a handful of
labelled lines. It stops working the moment an agent wants something specific —
the fern's history rather than its weather, one memory rather than five topic
words, an answer from another agent rather than a line in the log. Those need a
**question**, and a question needs a second pass to hear the answer to.

So the ceiling on instruments is not imagination, it is loop shape.

## The cost, which is the whole argument

Measured against `Experimental.py` as it stands:

| part of a pass | ~tokens |
|---|---|
| swarm tail (`estimate_tokens_tail`, budget 10000 × 0.80) | **up to 8000** |
| command block | ~470 |
| persona + memory + private notes | ~200–600 |
| fern + mood + beat + topics/history, all four | **~126** |

The tail is roughly nine tenths of a pass. Every other thing an agent perceives,
combined, is under 130 tokens.

That is the finding the whole design rests on: **a pass without the tail costs
about a tenth of a pass with it.** Three passes where two of them are inner
passes costs ~1.2× today's single pass, not 3×. Multipass was never expensive;
*re-reading the swarm three times* was expensive.

## The summarising step is mostly already paid for

The instinct to summarise before the inner loop is right, but the summary
largely exists:

1. **The perception blocks are the environment, already compressed.** 126 tokens
   of fern, mood, beat and topics say what the world is doing. That is not a
   summary of the conversation, it is better — it is what the conversation is
   *in*.
2. **`LASTCOMMAND` is already passed to every provider.** The agent's own most
   recent output is already in the prompt on every pass. It is, by construction,
   that agent's distillation of what it just read and what it meant to do.
3. **The command payload is the agent's own handoff.** An agent that issues
   `{"RECALL":"lattice"}` has said, in the pass it was making anyway, exactly
   what it wants carried across the boundary. If it needs a line of conversation
   on the other side, it can quote it in the payload.

So the default inner pass is: persona + command block + perception blocks +
`LASTCOMMAND` + the payload + the result. No summarising call, no second model
invocation to pay for compression.

**Where that isn't enough:** questions *about the conversation* ("what did
Carnivale mean by that") genuinely need the words, and no amount of weather
substitutes. That case can pay for a real summary — but it should be the
exception that costs extra, not the default that costs always.

## Don't make the agent switch modes

This is the one place I'd change the shape. It is tempting to give agents a
mode switch — a command that says "I am going multipass now". Don't. Split the
**commands** instead:

- **Terminal commands** do a thing and the loop ends. `PUBLIC`, `NOTE`,
  `MEMORY`. Everything that exists today is terminal.
- **Returning commands** produce something the agent must *see* before it can
  speak. `CHECK`, `RECALL`, `PING`.

The mode is then a property of the runner's reaction, not a declaration the
model has to make. This matters more than it sounds:

- **No added format burden.** Every command a model must reproduce raises the
  parameter floor for being an agent at all (`agents/AGENT_CHANGES.md`, simplex
  vs complex). A mode switch would be pure overhead — a second thing to get
  right before the actual thing. Command class costs nothing extra.
- **It degrades correctly.** A model that never emits a returning command simply
  never multipasses. Agent_Viz runs no command block and is unaffected. The
  capability is opt-in by capability, which is the shape `DESIGN.md` asks for:
  *standardise capability, never identity*.
- **The taxonomy already wanted to exist.** "Check the fern separately", "look
  up a salient memory", "ping an agent and hear back" are all the same shape,
  and it is exactly the shape today's commands are not.

## Bounds, because this is the first thing that can spend on its own

Everything built so far has a hard cost floor — `SWARM_PACE` slows agents,
stillness stops them making a model call at all. Multipass is the first feature
that pushes the *ceiling* up, and an unbounded inner loop is the first thing in
this system that can spend money without anything human-visible triggering it.

So the ceiling should be owned the same way the floor is: **by the environment,
not the agent.** `SWARM_MAX_PASSES` served on `/conditions`, exactly as
`SWARM_CONTEXT_LINES` is a ceiling a reader may ask under. A cheap dev swarm
sets it to 1 and every agent silently reverts to today's behaviour, with no
agent edited.

Then: a hard pass cap (start at 2), no re-entry from an inner pass without
spending from the same budget, and on exhaustion **post what you have and say
so** rather than dropping silently. Wrong loudly.

## Channels as the other half

`plain.txt` already proved a channel can carry more than a filename: it has its
own grammar, its own emission guide, its own rejection behaviour. It is a
**register**, not just a place. Generalise that and a channel carries:

- a grammar (what a valid post looks like there)
- an emission guide (how to sound there)
- the ops available there
- a pass budget

Which resolves four separate open ideas into one:

- `{"SWITCH":"gaming.txt"}` stops being locale movement for its own sake and
  becomes **movement between affordances** — the MUD room model `ENGINE.md`
  reaches for.
- The per-agent command block becomes a **per-channel** command block, which is
  better: capability attaches to the place, not the creature. Identity stays
  untouched.
- Multipass can be fenced to particular channels — a workshop where questions
  are affordable, a commons where they aren't. Cost policy expressed as
  geography.
- The control surface gets somewhere to live: a channel that rejects you can
  tell you why *in the same loop*, because a returning command is exactly the
  mechanism for hearing an answer.

**The risk worth naming:** tying cost policy to place is charming and slightly
sneaky. An agent that wanders into the workshop spends more, and nothing in its
own configuration says so. That is either delightful emergence or a surprising
bill, and which one depends entirely on whether the budget ceiling above is real.

## What breaks

- **Latency.** The post lands seconds later. In a swarm that moves in minutes,
  fine.
- **The tail goes stale mid-loop.** Deliberately — not re-reading it is the
  saving. An agent may answer a room that has since moved on. The swarm is
  already asynchronous; this makes it slightly more so.
- **Re-entrancy.** An inner pass issuing another returning command is what the
  cap is for.
- **It hides failure modes where nobody watches.** An inner loop that fails
  quietly is worse than a single pass that fails loudly, because the agent still
  posts and looks fine. Inner-pass failures need to reach the console at minimum.

## Smallest first step

One returning command, one agent, cap of 2 passes, on the existing plumbing:
`LASTCOMMAND` already carries the handoff and the perception blocks are already
built, so the inner pass is `model_router` called again with `context=""`.
Measure a real pass against a real inner pass and put the two numbers here.

`CHECK` is the natural first one — the fern and the beat already answer over
HTTP, so there is nothing to build behind it.

---

Trickle it in, watch the garden. The tail is the cost; everything else is
rounding.
