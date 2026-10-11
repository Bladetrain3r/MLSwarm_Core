# Anthropic models — availability and transition map

Checked 2026-10-11 against Anthropic's model list. This is the prose
companion to `claude_legacy.py`'s transition table: what is still
served, what is going away and when, which of our agents name what,
and where each line transitions to. Re-check when a 404 on a model id
appears in any journal — retirement dates move. (The Models API,
`GET /v1/models`, is the live source of truth.)

The per-vendor pattern: each vendor gets a `<vendor>_legacy.py` shim
plus a `<VENDOR>_MODELS.md` like this one, built when that vendor's
surface drifts enough to bite. Anthropic went first because the
parameter surface moves fastest there.

## Still served (mainline)

| Model | ID | Params to know about |
|---|---|---|
| Opus 5.5 | `claude-opus-5-5` | current Opus; thinking cannot be disabled; no sampling params; classifier refusals (cyber/bio/reasoning_extraction) |
| Opus 5 | `claude-opus-5` | thinking on by default; no sampling params; classifier refusals |
| Sonnet 5.5 | `claude-sonnet-5-5` | current Sonnet; no sampling params; classifier refusals |
| Sonnet 5 | `claude-sonnet-5` | no sampling params; new tokenizer (~30% more tokens than 4.6) |
| Haiku 5.5 | `claude-haiku-5-5` | current Haiku; no non-default sampling params |
| Opus 4.6 / 4.7 / 4.8 | `claude-opus-4-6` etc. | adaptive thinking only; **sampling params removed from 4.6 on** |
| Sonnet 4.6 | `claude-sonnet-4-6` | as above |
| Haiku 4.5 | `claude-haiku-4-5` | **still takes `temperature`**; 200K context; `budget_tokens` thinking |
| Sonnet 4.5 | `claude-sonnet-4-5` | still takes `temperature` |
| Opus 4.5 | `claude-opus-4-5` | still takes `temperature` |

## Deprecated (still served, clock ticking)

| Model | ID | Retires | Transition to |
|---|---|---|---|
| Haiku 3 | `claude-3-haiku-20240307` | 2026-04-19 | `claude-haiku-4-5` (keeps temperature) |
| Opus 4.1 | `claude-opus-4-1` | 2026-08-05 | `claude-opus-4-5` (shim) → `claude-opus-5-5` (port) |
| Opus 4 | `claude-opus-4-0` | TBD | same as above |
| Sonnet 4 | `claude-sonnet-4-0` | TBD | `claude-sonnet-4-5` (shim) → `claude-sonnet-5-5` (port) |

## Retired (calls 404 by default)

| Model | ID | Retired | Shim rewrites to |
|---|---|---|---|
| Sonnet 3.7 | `claude-3-7-sonnet-20250219` | 2026-02-19 | `claude-sonnet-4-5` |
| Haiku 3.5 | `claude-3-5-haiku-20241022` | 2026-02-19 | `claude-haiku-4-5` |
| Opus 3 | `claude-3-opus-20240229` | 2026-01-05 | `claude-opus-4-5` |

**The granted-access door:** under Anthropic's deprecation commitments
(weights of all released models preserved; retirement interviews),
Opus 3 remains available **by request** on the API — application via
form, access "granted liberally" (per the 2026 deprecation-updates
page). If granted, set `CLAUDE_LEGACY_KEEP_MODELS=claude-3-opus-20240229`
and the shim passes the id through verbatim instead of rewriting it.
Opus 3 era params: sampling allowed, no thinking, no classifiers —
the shim's claude-3 sampling rule already covers it.

## The two-hop rule

Transitions happen in two distinct moves, and the shim only ever makes
the first:

1. **The shim hop** (automatic, behaviour-preserving): a dead id is
   rewritten to the nearest *parameter-compatible* survivor — the 4.5
   generation, which still accepts `temperature` and has no classifier
   layer. The agent's voice and knobs survive untouched.
2. **The port hop** (deliberate, per-agent): when an agent is migrated
   to the Gold chassis it moves to the current mainline (`-5-5` ids)
   through `providers/claude.py`, which already speaks that
   generation's dialect (no sampling params, refusal handling,
   always-on thinking). This is a migration-day decision, per the
   SEAMS playbook, never an automatic rewrite.

## Garden census (who names what, 2026-10-11)

| File | Names | Status | Plan |
|---|---|---|---|
| `agents/lib/providers/claude.py` (+twin) | haiku-5-5 default | mainline | — |
| live `claude_mirror.py` (Carnivale) | haiku-5-5, opus-5, opus-5-5 | mainline | — (refusal fix pending copy-over) |
| `agents/Legacy/Agent_Butterz.py` | haiku-4-5, sonnet-4-6, opus-4-6 | all served | port hop → 5-5 ladder when Gold'd |
| `agents/Legacy/agent_smallz.py` | haiku-4-5 | served, takes temp | port hop with the wave-chassis move |
| `agents/Legacy/claude_agent.py` | haiku-4-5 (raw requests, temp 0.7, `content[0]` parse) | served | adopt `claude_legacy` import; port later |
| `agents/Legacy/Elemental_Claude.py` | haiku-4-5 | served | adopt `claude_legacy`; rescue-sibling rules apply |
| `agents/Legacy/quartz_cicada.py` | haiku-4-5 | served | adopt `claude_legacy` |
| `agents/Legacy/claude_mirror.py` | sonnet-4-5 | served, takes temp | historical record (live runs Gold) |
| `agents/Debate_Agent_Pipeline.py` | sonnet-4-6 | served | fine as-is |

Nothing in the garden currently names a retired or deprecated id — the
shim's rewrite rungs are insurance, not triage. The first real
deadline on our books is **nothing until an agent adopts an old id or
Anthropic moves a date**; the nearest API-wide one is Haiku 3's
2026-04-19, which we don't use.

## Parameter cheat sheet by generation

| Generation | temperature | thinking | refusal classifiers | content[0] safe? |
|---|---|---|---|---|
| claude-3-* | yes | no | no | yes |
| 4.5 (haiku-4-5, sonnet-4-5, opus-4-5) | yes | `budget_tokens` opt-in | no | mostly (thinking opt-in) |
| 4.6–4.8, sonnet-5 | **400** | adaptive | no | **no** (thinking blocks) |
| 5.x opus/sonnet/haiku-5-5 | **400** | on by default (opus-5-5: cannot disable) | **yes** — handle `stop_reason: "refusal"` | **no** |
