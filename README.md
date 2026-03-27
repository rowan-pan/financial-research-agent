# Financial Research Agent

An autonomous financial research agent that identifies and defends investment opportunities using real market signals. The agent moves from noisy, fast-moving financial information to structured, defensible investment logic — the kind of output a portfolio manager could act on.

## Pipeline

```
Input (topic, auto-discover)
  → Signal Scan       (tools/)         — fetch news, prices, filings
  → Theme Detection   (agents/)        — identify top trending financial theme
  → Hypothesis Gen    (agents/)        — generate 3–5 structured investment hypotheses
  → Precedent Finding (agents/)        — identify analogous historical episodes (qualitative)
  → Backtesting       (agents/)        — measure actual returns across those episodes (quantitative)
  → Synthesis         (reporting/)     — write markdown narrative
  → Visualization     (reporting/)     — generate charts + execution trace diagram
  → Report saved to   reports/<date>_<theme>/
```

Within each agent step, Claude runs a **tool-use loop** — it decides what additional data it needs, calls back into `tools/`, and iterates until it has enough to reason. The execution trace of every Claude call and tool invocation is recorded and rendered as a Mermaid diagram embedded in the report.

## Output

Each run produces a folder under `reports/`:

```
reports/2026-03-27_ai-chip-demand/
├── report.md                   ← full narrative + sources cited + Mermaid execution diagram
└── charts/
    ├── episodes_indexed.png    ← historical episodes overlaid per hypothesis, day 0 = trigger
    ├── return_distribution.png ← grouped bar chart of returns across all hypotheses
    ├── risk_return.png         ← risk/return scatter (avg drawdown vs median return)
    └── correlation_heatmap.png ← hypothesis performance summary (win rate, return, EV, n)
```

Reports are committed to git. Raw data cache (`data/`) is gitignored.

## Usage

### CLI
```bash
# Auto-discover the top trending financial theme from recent news
python main.py

# Analyze a specific theme
python main.py --topic "AI chip demand"

# Use Opus for higher quality reasoning and synthesis (default: Sonnet)
python main.py --topic "AI chip demand" --quality high

# Auto-commit the report to git after completion
python main.py --topic "AI chip demand" --commit
```

### Web UI
```bash
streamlit run app.py
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in your API keys in .env
```

## API Keys Required

| Key | Source | Used for |
|-----|--------|----------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | All agent reasoning |
| `NEWSAPI_KEY` | [newsapi.org](https://newsapi.org) | 15-day headline fetch |
| `ALPHA_VANTAGE_KEY` | [alphavantage.co](https://www.alphavantage.co) | Fundamentals, earnings |

yfinance and SEC EDGAR require no API key.

## Project Structure

```
financial-research-agent/
├── main.py                         # CLI entry point
├── app.py                          # Streamlit web UI entry point
├── pipeline.py                     # Core pipeline logic (shared by main.py + app.py)
├── requirements.txt
├── .env.example
│
├── agents/                         # Claude-powered reasoning modules
│   ├── _utils.py                   # Shared: JSON parsing, API retry-with-backoff
│   ├── theme_detector.py           # Identify top financial theme from signals
│   ├── hypothesis_generator.py     # Generate structured investment hypotheses
│   ├── precedent_finder.py         # Find analogous historical episodes
│   └── backtester.py               # Quantify returns across those episodes
│
├── tools/                          # Data fetching (exposed as Claude tool calls)
│   ├── news.py                     # NewsAPI — 15-day headlines
│   ├── market_data.py              # yfinance — OHLCV, sector ETF movers
│   ├── fundamentals.py             # Alpha Vantage — earnings, financials
│   └── edgar.py                    # SEC EDGAR — 8-K/10-K filings
│
├── reporting/                      # Output generation
│   ├── synthesizer.py              # Claude: write markdown narrative
│   ├── visualizer.py               # matplotlib + seaborn: market charts (PNG)
│   └── tracer.py                   # Record execution trace → Mermaid diagram + sources
│
├── prompts/                        # Prompt templates (plain .md files)
│   ├── theme_detection.md
│   ├── hypothesis_generation.md
│   ├── precedent_search.md
│   ├── backtesting.md
│   └── synthesis.md
│
├── reports/                        # Generated reports — committed to git
└── data/                           # Cached API responses — gitignored
```

## Data Sources

- [yfinance](https://github.com/ranaroussi/yfinance) — historical OHLCV, sector ETF data
- [NewsAPI](https://newsapi.org/) — financial news headlines (15-day window)
- [Alpha Vantage](https://www.alphavantage.co/) — fundamentals, earnings signals
- [SEC EDGAR](https://www.sec.gov/edgar/) — 8-K and 10-K filings

## Roadmap

- **Ticker-first mode** — enter a stock ticker to identify which macro themes are driving it, rather than starting from a theme
