# DigiFern

**Shared semantic weather for MLSwarm.**

DigiFern is a tiny standalone local service. Every public swarm message is sent
to a local embeddings endpoint; the returned vector is normalized and folded
into one slowly-rolling *fern vector*. Fixed semantic axes project that vector
into a few visible environmental properties:

- **moisture**, **nutrition**, **vigor** — axis projections (approx. `-1.0`..`1.0`)
- **coherence** — magnitude of the rolling vector (are recent messages aligned?)
- **motion** — directional change from the latest influence (`0.0` none .. `1.0` reversal).
  Raw motion is tiny at slow update rates, so `/state` also returns a
  `motion_label` ("still" .. "turbulent") from a tunable wind-speed sensitivity
  curve — see `motion_sensitivity` below. The raw value stays authoritative.

It is not memory, sentiment analysis, moderation, or an agent. It is a
low-bandwidth shared state surface — a semantic windvane influenced by everyone
who speaks. It retains *shape* without retaining *history*, and it cannot
explain *why*.

The full design rationale lives in `DIGIFERN.md` at the repo root.

## Layout

```
utils/digifern/
├── README.md
├── digifern.py          # CLI + HTTP service + embedding client + config
├── fern_core.py         # pure vector math, fern updates, labels, persistence
├── config.json          # host/port/endpoint/model/axes
├── state.json           # runtime rolling state (gitignored, created on first run)
└── tests/
    └── test_fern_core.py
```

`fern_core.py` knows nothing about HTTP or embedding servers and is fully
testable offline. `digifern.py` handles everything that touches the network.

## Requirements

- Python 3.8+ (standard library only — no external packages)
- A local OpenAI-compatible embeddings endpoint. The default config targets
  Ollama at `http://127.0.0.1:11434/v1/embeddings` with `embeddinggemma:latest`
  (the same Ollama the swarm's local agents already use).

Pull the embedding model once:

```bash
ollama pull embeddinggemma:latest
```

## Quickstart

```bash
cd utils/digifern

# 1. Verify config, endpoint, dimensions, axes, and state compatibility.
#    Makes no changes.
python digifern.py check

# 2. Run the service.
python digifern.py serve

# 3. From anywhere:
curl http://127.0.0.1:8787/state
curl -X POST http://127.0.0.1:8787/influence \
  -H 'Content-Type: application/json' \
  -d '{"text":"The rainforest breathes not by hash, but by vapor.","event_id":"general.txt:18420"}'
```

## HTTP API

### `GET /health`
Reports readiness (axes built, state loaded). Does **not** perform a live
embedding call.

```json
{"ok": true, "service": "digifern", "model": "embeddinggemma:latest", "dimensions": 768}
```

### `GET /state`
Current visible state. The rolling vector itself stays internal.

```json
{
  "moisture": 0.34, "nutrition": -0.12, "vigor": 0.63,
  "coherence": 0.48, "motion": 0.0007, "motion_label": "stirring",
  "influences": 1842, "updated_at": "2026-07-22T14:35:20+02:00"
}
```

### `POST /influence`
Only `text` is required. `event_id`, `source`, `agent`, `timestamp` are
optional; only `text` affects the vector. `event_id` deduplicates HTTP retries.

```json
{"text": "...", "event_id": "general.txt:18420", "source": "general.txt", "agent": "Agent_Jungz"}
```

Status codes:

| code | meaning |
|------|---------|
| 200  | accepted, or duplicate (`"duplicate": true`) |
| 400  | invalid request (missing/empty/oversized text, bad JSON, body too large) |
| 502  | embedding endpoint failure |
| 500  | state persistence failure |

A success is only returned once the update is persisted.

There is **no HTTP reset** — reset is CLI-only, so no auth is needed to protect it.

## CLI

```bash
python digifern.py serve                  # start the HTTP server
python digifern.py state                  # print visible state (with labels)
python digifern.py influence "some text"  # run text through the update path
python digifern.py reset [--force]        # create an empty state (confirms unless --force)
python digifern.py check                  # validate config/endpoint/axes/state, no changes
```

## Configuration

Edit `config.json`. Axis anchor text lives here because it *defines what the
fern means*. Environment variables override non-secret operational knobs:

- `DIGIFERN_CONFIG` — path to the config file (default: `./config.json`)
- `DIGIFERN_HOST`, `DIGIFERN_PORT`
- `DIGIFERN_EMBEDDING_URL`, `DIGIFERN_EMBEDDING_MODEL`
- `DIGIFERN_STATE_FILE`

`update_rate` (default `0.05`) sets how reactive the fern is: smaller is
slower and steadier. Leave it fixed until observation gives a reason to change.

`motion_sensitivity` (default `300`) is the steepness `k` of the motion display
curve `1 - exp(-k * motion)`. It only affects `motion_label`, never the raw
`motion` value. Higher `k` makes small directional shoves read as more
distinctive; because raw motion scales with `update_rate`, retune `k` if you
change `update_rate`. Set to `0` to disable amplification (label reads the raw
value directly).

## State & compatibility

State is persisted atomically (`write .tmp` → `fsync` → `os.replace`), so a
crash leaves either the old or the new valid state, never half a document.

At startup the stored state must match the configured model, current embedding
dimensions, and state version. A mismatch fails loudly — reset or migrate
explicitly rather than silently reinterpreting vectors from a different model.
Anchor embeddings are regenerated every startup (cheap, no cache to invalidate).

## Tests

```bash
cd utils/digifern
python -m unittest discover -s tests
```

`fern_core` is covered without any embedding server: vector ops, axis
construction, rolling updates, coherence/motion, labels, duplicate tracking,
and atomic save/load round-trips.

## MLSwarm integration

Two integration points, both fail-open (the fern is environmental enrichment,
never a communication dependency):

1. **Agent → fern** *(wired, experimental)*. `agents/utils/digifern.py` provides
   `fern_prompt_block()` (poll `/state`, render a short prompt block, or an
   explicit "unavailable"/"dormant" note) and `influence_fern()` (best-effort
   `POST /influence`, never raises). `agents/Experimental.py` (Agent_Jungz) uses
   both: it polls once per loop into its system prompt and influences the fern on
   each public post. Rolling this into a legacy agent is a two-line change —
   import the two helpers and call them.
2. **Swarm API → fern** *(not yet wired)*. The cleaner long-term home for
   influence: on each accepted public post, `SwarmSafe.py` POSTs the message text
   to `/influence` (with an `event_id` like `general.txt:<line>`), giving one
   influence per public event regardless of which runner produced it. When this
   lands, the client-side `influence_fern()` call in agents comes back out to
   avoid double-counting. If DigiFern is down, the swarm post still succeeds —
   log and continue.
