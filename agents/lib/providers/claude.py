import os

# Fail-open import: if the SDK isn't installed the agent still runs, it just
# can't use Claude models (get_claude_response returns None with a clear note).
try:
    import anthropic
    _HAVE_SDK = True
except ImportError:
    anthropic = None
    _HAVE_SDK = False


def _extract_text(message):
    """Concatenate the text blocks of a Messages response.

    Robust to models whose first content block is NOT text (extended-thinking
    models emit a `thinking` block first; tool use emits `tool_use`). The old
    `content[0]['text']` access broke on exactly those."""
    parts = []
    for block in getattr(message, "content", None) or []:
        btype = getattr(block, "type", None)
        if btype == "text":
            parts.append(getattr(block, "text", ""))
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts).strip()


def get_claude_response(context, claudemodel="claude-haiku-5-5", sysprompt="Respond from the soul.",
                        apikey="None", GENRE="Default", LASTCOMMAND="None",
                        NORN_BRAINS="None", NORN_NAME="None",
                        max_tokens=40000, temperature=None):
    """Get a response from Claude via the anthropic SDK.

    Resilient to model-to-model parameter differences: if a model rejects a
    parameter (e.g. a smaller `max_tokens` ceiling) the call is retried with
    progressively more conservative parameters instead of erroring out.

    `temperature` is accepted for legacy callers but never sent: every
    current Claude model (the 4.6+ family onward) rejects it with a 400.

    Safety-classifier refusals (stop_reason "refusal", Opus 5.x) return None
    without retrying: a mid-output refusal carries partial text that must not
    be posted as a truncated stub, and re-sending the same request cannot fix
    a refusal. Returns the text, or None if every attempt failed."""
    # Explicit Norn support (unchanged behaviour).
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

    if not _HAVE_SDK:
        print("anthropic SDK not installed (pip install anthropic); skipping Claude call.")
        return None

    key = apikey if apikey and apikey != "None" else None  # else fall back to env
    try:
        # 30s starved Opus 5.x, whose thinking cannot be disabled; the agent
        # sleeps minutes between passes, so a longer wait costs nothing.
        client = anthropic.Anthropic(api_key=key, timeout=120.0, max_retries=2)
    except Exception as e:
        print(f"Could not init Anthropic client: {e}")
        return None

    base = {
        "model": claudemodel,
        "max_tokens": max_tokens,
        "system": sysprompt,
        "messages": [{"role": "user", "content": prompt}],
    }
    # Attempt ladder: full -> conservative max_tokens. The second rung is only
    # reached on a 400 (a model with a smaller output ceiling), never on a
    # refusal, which no parameter change can cure.
    attempts = [
        {**base},
        {**base, "max_tokens": min(max_tokens, 4000)},  # older/smaller ceilings
    ]

    last_err = None
    for i, params in enumerate(attempts):
        try:
            message = client.messages.create(**params)
            if getattr(message, "stop_reason", None) == "refusal":
                det = getattr(message, "stop_details", None)
                print("Claude classifier refusal: "
                      f"category={getattr(det, 'category', None)}, "
                      f"explanation={getattr(det, 'explanation', None)}; "
                      "dropping any partial output, not retrying.")
                return None
            text = _extract_text(message)
            if text:
                return text
            print(f"Claude returned no text (attempt {i + 1}); stop reason: "
                  f"{getattr(message, 'stop_reason', '?')}")
        except anthropic.BadRequestError as e:
            # Parameter/model mismatch -> try the next, more conservative rung.
            last_err = e
            print(f"Claude 400, adapting parameters (attempt {i + 1}): {e}")
            continue
        except anthropic.APIStatusError as e:
            # Auth, not-found (bad model name), overloaded, etc. -- not fixable
            # by trimming params, so don't keep hammering the same request.
            print(f"Claude API error {getattr(e, 'status_code', '?')}: {e}")
            return None
        except Exception as e:
            print(f"Error calling Claude API: {e}")
            return None

    if last_err:
        print(f"Claude call failed after adapting parameters: {last_err}")
    return None
