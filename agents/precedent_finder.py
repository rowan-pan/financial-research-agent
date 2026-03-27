"""
agents/precedent_finder.py
For each hypothesis, identify historical market episodes with similar setups.
Returns qualitative episode data that the backtester will quantify.
"""

import json
from pathlib import Path

import anthropic

from agents._utils import _parse_json, api_call

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "precedent_search.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()


def find_precedents(hypothesis: dict, theme: dict, model: str, trace) -> list[dict]:
    """
    Find 2-4 historical episodes resembling the current hypothesis setup.

    Args:
        hypothesis: single hypothesis dict from generate_hypotheses()
        theme: theme dict from detect_theme()
        model: Claude model string
        trace: ExecutionTrace instance

    Returns:
        list of episode dicts with start_date, end_date, comparable_ticker,
        macro_parallel, price_behavior, approximate_return_pct, similarity, key_difference
    """
    client = anthropic.Anthropic()
    messages = [
        {
            "role": "user",
            "content": (
                f"Find historical precedents for this investment hypothesis:\n\n"
                f"Ticker: {hypothesis['ticker']} ({hypothesis.get('name', '')})\n"
                f"Direction: {hypothesis['direction']}\n"
                f"Timeframe: {hypothesis.get('timeframe', '30-60 days')}\n"
                f"Rationale: {hypothesis['rationale']}\n"
                f"Key catalyst: {hypothesis.get('key_catalyst', '')}\n\n"
                f"Macro theme driving this: {theme['theme']}\n"
                f"Theme summary: {theme['summary']}\n\n"
                "Identify 2-4 historical episodes where a similar macro setup or "
                "fundamental catalyst played out for this ticker or a comparable asset."
            ),
        }
    ]

    for _ in range(2):
        response = api_call(
            client,
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        trace.record_claude_call("precedent_finder", model, response.usage)
        text = next((b.text for b in response.content if hasattr(b, "text")), "")
        try:
            return _parse_json(text)
        except (json.JSONDecodeError, ValueError):
            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": "Now output only the JSON array as instructed. No commentary, no markdown fences.",
            })

    raise ValueError(f"Could not extract JSON from precedent_finder response for {hypothesis['ticker']}")


def find_all_precedents(hypotheses: list[dict], theme: dict, model: str, trace) -> dict:
    """
    Find precedents for all hypotheses.

    Returns:
        dict mapping ticker -> list of episode dicts
    """
    results = {}
    for hypothesis in hypotheses:
        ticker = hypothesis["ticker"]
        episodes = find_precedents(hypothesis, theme, model, trace)
        results[ticker] = episodes
    return results
