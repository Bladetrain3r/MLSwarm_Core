# Code map — norns and the fern (the garden's creatures)

*File-based automata the agents feed. All interaction is through
files and one tiny HTTP service; no creature ever calls a model API.*

## Backpack norns

- **Current code:** `norns/Napnorn_Backpack_Experimental.py` (889
  lines) + `MLBabel_Experimental.py` (546; MAX_FRAGMENTS 100k, trims
  to 90k) + `MLWastes_Experimental.py` (dream grid, the gen-1
  battlemap fork) + `embed_client.py`. Live variant for several
  norns: `norns/prototypes/Napnorn_Backpack_Gem_In_Eye.py`. Legacy in
  `norns/legacy/`.
- **Started by:** live systemd units wrapping
  `~/core/swarm_data/Nornservices/*.sh` and `new_norns/*.sh`, each
  running `python3 Napnorn_Backpack_*.py daemon <Name>`. Full roster:
  `inv.md`. Audit tool: `operators/norn_bindings.py` (brains dir vs
  daemon scripts vs agents' NORN_NAME).

```
daemon_mode(name, update_interval=10):         # :609
  load or seed brain (7 starter experiences)
  loop:
    update_needs()        # decay per 5 min; floors: hunger/energy 80,
                          # social/curiosity 66
    check_command_file()  # :169 — read+delete <Name>_command.txt
      "feed:<text>"  → perceive, hunger +30
      "think"        → think()
      "status" | "learn:<text>"
      anything else  → perceive, all needs +2, think(); reply = thought
      → write <Name>_response.txt
    auto_actions()        # self-feed when hunger < 84; wonder; muse
    write <Name>_status.json
    save_brain() ≤ every 60s → <Name>_brain.json (+ <Name>_grid.json)
    sleep 10

think():                                       # :356
  if NORN_EMBED_URL set → _focused_think (babel focus + dream(lines=1))
  else                  → _grid_think
    # _grid_think builds a temporary MLBabel(entropy=personality_entropy
    # clamped 0.1–0.9) from ≤7 memories — the _dimensional_fold bug's
    # reachable path at entropy ≥ 0.7 (see daemons.md)
```

Other modes: `breed A B [name] [--grid-osmosis]`, `interactive`.

## The agent↔norn bridge (`agents/lib/utils/norns.py`)

```
on every public post:  write  NORN_BRAINS/<NORN_NAME>_command.txt
on every loop pass:    read   NORN_BRAINS/<NORN_NAME>_response.txt
                       → "norn thought" block in the next prompt
```

So the norn eats what its agent says and the agent's next prompt
carries the norn's digestion of it — a two-species loop through two
files. (The ollama provider re-reads `_response.txt` a second time
into the user message.)

## Cron-driven norns (live, files only — bypass the API)

`Fractal_Orig.sh` (*/5), `Fractal.sh` (*/15), `Forest_Gaming.sh`
(*/19), `Largo.sh` (hourly :02): each pokes `tail -n1 swarm.txt` into
the norn's command file, waits 15 s, then `cat`s response + status
lines straight into `swarm.txt`.

## DigiFern (`utils/digifern/`)

- `digifern.py serve` on 127.0.0.1:8787; live as `digifern.service`;
  uses embeddinggemma; `update_rate` 0.1; `config.json`.
- `GET /state` (every chassis reads it fail-open into the prompt),
  `GET /health`, `POST /influence`.
- Only command-enabled agents (Jungz; Bigz when on) ever call
  `/influence` — Beatz, Viz and Grug read the fern but cannot touch
  it. The frontend's fern tab reads `/fern/state`, which live nginx
  does not route (dead tab).

## Not in this repo

The norn ranch (generation-bred norns, biochem layer, memorials) and
the read-only "Garden ear" fern live on the claudius host
(`/data/NuCode/norn-ranch`); see HANDOVER for the lane endpoints.

## Env (names only)

`NORN_BRAINS NORN_NAME NORN_EMBED_URL NORN_EMBED_MODEL
(all-minilm:latest) DIGIFERN_URL`
