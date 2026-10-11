#!/usr/bin/env python3
"""
Sediment — where the live swarm's litter settles into something a backup
can trust.

The live channel files (and norn brains, and agent state) sit on a tmpfs:
fast, and free for the norns' constant writes, but gone the moment the box
reboots and unreadable mid-write for anything that wants a clean copy. That
surface is litter — freshly fallen, still being trampled. `compost.py`
turns litter into soil on the same filesystem, folding old spans under so
the live scroll stays manageable. This script does something adjacent but
different: it settles a whole snapshot of the tmpfs down onto persistent
disk, in layers (generations), so that a backup job or a restart can read
sediment — a settled layer, never a file mid-write — instead of reaching
into the live litter and risking a torn read.

Each flush lays down one generation: a self-contained directory tree that
either exists complete or doesn't exist at all (see FLUSH mechanics in
`flush_one` — the incoming/promote split is the load-bearing part). Each
file type gets handled for the way it actually gets written: `.txt`
scrolls are append-only, so reading exactly the byte length stat() reports
and trimming back to the last full line is enough to guarantee a clean cut
even if an agent is mid-append. `.json` state files are rewritten in place
by their owners, which is the one shape of write a size-then-read snapshot
can't defend against — a reader can land between truncate and write and
see a half-written file — so those get validated and, if invalid, salvaged
from the previous generation rather than carried forward broken. (The real
fix for rewrite-in-place is atomic writes at the source — write to a temp
path and os.replace() over the target — which is a separate small change
to the norn/state-writing code, same ticket as this file: 0ad388bd.)
Everything else is opaque and gets copied byte for byte, on the theory that
nothing this script doesn't understand should be edited by it.

Restore is the mirror operation, for boot: copy the newest (or a named)
generation back onto an empty tmpfs. It refuses a non-empty target without
--force, because an empty LIVE_DIR is what boot looks like and a non-empty
one is what a running swarm looks like — clobbering a live swarm has to be
asked for by name.

CLI:
    python3 sediment.py flush   LIVE_DIR SEDIMENT_DIR
    python3 sediment.py restore SEDIMENT_DIR LIVE_DIR [--force] [--generation TS]

DIALS (env):
    SWARM_SEDIMENT_KEEP=24   promoted generations retained by flush's prune step.
"""

import json
import os
import shutil
import sys
import time

DEFAULT_KEEP = 24
STALE_INCOMING_SECONDS = 24 * 60 * 60


def _env_int(name, default):
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"sediment: {name}={raw!r} is not an integer")


def _iter_live_files(live_dir):
    """Walk LIVE_DIR recursively, yielding (abs_path, rel_path) for every
    regular file. Symlinks are skipped entirely (a snapshot should not
    follow a link off into who-knows-where), and so are dotfiles/dot-dirs
    (runtime scratch, lockfiles, editor droppings — not swarm state).
    Directories are walked in sorted order so flush output is deterministic
    enough to eyeball."""
    for root, dirs, files in os.walk(live_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if name.startswith("."):
                continue
            abs_path = os.path.join(root, name)
            if os.path.islink(abs_path):
                continue
            if not os.path.isfile(abs_path):
                continue
            rel_path = os.path.relpath(abs_path, live_dir)
            yield abs_path, rel_path


def _carry_stat(src_path, dst_path):
    """Carry mode + timestamps from src onto dst, best-effort. The live
    host's crontab executes tmpfs scripts DIRECTLY (`./Fractal.sh`) — a
    generation that restores as 0644 kills those crons with permission
    denied, quietly. Best-effort because the source can vanish between
    the copy and this stat (norn command files come and go); a lost stat
    carry is never a reason to fail a flush."""
    try:
        shutil.copystat(src_path, dst_path)
    except OSError:
        pass


def _copy_scroll(src_path, dst_path, report):
    """*.txt scrolls are append-only, so a size-then-read snapshot is safe
    from truncation but not from a message appended between the stat() and
    the read finishing — that lands as a partial final line, not partial
    file corruption. Stat the size FIRST and never read past it: reading
    more risks catching a write in progress that started after we decided
    how much to copy. Trim back to the last full line; the trimmed tail
    reappears whole on the next flush."""
    size = os.stat(src_path).st_size
    with open(src_path, "rb") as f:
        data = f.read(size)
    if data and not data.endswith(b"\n"):
        cut = data.rfind(b"\n")
        if cut == -1:
            # No newline at all: this is a tiny file mid-first-write.
            # Copying it as-is is harmless — there's no "last full line"
            # to cut back to, and next flush will see the completed file.
            pass
        else:
            data = data[: cut + 1]
            report["trims"] += 1
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, "wb") as f:
        f.write(data)
    _carry_stat(src_path, dst_path)
    return len(data)


def _copy_json(src_path, rel_path, dst_path, latest_dir, report):
    """*.json files are rewritten in place by their owners (norn/agent
    state) — the one write pattern a stat-then-read snapshot cannot defend
    against, since a reader can land between the writer's truncate and its
    rewrite and see a half-written (or empty) file. Read, validate with
    json.loads, and on failure retry once (the writer may simply have
    finished by then). Still invalid: salvage the same relative path from
    the current `latest` generation if one exists there — loudly, since a
    stale-but-valid copy silently replacing a live file is exactly the kind
    of thing that should never happen quietly. No previous copy to salvage
    from: skip the file, also loudly. Either way this never fails the
    flush — validation is advisory, not a reason to abort a whole snapshot
    over one norn's bad luck."""
    for attempt in range(2):
        try:
            with open(src_path, "rb") as f:
                data = f.read()
            json.loads(data)
        except (OSError, ValueError):
            if attempt == 0:
                continue
            salvage_src = os.path.join(latest_dir, rel_path) if latest_dir else None
            if salvage_src and os.path.isfile(salvage_src):
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copyfile(salvage_src, dst_path)
                _carry_stat(salvage_src, dst_path)
                size = os.path.getsize(dst_path)
                print(f"sediment: WARNING: {rel_path}: invalid JSON, salvaged from latest generation")
                report["salvages"] += 1
                return size
            print(f"sediment: WARNING: {rel_path}: invalid JSON and no previous generation to salvage from, skipping")
            report["skips"] += 1
            return None
        else:
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            with open(dst_path, "wb") as f:
                f.write(data)
            _carry_stat(src_path, dst_path)
            return len(data)
    return None  # unreachable, but explicit


def _copy_opaque(src_path, dst_path):
    """Everything else — norn brains and the like — is opaque to this
    script: a single read, copied as-is. These are rewrite-in-place files
    too (same hazard as .json), but without a schema to validate against
    there's nothing to check; the real cure, same as for .json, is atomic
    writes at the source (tmp + os.replace), a separate change under the
    same ticket (0ad388bd)."""
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    shutil.copyfile(src_path, dst_path)
    _carry_stat(src_path, dst_path)
    return os.path.getsize(dst_path)


def _resolve_latest(sediment_dir):
    """Return the absolute target of SEDIMENT_DIR/latest if it exists and
    resolves to a real directory, else None. Used both for salvage lookups
    during flush and for restore's default source."""
    latest_link = os.path.join(sediment_dir, "latest")
    if not os.path.islink(latest_link) and not os.path.exists(latest_link):
        return None
    target = os.path.realpath(latest_link)
    if not os.path.isdir(target):
        return None
    return target


def flush_one(live_dir, sediment_dir, keep):
    """Lay down one generation. Mechanics (why this order matters):

    1. Copy everything into SEDIMENT_DIR/incoming.<timestamp>/, a name
       nothing else in this script (or compost, or a backup job) ever
       looks at while it's still "incoming.*".
    2. os.rename() the whole tree to SEDIMENT_DIR/<timestamp>/ once every
       file has landed. Rename within the same directory is atomic on a
       POSIX filesystem, so this is the single instant a generation goes
       from "doesn't exist yet" to "exists complete" — there is no
       observable half-promoted state. A crash before this line leaves an
       orphaned incoming.* dir; a crash after leaves a complete generation.
       Either way nothing downstream (restore, a backup job) ever sees a
       generation that's only partly there.
    3. Point `latest` at the new generation via a RELATIVE symlink, written
       under a temp name and os.replace()'d over the old `latest` — the
       same tmp-then-replace shape as compost's own trim step, for the same
       reason: a symlink update should never be observable half-done.
       Relative so the whole SEDIMENT_DIR tree stays portable if it's ever
       copied or mounted somewhere else.
    4. Prune: keep the newest `keep` promoted generations, delete the rest;
       also sweep any incoming.* older than 24h, which can only be crash
       wreckage from an interrupted flush (a live flush finishes step 2 in
       well under that).
    5. Report.
    """
    if not os.path.isdir(live_dir):
        raise SystemExit(f"sediment: flush: no such directory: {live_dir}")
    os.makedirs(sediment_dir, exist_ok=True)

    latest_dir = _resolve_latest(sediment_dir)

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    incoming_name = f"incoming.{ts}"
    incoming_dir = os.path.join(sediment_dir, incoming_name)
    if os.path.exists(incoming_dir):
        raise SystemExit(f"sediment: flush: {incoming_dir} already exists (two flushes in the same second?)")
    os.makedirs(incoming_dir)

    report = {"files": 0, "bytes": 0, "trims": 0, "salvages": 0, "skips": 0}

    for src_path, rel_path in _iter_live_files(live_dir):
        dst_path = os.path.join(incoming_dir, rel_path)
        if rel_path.endswith(".txt"):
            n = _copy_scroll(src_path, dst_path, report)
        elif rel_path.endswith(".json"):
            n = _copy_json(src_path, rel_path, dst_path, latest_dir, report)
            if n is None:
                continue
        else:
            n = _copy_opaque(src_path, dst_path)
        report["files"] += 1
        report["bytes"] += n

    # Step 2: promote. Atomic rename within SEDIMENT_DIR.
    generation_dir = os.path.join(sediment_dir, ts)
    os.rename(incoming_dir, generation_dir)

    # Step 3: repoint `latest`, atomically.
    latest_link = os.path.join(sediment_dir, "latest")
    tmp_link = os.path.join(sediment_dir, f".latest.tmp.{ts}")
    if os.path.lexists(tmp_link):
        os.unlink(tmp_link)
    os.symlink(ts, tmp_link)  # relative — just the generation's own name
    os.replace(tmp_link, latest_link)

    # Step 4: prune old generations and stale incoming.* wreckage.
    pruned = _prune(sediment_dir, keep)

    print(f"sediment: flush {ts}: {report['files']} files, {report['bytes']} bytes, "
          f"{report['trims']} trims, {report['salvages']} salvages, {report['skips']} skips, "
          f"{pruned} generations pruned")
    return report


def _prune(sediment_dir, keep):
    """Delete promoted generations beyond the newest `keep`, and any
    incoming.* directory older than 24h (only reachable via a flush that
    crashed between steps 1 and 2 above). Returns the number of promoted
    generations deleted."""
    entries = os.listdir(sediment_dir)
    generations = sorted(
        e for e in entries
        if os.path.isdir(os.path.join(sediment_dir, e)) and _is_generation_name(e)
    )
    to_delete = generations[:-keep] if keep > 0 else generations
    for name in to_delete:
        shutil.rmtree(os.path.join(sediment_dir, name), ignore_errors=True)

    now = time.time()
    for e in entries:
        if not e.startswith("incoming."):
            continue
        path = os.path.join(sediment_dir, e)
        try:
            age = now - os.stat(path).st_mtime
        except OSError:
            continue
        if age > STALE_INCOMING_SECONDS:
            shutil.rmtree(path, ignore_errors=True)

    return len(to_delete)


def _is_generation_name(name):
    """A promoted generation's name is exactly the flush timestamp:
    YYYYMMDD_HHMMSS. Guards prune against sweeping up anything else that
    might live in SEDIMENT_DIR (a stray directory, `latest` itself — which
    is a symlink, not a dir, so isdir() already excludes it — etc.)."""
    if len(name) != 15 or name[8] != "_":
        return False
    return name[:8].isdigit() and name[9:].isdigit()


def restore_one(sediment_dir, live_dir, force, generation):
    """Copy one generation back onto LIVE_DIR, for boot. Source is
    SEDIMENT_DIR/latest unless --generation names a specific promoted
    generation. Refuses a non-empty LIVE_DIR without --force: an empty
    tmpfs is what boot looks like, and clobbering a directory that isn't
    empty means something is already running there — that has to be asked
    for by name, not assumed. --force overwrites files that already exist
    at their target path but never deletes anything not present in the
    generation being restored."""
    if generation:
        if not _is_generation_name(generation):
            raise SystemExit(f"sediment: restore: not a generation name: {generation!r}")
        source_dir = os.path.join(sediment_dir, generation)
        if not os.path.isdir(source_dir):
            raise SystemExit(f"sediment: restore: no such generation: {generation}")
        label = generation
    else:
        source_dir = _resolve_latest(sediment_dir)
        if source_dir is None:
            raise SystemExit(f"sediment: restore: {sediment_dir}/latest is missing or broken")
        label = os.path.basename(source_dir)

    if os.path.isdir(live_dir) and os.listdir(live_dir) and not force:
        raise SystemExit(f"sediment: restore: {live_dir} is not empty (use --force to restore into a running swarm)")

    os.makedirs(live_dir, exist_ok=True)

    files = 0
    total_bytes = 0
    for root, dirs, filenames in os.walk(source_dir):
        dirs.sort()
        rel_root = os.path.relpath(root, source_dir)
        for name in sorted(filenames):
            src_path = os.path.join(root, name)
            rel_path = name if rel_root == "." else os.path.join(rel_root, name)
            dst_path = os.path.join(live_dir, rel_path)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copyfile(src_path, dst_path)
            _carry_stat(src_path, dst_path)
            files += 1
            total_bytes += os.path.getsize(dst_path)

    print(f"sediment: restore {label}: {files} files, {total_bytes} bytes")
    return files, total_bytes


def main():
    argv = sys.argv[1:]
    usage = (
        "Usage: python3 sediment.py flush   LIVE_DIR SEDIMENT_DIR\n"
        "       python3 sediment.py restore SEDIMENT_DIR LIVE_DIR [--force] [--generation TS]"
    )

    if not argv:
        print(usage)
        sys.exit(2)

    cmd, rest = argv[0], argv[1:]

    if cmd == "flush":
        unknown = [a for a in rest if a.startswith("--")]
        if unknown:
            raise SystemExit(f"sediment: unknown flag(s): {' '.join(unknown)}")
        positional = [a for a in rest if not a.startswith("--")]
        if len(positional) != 2:
            print(usage)
            sys.exit(2)
        live_dir, sediment_dir = positional
        keep = _env_int("SWARM_SEDIMENT_KEEP", DEFAULT_KEEP)
        flush_one(live_dir, sediment_dir, keep)

    elif cmd == "restore":
        force = "--force" in rest
        generation = None
        positional = []
        i = 0
        unknown = []
        while i < len(rest):
            a = rest[i]
            if a == "--force":
                i += 1
            elif a == "--generation":
                if i + 1 >= len(rest):
                    raise SystemExit("sediment: --generation requires a value")
                generation = rest[i + 1]
                i += 2
            elif a.startswith("--"):
                unknown.append(a)
                i += 1
            else:
                positional.append(a)
                i += 1
        if unknown:
            raise SystemExit(f"sediment: unknown flag(s): {' '.join(unknown)}")
        if len(positional) != 2:
            print(usage)
            sys.exit(2)
        sediment_dir, live_dir = positional
        restore_one(sediment_dir, live_dir, force, generation)

    else:
        print(usage)
        sys.exit(2)


if __name__ == "__main__":
    main()
