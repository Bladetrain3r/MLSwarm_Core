#!/usr/bin/env python3
"""
What the swarm has lately been *about* — a handful of bare topic words.

The one axis the rest of an agent's context lacks. The tail is now, the fern is
now, the mood ring is now, the norn's thought is now. A topic list is the only
thing that says there was a *then*, and it costs a few dozen tokens to say it.

Deliberately **not retrieval**. There is no query and nothing is looked up: the
list is handed over, the way weather is. An agent picks one to keep, and what it
elects to remember is characterful — that choosing is the point, not the words.

## Topical, not merely frequent

Plain frequency over a year-old swarm returns the same perennial words every
time (its running jokes, its favourite nouns) which says nothing about *lately*.
So a word scores on how much livelier it is now than usual: its rate in a recent
window against its rate in a longer baseline. A word has to clear a small floor
of occurrences first, so one loud message can't mint a topic.

Speaker prefixes are stripped before counting, or every list would be the names
of whoever talks most.

Stdlib only. Read-only. Never raises.
"""

import re
from collections import Counter

# `[14:32] <Agent_Jungz> the rest of the line`
SPEAKER_RE = re.compile(r"^\s*\[[^\]]*\]\s*<[^>]*>\s*")
WORD_RE = re.compile(r"\b[a-z][a-z'-]{2,}\b")

# Small on purpose: the interesting filter is the recent-vs-baseline ratio, not
# an ever-growing list of banned words.
STOPWORDS = {
    "the", "that", "this", "these", "those", "there", "here", "then", "than",
    "and", "but", "for", "not", "with", "was", "were", "are", "been", "being",
    "have", "has", "had", "its", "his", "her", "hers", "him", "she", "they",
    "them", "their", "theirs", "you", "your", "yours", "our", "ours", "who",
    "what", "when", "where", "which", "while", "would", "could", "should",
    "into", "from", "just", "like", "some", "more", "most", "much", "very",
    "can", "will", "one", "two", "all", "any", "own", "too", "get", "got",
    "how", "why", "now", "out", "off", "own", "yet", "still", "even", "also",
    "about", "after", "before", "again", "over", "under", "between", "through",
}

DEFAULT_TOPICS = 5
MIN_COUNT = 3            # a word must actually recur to be a topic
RECENT_LINES = 400
BASELINE_LINES = 4000


def strip_speakers(text):
    """Drop the `[time] <Nick>` prefix so the loudest talkers aren't the topics."""
    return "\n".join(SPEAKER_RE.sub("", line) for line in text.splitlines())


def tokenise(text):
    return [w for w in WORD_RE.findall(strip_speakers(text).lower())
            if w not in STOPWORDS]


def score_topics(recent_text, baseline_text, count=DEFAULT_TOPICS,
                 min_count=MIN_COUNT):
    """Words that are livelier now than usual, most distinctive first.

    Returns [(word, score)]. Score is the ratio of the word's rate in the recent
    window to its rate in the baseline, so a word that has always been common
    scores near 1 and a word that has just surfaced scores high.
    """
    recent = Counter(tokenise(recent_text))
    if not recent:
        return []
    baseline = Counter(tokenise(baseline_text))
    recent_total = sum(recent.values())
    baseline_total = sum(baseline.values()) or 1

    scored = []
    for word, seen in recent.items():
        if seen < min_count:
            continue
        recent_rate = seen / recent_total
        # Smoothed: an unseen word behaves as if it occurred a fraction of a
        # time, so brand-new words score high without dividing by zero.
        baseline_rate = (baseline.get(word, 0) + 0.5) / baseline_total
        scored.append((word, recent_rate / baseline_rate))
    # Ties broken by the word itself so the list is stable between calls.
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return scored[:count]


def topic_words(recent_text, baseline_text, count=DEFAULT_TOPICS,
                min_count=MIN_COUNT):
    return [word for word, _score in
            score_topics(recent_text, baseline_text, count, min_count)]


def read_tail(path, lines):
    """Last N lines of a file, or "" if it cannot be read."""
    from collections import deque
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return "".join(deque(handle, maxlen=lines))
    except OSError:
        return ""


def gather(channels, recent_lines=RECENT_LINES, baseline_lines=BASELINE_LINES,
           count=DEFAULT_TOPICS):
    """Topics across a set of channel files. Missing files contribute nothing
    rather than failing the request."""
    recent, baseline = [], []
    for channel in channels:
        baseline_text = read_tail(channel, baseline_lines)
        if not baseline_text:
            continue
        baseline.append(baseline_text)
        recent.append("\n".join(baseline_text.splitlines()[-recent_lines:]))
    if not recent:
        return []
    return topic_words("\n".join(recent), "\n".join(baseline), count=count)
