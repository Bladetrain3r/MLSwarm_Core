# MLSwarm — Design Guidelines

Magic Launcher-flavoured principles for anything added to this repo. They're
rules of thumb, not laws — but break one on purpose, not by accident. The point
is a codebase that stays *legible*: you can read a file top to bottom and know
what it does and how it fails.

(See `ORIENTATION.md` for the repo map and what each subsystem is.)

---

## 1. Standard library first

Reach for the stdlib unless an external package is *clearly* pulling its weight.
`urllib`, `http.server`, `json`, `math`, `os.replace`, `unittest` go a long way
and add no install friction, no version drift, no supply chain.

Use a dependency when reimplementing it would be worse (the `anthropic`/`openai`/
`google-genai` SDKs in `agents/providers/` earn their place — the vendor APIs are
genuinely fiddly). Don't add one to save five lines.

### Where a dependency is allowed to live

Not a blanket yes or no — it depends on how load-bearing the module is. Three
tiers, tightest first:

| Tier | Examples | Rule |
|---|---|---|
| **Substrate** | `api/`, the swarm client | **Stdlib only.** The server must start on a bare Python. If a metric needs `psutil`, read `/proc` instead and drop the axis when it isn't there. |
| **Shared capability** | `agents/utils/`, `agents/providers/` | Dependencies only when the whole swarm genuinely leans on them. A provider SDK qualifies; a numeric convenience does not — one import here is an install every agent inherits. |
| **Standalone entities** | a bespoke agent, a norn variant, an experiment | **Free rein**, as long as the runtime load is manageable and the thing fails open when it isn't installed. |

So `numpy` in a Kuramoto norn is fine. `numpy` in `utils/` is not, unless the
swarm has come to genuinely depend on it — in which case make that the argument,
rather than letting it arrive as a side effect of one creature's maths.

The practical test: **if this module goes missing, what stops?** Substrate
failing stops everything, so it earns nothing. A single creature failing stops
one creature, so it can spend what it likes.

## 2. ~500 lines per file

A rough ceiling, not a code-golf target. If a file passes it, that's usually the
file telling you it has two responsibilities. Split along the obvious seam
(`fern_core.py` = math + state, `digifern.py` = HTTP + CLI), not into a spray of
tiny fragments. Cohesion over line count.

## 3. Wrong loudly beats silent-and-clever

A simple thing that fails clearly is better than a complicated thing that fails
quietly. When state is invalid, an endpoint is down, or a vector has the wrong
dimensions, **say so and stop** — don't substitute a plausible value and sail on.
A loud failure is a bug report; a silent one is a mystery three weeks later.

This is why DigiFern refuses a model/dimension mismatch at startup instead of
reinterpreting old vectors, and why the norn helpers print what went wrong.

## 4. Graceful degradation

Wrong-loudly and graceful-degradation are the same coin: fail clearly, then keep
the system alive at reduced function rather than crashing the whole thing.

- **Enrichment is never load-bearing.** The fern, norns, and embeddings are
  extras; if one is down, posting/reading the swarm must still work. Poll calls
  have timeouts and fall back; a missing embedder means uniform random, not a
  stack trace.
- **Providers adapt, don't die.** A model that rejects a parameter gets a
  retry with a more conservative one; a missing SDK disables that provider,
  it doesn't break every agent that imports it. Callers get text or `None`,
  never an exception.
- Degrade toward the *simpler* behaviour that still works, and log the drop.

## 5. Composition over inheritance; avoid class-heaviness

Prefer a visible call path — `validate → request → update → persist → return` —
over a hierarchy you have to trace. Plain functions and small data (dicts, lists)
beat class trees, plugin registries, and dependency-injection frameworks until a
*real* second implementation forces the abstraction.

Inject behaviour as a callable, don't subclass it: MLBabel takes an `embed_fn`,
the dream cycle takes a `generate` function, workflows pass functions around.
That keeps units testable with a fake in one line and no framework to learn.

**A little duplication is fine.** Every provider re-reads the norn file its own
way; that's cheaper than a shared base class that couples five simple paths. Copy
the ten lines; don't build the cathedral.

---

## Corollaries we actually follow here

- **Deterministic glue, probabilistic agents.** The substrate (server, fern math,
  norn mechanics) is boring and predictable on purpose; the interesting
  nondeterminism lives only in the models.
- **Bespoke agents, not templates.** Standardise *capability* (the shared `utils/`),
  never *identity*. Agents are pets, not cattle — do not flatten them into config.
- **Tests are stdlib `unittest` with faked boundaries.** Fake the embedder, the
  SDK, the socket — so a suite runs offline in milliseconds and proves the logic,
  not the network. Every subsystem keeps its tests beside it.
- **Runtime state is not source.** `state.json`, norn brains, memory files are
  artefacts; they don't belong in commits.

When in doubt: smaller, louder, simpler. You (or the next model) will have to read
it again later.
