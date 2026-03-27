"""
app.py
Streamlit web UI for the financial research agent.
Run locally: streamlit run app.py
Hosted on Streamlit Community Cloud (auto-deploys from main branch).
"""

import os
from pathlib import Path

import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Financial Research Agent",
    page_icon="📈",
    layout="wide",
)

# ── Sidebar: API keys + settings ─────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Settings")

    st.subheader("API Keys")
    anthropic_key = st.text_input(
        "Anthropic API Key", type="password",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        help="Get yours at console.anthropic.com"
    )
    newsapi_key = st.text_input(
        "NewsAPI Key", type="password",
        value=os.getenv("NEWSAPI_KEY", ""),
        help="Get yours at newsapi.org"
    )
    alpha_key = st.text_input(
        "Alpha Vantage Key", type="password",
        value=os.getenv("ALPHA_VANTAGE_KEY", ""),
        help="Get yours at alphavantage.co"
    )

    st.divider()
    st.subheader("Model Quality")
    quality = st.radio(
        "Reasoning model",
        options=["standard", "high"],
        format_func=lambda x: "Standard — claude-sonnet-4-6 (faster, cheaper)" if x == "standard"
                               else "High — claude-opus-4-6 (slower, more thorough)",
        index=0,
    )

    st.divider()
    commit_report = st.checkbox("Auto-commit report to git after completion", value=False)

    st.divider()
    st.caption("Built with [Claude](https://anthropic.com) · [GitHub](https://github.com/rowan-pan/financial-research-agent)")


# ── Main area ─────────────────────────────────────────────────────────────────
st.title("📈 Financial Research Agent")
st.caption("From noisy market signals to structured, defensible investment logic.")

st.divider()

col1, col2 = st.columns([3, 1])
with col1:
    topic = st.text_input(
        "Investment theme (optional)",
        placeholder="e.g. AI chip demand, rising interest rates, energy transition ...",
        help="Leave blank to auto-discover the top trending theme from the last 15 days of news.",
    )
with col2:
    st.write("")
    st.write("")
    run_button = st.button("▶ Run Analysis", type="primary", use_container_width=True)

st.divider()

# ── Run pipeline ──────────────────────────────────────────────────────────────
if run_button:
    # Validate keys
    missing = []
    if not anthropic_key:
        missing.append("Anthropic API Key")
    if not newsapi_key:
        missing.append("NewsAPI Key")
    if not alpha_key:
        missing.append("Alpha Vantage Key")
    if missing:
        st.error(f"Missing API keys: {', '.join(missing)}. Enter them in the sidebar.")
        st.stop()

    # Inject keys into environment for this run
    os.environ["ANTHROPIC_API_KEY"] = anthropic_key
    os.environ["NEWSAPI_KEY"] = newsapi_key
    os.environ["ALPHA_VANTAGE_KEY"] = alpha_key

    status_box = st.empty()
    progress = st.progress(0)
    steps = [
        "Detecting theme...",
        "Generating hypotheses...",
        "Finding precedents...",
        "Backtesting...",
        "Synthesizing report...",
        "Generating charts...",
        "Writing report...",
    ]
    step_idx = [0]

    def on_status(msg: str):
        status_box.info(f"⏳ {msg}")
        pct = min(int(step_idx[0] / len(steps) * 100), 95)
        progress.progress(pct)
        step_idx[0] += 1

    from pipeline import run_pipeline
    import subprocess

    with st.spinner("Running pipeline..."):
        report_dir = run_pipeline(
            topic=topic.strip() or None,
            quality=quality,
            on_status=on_status,
        )

    progress.progress(100)
    status_box.success("✅ Analysis complete!")

    # Auto-commit if requested
    if commit_report:
        from datetime import datetime
        theme_name = report_dir.name.split("_", 1)[1].replace("-", " ")
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        msg = f"Research report: {theme_name} ({date_str})"
        try:
            subprocess.run(["git", "add", str(report_dir)], check=True)
            subprocess.run(["git", "commit", "-m", msg], check=True)
            st.info(f"Committed to git: {msg}")
        except Exception as e:
            st.warning(f"Git commit skipped: {e}")

    # ── Display report ────────────────────────────────────────────────────────
    report_path = report_dir / "report.md"
    charts_dir = report_dir / "charts"

    st.divider()
    st.subheader("📄 Report")

    report_text = report_path.read_text()
    # Strip chart and execution trace sections for inline display (shown separately)
    display_text = report_text.split("\n\n---\n\n## Charts")[0]
    st.markdown(display_text)

    # Charts
    st.divider()
    st.subheader("📊 Charts")
    chart_files = sorted(charts_dir.glob("*.png")) if charts_dir.exists() else []
    if chart_files:
        cols = st.columns(min(len(chart_files), 3))
        for i, chart in enumerate(chart_files):
            with cols[i % 3]:
                st.image(str(chart), use_container_width=True, caption=chart.stem.replace("_", " ").title())
    else:
        st.caption("No charts generated.")

    # Execution trace
    st.divider()
    with st.expander("🔍 Execution Trace (Mermaid diagram)", expanded=False):
        if "## Execution Trace" in report_text:
            trace_section = report_text.split("## Execution Trace\n\n")[1]
            st.markdown(trace_section)

    # Download button
    st.divider()
    st.download_button(
        label="⬇ Download report.md",
        data=report_path.read_bytes(),
        file_name=f"{report_dir.name}_report.md",
        mime="text/markdown",
    )
