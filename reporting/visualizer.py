"""
reporting/visualizer.py
Generate charts for each hypothesis using matplotlib.
Produces three PNGs per report: episodes_indexed, return_distribution, correlation_heatmap.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from datetime import datetime, timedelta

from tools.market_data import fetch_price_window


def _get_episode_prices(episodes: list[dict], ticker: str) -> list[dict]:
    """Fetch price series for each episode, normalized to day-0 = 100."""
    series = []
    for ep in episodes:
        comparable = ep.get("comparable_ticker", ticker)
        start = ep.get("start_date", "")
        end = ep.get("end_date", "")
        if not start or not end:
            continue
        prices = fetch_price_window(comparable, start, end)
        if len(prices) < 5:
            continue
        closes = [p["close"] for p in prices]
        base = closes[0]
        normalized = [c / base * 100 for c in closes]
        series.append({
            "label": ep.get("episode_label", start[:4]),
            "values": normalized,
            "similarity": ep.get("similarity", "medium"),
        })
    return series


def plot_episodes_indexed(
    ticker: str,
    direction: str,
    episodes: list[dict],
    charts_dir: Path,
) -> Path:
    """
    Indexed price chart: all historical episodes overlaid, day 0 = 100.
    Current episode (if price data available) shown in a distinct color.
    """
    fig, ax = plt.subplots(figsize=(10, 5))

    series = _get_episode_prices(episodes, ticker)
    colors = plt.cm.Blues(np.linspace(0.4, 0.9, max(len(series), 1)))

    for i, s in enumerate(series):
        days = list(range(len(s["values"])))
        ax.plot(days, s["values"], color=colors[i], linewidth=1.5, label=s["label"], alpha=0.8)

    ax.axhline(100, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
    ax.set_xlabel("Days from trigger event")
    ax.set_ylabel("Indexed price (day 0 = 100)")
    ax.set_title(f"{ticker} — Historical Episodes ({direction.upper()})")
    if series:
        ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    out = charts_dir / "episodes_indexed.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def plot_return_distribution(
    ticker: str,
    direction: str,
    backtest: dict,
    charts_dir: Path,
) -> Path:
    """
    Return distribution: histogram of returns across episodes.
    """
    episodes = backtest.get("episodes", [])
    returns = [
        e["actual_return_pct"]
        for e in episodes
        if e.get("data_available") and e.get("actual_return_pct") is not None
    ]

    fig, ax = plt.subplots(figsize=(8, 4))

    if returns:
        colors = ["#2ecc71" if r > 0 else "#e74c3c" for r in returns]
        labels = [e.get("episode_label", f"Ep {i+1}") for i, e in enumerate(episodes) if e.get("data_available")]
        ax.bar(labels[:len(returns)], returns, color=colors, edgecolor="white", linewidth=0.5)
        ax.axhline(0, color="gray", linewidth=0.8)
        median = backtest.get("median_return_pct")
        if median is not None:
            ax.axhline(median, color="#3498db", linestyle="--", linewidth=1.2, label=f"Median: {median:.1f}%")
            ax.legend(fontsize=8)
    else:
        ax.text(0.5, 0.5, "No data available", ha="center", va="center", transform=ax.transAxes)

    ax.set_ylabel("Return (%)")
    ax.set_title(f"{ticker} — Return by Episode ({direction.upper()})")
    ax.tick_params(axis="x", rotation=20)
    ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()

    out = charts_dir / "return_distribution.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def plot_correlation_heatmap(
    hypotheses: list[dict],
    backtest_results: list[dict],
    charts_dir: Path,
) -> Path:
    """
    Consistency heatmap: rows = hypotheses, columns = metrics (win rate, avg return, drawdown).
    Shows at a glance which hypotheses have the strongest/most consistent historical backing.
    """
    tickers = [h["ticker"] for h in hypotheses]
    metrics = ["win_rate_pct", "avg_return_pct", "avg_max_drawdown_pct"]
    labels = ["Win Rate %", "Avg Return %", "Avg Max DD %"]

    data = []
    for bt in backtest_results:
        row = [bt.get(m) for m in metrics]
        data.append(row)

    # Replace None with 0
    arr = np.array([[v if v is not None else 0.0 for v in row] for row in data], dtype=float)

    fig, ax = plt.subplots(figsize=(7, max(3, len(tickers) * 0.8)))

    if arr.size > 0:
        # Normalize each column to [0, 1] for color mapping
        norm_arr = arr.copy()
        for col in range(arr.shape[1]):
            col_min, col_max = arr[:, col].min(), arr[:, col].max()
            if col_max > col_min:
                norm_arr[:, col] = (arr[:, col] - col_min) / (col_max - col_min)
            else:
                norm_arr[:, col] = 0.5

        im = ax.imshow(norm_arr, cmap="RdYlGn", aspect="auto", vmin=0, vmax=1)

        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_yticks(range(len(tickers)))
        ax.set_yticklabels(tickers, fontsize=9)

        for i in range(len(tickers)):
            for j in range(len(labels)):
                val = arr[i, j]
                text = f"{val:.1f}" if val != 0 else "N/A"
                ax.text(j, i, text, ha="center", va="center", fontsize=8, color="black")

    ax.set_title("Hypothesis Consistency Heatmap")
    plt.tight_layout()

    out = charts_dir / "correlation_heatmap.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def generate_all_charts(
    hypotheses: list[dict],
    precedents: dict,
    backtest_results: list[dict],
    charts_dir: Path,
    trace,
) -> list[Path]:
    """
    Generate all three charts for the report.
    Charts are saved to charts_dir. Returns list of created file paths.
    """
    charts_dir.mkdir(parents=True, exist_ok=True)
    created = []

    # Per-hypothesis charts use the first hypothesis for indexed + distribution
    # Heatmap covers all hypotheses
    if hypotheses and backtest_results:
        first_hypo = hypotheses[0]
        first_bt = backtest_results[0]
        first_episodes = precedents.get(first_hypo["ticker"], [])

        created.append(
            plot_episodes_indexed(
                first_hypo["ticker"], first_hypo["direction"], first_episodes, charts_dir
            )
        )
        created.append(
            plot_return_distribution(
                first_hypo["ticker"], first_hypo["direction"], first_bt, charts_dir
            )
        )

    created.append(
        plot_correlation_heatmap(hypotheses, backtest_results, charts_dir)
    )

    trace.record_tool_call("visualizer", "generate_charts", {"count": len(created)})
    return created
