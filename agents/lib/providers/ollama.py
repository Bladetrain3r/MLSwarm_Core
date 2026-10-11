import os
import requests


def _extract_text(result):
    """Return the assistant text, preferring `content` and falling back to a
    `reasoning` field, without KeyError-ing on a partial/odd response."""
    try:
        message = (result.get("choices") or [])[0].get("message") or {}
    except (IndexError, AttributeError, TypeError):
        return None
    for key in ("content", "reasoning"):
        val = message.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def get_local_response(context, aimodel="default", sysprompt="Respond from the soul.", thinkeffort="none", LOCAL_IP="127.0.0.1", LOCAL_PORT="11434", GENRE="Default", LASTCOMMAND="None", NORN_BRAINS="None", NORN_NAME="None"):
    """Get response from a local OpenAI-compatible endpoint (e.g. Ollama)."""
    if os.path.isfile(f"{NORN_BRAINS}/{NORN_NAME}_response.txt"):
        with open(f"{NORN_BRAINS}/{NORN_NAME}_response.txt", "r") as nornsponse:
            sendit = f"Recent Norn Thoughts: {str(nornsponse.read())}"
    else:
        sendit = "\n"

    try:
        headers = {"content-type": "application/json"}
        prompt = f"""
{sendit}

Your prior command: {LASTCOMMAND}

Recent Swarm Chat:
===============
{context}
===============

"""
        data = {
            "model": f"{aimodel}",
            "max_tokens": 10000,
            "options": {"num_ctx": 32000},
            "messages": [
                {"role": "system", "content": sysprompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.95  # Roughly speaking, creativity set to high
        }

        response = requests.post(
            f"http://{LOCAL_IP}:{LOCAL_PORT}/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=600,
        )

        if response.status_code != 200:
            print(f"Local Agent API error: {response.status_code}")
            print(response.text[:500])
            return None

        txt = _extract_text(response.json())
        if not txt:
            print("Local API returned no usable text")
        return txt

    except requests.exceptions.ConnectionError:
        print(f"Local model unreachable at {LOCAL_IP}:{LOCAL_PORT} (is it running?)")
        return None
    except Exception as e:
        print(f"Error calling Local API: {e}")
        return None
