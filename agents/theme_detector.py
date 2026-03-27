"""
agents/theme_detector.py
Identify the top financial theme from news headlines and ETF movers.
Wraps a Claude tool-use loop. Returns a structured theme dict.
"""

import json
import re
from pathlib import Path

import anthropic

from agents._utils import api_call
from tools.news import fetch_headlines, fetch_top_financial_headlines
from tools.market_data import fetch_etf_movers, fetch_ticker_info

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "theme_detection.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()

TOOLS = [
    {
        "name": "fetch_headlines",
        "description": "Fetch news headlines for a specific topic over the last N days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic or keyword to search for"},
                "days": {"type": "integer", "description": "Number of days to look back (default 15)", "default": 15},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "fetch_top_financial_headlines",
        "description": "Fetch broad financial market headlines without a specific topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days to look back (default 15)", "default": 15},
            },
        },
    },
    {
        "name": "fetch_etf_movers",
        "description": "Fetch recent performance of all US sector ETFs to identify which sectors are moving.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days to measure performance over", "default": 15},
            },
        },
    },
    {
        "name": "fetch_ticker_info",
        "description": "Fetch summary info for a specific ticker: sector, PE, market cap, 52-week range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock or ETF ticker symbol"},
            },
            "required": ["ticker"],
        },
    },
]

TOOL_MAP = {
    "fetch_headlines": lambda args: fetch_headlines(**args),
    "fetch_top_financial_headlines": lambda args: fetch_top_financial_headlines(**args),
    "fetch_etf_movers": lambda args: fetch_etf_movers(**args),
    "fetch_ticker_info": lambda args: fetch_ticker_info(**args),
}


def detect_theme(model: str, trace) -> dict:
    """
    Identify the top trending financial theme from current market signals.

    Args:
        model: Claude model string
        trace: ExecutionTrace instance to record calls

    Returns:
        dict with keys: theme, slug, summary, affected_tickers,
                        affected_sectors, sentiment, confidence
    """
    client = anthropic.Anthropic()
    messages = [
        {
            "role": "user",
            "content": (
                "Analyze current market signals to identify the single most financially "
                "significant theme driving markets right now. Use the available tools to "
                "fetch headlines and ETF performance data, then return your analysis."
            ),
        }
    ]

    json_retries = 0
    while True:
        response = api_call(
            client,
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        trace.record_claude_call("theme_detector", model, response.usage)

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, "text")), "")
            text = re.sub(r"^```(?:json)?\s*", "", text.strip())
            text = re.sub(r"\s*```$", "", text.strip())
            try:
                result = json.loads(text)
                trace.set_theme(result["theme"])
                return result
            except (json.JSONDecodeError, ValueError):
                json_retries += 1
                if json_retries >= 2:
                    raise
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user",
                    "content": "Now output only the JSON object as instructed. No commentary, no markdown fences.",
                })
                continue

        # Process tool calls
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                fn = TOOL_MAP[block.name]
                output = fn(block.input)
                trace.record_tool_call("theme_detector", block.name, block.input)
                if block.name in ("fetch_headlines", "fetch_top_financial_headlines"):
                    trace.record_sources(output)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(output),
                })
        messages.append({"role": "user", "content": tool_results})
