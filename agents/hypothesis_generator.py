"""
agents/hypothesis_generator.py
Generate structured investment hypotheses for a given theme.
Wraps a Claude tool-use loop. Returns a list of hypothesis dicts.
"""

import json
from pathlib import Path

import anthropic

from agents._utils import _parse_json, api_call

from tools.news import fetch_headlines
from tools.market_data import fetch_price_history, fetch_ticker_info, fetch_ticker_news
from tools.fundamentals import fetch_company_overview, fetch_earnings, fetch_sector_performance

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "hypothesis_generation.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()

TOOLS = [
    {
        "name": "fetch_headlines",
        "description": "Fetch news headlines for a topic over the last N days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "days": {"type": "integer", "default": 15},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "fetch_ticker_info",
        "description": "Fetch current price, sector, PE ratio, and market cap for a ticker.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "fetch_price_history",
        "description": "Fetch historical OHLCV price data for a ticker.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "period": {"type": "string", "description": "e.g. '1y', '2y'", "default": "1y"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "fetch_ticker_news",
        "description": "Fetch recent news articles for a specific ticker.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "fetch_company_overview",
        "description": "Fetch company fundamentals from Alpha Vantage: PE, EPS, revenue, profit margin.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "fetch_earnings",
        "description": "Fetch recent earnings surprises (quarterly and annual) for a ticker.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "fetch_sector_performance",
        "description": "Fetch sector performance snapshot across multiple timeframes.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

TOOL_MAP = {
    "fetch_headlines": lambda args: fetch_headlines(**args),
    "fetch_ticker_info": lambda args: fetch_ticker_info(**args),
    "fetch_price_history": lambda args: fetch_price_history(**args),
    "fetch_ticker_news": lambda args: fetch_ticker_news(**args),
    "fetch_company_overview": lambda args: fetch_company_overview(**args),
    "fetch_earnings": lambda args: fetch_earnings(**args),
    "fetch_sector_performance": lambda args: fetch_sector_performance(**args),
}


def generate_hypotheses(theme: dict, model: str, trace) -> list[dict]:
    """
    Generate 3-5 investment hypotheses for the given theme.

    Args:
        theme: dict from detect_theme()
        model: Claude model string
        trace: ExecutionTrace instance

    Returns:
        list of hypothesis dicts
    """
    client = anthropic.Anthropic()
    messages = [
        {
            "role": "user",
            "content": (
                f"Generate investment hypotheses for the following theme:\n\n"
                f"Theme: {theme['theme']}\n"
                f"Summary: {theme['summary']}\n"
                f"Affected tickers: {', '.join(theme.get('affected_tickers', []))}\n"
                f"Affected sectors: {', '.join(theme.get('affected_sectors', []))}\n"
                f"Sentiment: {theme.get('sentiment', 'unknown')}\n\n"
                "Use the available tools to fetch current price and fundamental data "
                "for the affected assets before forming your hypotheses."
            ),
        }
    ]

    json_retries = 0
    while True:
        response = api_call(
            client,
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        trace.record_claude_call("hypothesis_generator", model, response.usage)

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, "text")), "")
            try:
                return _parse_json(text)
            except (json.JSONDecodeError, ValueError):
                json_retries += 1
                if json_retries >= 2:
                    raise
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user",
                    "content": "Now output only the JSON array as instructed. No commentary, no markdown fences.",
                })
                continue

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                fn = TOOL_MAP[block.name]
                output = fn(block.input)
                trace.record_tool_call("hypothesis_generator", block.name, block.input)
                if block.name in ("fetch_headlines", "fetch_top_financial_headlines"):
                    trace.record_sources(output)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(output),
                })
        messages.append({"role": "user", "content": tool_results})
