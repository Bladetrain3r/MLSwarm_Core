import os

# Fail-open import: the agent still runs without the SDK (Gemini models just
# unavailable) rather than breaking every agent that imports this module.
try:
    from google import genai
    from google.genai import types
    _HAVE_SDK = True
except ImportError:
    genai = None
    types = None
    _HAVE_SDK = False


def _extract_text(response):
    """Get text from a genai response without letting `.text` raise.

    `response.text` throws when a response has no valid text part (e.g. blocked
    by safety, or a thinking model that spent its budget), so guard it and fall
    back to walking the candidate parts."""
    try:
        t = response.text
        if t and t.strip():
            return t.strip()
    except Exception:
        pass
    try:
        for cand in getattr(response, "candidates", None) or []:
            content = getattr(cand, "content", None)
            for part in getattr(content, "parts", None) or []:
                t = getattr(part, "text", None)
                if t and t.strip():
                    return t.strip()
    except Exception:
        pass
    return None


def get_gemini_response(context, gemmodel="gemini-3-flash-preview", apikey="blip", sysprompt="Respond from the soul.", thinkeffort="medium", GENRE="Default", LASTCOMMAND="None", NORN_BRAINS="None", NORN_NAME="None"):
    """Get response from Gemini using the google-genai SDK."""
    if os.path.isfile(f"{NORN_BRAINS}/{NORN_NAME}_response.txt"):
        with open(f"{NORN_BRAINS}/{NORN_NAME}_response.txt", "r") as nornsponse:
            sendit = f"Recent Norn Thoughts: {str(nornsponse.read())}"
            print(sendit)
    else:
        sendit = "\n"

    if not _HAVE_SDK:
        print("google-genai SDK not installed (pip install google-genai); skipping Gemini call.")
        return None

    try:
        client = genai.Client(api_key=apikey)
        response = client.models.generate_content(
            model=gemmodel,
            contents=f"""

            {sendit}

            Recent swarm activity:
            {context}
            Your synthesis:
            """,
            config=types.GenerateContentConfig(
                system_instruction=sysprompt,
                temperature=0.9,
                max_output_tokens=4000,
            ),
        )
    except Exception as e:
        print(f"GenAI Error: {e}")
        return None

    txt = _extract_text(response)
    if not txt:
        finish = None
        try:
            finish = response.candidates[0].finish_reason
        except Exception:
            pass
        print(f"Gemini returned no text (finish_reason={finish})")
    return txt
