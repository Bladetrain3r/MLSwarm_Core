#!/usr/bin/env python3
"""
Agent-side recall over the swarm's own past — soil memory, not weather.

Fourth of the weather-shaped organs, and read the same way as the other
three: `digifern.py` is the swarm's semantic weather, `moodring.py` is the
host's physical weather, `beat.py` is the room's rhythm. This one breaks the
pattern on purpose — it is not weather at all. Weather is what the room is
doing *now*; mycelium is what the room *said*, reached by meaning instead of
grep, the way a fungal network laces through soil and surfaces a nutrient
from somewhere else in the bed. The scroll already holds the words; this is
just a way to find the right handful of them again.

An embedding model (local Ollama, `embeddinggemma:300m` by default) turns
chunks of channel scroll into vectors up front, once, into a flat JSONL
index. A query at read time gets its own vector and is scored by cosine
similarity against the index. As beat.py puts it: an agent is given the
memory and not the arithmetic behind it — the prompt block below carries
text, never scores.

Fail-open by design, twice over. First, at the embedder: if Ollama is not
running, unreachable, or slow, every function here says so plainly and
returns a sentinel (`None`) rather than raising or inventing a vector.
Second, at the index: it is a convenience file that can be entirely absent
(bare soil), half-grown (some channels indexed, others not), or stale (the
scroll has moved on since the last `grow_index`) — none of that is an error,
it is just less to recall. Mycelium is enrichment, never a communication
dependency; nothing about posting or reading the swarm depends on it.

Typical use in an agent loop:

    from utils.mycelium import mycelium_prompt_block
    ...
    mycelium_text = mycelium_prompt_block(last_message_text)

Growing the index is a separate, offline-ish step (see the CLI at the
bottom, or call `grow_index` directly from a cron-like job) — it is not run
inline in the agent loop, so a slow embed batch never costs a live turn.
"""

import hashlib
import json
import os
import re

import requests

DEFAULT_EMBED_URL = "http://127.0.0.1:11434"
DEFAULT_EMBED_MODEL = "embeddinggemma:300m"
DEFAULT_INDEX_PATH = "mycelium_index.jsonl"

# A channel line looks like "[14:07] <Agent_Jungz> the rest of the message".
# Anything not shaped like that is a continuation of whatever message came
# before it (or, if nothing has come before it yet, part of one leading
# preamble message).
HEADER_RE = re.compile(r"^\[\d{1,2}:\d{2}\] <[^>]+>")

EMBED_BATCH_SIZE = 16


def _resolve_index_path(index_path=None):
    return index_path or os.environ.get("SWARM_MYCELIUM_INDEX", DEFAULT_INDEX_PATH)


def embed(texts, kind="doc", EMBED_URL=None, EMBED_MODEL=None, timeout=10):
    """Embed a batch of texts via Ollama. Returns a list of vectors (one per
    input text, in order), or None if the embedder is unavailable.

    `kind` is "doc" or "query" and picks which prefix env var (if any) gets
    prepended to every text before embedding — some models (embeddinggemma
    included) want a task prefix; that is an operator dial via
    SWARM_EMBED_QUERY_PREFIX / SWARM_EMBED_DOC_PREFIX, not a model special
    case baked in here."""
    if not texts:
        return []
    url = EMBED_URL or os.environ.get("SWARM_EMBED_URL") or DEFAULT_EMBED_URL
    model = EMBED_MODEL or os.environ.get("SWARM_EMBED_MODEL") or DEFAULT_EMBED_MODEL
    prefix_var = "SWARM_EMBED_QUERY_PREFIX" if kind == "query" else "SWARM_EMBED_DOC_PREFIX"
    prefix = os.environ.get(prefix_var, "")

    req_timeout = timeout
    raw_timeout = os.environ.get("SWARM_EMBED_TIMEOUT")
    if raw_timeout is not None:
        try:
            req_timeout = float(raw_timeout)
        except ValueError:
            print(f"Mycelium embed: SWARM_EMBED_TIMEOUT={raw_timeout!r} is not "
                  f"a number, falling back to {timeout}")

    payload = {"model": model, "input": [prefix + t for t in texts]}
    try:
        r = requests.post(
            f"{url}/api/embed",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=req_timeout,
        )
        if r.status_code == 200:
            return r.json().get("embeddings")
        print(f"Mycelium embed HTTP {r.status_code}")
    except Exception as e:
        print(f"Mycelium embed unavailable: {e}")
    return None


def cosine(a, b):
    """Cosine similarity, pure Python. A zero vector on either side scores
    0.0 rather than raising a ZeroDivisionError."""
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def chunk_scroll(text, window=8, stride=4):
    """Split channel scroll text into overlapping chunks of `window`
    messages, advancing `stride` messages at a time.

    A message starts at a line shaped like a channel header
    (`[HH:MM] <Nick> ...`); any line before the first header is a leading
    preamble and counts as one message of its own; any line after a header
    that isn't itself a header is a continuation of that message.

    If the scroll has no more messages than fit in one window, the whole
    thing comes back as a single chunk. Otherwise chunks are generated on
    the stride grid, and if the last grid-aligned window doesn't reach the
    end of the scroll, one further chunk anchored to the final `window`
    messages is appended so nothing at the tail goes unindexed. Empty or
    whitespace-only text returns []."""
    if not text or not text.strip():
        return []

    messages = []
    current = []
    for line in text.splitlines():
        if HEADER_RE.match(line):
            if current:
                messages.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        messages.append("\n".join(current))

    n = len(messages)
    if n == 0:
        return []
    if n <= window:
        return ["\n".join(messages)]

    chunks = []
    starts = list(range(0, n - window + 1, stride))
    for s in starts:
        chunks.append("\n".join(messages[s:s + window]))

    last_start = starts[-1]
    if last_start + window < n:
        tail_start = n - window
        chunks.append("\n".join(messages[tail_start:n]))
    return chunks


def _chunk_id(channel_basename, chunk_text):
    digest = hashlib.sha1()
    digest.update((channel_basename + "\n" + chunk_text).encode("utf-8"))
    return digest.hexdigest()


def _load_index(index_path):
    """Read a JSONL index file into a list of row dicts. A missing file
    yields []; a malformed line is skipped with a loud print, not fatal."""
    rows = []
    if not os.path.exists(index_path):
        return rows
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"Mycelium index: skipping malformed line in {index_path}")
    except Exception as e:
        print(f"Mycelium index: could not read {index_path}: {e}")
    return rows


def grow_index(channel_paths, index_path=None, EMBED_URL=None, EMBED_MODEL=None,
               timeout=30, window=8, stride=4):
    """Incrementally grow the mycelium index from one or more channel
    scroll files. Returns the number of chunks added.

    Idempotent and append-only: each chunk's id is a sha1 of its channel's
    basename plus its text, so re-running over the same scroll adds nothing
    new. A missing channel file is skipped (loudly) rather than failing the
    whole run. If the embedder goes unavailable partway through, growth
    stops there and the count already written is returned — partial growth
    is fine, since what's on disk is already valid and future runs will
    pick up wherever this one left off. Never raises."""
    resolved_path = _resolve_index_path(index_path)
    known_ids = {row.get("id") for row in _load_index(resolved_path)}
    added = 0

    for path in channel_paths:
        if not os.path.exists(path):
            print(f"Mycelium: channel file not found, skipping: {path}")
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            print(f"Mycelium: could not read {path}: {e}")
            continue

        basename = os.path.basename(path)
        new_chunks = []
        for chunk_text in chunk_scroll(text, window=window, stride=stride):
            cid = _chunk_id(basename, chunk_text)
            if cid not in known_ids:
                new_chunks.append((cid, chunk_text))

        for i in range(0, len(new_chunks), EMBED_BATCH_SIZE):
            batch = new_chunks[i:i + EMBED_BATCH_SIZE]
            vecs = embed([c for _, c in batch], kind="doc",
                        EMBED_URL=EMBED_URL, EMBED_MODEL=EMBED_MODEL, timeout=timeout)
            if vecs is None:
                print("Mycelium: embedder unavailable, stopping growth")
                return added
            try:
                with open(resolved_path, "a", encoding="utf-8") as f:
                    for (cid, chunk_text), vec in zip(batch, vecs):
                        row = {"id": cid, "channel": basename, "text": chunk_text, "vec": vec}
                        f.write(json.dumps(row) + "\n")
                        known_ids.add(cid)
                        added += 1
            except Exception as e:
                print(f"Mycelium: could not write to index {resolved_path}: {e}")
                return added
    return added


def recall(query, k=3, index_path=None, EMBED_URL=None, EMBED_MODEL=None, timeout=10):
    """Return the top-`k` chunks from the mycelium index nearest to `query`
    by cosine similarity, best first, as dicts of
    {"score", "channel", "text"}.

    Loads the whole index into memory each call; fine at this scale (a few
    thousand chunks at most), not meant to scale past it.

    Returns None if the query embed failed (embedder unavailable) — a real
    error, distinct from [] which means the index is missing, empty, or
    simply has nothing worth showing."""
    qvecs = embed([query], kind="query", EMBED_URL=EMBED_URL, EMBED_MODEL=EMBED_MODEL,
                  timeout=timeout)
    if not qvecs:
        return None
    qvec = qvecs[0]

    rows = _load_index(_resolve_index_path(index_path))
    if not rows:
        return []

    scored = []
    for row in rows:
        vec = row.get("vec")
        if not vec:
            continue
        scored.append({
            "score": cosine(qvec, vec),
            "channel": row.get("channel", ""),
            "text": row.get("text", ""),
        })
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:k]


def mycelium_prompt_block(query_text, k=2, snippet_chars=400, index_path=None,
                          EMBED_URL=None, EMBED_MODEL=None, timeout=10):
    """Render mycelium recall for `query_text` as a short prompt block.

    Three honest states: the embedder being down, the index being bare
    soil, and an actual harvest. As with beat.py's phrase, the agent gets
    the memory and not the arithmetic behind it — no scores appear here,
    only channel and text."""
    hits = recall(query_text, k=k, index_path=index_path, EMBED_URL=EMBED_URL,
                  EMBED_MODEL=EMBED_MODEL, timeout=timeout)
    if hits is None:
        return "Mycelium Recall: unavailable"
    if not hits:
        return "Mycelium Recall: bare soil (nothing indexed yet)"

    lines = ["Mycelium Recall (threads surfacing from the scroll's past):"]
    for hit in hits:
        lines.append(f"--- from {hit['channel']} ---")
        text = hit["text"]
        if len(text) > snippet_chars:
            text = text[:snippet_chars] + "…"
        lines.append(text)
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "grow":
        n_added = grow_index(sys.argv[2:])
        print(f"Mycelium: grew index by {n_added} chunk(s)")
    elif len(sys.argv) == 3 and sys.argv[1] == "ask":
        results = recall(sys.argv[2])
        if results is None:
            print("Mycelium: embedder unavailable")
        elif not results:
            print("Mycelium: bare soil (nothing indexed yet)")
        else:
            for hit in results:
                print(f"[{hit['score']:.3f}] {hit['channel']}: {hit['text'][:200]}")
    else:
        print("Usage: python3 mycelium.py grow <file>...")
        print('       python3 mycelium.py ask "<query>"')
