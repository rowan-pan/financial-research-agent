"""
agents/backtester.py
Quantify historical returns for each episode identified by precedent_finder.
Fetches actual price data and calculates return metrics, then uses Claude
to interpret the results in context.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import anthropic
import numpy as np
import statsmodels.api as sm

from agents._utils import _parse_json, api_call

from tools.market_data import fetch_price_window, fetch_sector_etf

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "backtesting.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()


def _daily_returns(prices: list[dict]) -> tuple[list[str], list[float]]:
    """Return (dates, daily_returns) from a price list. dates[i] corresponds to return[i]."""
    dates = [p["date"] for p in prices]
    closes = [p["close"] for p in prices]
    rets = [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
    ]
    return dates[1:], rets


def _window_return(prices: list[dict]) -> float | None:
    """Total return over a price window (first close → last close)."""
    if len(prices) < 2:
        return None
    return (prices[-1]["close"] - prices[0]["close"]) / prices[0]["close"] * 100


def _compute_abnormal_return(
    ticker: str,
    episode_start: str,
    episode_end: str,
    actual_return_pct: float,
) -> dict:
    """
    Estimate abnormal return for an episode using a two-factor OLS market model.
    Betas are estimated from the 252 trading days before the episode trigger date.

    Falls back to single-factor (SPY only) if:
      - Sector ETF is unavailable or has <60 pre-period days
      - Two-factor R² < 0.1

    Returns raw return only (model_used="raw") if:
      - Fewer than 60 aligned pre-period trading days are available

    Returns a dict to be merged into the episode result.
    """
    _null = {
        "spy_return_pct": None,
        "sector_etf": None,
        "sector_return_pct": None,
        "beta_market": None,
        "beta_sector": None,
        "r_squared": None,
        "abnormal_return_pct": None,
        "model_used": "raw",
        "model_note": "",
    }

    # ── Pre-period window (~252 trading days) ────────────────────────────────
    try:
        day0 = datetime.strptime(episode_start, "%Y-%m-%d")
    except ValueError:
        return {**_null, "model_note": "Invalid episode start date"}

    pre_end = (day0 - timedelta(days=1)).strftime("%Y-%m-%d")
    pre_start = (day0 - timedelta(days=380)).strftime("%Y-%m-%d")

    stock_pre = fetch_price_window(ticker, pre_start, pre_end)
    spy_pre = fetch_price_window("SPY", pre_start, pre_end)

    stock_dates, stock_rets = _daily_returns(stock_pre)
    spy_dates, spy_rets = _daily_returns(spy_pre)

    # Align on common dates
    common = sorted(set(stock_dates) & set(spy_dates))
    if len(common) < 60:
        return {**_null, "model_note": f"Only {len(common)} pre-period trading days available (<60); reporting raw return"}

    idx_stk = {d: r for d, r in zip(stock_dates, stock_rets)}
    idx_spy = {d: r for d, r in zip(spy_dates, spy_rets)}
    y = np.array([idx_stk[d] for d in common])
    x_spy = np.array([idx_spy[d] for d in common])

    # ── Try two-factor model ──────────────────────────────────────────────────
    sector_etf = fetch_sector_etf(ticker)
    model_used = "1F"
    beta_sector = None
    r_squared = None

    if sector_etf:
        sec_pre = fetch_price_window(sector_etf, pre_start, pre_end)
        sec_dates, sec_rets = _daily_returns(sec_pre)
        common2 = sorted(set(common) & set(sec_dates))
        if len(common2) >= 60:
            idx_sec = {d: r for d, r in zip(sec_dates, sec_rets)}
            y2 = np.array([idx_stk[d] for d in common2])
            x2 = sm.add_constant(np.column_stack([
                [idx_spy[d] for d in common2],
                [idx_sec[d] for d in common2],
            ]))
            res2 = sm.OLS(y2, x2).fit()
            if res2.rsquared >= 0.1:
                alpha = res2.params[0]
                beta_mkt = res2.params[1]
                beta_sector = res2.params[2]
                r_squared = round(res2.rsquared, 3)
                model_used = "2F"
            # else fall through to single-factor below

    if model_used == "1F":
        x1 = sm.add_constant(x_spy)
        res1 = sm.OLS(y, x1).fit()
        alpha = res1.params[0]
        beta_mkt = res1.params[1]
        r_squared = round(res1.rsquared, 3)
        note = "" if sector_etf else "No sector ETF mapping for this ticker; using single-factor model"
    else:
        note = ""

    # ── Benchmark returns over episode window ─────────────────────────────────
    spy_ep = fetch_price_window("SPY", episode_start, episode_end)
    spy_window_ret = _window_return(spy_ep)

    sector_window_ret = None
    if model_used == "2F" and sector_etf:
        sec_ep = fetch_price_window(sector_etf, episode_start, episode_end)
        sector_window_ret = _window_return(sec_ep)

    if spy_window_ret is None:
        return {**_null, "model_note": "Could not fetch SPY episode window data"}

    # ── Expected and abnormal return ──────────────────────────────────────────
    n_days = len(spy_ep)  # use SPY episode window length (trades every business day)
    expected = (
        alpha * n_days
        + beta_mkt * spy_window_ret / 100
        + (beta_sector * sector_window_ret / 100 if beta_sector is not None and sector_window_ret is not None else 0)
    ) * 100
    abnormal = round(actual_return_pct - expected, 2)

    return {
        "spy_return_pct": round(spy_window_ret, 2) if spy_window_ret is not None else None,
        "sector_etf": sector_etf if model_used == "2F" else None,
        "sector_return_pct": round(sector_window_ret, 2) if sector_window_ret is not None else None,
        "beta_market": round(beta_mkt, 3),
        "beta_sector": round(beta_sector, 3) if beta_sector is not None else None,
        "r_squared": r_squared,
        "abnormal_return_pct": abnormal,
        "model_used": model_used,
        "model_note": note,
    }


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

    actual_return_rounded = round(actual_return, 2)
    abnormal_data = _compute_abnormal_return(comparable, start, end, actual_return_rounded)

    return {
        **episode,
        "actual_return_pct": actual_return_rounded,
        "max_drawdown_pct": round(max_dd, 2),
        "data_available": True,
        "price_points": len(prices),
        **abnormal_data,
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

    # Abnormal return summary
    abnormal_returns = [m["abnormal_return_pct"] for m in available if m.get("abnormal_return_pct") is not None]
    if abnormal_returns:
        ab_sorted = sorted(abnormal_returns)
        ab_mid = len(ab_sorted) // 2
        ab_median = ab_sorted[ab_mid] if len(ab_sorted) % 2 else (ab_sorted[ab_mid - 1] + ab_sorted[ab_mid]) / 2
        avg_abnormal = round(sum(abnormal_returns) / len(abnormal_returns), 2)
        median_abnormal = round(ab_median, 2)
    else:
        avg_abnormal = None
        median_abnormal = None

    models_used = [m.get("model_used", "raw") for m in available]
    model_counts = {m: models_used.count(m) for m in set(models_used)}
    dominant_model = max(model_counts, key=model_counts.get) if len(model_counts) == 1 else "mixed"

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
        "avg_abnormal_return_pct": avg_abnormal,
        "median_abnormal_return_pct": median_abnormal,
        "dominant_model": dominant_model,
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
