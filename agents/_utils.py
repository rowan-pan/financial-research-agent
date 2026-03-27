"""
agents/_utils.py
Shared helpers for agent modules.
"""

import json
import re
import time

import anthropic


def _parse_json(text: str):
    """Strip markdown code fences then parse JSON."""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


def api_call(client: anthropic.Anthropic, max_retries: int = 3, **kwargs):
    """
    Call client.messages.create with exponential backoff on rate limit errors.
    Only waits when a 429 is actually returned — no cost when quota is healthy.
    """
    for attempt in range(max_retries):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            if attempt == max_retries - 1:
                raise
            wait = 60 * (attempt + 1)  # 60s, 120s, ...
            print(f"  ⏳ Rate limit hit, retrying in {wait}s...", flush=True)
            time.sleep(wait)
