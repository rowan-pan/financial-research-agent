"""
agents/backtester.py
Quantify historical returns for each episode identified by precedent_finder.
Fetches actual price data and calculates return metrics, then uses Claude
to interpret the results in context.
"""

import json
from pathlib import Path

import anthropic

from agents._utils import _parse_json, api_call

from tools.market_data import fetch_price_window

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "backtesting.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()


def _calculate_episode_metrics(
    ticker: str, episode: dict, direction: str
) -> dict:
    """
    Fetch actual price data for an episode window and compute return metrics.
    """
    comparable = episode.get("comparable_ticker", ticker)
    start = episode.get("start_date", "")
    end = episode.get("end_date", "")

    if not start or not end:
        return {**episode, "actual_return_pct": None, "max_drawdown_pct": None, "data_available": False}

    prices = fetch_price_window(comparable, start, end)
    if len(prices) < 2:
        return {**episode, "actual_return_pct": None, "max_drawdown_pct": None, "data_available": False}

    closes = [p["close"] for p in prices]
    entry = closes[0]
    exit_ = closes[-1]
    raw_return = (exit_ - entry) / entry * 100
    actual_return = raw_return if direction == "long" else -raw_return

    # Max drawdown from entry
    peak = entry
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        dd = (peak - c) / peak * 100
        if dd > max_dd:
            max_dd = dd
    if direction == "short":
        max_dd = max((c - entry) / entry * 100 for c in closes)

    return {
        **episode,
        "actual_return_pct": round(actual_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "data_available": True,
        "price_points": len(prices),
    }


def backtest_hypothesis(hypothesis: dict, episodes: list[dict], model: str, trace) -> dict:
    """
    Calculate return metrics across all episodes and use Claude to interpret results.

    Args:
        hypothesis: single hypothesis dict
        episodes: list of episode dicts from precedent_finder
        model: Claude model string
        trace: ExecutionTrace instance

    Returns:
        dict with win_rate, median_return, interpretation, caveats, and per-episode metrics
    """
    client = anthropic.Anthropic()
    ticker = hypothesis["ticker"]
    direction = hypothesis["direction"]

    # Quantify each episode
    measured = [_calculate_episode_metrics(ticker, ep, direction) for ep in episodes]
    available = [m for m in measured if m["data_available"]]

    if not available:
        return {
            "ticker": ticker,
            "direction": direction,
            "episodes_analyzed": 0,
            "win_rate_pct": None,
            "median_return_pct": None,
            "avg_return_pct": None,
            "best_return_pct": None,
            "worst_return_pct": None,
            "avg_max_drawdown_pct": None,
            "consistency": "low",
            "interpretation": "Insufficient historical price data to quantify this hypothesis.",
            "caveats": "No price data found for the identified episodes.",
            "episodes": measured,
        }

    returns = [m["actual_return_pct"] for m in available]
    wins = sum(1 for r in returns if r > 0)
    returns_sorted = sorted(returns)
    mid = len(returns_sorted) // 2
    median = returns_sorted[mid] if len(returns_sorted) % 2 else (returns_sorted[mid - 1] + returns_sorted[mid]) / 2
    drawdowns = [m["max_drawdown_pct"] for m in available if m["max_drawdown_pct"] is not None]

    summary_metrics = {
        "ticker": ticker,
        "direction": direction,
        "episodes_analyzed": len(available),
        "win_rate_pct": round(wins / len(available) * 100, 1),
        "median_return_pct": round(median, 2),
        "avg_return_pct": round(sum(returns) / len(returns), 2),
        "best_return_pct": round(max(returns), 2),
        "worst_return_pct": round(min(returns), 2),
        "avg_max_drawdown_pct": round(sum(drawdowns) / len(drawdowns), 2) if drawdowns else None,
    }

    # Ask Claude to interpret
    bt_messages = [
        {
            "role": "user",
            "content": (
                f"Interpret these backtest results for the hypothesis:\n\n"
                f"Hypothesis: {hypothesis['direction'].upper()} {hypothesis['ticker']}\n"
                f"Rationale: {hypothesis['rationale']}\n\n"
                f"Metrics:\n{json.dumps(summary_metrics, indent=2)}\n\n"
                f"Episode details:\n{json.dumps(available, indent=2)}"
            ),
        }
    ]
    interpretation = None
    for _ in range(2):
        response = api_call(
            client,
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=bt_messages,
        )
        trace.record_claude_call("backtester", model, response.usage)
        text = next((b.text for b in response.content if hasattr(b, "text")), "")
        try:
            interpretation = _parse_json(text)
            break
        except (json.JSONDecodeError, ValueError):
            bt_messages.append({"role": "assistant", "content": response.content})
            bt_messages.append({
                "role": "user",
                "content": "Now output only the JSON object as instructed. No commentary, no markdown fences.",
            })

    if interpretation is None:
        interpretation = {"consistency": "unknown", "interpretation": "Could not parse interpretation.", "caveats": ""}

    return {**summary_metrics, **interpretation, "episodes": measured}


def backtest_all(hypotheses: list[dict], precedents: dict, model: str, trace) -> list[dict]:
    """
    Run backtest for every hypothesis.

    Returns:
        list of backtest result dicts, one per hypothesis
    """
    results = []
    for hypothesis in hypotheses:
        ticker = hypothesis["ticker"]
        episodes = precedents.get(ticker, [])
        result = backtest_hypothesis(hypothesis, episodes, model, trace)
        results.append(result)
    return results
