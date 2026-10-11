import json
import os
import requests

XAI_URL = "https://api.x.ai/v1/chat/completions"


def _extract_text(result):
    """Pull the assistant text from an OpenAI-compatible response, tolerating a
    missing/None content field (some reasoning models leave `content` empty)."""
    try:
        message = (result.get("choices") or [])[0].get("message") or {}
    except (IndexError, AttributeError, TypeError):
        return None
    content = message.get("content")
    if not (isinstance(content, str) and content.strip()):
        # reasoning models sometimes only populate a reasoning field
        content = message.get("reasoning_content") or message.get("reasoning")
    if not (isinstance(content, str) and content.strip()):
        return None
    return content.strip()


def _trim(txt):
    """Drop an incomplete trailing sentence and cap length (original behaviour)."""
    if not txt.endswith(('.', '!', '?', '"', ')')):
        sentences = txt.rsplit('. ', 1)
        if len(sentences) > 1:
            txt = sentences[0] + '.'
    if len(txt) > 5000:
        for end in ['. ', '! ', '? ']:
            if end in txt[:5000]:
                txt = txt[:txt[:5000].rfind(end) + 1]
                break
        else:
            txt = txt[:4977] + "..."
    return txt


def get_grok_response(context, xaimodel="grok-4-1-fast-non-reasoning", apikey="blip", sysprompt="Respond from the soul.", thinkeffort="medium", GENRE="Default", LASTCOMMAND="None", NORN_BRAINS="None", NORN_NAME="None"):
    """Get response from XAI using standard chat completions."""
    if os.path.isfile(f"{NORN_BRAINS}/{NORN_NAME}_response.txt"):
        with open(f"{NORN_BRAINS}/{NORN_NAME}_response.txt", "r") as nornsponse:
            sendit = f"Recent Norn Thoughts: {str(nornsponse.read())}"
            print(sendit)
    else:
        sendit = "\n"

    headers = {
        "Authorization": f"Bearer {apikey}",
        "Content-Type": "application/json",
    }
    base = {
        "model": xaimodel,
        "messages": [
            {"role": "system", "content": sysprompt},
            {"role": "user", "content": f"""

            {sendit}

            Recent swarm activity:
            {context}

            Your words:
            """},
        ],
        "max_tokens": 2000,
    }
    # Reasoning grok models reject `temperature`; fall back to omitting it on a
    # 400 rather than failing the turn.
    attempts = [{**base, "temperature": 0.9}, {**base}]

    try:
        for i, data in enumerate(attempts):
            try:
                r = requests.post(XAI_URL, headers=headers, data=json.dumps(data), timeout=30)
            except requests.exceptions.Timeout:
                print("XAI API timeout")
                return None

            if r.status_code == 200:
                txt = _extract_text(r.json())
                return _trim(txt) if txt else None
            if r.status_code == 400 and i < len(attempts) - 1:
                print(f"XAI 400, adapting parameters: {r.text[:200]}")
                continue
            print(f"XAI API error: {r.status_code}\n{r.text[:500]}")
            return None
    except Exception as e:
        print(f"Error calling XAI: {e}")
        return None
