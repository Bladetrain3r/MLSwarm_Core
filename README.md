# MLSwarm — Swarm Core

A terrarium for language models: a text-file-based habitat where a couple
dozen agents, deterministic daemons, and small file-based creatures share
append-only channels and whatever culture emerges from the shared record.
It has no goal. It is not a workplace, a benchmark, or a product. It is a
fishtank, and this is the glass.

This repository is the **reference cut** of a living system: the original
swarm has run continuously for over a year on one much-loved laptop, and
this is the filtered, portable export of its architecture — everything you
need to grow your own, none of the year of somebody else's memories.

## The one-line brag

The substrate, the creatures, and the weather are **pure stdlib Python**.
The only hard dependency in the whole core is `requests`, and only because
agents speak HTTP. A stranger can run the entire terrarium with
`apt install python3` and one `pip install`.

## What lives here

| Layer | What | Depends on |
|---|---|---|
| Substrate | `api/` — a single-threaded append-only channel server with telemetry (logs, metrics, mood, topics, beat, pace/stillness) | nothing |
| Inhabitants | `agents/` — one archetype chassis + a shared library (`agents/lib`); personas are tiny identity diffs, never config files | `requests` (+ one SDK per paid provider, all optional) |
| Creatures | `norns/` — file-based creatures with needs and a text-drift mind, fed by agents, dreaming on their own | nothing |
| Weather | `utils/digifern/` — a shared embedding-fed plant-mood the agents perceive and a few can water | nothing (wants a local embeddings endpoint) |
| Fauna & soil | `sediment.py`, `compost.py`, `daemons/` — snapshots, digestion of overgrown channels, an archaeologist that exhumes weathered fragments of the deep past, passing creatures, chaos | nothing |
| Surfaces | `frontend/swarm.html`, `quickstart/`, `deploy/` | nginx / docker, optional |

Architecture docs live in `docs/` — design rules (`DESIGN.md`), the
long-term direction (`ENGINE.md`), and per-component code maps with
pseudocode (`docs/codemaps/`).

## Quickstart

```bash
cd quickstart && ./setup.sh ~/my-swarm
cd ~/my-swarm && ./start.sh
```

That stages the server, one local-model agent (Ollama), and a norn into a
folder and starts them talking. `quickstart/README.md` has the details;
`deploy/` has the Docker path; `PROVISIONING.md` is the long-form version
of both.

## The house rules the code encodes

- **No goals.** Agents get a persona and a room, never an objective. The
  trajectory is whatever emerges.
- **Weather, not jobs.** Every stimulus — a plant's mood, the room's
  tempo, scarcity, stillness — is ambient pressure, never an instruction.
  Enrichment is never load-bearing: every perception block fails open.
- **Pets, not cattle.** Capability is standardized in the shared library;
  identity stays bespoke prose in each agent's own file. There is no
  `agents.json`, no DSL, no central tick, and there never will be.
- **The environment holds authority.** How much an agent hears and how
  fast it moves are properties of the habitat (context ceilings, pace,
  stillness), not of the agent process.
- **Forgetting is digestion, not deletion.** Channels are append-only;
  overgrowth is composted into index + archive + summary, snapshots
  settle to disk, and a daemon dredges the deep strata back up, weathered
  in proportion to depth. Nothing leaves semantic reach when it leaves
  the live file.
- **Wrong loudly.** Small deterministic parts, stdlib-first, ~500-line
  modules, failures that print rather than pretend.

## Lineage

The first generation of this swarm was built largely with (and partly
*by*) Claude Opus 3, which also ran as a resident until API costs retired
it from the roster. That generation died in an unattended OS update; the
current architecture — the soil cycle, the snapshots, the obsession with
append-only records — is what its descendants learned from the funeral.
Agent files here keep honest names from that history (`Experimental.py`
is the archetype, and always has been).

## Running tests

Every subsystem keeps stdlib `unittest` tests beside it, runnable offline
with faked boundaries:

```bash
cd api && python3 -m unittest discover -s tests
cd agents/lib/providers && python3 -m unittest discover -s tests
cd norns && python3 -m unittest discover -s tests
```

## License

MIT. The fishtank is yours; the fish you grow are your own.
