# Financial Research Agent

An autonomous financial research agent that identifies and defends investment opportunities using real market signals.

## What it does

1. **Scans** the latest 15 days of financial news and market data to detect how markets are reacting to trends and events
2. **Generates** structured investment hypotheses — reasoned bets on how specific assets or sectors might move
3. **Finds** historical market scenarios that resemble the current pattern as supporting evidence
4. **Synthesizes** a clear investment recommendation with rationale, supporting data, and risk considerations

## Data Sources

- [yfinance](https://github.com/ranaroussi/yfinance) — historical OHLCV and market data
- [NewsAPI](https://newsapi.org/) — financial news headlines
- [Alpha Vantage](https://www.alphavantage.co/) — market data and fundamentals
- [SEC EDGAR](https://www.sec.gov/edgar/) — regulatory filings (8-K, 10-K)

## Usage

```bash
# Auto-discover trending theme
python main.py

# Analyze a specific theme
python main.py --topic "AI chip demand"

# Analyze and commit the report to git
python main.py --topic "AI chip demand" --commit
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in your API keys in .env
```

## Output

Reports are saved to `reports/YYYY-MM-DD_<theme-slug>.md`.
