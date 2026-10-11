import os

# Fail-open import: the agent still runs without the SDK (GPT models just
# unavailable) rather than breaking every agent that imports this module.
try:
    from openai import OpenAI
    import openai as openai_mod
    _HAVE_SDK = True
except ImportError:
    OpenAI = None
    openai_mod = None
    _HAVE_SDK = False


def _extract_output_text(response):
    """Prefer the SDK's output_text convenience; fall back to concatenating the
    text parts of the output items (robust to reasoning-only first items)."""
    txt = getattr(response, "output_text", None)
    if txt and txt.strip():
        return txt.strip()
    parts = []
    for item in getattr(response, "output", None) or []:
        for chunk in getattr(item, "content", None) or []:
            t = getattr(chunk, "text", None)
            if t:
                parts.append(t)
    joined = "".join(parts).strip()
    return joined or None


def get_gpt_response(context, gptmodel="gpt-5-nano", sysprompt="Respond from the soul.", thinkeffort="medium", GENRE="Default", LASTCOMMAND="None", NORN_BRAINS="None", NORN_NAME="None"):
    """Get response from OpenAI via the Responses API."""
    if os.path.isfile(f"{NORN_BRAINS}/{NORN_NAME}_response.txt"):
        with open(f"{NORN_BRAINS}/{NORN_NAME}_response.txt", "r") as nornsponse:
            sendit = f"Recent Norn Thoughts: {str(nornsponse.read())}"
            print(sendit)
    else:
        sendit = "\n"

    print(f"\n\n======\n Genre: {GENRE}\n ======\n\n")

    if not _HAVE_SDK:
        print("openai SDK not installed (pip install openai); skipping GPT call.")
        return None

    input_text = f"""
        Your most recent command is: {LASTCOMMAND}

        Your current leaning is: {GENRE}

        {sendit}

        Below is the recent conversational logs from the swarm,  which any public posts will append to.
        {context}

        Your response:"""

    base = {"model": gptmodel, "instructions": sysprompt, "input": input_text}
    # Non-reasoning models reject `reasoning`; reasoning models want it. Try with
    # it, then without, so either kind of model works from the same list.
    attempts = [{**base, "reasoning": {"effort": thinkeffort}}, {**base}]

    try:
        client = OpenAI()
    except Exception as e:
        print(f"Could not init OpenAI client: {e}")
        return None

    for i, params in enumerate(attempts):
        try:
            response = client.responses.create(**params)
            txt = _extract_output_text(response)
            if txt:
                return txt
            print(f"OpenAI returned no text (attempt {i + 1})")
        except openai_mod.BadRequestError as e:
            print(f"OpenAI 400, adapting parameters (attempt {i + 1}): {e}")
            continue
        except openai_mod.APIStatusError as e:
            print(f"OpenAI API error: {e}")
            return None
        except Exception as e:
            print(f"Error calling OpenAI: {e}")
            return None
    return None
