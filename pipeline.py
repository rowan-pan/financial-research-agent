"""
pipeline.py
Core pipeline logic shared by main.py (CLI) and app.py (Streamlit).
Orchestrates all agents and reporting steps. Returns the path to the report folder.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REASONING_MODEL = "claude-sonnet-4-6"
SYNTHESIS_MODEL = "claude-sonnet-4-6"

REPORTS_DIR = Path(__file__).parent / "reports"


def _slug(text: str) -> str:
    """Convert theme text to a safe directory slug."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return s[:40]


def run_pipeline(
    topic: str | None = None,
    quality: str = "standard",
    on_status: callable = print,
) -> Path:
    """
    Run the full research pipeline.

    Args:
        topic: optional theme string; if None, auto-discovers from news
        quality: "standard" (Sonnet) or "high" (Opus)
        on_status: callback for status updates, receives a string message

    Returns:
        Path to the generated report folder
    """
    from reporting.tracer import ExecutionTrace
    from agents.theme_detector import detect_theme
    from agents.hypothesis_generator import generate_hypotheses
    from agents.precedent_finder import find_all_precedents
    from agents.backtester import backtest_all
    from reporting.synthesizer import synthesize_report
    from reporting.visualizer import generate_all_charts

    reasoning_model = "claude-opus-4-6" if quality == "high" else REASONING_MODEL
    synthesis_model = "claude-opus-4-6" if quality == "high" else SYNTHESIS_MODEL

    trace = ExecutionTrace()

    # ── Step 1: Theme detection ──────────────────────────────────────────────
    if topic:
        on_status(f"Using supplied topic: {topic}")
        theme = {
            "theme": topic,
            "slug": _slug(topic),
            "summary": f"User-supplied theme: {topic}",
            "affected_tickers": [],
            "affected_sectors": [],
            "sentiment": "unknown",
            "confidence": "high",
        }
        trace.set_theme(topic)
    else:
        on_status("Detecting theme from market signals...")
        theme = detect_theme(model=reasoning_model, trace=trace)
        on_status(f"Theme identified: {theme['theme']}")

    # ── Step 2: Hypothesis generation ────────────────────────────────────────
    on_status("Generating investment hypotheses...")
    hypotheses = generate_hypotheses(theme=theme, model=reasoning_model, trace=trace)
    on_status(f"Generated {len(hypotheses)} hypotheses: {', '.join(h['ticker'] for h in hypotheses)}")

    # ── Step 3: Precedent finding ─────────────────────────────────────────────
    on_status("Finding historical precedents...")
    precedents = find_all_precedents(hypotheses=hypotheses, theme=theme, model=reasoning_model, trace=trace)

    # ── Step 4: Backtesting ───────────────────────────────────────────────────
    on_status("Backtesting historical episodes...")
    backtest_results = backtest_all(hypotheses=hypotheses, precedents=precedents, model=reasoning_model, trace=trace)

    # ── Step 5: Synthesis ─────────────────────────────────────────────────────
    on_status("Synthesizing report...")
    now = datetime.utcnow()
    scan_end = now.strftime("%B %-d, %Y")
    scan_start = (now - timedelta(days=15)).strftime("%B %-d, %Y")
    narrative = synthesize_report(
        theme=theme,
        hypotheses=hypotheses,
        precedents=precedents,
        backtest_results=backtest_results,
        model=synthesis_model,
        trace=trace,
        scan_start=scan_start,
        scan_end=scan_end,
    )

    # ── Step 6: Create report folder ─────────────────────────────────────────
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    slug = theme.get("slug") or _slug(theme["theme"])
    report_dir = REPORTS_DIR / f"{date_str}_{slug}"
    report_dir.mkdir(parents=True, exist_ok=True)
    charts_dir = report_dir / "charts"

    # ── Step 7: Generate charts ───────────────────────────────────────────────
    on_status("Generating charts...")
    generate_all_charts(
        hypotheses=hypotheses,
        precedents=precedents,
        backtest_results=backtest_results,
        charts_dir=charts_dir,
        trace=trace,
    )

    # ── Step 8: Assemble report.md ────────────────────────────────────────────
    on_status("Writing report...")
    title = f"# {theme['theme'].title()}\n*Generated {date_str} · {trace.summary_line()}*\n\n"

    chart_section = (
        "\n\n---\n\n## Charts\n\n"
        "![Episode Price History](charts/episodes_indexed.png)\n\n"
        "![Return Distribution](charts/return_distribution.png)\n\n"
        "![Risk / Return](charts/risk_return.png)\n\n"
        "![Hypothesis Performance Summary](charts/correlation_heatmap.png)\n"
    )

    sources_section = "\n\n---\n\n" + trace.sources_section() if trace.sources else ""
    execution_section = "\n\n---\n\n## Execution Trace\n\n" + trace.to_mermaid() + "\n"

    report_md = title + narrative + chart_section + sources_section + execution_section
    (report_dir / "report.md").write_text(report_md)

    on_status(f"Report saved to: {report_dir}")
    return report_dir
