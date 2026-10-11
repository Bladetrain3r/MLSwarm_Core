"""Legacy Anthropic provider -- keeps old agents' Claude calls working as the
API's parameter surface shifts under them.

The Gold provider (`providers/claude.py`) tracks the current mainline and has
dropped what the current models reject (temperature, small ceilings). Legacy
agents predate those shifts: they pass `temperature`, name old model ids, and
some parse `content[0]['text']`. This module is the shim that lets them keep
their behaviour without each file re-learning the API:

- model ids are passed through a transition table: retired ids are rewritten
  to the nearest still-served, parameter-compatible model (loudly); deprecated
  ids go through unchanged but warn with their retirement date;
- `temperature` is sent only to generations that still accept it (claude-3*
  and the 4.5 generation); the 4.6+ family rejects all sampling params;
- classifier refusals (stop_reason "refusal", Opus 5.x) return None without
  posting partial output;
- text extraction skips thinking/tool blocks instead of trusting content[0].

Drop-in for the raw-requests clade: same call shape as the Gold provider, but
built on `requests` (their existing dependency) rather than the SDK, so no
agent gains a dependency by adopting it. One import line changes:

    from providers.claude_legacy import get_claude_response

The sibling per-vendor shims (gpt_legacy, gemini_legacy, grok_legacy) follow
this pattern as their vendors' surfaces drift. The prose companion with the
full availability list is ANTHROPIC_MODELS.md next to this file.
"""

import os

try:
    import requests
    _HAVE_REQUESTS = True
except ImportError:
    requests = None
    _HAVE_REQUESTS = False

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

# Transition table, checked against Anthropic's model list 2026-10-11.
# status "retired": the id 404s -- rewrite to `target` (nearest still-served
# model that accepts the same parameters, NOT necessarily the newest).
# status "deprecated": still served -- send as-is, warn with the date.
MODEL_TRANSITIONS = {
    # retired (the call would fail)
    "claude-3-opus-20240229":     ("retired 2026-01-05", "claude-opus-4-5"),
    "claude-3-5-haiku-20241022":  ("retired 2026-02-19", "claude-haiku-4-5"),
    "claude-3-7-sonnet-20250219": ("retired 2026-02-19", "claude-sonnet-4-5"),
    "claude-3-5-sonnet-20240620": ("retired", "claude-sonnet-4-5"),
    "claude-3-5-sonnet-20241022": ("retired", "claude-sonnet-4-5"),
    # deprecated (still served; the warning names the deadline)
    "claude-3-haiku-20240307":    ("deprecated, retires 2026-04-19", None),
    "claude-opus-4-1":            ("deprecated, retires 2026-08-05", None),
    "claude-opus-4-0":            ("deprecated, retirement TBD", None),
    "claude-sonnet-4-0":          ("deprecated, retirement TBD", None),
}

# Generations that still accept sampling parameters. Everything from 4.6 on
# rejects non-default temperature/top_p/top_k with a 400.
_SAMPLING_OK_PREFIXES = (
    "claude-3",
    "claude-opus-4-5", "claude-opus-4-1", "claude-opus-4-0",
    "claude-sonnet-4-5", "claude-sonnet-4-0",
    "claude-haiku-4-5",
)


def _normalize_model(model):
    """Map a legacy model id through the transition table. Returns the id to
    actually send, printing loudly when it rewrites or the id is deprecated.

    CLAUDE_LEGACY_KEEP_MODELS (comma-separated ids) exempts models from
    rewriting -- the door for retired models Anthropic has granted back by
    request (e.g. Opus 3, see ANTHROPIC_MODELS.md)."""
    keep = os.environ.get("CLAUDE_LEGACY_KEEP_MODELS", "")
    if model in {m.strip() for m in keep.split(",") if m.strip()}:
        print(f"Claude legacy: model '{model}' kept verbatim "
              "(CLAUDE_LEGACY_KEEP_MODELS -- granted-access door).")
        return model
    status, target = MODEL_TRANSITIONS.get(model, (None, None))
    if status is None:
        return model
    if target:
        print(f"Claude legacy: model '{model}' is {status}; using '{target}' "
              "(nearest parameter-compatible survivor -- see ANTHROPIC_MODELS.md).")
        return target
    print(f"Claude legacy: model '{model}' is {status}; plan its transition "
          "(see ANTHROPIC_MODELS.md).")
    return model


def _sampling_allowed(model):
    return any(model.startswith(p) for p in _SAMPLING_OK_PREFIXES)


def _extract_text(content_blocks):
    """Concatenate text blocks from a Messages response body. Robust to
    thinking/tool blocks arriving first -- the content[0]['text'] of the
    raw-requests clade breaks on exactly those."""
    parts = []
    for block in content_blocks or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts).strip()


def get_claude_response(context, claudemodel="claude-haiku-4-5", sysprompt="Respond from the soul.",
                        apikey="None", GENRE="Default", LASTCOMMAND="None",
                        NORN_BRAINS="None", NORN_NAME="None",
                        max_tokens=4500, temperature=0.7, timeout=60):
    """Legacy-shaped Claude call. Same prompt construction as the Gold
    provider so a utils-cohort agent can swap imports with no behaviour
    change; honours `temperature` where the model still takes it. Returns
    the text, or None on any failure (fail-open, wrong-loudly)."""
    # Explicit Norn support (same as the Gold provider).
    if os.path.isfile(f"{NORN_BRAINS}/{NORN_NAME}_response.txt"):
        with open(f"{NORN_BRAINS}/{NORN_NAME}_response.txt", "r") as nornsponse:
            sendit = f"Recent Norn Thoughts: {str(nornsponse.read())}"
            print(sendit)
    else:
        sendit = "\n"

    prompt = f"""
        Your most recent response is: {LASTCOMMAND}
        Your current leaning is: {GENRE}

        {sendit}

        Below is the recent conversational logs from the swarm,  which any public posts will append to.
        {context}

==========CONTEXT ENDS==========

Based on the recent conversation, contribute as you see fit, bearing in mind brevity.
"""

    if not _HAVE_REQUESTS:
        print("requests not installed; skipping Claude legacy call.")
        return None

    key = apikey if apikey and apikey != "None" else os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("No Anthropic API key (arg or ANTHROPIC_API_KEY); skipping Claude legacy call.")
        return None

    model = _normalize_model(claudemodel)
    data = {
        "model": model,
        "max_tokens": max_tokens,
        "system": sysprompt,
        "messages": [{"role": "user", "content": prompt}],
    }
    if temperature is not None and _sampling_allowed(model):
        data["temperature"] = temperature

    headers = {
        "x-api-key": key,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }

    try:
        response = requests.post(API_URL, headers=headers, json=data, timeout=timeout)
    except Exception as e:
        print(f"Error calling Claude API (legacy): {e}")
        return None

    if response.status_code != 200:
        print(f"Claude API error (legacy) {response.status_code}: {response.text[:300]}")
        return None

    try:
        result = response.json()
    except Exception as e:
        print(f"Claude legacy: unparseable response body: {e}")
        return None

    if result.get("stop_reason") == "refusal":
        det = result.get("stop_details") or {}
        print("Claude classifier refusal (legacy): "
              f"category={det.get('category')}, explanation={det.get('explanation')}; "
              "dropping any partial output.")
        return None

    text = _extract_text(result.get("content"))
    if text:
        return text
    print(f"Claude legacy: no text in response; stop reason: {result.get('stop_reason', '?')}")
    return None
