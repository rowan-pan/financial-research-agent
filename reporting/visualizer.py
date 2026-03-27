"""
reporting/visualizer.py
Generate charts for each hypothesis using matplotlib.
Produces three PNGs per report: episodes_indexed, return_distribution, correlation_heatmap.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

sns.set_theme(style="whitegrid", palette="muted", font_scale=1.0)

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
    hypotheses: list[dict],
    precedents: dict,
    charts_dir: Path,
) -> Path:
    """
    Indexed price chart: one subplot per hypothesis, all historical episodes overlaid.
    Day 0 = 100. Each hypothesis gets its own panel with distinct episode colors.
    """
    n = len(hypotheses)
    fig, axes = plt.subplots(n, 1, figsize=(10, 4 * n), squeeze=False)

    ticker_colors = [
        "#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6",
        "#1abc9c", "#e67e22", "#34495e",
    ]

    for idx, hypo in enumerate(hypotheses):
        ax = axes[idx][0]
        ticker = hypo["ticker"]
        direction = hypo["direction"]
        episodes = precedents.get(ticker, [])
        series = _get_episode_prices(episodes, ticker)

        for i, s in enumerate(series):
            color = ticker_colors[i % len(ticker_colors)]
            days = list(range(len(s["values"])))
            ax.plot(days, s["values"], color=color, linewidth=1.5, label=s["label"], alpha=0.85)

        ax.axhline(100, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
        ax.set_title(f"{ticker} — Historical Episodes ({direction.upper()})", fontsize=10)
        ax.set_ylabel("Indexed (day 0 = 100)", fontsize=8)
        if series:
            ax.legend(fontsize=7, loc="upper left")
        ax.grid(True, alpha=0.3)

    axes[-1][0].set_xlabel("Days from trigger event")
    plt.tight_layout()

    out = charts_dir / "episodes_indexed.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def plot_return_distribution(
    hypotheses: list[dict],
    backtest_results: list[dict],
    charts_dir: Path,
) -> Path:
    """
    Grouped bar chart: one group per hypothesis, one bar per episode.
    Green = positive return, red = negative.
    """
    fig, ax = plt.subplots(figsize=(12, 5))

    group_gap = 0.4
    bar_width = 0.6
    x_pos = 0.0
    x_ticks = []
    x_labels = []

    for hypo, bt in zip(hypotheses, backtest_results):
        ticker = hypo["ticker"]
        episodes = bt.get("episodes", [])
        available = [e for e in episodes if e.get("data_available") and e.get("actual_return_pct") is not None]

        if not available:
            continue

        for ep in available:
            ret = ep["actual_return_pct"]
            color = "#2ecc71" if ret > 0 else "#e74c3c"
            ax.bar(x_pos, ret, width=bar_width, color=color, edgecolor="white", linewidth=0.5)
            label = ep.get("episode_label", "")[:10]
            x_ticks.append(x_pos)
            x_labels.append(f"{ticker}\n{label}")
            x_pos += bar_width + 0.15

        # Draw median line across the group
        median = bt.get("median_return_pct")
        group_start = x_pos - len(available) * (bar_width + 0.15) - 0.15 + bar_width / 2
        group_end = x_pos - 0.15 - bar_width / 2
        if median is not None:
            ax.hlines(median, group_start - bar_width / 2, group_end + bar_width / 2,
                      colors="#3498db", linestyles="--", linewidth=1.2)

        x_pos += group_gap

    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels, fontsize=7, rotation=45, ha="right")
    ax.set_ylabel("Return (%)")
    ax.set_title("Return by Episode — All Hypotheses")
    ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.2)

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
    Hypothesis performance summary heatmap: rows = hypotheses,
    columns = win rate, avg return, avg max drawdown, n (sample size).
    """
    def _expected_value(bt: dict) -> float | None:
        episodes = bt.get("episodes", [])
        returns = [e["actual_return_pct"] for e in episodes
                   if e.get("data_available") and e.get("actual_return_pct") is not None]
        if not returns:
            return None
        wr = (bt.get("win_rate_pct") or 0) / 100
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        return round(wr * avg_win + (1 - wr) * avg_loss, 1)

    tickers = [h["ticker"] for h in hypotheses]
    metrics = ["win_rate_pct", "avg_return_pct", "avg_max_drawdown_pct", "episodes_analyzed"]
    labels = ["Win Rate %", "Avg Return %", "Avg Max DD %", "n", "Exp Value %"]

    data = []
    for bt in backtest_results:
        row = [bt.get(m) for m in metrics] + [_expected_value(bt)]
        data.append(row)

    arr = np.array([[v if v is not None else 0.0 for v in row] for row in data], dtype=float)

    fig, ax = plt.subplots(figsize=(10, max(3, len(tickers) * 0.8)))

    if arr.size > 0:
        # Build annotation matrix
        n_col = 3
        annot = np.empty(arr.shape, dtype=object)
        for i in range(arr.shape[0]):
            for j in range(arr.shape[1]):
                val = arr[i, j]
                if j == n_col:
                    annot[i, j] = str(int(val))
                elif val == 0:
                    annot[i, j] = "N/A"
                else:
                    annot[i, j] = f"{val:.1f}"

        # Normalize for color mapping; n column stays mid (neutral)
        norm_arr = arr.copy()
        for col in range(arr.shape[1]):
            if col == n_col:
                norm_arr[:, col] = 0.5
                continue
            col_min, col_max = arr[:, col].min(), arr[:, col].max()
            norm_arr[:, col] = (
                (arr[:, col] - col_min) / (col_max - col_min)
                if col_max > col_min else np.full(arr.shape[0], 0.5)
            )

        sns.heatmap(
            norm_arr,
            ax=ax,
            annot=annot,
            fmt="",
            cmap="RdYlGn",
            vmin=0, vmax=1,
            xticklabels=labels,
            yticklabels=tickers,
            linewidths=0.5,
            linecolor="white",
            cbar=False,
        )
        ax.tick_params(axis="x", labelsize=9)
        ax.tick_params(axis="y", labelsize=9, rotation=0)

    ax.set_title("Hypothesis Performance Summary")
    plt.tight_layout()

    out = charts_dir / "correlation_heatmap.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def plot_risk_return(
    hypotheses: list[dict],
    backtest_results: list[dict],
    charts_dir: Path,
) -> Path:
    """
    Risk/return scatter: x = avg max drawdown, y = median return.
    Circle markers with ticker label inside. Direction + win rate annotated beside each dot.
    Green = positive median return, red = negative.
    Horizontal dashed line at y = 0. Top-left quadrant label.
    """
    circle_colors = [
        "#2ecc71", "#3498db", "#9b59b6", "#e67e22", "#1abc9c",
        "#e74c3c", "#f39c12", "#34495e",
    ]

    fig, ax = plt.subplots(figsize=(9, 6))

    for i, (hypo, bt) in enumerate(zip(hypotheses, backtest_results)):
        ticker = hypo["ticker"]
        direction = hypo["direction"].capitalize()
        x = bt.get("avg_max_drawdown_pct")
        y = bt.get("median_return_pct")
        win_rate = bt.get("win_rate_pct")
        if x is None or y is None:
            continue

        color = circle_colors[i % len(circle_colors)]
        ax.scatter(x, y, s=800, color=color, zorder=3, edgecolors="white", linewidths=1.5)

        # Ticker label inside the circle
        ax.text(x, y, ticker[:4], ha="center", va="center", fontsize=7,
                color="white", fontweight="bold", zorder=4)

        # Direction + win rate beside the dot
        win_str = f"{win_rate:.0f}% win" if win_rate is not None else ""
        ax.annotate(f"{direction} · {win_str}", (x, y),
                    textcoords="offset points", xytext=(22, 6), fontsize=8, color="#444444")

    ax.axhline(0, color="gray", linestyle="--", linewidth=1.0, alpha=0.7)

    # Quadrant labels
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    ax.text(xlim[0] + (xlim[1] - xlim[0]) * 0.02, ylim[1] * 0.92,
            "Best: high return, low risk", fontsize=8, color="#2ecc71", alpha=0.8)
    ax.text(xlim[1] * 0.65, ylim[0] * 0.85,
            "Worst: low return, high risk", fontsize=8, color="#e74c3c", alpha=0.8)

    ax.set_xlabel("Avg Max Drawdown →")
    ax.set_ylabel("Median Return →")
    ax.set_title("Backtest Risk / Return by Hypothesis")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    out = charts_dir / "risk_return.png"
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

    if hypotheses and backtest_results:
        created.append(plot_episodes_indexed(hypotheses, precedents, charts_dir))
        created.append(plot_return_distribution(hypotheses, backtest_results, charts_dir))
        created.append(plot_risk_return(hypotheses, backtest_results, charts_dir))

    created.append(plot_correlation_heatmap(hypotheses, backtest_results, charts_dir))

    trace.record_tool_call("visualizer", "generate_charts", {"count": len(created)})
    return created
