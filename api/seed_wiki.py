#!/usr/bin/env python3

import requests
import sys
import time
import json

WIKI_API = "https://en.wikipedia.org/api/rest_v1/page/summary/"
WIKI_RANDOM = "https://en.wikipedia.org/api/rest_v1/page/random/summary"
WIKI_CATEGORIES = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    "User-Agent": "SwarmSeedBot/0.1 (contact: set-your-contact-here)"
}

# ---- Config ----
ALLOWED_CATEGORY_KEYWORDS = [
    "Science",
    "Physics",
    "Mathematics",
    "Technology",
    "Astronomy",
    "Biology",
    "Geography",
    "History",
    "Philosophy",
    "Engineering"
]

MAX_RETRIES = 3
TIMEOUT = 10


def fetch_random_summary():
    r = requests.get(WIKI_RANDOM, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_categories(title):
    params = {
        "action": "query",
        "prop": "categories",
        "format": "json",
        "titles": title,
        "cllimit": "max"
    }

    r = requests.get(WIKI_CATEGORIES, params=params, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        return [c["title"] for c in page.get("categories", [])]

    return []


def category_allowed(categories):
    for cat in categories:
        for keyword in ALLOWED_CATEGORY_KEYWORDS:
            if keyword.lower() in cat.lower():
                return True
    return False


def get_seed():
    for attempt in range(1, MAX_RETRIES + 1):
        summary = fetch_random_summary()

        # Skip disambiguation or missing extracts
        if summary.get("type") != "standard":
            continue

        title = summary.get("title")
        extract = summary.get("extract")

        if not title or not extract:
            continue

        # categories = fetch_categories(title)

        return {
            "seed_title": title,
            "seed_summary": extract.strip(),
            # "seed_url": summary.get("content_urls", {}).get("desktop", {}).get("page"),
            # "categories": categories,
            "timestamp": int(time.time())
        }
    time.sleep(1)

    return None


def main():
    seed = get_seed()
    if not seed:
        print("No suitable seed found after retries.", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(seed, indent=2))


if __name__ == "__main__":
    main()
