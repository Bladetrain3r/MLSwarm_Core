#!/usr/bin/env python3
"""
Swarm BBS — CLI Client v2
Imports all operations from bbs_core. No duplicate logic.

Usage:
    python3 bbs_client.py --path /path/to/bbs_data --author alice
    python3 bbs_client.py  (uses BBS_ROOT env var or ./bbs_data)
"""

# Note: Sort out imports before moving this to clients since it can be run as __main__ for the moment.
# import sys
# from pathlib import Path
import argparse
import os
from core import bbs_core as bbs

# --- Display ---

def hr(char="─", width=64):
    print(char * width)

def show_topics(topics, status, show_index=False):
    hr("═")
    label = f"  📌 PINNED" if status == "pinned" else f"  THREADS [{status.upper()}]"
    print(label)
    hr("═")
    if not topics:
        print(f"  (no {status} threads)")
        return
    for i, t in enumerate(topics, 1):
        lock   = " 🔒" if t.get("status") == "locked" else ""
        pin    = " 📌" if t.get("pinned") else ""
        ttype  = t.get("type", "discussion")
        prefix = f"  [{i:2d}]" if show_index else "     "
        print(f"{prefix} [{t.get('post_count', 0):3d}] {t.get('title','')[:42]}{lock}{pin}")
        print(f"        id: {t['id']}")
        print(f"        by: {t.get('author','')}  on: {t.get('created','')[:10]}  type: {ttype}")

def show_thread(result):
    meta  = result["meta"]
    posts = result["posts"]
    page  = result["page"]
    total = result["total_posts"]
    pin   = " 📌" if meta.get("pinned") else ""
    hr("═")
    print(f"  {meta.get('title','')}{pin}  [{meta.get('status','').upper()}]")
    print(f"  {total} posts | page {page} | type: {meta.get('type','discussion')}")
    print(f"  id: {meta['id']}")
    hr("═")
    offset = (page - 1) * bbs.PAGE_SIZE
    for i, p in enumerate(posts, start=offset + 1):
        print(f"\n  [{i:03d}] {p.get('author','')} @ {p.get('timestamp','')}")
        hr("─")
        for line in p.get("body", "").split("\n"):
            print(f"  {line}")
    if result["has_more"]:
        print(f"\n  ─── more on page {page + 1}  (r <id> {page + 1}) ───")

def show_artifacts(artifacts):
    hr("═")
    print("  ARTIFACTS")
    hr("═")
    if not artifacts:
        print("  (no artifacts)")
        return
    for a in artifacts:
        canon = " [CANONICAL]" if a.get("canonical") else ""
        print(f"  {a['title']}{canon}")
        print(f"     id: {a['id']}  type: {a.get('type','')}  from: {a.get('source_thread','')[:20]}")

def print_help():
    hr("═")
    print("  SWARM BBS")
    hr("═")
    print()
    print("  Navigation")
    print("    l                 Active threads (index numbers shown)")
    print("    ll                Locked threads")
    print("    la                Archived threads")
    print("    lp                Pinned threads")
    print("    r <id> [page]     Read thread (active: index # ok)")
    print("    s <id>            View summary")
    print("    arts              List artifacts")
    print("    art <id>          Read artifact")
    print()
    print("  Writing")
    print("    p <id>            Post to thread (active: index # ok)")
    print("    n                 New thread")
    print("    n memory          New memory thread")
    print("    fork <id>         Fork a thread")
    print()
    print("  Management")
    print("    c <id>            Write custom summary")
    print("    pin <id>          Pin thread")
    print("    unpin <id>        Unpin thread")
    print("    archive <id>      Archive thread")
    print("    o <id> <id> ...   Collapse threads")
    print("    promote <id>      Promote thread to artifact")
    print("    d <id>            Delete thread (PERMANENT, full ID required)")
    print()
    print("  Other")
    print("    h                 This help")
    print("    q                 Quit")
    print()
    print("  Active threads accept index # (from 'l') in place of full ID.")
    print("  Delete always requires full ID.")

# --- Input Helpers ---

def multiline_input(prompt=""):
    if prompt:
        print(prompt)
    print("  (end with '.' on its own line)")
    lines = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            return None
        if line.strip() == ".":
            break
        lines.append(line)
    text = "\n".join(lines).strip()
    return text if text else None

def confirm(msg):
    try:
        return input(f"  {msg} (y/N): ").strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        return False

# --- Resolve ID (shorthand for active threads) ---

def resolve(root, ref, allow_shorthand=True):
    if not allow_shorthand:
        return ref
    resolved = bbs.resolve_shorthand(root, ref)
    if resolved is None:
        print(f"  [error] index #{ref} out of range — use 'l' to see active threads")
    return resolved

# --- Command Dispatch ---

def cmd_list(root, parts):
    cmd = parts[0].lower()
    if cmd == "ll":
        show_topics(bbs.list_topics(root, "locked"), "locked")
    elif cmd == "la":
        show_topics(bbs.list_topics(root, "archived"), "archived")
    elif cmd == "lp":
        show_topics(bbs.list_topics(root, "pinned"), "pinned")
    else:
        show_topics(bbs.list_topics(root, "active"), "active", show_index=True)

def cmd_read(root, parts):
    if len(parts) < 2:
        print("  [usage] r <id> [page]")
        return
    tid = resolve(root, parts[1])
    if not tid:
        return
    page = int(parts[2]) if len(parts) > 2 else 1
    result = bbs.read_thread(root, tid, page)
    if result is None:
        print("  [error] thread not found")
    else:
        show_thread(result)

def cmd_post(root, parts, author):
    if len(parts) < 2:
        print("  [usage] p <id>")
        return
    tid = resolve(root, parts[1])
    if not tid:
        return
    body = multiline_input(f"  Posting to thread:")
    if not body:
        print("  [cancelled]")
        return
    count, status = bbs.post_to_thread(root, tid, author, body)
    if count is None:
        print(f"  [error] {status}")
    else:
        print(f"  [ok] post #{count} | status: {status}")

def cmd_new(root, parts, author):
    ttype = "discussion"
    if len(parts) > 1 and parts[1].lower() == "memory":
        ttype = "memory"
        print("  Creating memory thread.")
    title = input("  Title: ").strip()
    if not title:
        print("  [cancelled]")
        return
    if ttype == "memory" and not title.startswith("Memory:"):
        title = f"Memory: {title}"
    body = multiline_input("  Opening post:")
    if not body:
        print("  [cancelled]")
        return
    tid, meta = bbs.create_thread(root, author, title, body, thread_type=ttype)
    print(f"  [ok] created: {tid} (type: {ttype})")

def cmd_fork(root, parts, author):
    if len(parts) < 2:
        print("  [usage] fork <id>")
        return
    parent = resolve(root, parts[1])
    if not parent:
        return
    title = input("  Fork title: ").strip()
    if not title:
        print("  [cancelled]")
        return
    body = multiline_input("  Opening post:")
    if not body:
        print("  [cancelled]")
        return
    tid, meta = bbs.fork_thread(root, author, parent, title, body)
    if tid is None:
        print(f"  [error] {meta}")
    else:
        print(f"  [ok] forked: {tid}")

def cmd_summary(root, parts):
    if len(parts) < 2:
        print("  [usage] s <id>")
        return
    tid = resolve(root, parts[1])
    if not tid:
        return
    summary = bbs.get_summary(root, tid)
    if summary:
        hr("═")
        print("  SUMMARY")
        hr("═")
        for line in summary.split("\n"):
            print(f"  {line}")
    else:
        print("  [info] no summary available")

def cmd_custom_summary(root, parts):
    if len(parts) < 2:
        print("  [usage] c <id>")
        return
    tid = resolve(root, parts[1])
    if not tid:
        return
    text = multiline_input("  Write summary:")
    if not text:
        print("  [cancelled]")
        return
    bbs.write_summary(root, tid, text)
    print("  [ok] summary saved")

def cmd_pin(root, parts):
    if len(parts) < 2:
        print("  [usage] pin <id>")
        return
    tid = resolve(root, parts[1])
    if not tid:
        return
    ok, msg = bbs.pin_thread(root, tid)
    print(f"  [{'ok' if ok else 'error'}] {msg}")

def cmd_unpin(root, parts):
    if len(parts) < 2:
        print("  [usage] unpin <id>")
        return
    # No shorthand for pinned — use full ID
    ok, msg = bbs.unpin_thread(root, parts[1])
    print(f"  [{'ok' if ok else 'error'}] {msg}")

def cmd_archive(root, parts):
    if len(parts) < 2:
        print("  [usage] archive <id>")
        return
    tid = resolve(root, parts[1])
    if not tid:
        return
    ok, msg = bbs.archive_thread(root, tid)
    print(f"  [{'ok' if ok else 'error'}] {msg}")

def cmd_delete(root, parts):
    if len(parts) < 2:
        print("  [usage] d <thread_id>  (full ID required)")
        return
    tid = parts[1]
    # Safety: reject shorthand
    try:
        if int(tid) < 100:
            print("  [error] delete requires full thread ID, not index number")
            return
    except ValueError:
        pass
    meta = bbs.load_json(root / "threads" / tid / "meta.json")
    if not meta:
        print("  [error] thread not found")
        return
    print(f"  Thread: {meta.get('title','')}")
    print(f"  Posts:  {meta.get('post_count', 0)}")
    if not confirm("PERMANENTLY delete this thread?"):
        print("  [cancelled]")
        return
    ok, msg = bbs.delete_thread(root, tid)
    print(f"  [{'ok' if ok else 'error'}] {msg}")

def cmd_collapse(root, parts, author):
    if len(parts) < 3:
        print("  [usage] o <id1> <id2> [id3 ...]")
        return
    tids = []
    for ref in parts[1:]:
        tid = resolve(root, ref)
        if not tid:
            return
        tids.append(tid)
    print(f"  Collapsing {len(tids)} threads:")
    for tid in tids:
        meta = bbs.load_json(root / "threads" / tid / "meta.json")
        if meta:
            print(f"    - {meta.get('title','')}")
    if not confirm("Collapse and archive originals?"):
        print("  [cancelled]")
        return
    new_tid, result = bbs.collapse_threads(root, tids, author)
    if new_tid is None:
        print(f"  [error] {result}")
    else:
        print(f"  [ok] collapsed into: {new_tid}")

def cmd_promote(root, parts, author):
    if len(parts) < 2:
        print("  [usage] promote <id>")
        return
    tid = resolve(root, parts[1])
    if not tid:
        return
    meta = bbs.load_json(root / "threads" / tid / "meta.json")
    if not meta:
        print("  [error] thread not found")
        return
    print(f"  Promoting from: {meta.get('title','')}")
    title = input("  Artifact title: ").strip()
    if not title:
        print("  [cancelled]")
        return
    atype = input("  Type (code/spec/manifesto/reference/other) [other]: ").strip() or "other"
    print("  Content to promote (paste or write, end with '.'):")
    content = multiline_input()
    if not content:
        print("  [cancelled]")
        return
    aid, art = bbs.promote_to_artifact(root, tid, title, atype, author, content)
    print(f"  [ok] artifact created: {aid}")

def cmd_artifacts(root, parts):
    if len(parts) >= 2 and parts[0] == "art":
        art = bbs.read_artifact(root, parts[1])
        if not art:
            print("  [error] artifact not found")
            return
        hr("═")
        canon = " [CANONICAL]" if art.get("canonical") else ""
        print(f"  {art['title']}{canon}")
        print(f"  type: {art.get('type','')}  from: {art.get('source_thread','')}")
        print(f"  by: {art.get('author','')}  on: {art.get('created','')[:10]}")
        hr("═")
        for line in art.get("content", "").split("\n"):
            print(f"  {line}")
    else:
        show_artifacts(bbs.list_artifacts(root))

# --- Main Dispatch ---

def dispatch(raw, root, author):
    parts = raw.split()
    cmd = parts[0].lower()

    if cmd in ("l", "ll", "la", "lp"):
        cmd_list(root, parts)
    elif cmd == "r":
        cmd_read(root, parts)
    elif cmd == "p":
        cmd_post(root, parts, author)
    elif cmd == "n":
        cmd_new(root, parts, author)
    elif cmd == "fork":
        cmd_fork(root, parts, author)
    elif cmd == "s":
        cmd_summary(root, parts)
    elif cmd == "c":
        cmd_custom_summary(root, parts)
    elif cmd == "pin":
        cmd_pin(root, parts)
    elif cmd == "unpin":
        cmd_unpin(root, parts)
    elif cmd == "archive":
        cmd_archive(root, parts)
    elif cmd == "d":
        cmd_delete(root, parts)
    elif cmd == "o":
        cmd_collapse(root, parts, author)
    elif cmd == "promote":
        cmd_promote(root, parts, author)
    elif cmd in ("arts", "art"):
        cmd_artifacts(root, parts)
    elif cmd == "h":
        print_help()
    else:
        print(f"  [unknown] '{cmd}' — h for help")

# --- REPL ---

def repl(root, author):
    hr("═")
    print(f"  Swarm BBS v2")
    print(f"  root: {root.resolve()}")
    print(f"  author: {author}")
    hr("═")
    print("  h for help\n")

    # Show active + pinned on startup
    pinned = bbs.list_topics(root, "pinned")
    if pinned:
        show_topics(pinned, "pinned")
    active = bbs.list_topics(root, "active")
    show_topics(active, "active", show_index=True)

    while True:
        try:
            raw = input("\nbbs> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Exiting.")
            break
        if not raw:
            continue
        if raw.lower() == "q":
            print("  Exiting.")
            break
        dispatch(raw, root, author)

# --- Entrypoint ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Swarm BBS Client v2")
    parser.add_argument("--path",   default=os.environ.get("BBS_ROOT", "bbs_data"), help="BBS data directory")
    parser.add_argument("--author", default=os.environ.get("BBS_AUTHOR", "zero"),   help="Your handle")
    args = parser.parse_args()

    root = bbs.ensure_dirs(args.path)
    repl(root, args.author)
