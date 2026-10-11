#!/usr/bin/env python3
"""
text_sanitiser.py

Lightweight, standalone text hygiene module.

Designed for:
- NapNorns
- Swarm agents
- LLM boundary filtering
- File-based IPC stability

Deterministic. No external dependencies.
"""

import re


# ---------------------------------------------------------------------------
# Individual Filters
# ---------------------------------------------------------------------------

def collapse_backslash_hell(text: str) -> str:
    """
    Collapse sequences of 5+ backslashes into exactly 4.
    Prevents runaway escape storms.
    """
    return re.sub(r'\\{5,}', r'\\\\', text)


def strip_control_chars(text: str) -> str:
    """
    Remove non-printable control characters except newline and tab.
    Protects file I/O and terminal stability.
    """
    return re.sub(r'[\x00-\x08\x0B-\x1F\x7F]', '', text)


def collapse_repeated_words(text: str, max_repeats: int = 4) -> str:
    """
    Collapse excessive word repetition.
    Example:
        "yes yes yes yes yes yes"
    becomes:
        "yes yes yes yes"

    max_repeats defines how many sequential repeats are allowed.
    """

    def replacer(match):
        word = match.group(1)
        return (" " + word) * max_repeats

    pattern = re.compile(
        r'\b(\w+)(\s+\1\b){%d,}' % max_repeats,
        flags=re.IGNORECASE
    )

    return pattern.sub(replacer, text)


# ---------------------------------------------------------------------------
# Sanitiser Pipeline
# ---------------------------------------------------------------------------

class TextSanitiser:
    """
    Composable sanitisation pipeline.
    """

    def __init__(self, preset: str = "default"):
        self.presets = {
            "default": [
                collapse_backslash_hell,
                strip_control_chars,
                collapse_repeated_words,
            ],
            "light": [
                collapse_backslash_hell,
                strip_control_chars,
            ],
            "none": []
        }

        self.preset = preset if preset in self.presets else "default"

    def process(self, text: str) -> str:
        """
        Apply sanitisation preset to text.
        """
        if not isinstance(text, str):
            return text

        for rule in self.presets[self.preset]:
            text = rule(text)

        return text

    def set_preset(self, preset: str):
        """
        Switch sanitisation preset dynamically.
        """
        if preset in self.presets:
            self.preset = preset


# ---------------------------------------------------------------------------
# Optional CLI Mode (for quick testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    sanitiser = TextSanitiser()

    if not sys.stdin.isatty():
        input_text = sys.stdin.read()
        print(sanitiser.process(input_text))
    else:
        print("Usage: echo 'text' | python text_sanitiser.py")
