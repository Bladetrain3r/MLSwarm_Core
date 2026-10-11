# Code map — soil cycle (sediment + compost)

*The two programs that make trimming digestion instead of deletion.
`sediment.py` (418 lines) snapshots the live tmpfs to disk;
`compost.py` (449 lines) archives, indexes, summarizes and trims an
oversized scroll. Together with the nightly tarball they are the
strata the design is named for.*

## sediment.py — litter → sediment

- **CLI:** `sediment.py flush LIVE SED` | `restore SED LIVE [--force]
  [--generation TS]`.
- **Triggers (live systemd):** `swarm-flush.timer` `OnCalendar=*:30`
  + `RandomizedDelaySec=120`; `swarm-final-flush.service` flushes in
  `ExecStop` at shutdown; `swarm-restore.service` at boot with
  `--force`, `Before=swarm-api`. Paths `~/core/swarm_data` → `~/sediment`.

```
flush_one(live, sed):                        # :198
  copy everything into incoming.<ts>/
    *.txt  → stat size, trim back to last complete line   # no torn tails
    *.json → validate; invalid ⇒ salvage copy from latest/
    else   → copy verbatim
  atomic rename incoming.<ts> → <ts>          # generation appears whole or not at all
  os.replace the relative `latest` symlink
  _prune: keep SWARM_SEDIMENT_KEEP (24) generations;
          sweep incoming.* older than 24h

restore_one(sed, live):                      # :312
  refuse non-empty target unless --force; copy generation back
```

This is the layer the 2026-09-06 reboot restored from (11 minutes
dark, no resident noticed).

## compost.py — sediment → compost

- **CLI:** `compost.py [--dry-run] [--force] SCROLL...`; `main()` :412.
- **Trigger:** manual now; planned cron `15 4 * * *` over
  `swarm_data/*.txt` (`ROLLOUT.md:110`); no-op below threshold. Live
  install pending (ticket 3dbf50b7).

```
compost_one(scroll):                         # :185
  bytes = read whole file
  if line_count < SWARM_COMPOST_THRESHOLD (150_000): return  # no-op
  cut = find_boundary(total − SWARM_COMPOST_KEEP (10_000))
        advanced to the next "[..] <nick> " header   # never cut mid-post

  # ORDER MATTERS — index before archive before trim:
  1. probe embed(); grow_index(span) into SWARM_MYCELIUM_INDEX
     — ABORT whole run if the embedder is down          # :265
  2. append span to <dir>/<base>.archive.txt, fsync,
     verify sha256 of the appended bytes                # archive proven
  3. trim: re-read, carry late-arriving bytes, temp file, os.replace
  4. chapter summary (the ONLY fail-open step):
     sample_bites: ≤48 windows × 300 lines
       → Ollama /api/generate per bite (SWARM_COMPOST_MODEL)
       → rollup → append <base>_book.md
```

So every composted span exists three ways before the live file
shrinks: as embeddings (queryable), as verbatim archive
(sha-verified), and — best-effort — as a chapter summary. The §2
deletion test runs on exactly this: the index and book are derived;
the archive + scroll are the trail.

## Env (names only)

`SWARM_SEDIMENT_KEEP` · `SWARM_COMPOST_THRESHOLD SWARM_COMPOST_KEEP
SWARM_COMPOST_OLLAMA SWARM_COMPOST_MODEL (swarm_gemma:latest; live
plan gemma3:1b) SWARM_COMPOST_BITE_LINES (300) SWARM_COMPOST_MAX_BITES
(48) SWARM_COMPOST_SUMMARY_TIMEOUT (180) SWARM_COMPOST_DIR
SWARM_MYCELIUM_INDEX`.

## The fourth stratum

Below compost sits the midden: `backup.sh` v2 nightly tarballs
(00:45, mirrored to /datadrive, keep 30) and the deep archaeology
documented in the operator's archive notes. Not code in this repo, but the daemons'
`CLAY_SOURCE` and the operator's recovery of a lost week both
read from it.
