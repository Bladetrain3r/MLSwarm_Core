#!/usr/bin/env python3
"""
Composting the swarm's own scrolls — the substrate maintaining itself.

The live channel file is surface litter: the part agents actually read,
freshly fallen and still legible line by line. Left alone it piles up
forever. `mycelium.py` is what keeps composted nutrients reachable after
they leave the surface — it does not care whether the text it indexes is
still sitting in the live scroll or has already gone under. This script is
the composting itself: when a scroll grows past a threshold, the old span
is turned under (archived to a flat file, folded into the mycelium index,
summarised into a rolling history book) and the live file is trimmed back
to a manageable tail. Nothing is lost — it just moves from litter to soil,
which is where nutrients belong once they're no longer needed on top.

This is autopoiesis, not housekeeping performed on the swarm from outside:
the swarm producing and maintaining its own memory substrate is part of
what it means for this thing to be a self-sustaining habitat rather than a
log file with agents attached (see ORIENTATION.md §1). No agent needs to
know this script exists; a scroll simply never grows without bound, and the
past it sheds stays recallable through mycelium and readable through the
chapter books.

Order of operations per scroll is load-bearing, not stylistic — see the
comments at each step. Composting is meant to be safe to re-run: a scroll
that dies mid-composting (crash, killed process, dead network) can be run
again and either resumes cleanly or reports the exact failure, never a
silent double-archive or a truncated live scroll.

CLI:
    python3 compost.py [--dry-run] [--force] SCROLL [SCROLL...]

Each SCROLL is a live channel file (e.g. general.txt). Scrolls are
composted independently — one scroll's failure aborts only that scroll,
and the process exits nonzero if any scroll failed.
"""

import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
import urllib.error

DEFAULT_THRESHOLD = 150_000
DEFAULT_KEEP = 10_000
DEFAULT_OLLAMA = "http://127.0.0.1:11434"
DEFAULT_MODEL = "swarm_gemma:latest"
DEFAULT_BITE_LINES = 300
DEFAULT_MAX_BITES = 48
DEFAULT_SUMMARY_TIMEOUT = 180

# A message-boundary header, matched against raw bytes: "[HH:MM] <Nick> text".
# The bracket body is intentionally permissive (`[^\]]*`) because a rare
# malformed header shows up in the wild as "[] <Odd> ..." — an empty
# timestamp is still a real message boundary, just not a parsable one.
HEADER_RE = re.compile(rb"^\[[^\]]*\] <[^>]+> ")

# A parsable timestamp specifically, for span reporting only (HH:MM).
# Malformed headers like "[] <Odd>" are real boundaries but carry no time
# to report, so this is stricter than HEADER_RE on purpose.
TIMESTAMP_RE = re.compile(rb"^\[(\d{1,2}:\d{2})\]")


def _env_int(name, default):
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"compost: {name}={raw!r} is not an integer")


def _env_float(name, default):
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        raise SystemExit(f"compost: {name}={raw!r} is not a number")


def find_boundary(lines, start):
    """Scan forward from `start` for the first line shaped like a message
    header, so a trimmed tail never opens mid-message. Returns the index,
    or None if nothing from `start` to the end of `lines` matches — a
    scroll can legitimately be one giant unbroken message near the cut,
    and that's a loud-abort case rather than a guess."""
    for i in range(start, len(lines)):
        if HEADER_RE.match(lines[i]):
            return i
    return None


def find_timestamp(lines, forward=True):
    """First (forward) or last (not forward) parsable [HH:MM] in `lines`,
    or None if the span has no clean timestamp at all (e.g. it's entirely
    the "[] <Odd>" malformed header, or continuation lines)."""
    rng = range(len(lines)) if forward else range(len(lines) - 1, -1, -1)
    for i in rng:
        m = TIMESTAMP_RE.match(lines[i])
        if m:
            return m.group(1).decode("ascii")
    return None


def ollama_generate(prompt, ollama_url, model, timeout):
    """One blocking call to Ollama's /api/generate, non-streaming. Returns
    the response text, or raises — callers in the chapter step (the one
    fail-open stage) are responsible for catching."""
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        f"{ollama_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    text = body.get("response", "").strip()
    if not text:
        raise ValueError("Ollama returned an empty response")
    return text


def sample_bites(span_lines, bite_lines, max_bites):
    """Pick up to `max_bites` evenly spaced windows of `bite_lines` lines
    across `span_lines`. Returns a list of (start, end) index pairs. If the
    whole span fits in fewer windows than max_bites, every window is used
    (no padding to max_bites) — sampling density backs off gracefully on
    short spans instead of overlapping windows pointlessly."""
    total = len(span_lines)
    if total == 0:
        return []
    n_windows = max(1, -(-total // bite_lines))  # ceil division
    n_bites = min(max_bites, n_windows)
    if n_bites <= 1:
        return [(0, min(bite_lines, total))]
    windows = []
    step = (total - bite_lines) / (n_bites - 1) if total > bite_lines else 0
    for i in range(n_bites):
        start = int(round(i * step))
        start = max(0, min(start, total - 1))
        end = min(start + bite_lines, total)
        windows.append((start, end))
    return windows


def summarise_span(span_lines, ollama_url, model, bite_lines, max_bites, timeout):
    """Summarise a composted span into a 2-3 paragraph chapter. Raises on
    any summariser failure (dead Ollama, timeout, bad response) — the
    caller treats this whole stage as fail-open and writes a placeholder
    chapter instead, so raising here is the correct, expected path when
    the model is unavailable, not a bug to suppress internally."""
    windows = sample_bites(span_lines, bite_lines, max_bites)
    bite_summaries = []
    for start, end in windows:
        text = b"\n".join(span_lines[start:end]).decode("utf-8", errors="replace")
        prompt = (
            "The following is a stretch of a multi-agent chat log. Nicknames "
            "in <angle brackets> identify who said what. In 2-3 plain-prose "
            "sentences, summarise what happened in this stretch — keep the "
            "nicks, skip the play-by-play.\n\n" + text
        )
        bite_summaries.append(ollama_generate(prompt, ollama_url, model, timeout))

    if len(bite_summaries) == 1:
        return bite_summaries[0]

    rollup_prompt = (
        "The following are short summaries of consecutive stretches of the "
        "same multi-agent chat log, in order. Turn them into a single "
        "flowing chapter, 2-3 paragraphs, plain prose, keeping nicknames. "
        "Don't just list the stretches — tell it as one passage of time.\n\n"
        + "\n\n".join(f"- {s}" for s in bite_summaries)
    )
    return ollama_generate(rollup_prompt, ollama_url, model, timeout)


def compost_one(scroll_path, args):
    """Compost a single scroll. Returns True on success (including the
    below-threshold no-op and the dry-run preview), False on abort.
    Prints its own report; never raises past this function — every failure
    mode is caught here and turned into a loud, specific message."""
    name = os.path.basename(scroll_path)
    if name.endswith(".txt"):
        base = name[:-4]
    else:
        base = name

    if not os.path.isfile(scroll_path):
        print(f"compost: {name}: no such file")
        return False

    # Step 1: read as bytes. Scrolls carry corruption glyphs from the wire;
    # decoding here would be lossy on the surgery path (the archive/trim
    # byte-copy must reproduce the file exactly), so this stays bytes end
    # to end. Decoding only happens later, per-bite, for the LLM prompt.
    try:
        raw = open(scroll_path, "rb").read()
    except OSError as e:
        print(f"compost: {name}: could not read: {e}")
        return False

    lines = raw.split(b"\n")
    # A trailing empty element after the file's final newline is not a
    # line — splitting "a\nb\n" gives ["a", "b", ""].
    trailing_newline = len(lines) > 0 and lines[-1] == b""
    if trailing_newline:
        lines = lines[:-1]
    total_lines = len(lines)

    # Step 2: threshold check.
    if not args.force and total_lines < args.threshold:
        print(f"compost: {name} below threshold ({total_lines} < {args.threshold}), soil undisturbed")
        return True

    compost_dir = args.compost_dir_for(scroll_path)

    # Step 3: find the cut. Scan forward from the naive target so the kept
    # tail always opens on a real message boundary, never mid-message.
    target = max(0, total_lines - args.keep)
    cut = find_boundary(lines, target)
    if cut is None:
        print(f"compost: {name}: no message boundary found from line {target} to end of file, aborting")
        return False

    span = lines[:cut]
    kept = lines[cut:]
    span_lines_n = len(span)
    kept_lines_n = len(kept)
    first_ts = find_timestamp(span, forward=True)
    last_ts = find_timestamp(span, forward=False)

    if args.dry_run:
        print(f"compost: {name} (dry-run)")
        print(f"  would compost {span_lines_n} lines, keep {kept_lines_n} "
              f"(target keep {args.keep}, cut adjusted by {cut - target} lines)")
        print(f"  span [{first_ts or '?'}]..[{last_ts or '?'}]")
        print(f"  archive -> {os.path.join(compost_dir, base + '.archive.txt')}")
        print(f"  book    -> {os.path.join(compost_dir, base + '_book.md')}")
        return True

    try:
        os.makedirs(compost_dir, exist_ok=True)
    except OSError as e:
        print(f"compost: {name}: could not create compost dir {compost_dir}: {e}")
        return False

    span_bytes = b"\n".join(span)

    # Step 6, done BEFORE archiving on purpose: mycelium's index is
    # sha1-deduped on (channel basename, chunk text), so growing it twice
    # over the same span is a no-op. Archiving is a raw byte-append with no
    # such dedup. If we archived first and then died before indexing, a
    # retry would re-append the same span to the archive and corrupt it
    # (or need its own dedup logic); doing mycelium first means a retry
    # after a crash here just re-grows the index for free and nothing has
    # touched the archive or the live scroll yet.
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = os.path.join(tmpdir, name)  # same basename: index source label matches the channel
            with open(temp_path, "wb") as f:
                f.write(span_bytes)
            repo_agents_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents")
            if repo_agents_dir not in sys.path:
                sys.path.insert(0, repo_agents_dir)
            from utils.mycelium import embed, grow_index
            # grow_index is deliberately fail-open in its own right (see its
            # docstring: "Never raises") — an unreachable embedder makes it
            # print a warning and hand back the count already written, same
            # shape of return as a fully-idempotent no-op retry. Composting
            # needs to tell those two apart (one is "nothing to do", the
            # other is "wrong loudly"), so probe the embedder directly
            # first; grow_index's own return value is not a reliable
            # failure signal here. A probe-then-grow race (embedder dies
            # in between) remains, same tolerance as the trim race below.
            if embed(["compost mycelium probe"], kind="doc") is None:
                raise RuntimeError("mycelium embedder unavailable")
            chunks_added = grow_index([temp_path], index_path=args.index_path)
    except Exception as e:
        print(f"compost: {name}: mycelium indexing failed, aborting before touching archive or live scroll: {e}")
        return False

    # Step 7: archive. Append-then-verify: record the pre-append size, add
    # the span, flush+fsync so the bytes are actually on disk, then reopen
    # and re-read exactly the delta we just wrote and hash it against the
    # span's own hash. Any mismatch means the append is suspect (partial
    # write, disk issue) and we stop with the live scroll still untouched
    # rather than trim against an archive we can't trust.
    archive_path = os.path.join(compost_dir, base + ".archive.txt")
    span_sha = hashlib.sha256(span_bytes).hexdigest()
    try:
        old_size = os.path.getsize(archive_path) if os.path.exists(archive_path) else 0
        with open(archive_path, "ab") as f:
            f.write(span_bytes + b"\n")
            f.flush()
            os.fsync(f.fileno())
        with open(archive_path, "rb") as f:
            f.seek(old_size)
            delta = f.read(len(span_bytes))
        if hashlib.sha256(delta).hexdigest() != span_sha:
            print(f"compost: {name}: archive verification failed after append, aborting (live scroll untouched)")
            return False
    except OSError as e:
        print(f"compost: {name}: archive write/verify failed: {e}")
        return False

    # Step 8: trim, with a late-arrival recheck. Between step 1's read and
    # now, an agent may have appended fresh lines to the live scroll; if we
    # blindly overwrote with `kept` we'd eat them. Re-read and, if the file
    # grew past the byte length we snapshotted, tack the extra bytes onto
    # the tail we're about to write. A tiny race remains regardless — a
    # write landing between this re-read and the os.replace below is still
    # possible, exactly as it was for the old rotate.sh split-based
    # rotation this replaces. Run compost at quiet hours.
    try:
        current = open(scroll_path, "rb").read()
    except OSError as e:
        print(f"compost: {name}: could not re-read live scroll before trim: {e}")
        return False
    kept_bytes = b"\n".join(kept)
    if trailing_newline:
        kept_bytes += b"\n"
    if len(current) > len(raw):
        kept_bytes += current[len(raw):]

    scroll_dir = os.path.dirname(os.path.abspath(scroll_path)) or "."
    try:
        fd, tmp_path = tempfile.mkstemp(dir=scroll_dir, prefix="." + name + ".compost-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(kept_bytes)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, scroll_path)
        except Exception:
            os.unlink(tmp_path)
            raise
    except OSError as e:
        print(f"compost: {name}: trim failed: {e}")
        return False

    # Step 9: chapter — the one fail-open stage. A summarising failure
    # (Ollama down, timeout, bad output) does NOT undo steps 6-8; the span
    # is already safe in the archive and reachable via mycelium, so the
    # compost has already succeeded. Losing the chapter loses only prose.
    date_str = time.strftime("%Y-%m-%d")
    n_windows = len(sample_bites(span, args.bite_lines, args.max_bites))
    header = (f"## Chapter — {date_str} — {span_lines_n} lines composted "
              f"(span [{first_ts or '?'}]…[{last_ts or '?'}], "
              f"sampled {n_windows} of {-(-span_lines_n // args.bite_lines) if span_lines_n else 0} windows)")
    chapter_written = True
    try:
        chapter_text = summarise_span(span, args.ollama_url, args.model, args.bite_lines,
                                       args.max_bites, args.summary_timeout)
    except Exception as e:
        chapter_text = "_Chapter unwritten — summarizer unavailable. The span rests whole in the archive; the mycelium reaches it._"
        chapter_written = False
        print(f"compost: {name}: chapter summariser unavailable ({e}), archived without prose")

    book_path = os.path.join(compost_dir, base + "_book.md")
    try:
        with open(book_path, "a", encoding="utf-8") as f:
            f.write(header + "\n\n" + chapter_text + "\n\n")
    except OSError as e:
        # The chapter is enrichment on top of an already-successful compost;
        # failing to write it is reported but does not flip this to failure.
        print(f"compost: {name}: could not write chapter to {book_path}: {e}")

    print(f"compost: {name}: composted {span_lines_n} lines, kept {kept_lines_n}, "
          f"archive={archive_path}, mycelium+{chunks_added}, "
          f"chapter={'written' if chapter_written else 'unwritten'}")
    return True


class Args:
    """Resolved CLI + env configuration, gathered in one place instead of
    passed as a dozen loose parameters."""

    def __init__(self, dry_run, force, scrolls):
        self.dry_run = dry_run
        self.force = force
        self.scrolls = scrolls
        self.threshold = _env_int("SWARM_COMPOST_THRESHOLD", DEFAULT_THRESHOLD)
        self.keep = _env_int("SWARM_COMPOST_KEEP", DEFAULT_KEEP)
        self.ollama_url = os.environ.get("SWARM_COMPOST_OLLAMA", DEFAULT_OLLAMA)
        self.model = os.environ.get("SWARM_COMPOST_MODEL", DEFAULT_MODEL)
        self.bite_lines = _env_int("SWARM_COMPOST_BITE_LINES", DEFAULT_BITE_LINES)
        self.max_bites = _env_int("SWARM_COMPOST_MAX_BITES", DEFAULT_MAX_BITES)
        self.summary_timeout = _env_float("SWARM_COMPOST_SUMMARY_TIMEOUT", DEFAULT_SUMMARY_TIMEOUT)
        # SWARM_MYCELIUM_INDEX is only defaulted here if unset; when set it
        # is passed straight through to grow_index untouched, per its own
        # env-or-argument resolution in mycelium.py. `index_path` itself is
        # filled in per-scroll by main(), since its default depends on
        # which scroll's compost dir is in play.
        self._index_path_env = os.environ.get("SWARM_MYCELIUM_INDEX")
        self.index_path = None

    def compost_dir_for(self, scroll_path):
        env_dir = os.environ.get("SWARM_COMPOST_DIR")
        if env_dir:
            return env_dir
        return os.path.join(os.path.dirname(os.path.abspath(scroll_path)), "compost")


def main():
    argv = sys.argv[1:]
    dry_run = "--dry-run" in argv
    force = "--force" in argv
    unknown = [a for a in argv if a.startswith("--") and a not in ("--dry-run", "--force")]
    if unknown:
        raise SystemExit(f"compost: unknown flag(s): {' '.join(unknown)}")
    scrolls = [a for a in argv if not a.startswith("--")]

    if not scrolls:
        print("Usage: python3 compost.py [--dry-run] [--force] SCROLL [SCROLL...]")
        sys.exit(2)

    args = Args(dry_run, force, scrolls)

    any_failed = False
    for scroll_path in scrolls:
        # Resolve the mycelium index path per-scroll: default is inside
        # that scroll's own compost dir unless SWARM_MYCELIUM_INDEX pins
        # one location for every scroll processed in this run.
        compost_dir = args.compost_dir_for(scroll_path)
        args.index_path = args._index_path_env or os.path.join(compost_dir, "mycelium.jsonl")
        try:
            ok = compost_one(scroll_path, args)
        except Exception as e:
            # Belt and braces: compost_one is written to catch everything
            # itself, but a scroll's failure must never take down the rest
            # of the batch, so nothing escapes this loop uncaught.
            print(f"compost: {os.path.basename(scroll_path)}: unexpected error: {e}")
            ok = False
        if not ok:
            any_failed = True

    sys.exit(1 if any_failed else 0)


if __name__ == "__main__":
    main()
