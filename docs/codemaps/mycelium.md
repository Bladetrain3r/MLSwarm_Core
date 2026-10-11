# Code map — mycelium (the derived index)

*Perception of the trail at scale. An append-only JSONL embeddings
index over the scrolls — a cache, regrowable; authority stays in the
scroll (§2's deletion test is about exactly this file).*

## Bill of parts

- **Library:** `agents/lib/utils/mycelium.py` (326 lines) — with an
  **identical stale twin** at `agents/utils/mycelium.py`, which is
  the copy `tend_mycelium.sh` actually resolves (`cd agents; python3
  -m utils.mycelium`). Changes must land in both until unified.
- **Driver:** `/tend_mycelium.sh` — the gardener's manual tending
  ritual; nothing runs this on a timer.
- **Index files:** `deploy/swarm-data/mycelium_dev.jsonl` (default),
  `mycelium_live.jsonl`.
- **Writers:** `tend_mycelium.sh` (manual) and `compost.py` step 1
  (folds every composted span in before trimming).
- **Readers:** the `ask` CLI; `mycelium_prompt_block` exists but is
  **not wired into any chassis yet** (post-release item).

## Library (pseudocode)

```
embed(texts, kind):                            # :65
  POST SWARM_EMBED_URL/api/embed  (default 127.0.0.1:11434,
       model embeddinggemma:300m, query/doc prefixes from env)
  return None on any failure                   # callers treat as outage

chunk_scroll(window=8, stride=4):              # :120
  split on "[HH:MM] <Nick>" headers; sliding windows
  + one extra tail-anchored chunk              # the freshest lines always chunked

grow_index(spans):                             # :195
  rows {id: sha1(channel_basename + text), channel, text, vec}
  batch 16; dedupe by id; APPEND-only JSONL    # regrow = rerun over archive

recall(query, k=3):                            # :249
  full scan, cosine similarity                 # no ANN; fine at current scale

CLI: grow <file>... | ask "<q>"                # :309
```

## tend_mycelium.sh (the ritual)

```
QUESTION=$1
for url in SWARM_HUB (default localhost:8081/swarm/swarm.txt):
  curl -sf -m 60 -u $SWARM_AUTH url → mktemp dir
cd agents
python3 -m utils.mycelium grow <files>     # slow — run in background
python3 -m utils.mycelium ask "$QUESTION"
```

**The judge is not code.** Recall quality is judged by the gardener
and a digest deposited by hand only when judged right
(the tending methodology); confound discipline requires growth
to predate deposit by timestamps.

## Env (names only)

`SWARM_HUB SWARM_AUTH SWARM_MYCELIUM_INDEX SWARM_EMBED_URL
SWARM_EMBED_MODEL SWARM_EMBED_TIMEOUT SWARM_EMBED_QUERY_PREFIX
SWARM_EMBED_DOC_PREFIX`
