#!/usr/bin/env python3
"""
Swarm BBS — Core Module
All BBS operations live here. CLI and API both import from this.
Stdlib only. Filesystem-based. Debuggable with cat.
"""

import json
import os
import time
import hashlib
import fcntl
from pathlib import Path
from contextlib import contextmanager

# --- Config ---
DEFAULT_ROOT    = Path(os.environ.get("BBS_ROOT", "bbs_data"))
MAX_ACTIVE      = int(os.environ.get("BBS_MAX_ACTIVE", 10))
POST_CAP        = int(os.environ.get("BBS_POST_CAP", 30))
PAGE_SIZE       = int(os.environ.get("BBS_PAGE_SIZE", 5))

# --- Roles ---
ROLES = {
    "admin":        {"list", "read", "post", "create", "summary_read", "summary_write",
                     "summary_custom", "collapse", "promote", "archive", "pin", "unpin",
                     "delete", "fork"},
    "documenter":   {"list", "read", "post", "create", "summary_read", "summary_write",
                     "summary_custom", "collapse", "promote", "archive", "fork"},
    "poster":       {"list", "read", "post", "create", "summary_read", "fork"},
    "observer":     {"list", "read", "summary_read"},
}

# --- Locking ---

@contextmanager
def file_lock(lock_path):
    """Advisory lock via fcntl. Creates .lock file, blocks until acquired."""
    lock_path = Path(str(lock_path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fp = open(lock_path, "w")
    try:
        fcntl.flock(fp, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fp, fcntl.LOCK_UN)
        fp.close()

# --- Filesystem Helpers ---

def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return None

def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2))

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def make_thread_id(title):
    ts = str(int(time.time() * 1000))
    h  = hashlib.sha1((title + ts).encode()).hexdigest()[:6]
    return f"{ts}_{h}"

# --- Bootstrap ---

def ensure_dirs(root=None):
    root = Path(root or DEFAULT_ROOT)
    for d in ["threads", "index", "summaries", "artifacts"]:
        (root / d).mkdir(parents=True, exist_ok=True)
    for idx in ["active", "locked", "archived", "pinned"]:
        p = root / "index" / f"{idx}.json"
        if not p.exists():
            save_json(p, [])
    return root

# --- Index Operations ---

def _load_index(root, status):
    return load_json(root / "index" / f"{status}.json") or []

def _save_index(root, status, ids):
    save_json(root / "index" / f"{status}.json", ids)

def _add_to_active(root, tid):
    with file_lock(root / "index" / "active.json"):
        ids = _load_index(root, "active")
        if tid not in ids:
            ids.insert(0, tid)
            while len(ids) > MAX_ACTIVE:
                old = ids.pop()
                _move_index(root, old, "active", "locked")
            _save_index(root, "active", ids)

def _move_index(root, tid, src, dst):
    """Move thread between indexes. Caller must hold appropriate locks."""
    for s in [src, dst]:
        p = root / "index" / f"{s}.json"
        if not p.exists():
            save_json(p, [])
    s_ids = _load_index(root, src)
    d_ids = _load_index(root, dst)
    if tid in s_ids:
        s_ids.remove(tid)
        _save_index(root, src, s_ids)
    if tid not in d_ids:
        d_ids.insert(0, tid)
        _save_index(root, dst, d_ids)

def resolve_shorthand(root, ref):
    """If ref is a small integer, resolve to active thread ID. Otherwise return as-is."""
    try:
        idx = int(ref)
        if idx < 100:  # plausible index number, not a timestamp prefix
            active = _load_index(root, "active")
            if 1 <= idx <= len(active):
                return active[idx - 1]
            return None  # out of range
    except ValueError:
        pass
    return ref

# --- Thread Operations ---

def list_topics(root, status="active"):
    ids = _load_index(root, status)
    result = []
    for tid in ids:
        meta = load_json(root / "threads" / tid / "meta.json")
        if meta:
            result.append(meta)
    return result

def read_thread(root, tid, page=1):
    thread_dir = root / "threads" / tid
    meta = load_json(thread_dir / "meta.json")
    if not meta:
        return None
    posts_dir  = thread_dir / "posts"
    post_files = sorted(posts_dir.glob("*.json")) if posts_dir.exists() else []
    start = (page - 1) * PAGE_SIZE
    end   = start + PAGE_SIZE
    posts = [p for p in (load_json(f) for f in post_files[start:end]) if p]
    return {
        "meta":        meta,
        "posts":       posts,
        "page":        page,
        "total_posts": len(post_files),
        "has_more":    end < len(post_files),
    }

def create_thread(root, author, title, body, thread_type="discussion"):
    tid = make_thread_id(title)
    thread_dir = root / "threads" / tid
    (thread_dir / "posts").mkdir(parents=True, exist_ok=True)
    ts = now_iso()
    meta = {
        "id": tid, "title": title, "author": author,
        "created": ts, "status": "active", "type": thread_type,
        "post_count": 1, "pinned": False,
    }
    save_json(thread_dir / "meta.json", meta)
    save_json(thread_dir / "posts" / "0001.json", {
        "author": author, "timestamp": ts, "body": body,
    })
    _add_to_active(root, tid)
    return tid, meta

def post_to_thread(root, tid, author, body):
    thread_dir = root / "threads" / tid
    with file_lock(thread_dir / "meta.json"):
        meta = load_json(thread_dir / "meta.json")
        if not meta:
            return None, "thread not found"
        if meta.get("status") != "active":
            return None, "thread is locked"
        if meta.get("pinned") and meta.get("type") == "pinned":
            return None, "pinned threads are read-only (use admin to update)"

        posts_dir = thread_dir / "posts"
        posts_dir.mkdir(exist_ok=True)
        count = meta.get("post_count", 0) + 1
        save_json(posts_dir / f"{count:04d}.json", {
            "author": author, "timestamp": now_iso(), "body": body,
        })
        meta["post_count"] = count
        if count >= POST_CAP:
            meta["status"] = "locked"
        save_json(thread_dir / "meta.json", meta)

    # Move index outside thread lock to avoid nested locks
    if meta["status"] == "locked":
        with file_lock(root / "index" / "active.json"):
            _move_index(root, tid, "active", "locked")

    return count, meta["status"]

def delete_thread(root, tid):
    """Permanent deletion. Removes thread dir and all index references."""
    import shutil
    thread_dir = root / "threads" / tid
    if not thread_dir.exists():
        return False, "thread not found"
    shutil.rmtree(thread_dir)
    # Remove from all indexes
    for status in ["active", "locked", "archived", "pinned"]:
        with file_lock(root / "index" / f"{status}.json"):
            ids = _load_index(root, status)
            if tid in ids:
                ids.remove(tid)
                _save_index(root, status, ids)
    # Remove summary if exists
    summary_path = root / "summaries" / f"{tid}.txt"
    if summary_path.exists():
        summary_path.unlink()
    return True, "deleted"

def archive_thread(root, tid):
    thread_dir = root / "threads" / tid
    meta = load_json(thread_dir / "meta.json")
    if not meta:
        return False, "thread not found"
    # Find which index it's currently in
    for status in ["active", "locked"]:
        with file_lock(root / "index" / f"{status}.json"):
            ids = _load_index(root, status)
            if tid in ids:
                _move_index(root, tid, status, "archived")
                break
    meta["status"] = "archived"
    save_json(thread_dir / "meta.json", meta)
    return True, "archived"

def fork_thread(root, author, parent_tid, title, body):
    """Create new thread with reference to parent."""
    parent_meta = load_json(root / "threads" / parent_tid / "meta.json")
    if not parent_meta:
        return None, "parent thread not found"
    fork_body = f"[forked from: {parent_tid} — \"{parent_meta['title']}\"]\n\n{body}"
    tid, meta = create_thread(root, author, title, fork_body, thread_type="discussion")
    return tid, meta

# --- Pinned Threads ---

def pin_thread(root, tid):
    thread_dir = root / "threads" / tid
    meta = load_json(thread_dir / "meta.json")
    if not meta:
        return False, "thread not found"
    # Remove from active/locked if present
    for status in ["active", "locked"]:
        with file_lock(root / "index" / f"{status}.json"):
            ids = _load_index(root, status)
            if tid in ids:
                ids.remove(tid)
                _save_index(root, status, ids)
    # Add to pinned
    with file_lock(root / "index" / "pinned.json"):
        pinned = _load_index(root, "pinned")
        if tid not in pinned:
            pinned.insert(0, tid)
            _save_index(root, "pinned", pinned)
    meta["pinned"] = True
    meta["type"]   = "pinned"
    meta["status"] = "active"  # pinned threads stay "active" but outside the cap
    save_json(thread_dir / "meta.json", meta)
    return True, "pinned"

def unpin_thread(root, tid):
    thread_dir = root / "threads" / tid
    meta = load_json(thread_dir / "meta.json")
    if not meta:
        return False, "thread not found"
    with file_lock(root / "index" / "pinned.json"):
        pinned = _load_index(root, "pinned")
        if tid in pinned:
            pinned.remove(tid)
            _save_index(root, "pinned", pinned)
    meta["pinned"] = False
    meta["type"]   = "discussion"
    save_json(thread_dir / "meta.json", meta)
    _add_to_active(root, tid)
    return True, "unpinned — moved to active"

# --- Summaries ---

def get_summary(root, tid):
    p = root / "summaries" / f"{tid}.txt"
    return p.read_text() if p.exists() else None

def write_summary(root, tid, text):
    (root / "summaries").mkdir(exist_ok=True)
    (root / "summaries" / f"{tid}.txt").write_text(text)
    return True

# --- Artifacts ---

def promote_to_artifact(root, source_tid, title, artifact_type, author, content):
    aid = f"art_{make_thread_id(title)}"
    artifact = {
        "id":            aid,
        "source_thread": source_tid,
        "title":         title,
        "type":          artifact_type,
        "author":        author,
        "created":       now_iso(),
        "content":       content,
        "canonical":     True,
    }
    save_json(root / "artifacts" / f"{aid}.json", artifact)
    return aid, artifact

def list_artifacts(root):
    arts = []
    art_dir = root / "artifacts"
    for f in sorted(art_dir.glob("*.json")):
        a = load_json(f)
        if a:
            arts.append(a)
    return arts

def read_artifact(root, aid):
    return load_json(root / "artifacts" / f"{aid}.json")

# --- Collapse ---

def collapse_threads(root, tids, author):
    """Merge multiple threads into a single new thread with combined content."""
    bodies = []
    titles = []
    for tid in tids:
        meta = load_json(root / "threads" / tid / "meta.json")
        if not meta:
            return None, f"thread {tid} not found"
        titles.append(meta["title"])
        posts_dir = root / "threads" / tid / "posts"
        post_files = sorted(posts_dir.glob("*.json")) if posts_dir.exists() else []
        for pf in post_files:
            p = load_json(pf)
            if p:
                bodies.append(f"[{p['author']} @ {p['timestamp']}]\n{p['body']}")

    combined_title = f"Collapsed: {' + '.join(t[:30] for t in titles)}"
    combined_body  = f"[collapsed from: {', '.join(tids)}]\n\n" + "\n\n---\n\n".join(bodies)

    new_tid, new_meta = create_thread(root, author, combined_title, combined_body)

    # Archive the originals
    for tid in tids:
        archive_thread(root, tid)

    return new_tid, new_meta
