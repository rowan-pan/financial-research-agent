# CLAUDE.md — Financial Research Agent

## Project Purpose

Autonomous financial research agent that scans the last 15 days of market signals and news, generates structured investment hypotheses for US equities and sector ETFs, finds historical precedents, backtests them quantitatively, and synthesizes a markdown report a portfolio manager could act on.

## Tech Stack

- **Python 3.11+**
- **Anthropic SDK** (`anthropic`) — claude-sonnet-4-6 by default; claude-opus-4-6 via `--quality high`
- **yfinance** — historical OHLCV, fundamentals, sector ETF data (no API key required)
- **NewsAPI** (`newsapi-python`) — 15-day cross-market headline fetch by topic/keyword
- **Alpha Vantage** — earnings estimates, sector snapshots, economic indicators
- **SEC EDGAR** — 8-K/10-K filings via public REST API (no key required)
- **matplotlib** — chart generation (PNG files)
- **Streamlit** — web UI (`app.py`), hosted on Streamlit Community Cloud
- **python-dotenv** — API key management via `.env`

## Architecture

### Separation of concerns — strictly enforced

| Folder/File | Role | Claude involved? |
|-------------|------|-----------------|
| `tools/` | Fetch raw data only. No reasoning, no formatting. | No |
| `agents/` | Reason over data. Each module wraps a Claude tool-use loop. | Yes |
| `agents/_utils.py` | Shared helpers: JSON fence-stripping, API retry-with-backoff. | No |
| `reporting/` | Generate output (markdown, charts, Mermaid diagram, sources). | Yes (synthesizer only) |
| `prompts/` | Prompt templates as plain `.md` files. No logic. | N/A |
| `pipeline.py` | Core pipeline logic. Called by both `main.py` and `app.py`. | No |
| `main.py` | CLI entry point. Parses args, calls `pipeline.py`. | No |
| `app.py` | Streamlit web UI. Renders interface, calls `pipeline.py`. | No |

**Never put data-fetching logic in `agents/`. Never put reasoning logic in `tools/`.**

### Claude tool-use loop pattern

Every agent module follows this pattern:
1. Build a list of available tools (pointing to functions in `tools/`)
2. Call `client.messages.create()` with `tools=` parameter
3. Loop: if response contains `tool_use` blocks, execute the tool, append result, call Claude again
4. Exit loop when `stop_reason == "end_turn"`
5. Parse and return structured output

### Model selection

Two model constants are defined in `pipeline.py` and passed into every agent and reporting module:

```python
REASONING_MODEL = "claude-sonnet-4-6"   # used by all agents
SYNTHESIS_MODEL = "claude-sonnet-4-6"   # used by reporting/synthesizer.py
```

When the user passes `--quality high` (CLI) or selects "High Quality" in the Streamlit UI, both constants switch to `"claude-opus-4-6"`. Default is Sonnet throughout. Model selection is always the user's decision — never escalate automatically. Do not hardcode model strings anywhere other than `pipeline.py`.

### Execution tracer

`reporting/tracer.py` exports an `ExecutionTrace` object instantiated in `pipeline.py` and passed through every agent and reporting call. Every Claude API call and tool invocation must be recorded on it. At the end of the run it renders a Mermaid flowchart embedded in `report.md` showing the full execution path.

## Pipeline Order

```
pipeline.py
  1. tools/news.py + tools/market_data.py + tools/edgar.py — fetch signals
  2. agents/theme_detector.py — identify theme (skipped if topic supplied)
  3. agents/hypothesis_generator.py — generate 3–5 structured hypotheses
  4. agents/precedent_finder.py — find analogous historical episodes (qualitative)
  5. agents/backtester.py — measure returns across those episodes (quantitative)
  6. reporting/synthesizer.py — write markdown narrative
  7. reporting/visualizer.py — generate PNG charts
  8. reporting/tracer.py — render Mermaid execution diagram into report.md
  9. Write report to reports/<YYYY-MM-DD>_<theme-slug>/
  10. git commit (if --commit flag or Streamlit toggle)
```

## Entry Points

### CLI (`main.py`)
```bash
python main.py                                          # auto-discover theme, Sonnet
python main.py --topic "AI chip demand"                 # specific topic, Sonnet
python main.py --topic "AI chip demand" --quality high  # use Opus
python main.py --topic "AI chip demand" --commit        # auto-commit report
```

### Web UI (`app.py`)
```bash
streamlit run app.py
```
Local Streamlit UI. Not hosted — run locally and share reports directly.

## Report Output Structure

```
reports/YYYY-MM-DD_<theme-slug>/
├── report.md                   ← narrative + sources cited + Mermaid execution diagram
└── charts/
    ├── episodes_indexed.png    ← historical episodes overlaid per hypothesis, day 0 = trigger
    ├── return_distribution.png ← grouped bar chart of returns across all hypotheses
    ├── risk_return.png         ← risk/return scatter (avg drawdown vs median return)
    └── correlation_heatmap.png ← hypothesis performance summary (win rate, return, EV, n)
```

- Report folders are **committed to git** (`reports/` is tracked)
- Raw data cache (`data/`) is **gitignored**
- Theme slug: lowercase, hyphens only, max 40 chars (e.g. `ai-chip-demand`)
- Auto-commit message format: `Research report: <theme> (<YYYY-MM-DD>)`

## Environment Variables

All API keys live in `.env` locally (gitignored). Never hardcode keys. Never commit `.env`.

```
ANTHROPIC_API_KEY=
NEWSAPI_KEY=
ALPHA_VANTAGE_KEY=
```

Load with:
```python
from dotenv import load_dotenv
import os
load_dotenv()
key = os.getenv("ANTHROPIC_API_KEY")
```

## Rate Limits

| API | Free tier limit | Mitigation |
|-----|----------------|------------|
| Alpha Vantage | 5 req/min, 500/day | Rate limiter in `tools/fundamentals.py`, cache responses in `data/` |
| NewsAPI | 100 req/day | Cache responses in `data/`, batch queries |
| Anthropic | Varies by tier | No special handling needed for single-user runs |

Always cache raw API responses in `data/` during development to avoid burning quota on repeated runs.

## Asset Scope

US equities and sector ETFs only (NYSE/NASDAQ). Sector ETF universe:
`XLK, XLE, XLF, XLV, XLI, XLY, XLP, XLB, XLU, XLRE, XLC`

Do not expand to crypto, FX, or fixed income without explicit instruction.

## Roadmap (not yet built)

- **Ticker-first mode** — user enters a stock ticker; agent identifies which macro themes are driving it rather than starting from a theme. Pipeline is identical from hypothesis generation onward.

## What Not To Do

- Do not add features beyond what is requested
- Do not add error handling for scenarios that cannot happen
- Do not mock API responses in production code paths
- Do not put prompt text inline in Python — always load from `prompts/`
- Do not make agents stateful — each agent function takes input, returns output, no side effects beyond the tracer
- Do not escalate models automatically — model selection is always the user's decision via `--quality` or the Streamlit toggle
- Do not commit `.env`, `data/`, or `__pycache__`
