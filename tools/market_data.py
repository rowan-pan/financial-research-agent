"""
tools/market_data.py
Fetch market prices, ETF data, and fundamentals via yfinance.
Returns plain data — no reasoning, no formatting.
"""

import json
from pathlib import Path

import pandas as pd
import yfinance as yf

CACHE_DIR = Path(__file__).parent.parent / "data"
CACHE_DIR.mkdir(exist_ok=True)

SECTOR_ETFS = ["XLK", "XLE", "XLF", "XLV", "XLI", "XLY", "XLP", "XLB", "XLU", "XLRE", "XLC"]

SECTOR_ETF_MAP = {
    "Financial Services": "XLF",
    "Technology": "QQQ",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Healthcare": "XLV",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Utilities": "XLU",
    "Real Estate": "VNQ",
    "Materials": "XLB",
    "Communication Services": "XLC",
}


def fetch_sector_etf(ticker: str) -> str | None:
    """
    Return the most appropriate sector ETF for a ticker based on its yfinance sector
    classification, or None if the sector is unknown or unmapped.
    Used by the backtester to select the second factor in the OLS market model.
    """
    try:
        sector = yf.Ticker(ticker).info.get("sector", "")
        return SECTOR_ETF_MAP.get(sector)
    except Exception:
        return None


def fetch_price_history(ticker: str, period: str = "2y") -> list[dict]:
    """
    Fetch OHLCV history for a ticker.
    period: yfinance period string e.g. "1y", "2y", "5y"
    Returns list of {date, open, high, low, close, volume}.
    """
    cache_file = CACHE_DIR / f"prices_{ticker}_{period}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if df.empty:
        return []

    # Flatten MultiIndex columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    records = [
        {
            "date": str(idx.date()),
            "open": round(float(row["Open"]), 4),
            "high": round(float(row["High"]), 4),
            "low": round(float(row["Low"]), 4),
            "close": round(float(row["Close"]), 4),
            "volume": int(row["Volume"]),
        }
        for idx, row in df.iterrows()
    ]

    cache_file.write_text(json.dumps(records, indent=2))
    return records


def fetch_etf_movers(days: int = 15) -> list[dict]:
    """
    Fetch recent performance of all sector ETFs.
    Returns list of {ticker, return_pct, avg_volume_ratio} sorted by absolute return.
    """
    cache_file = CACHE_DIR / f"etf_movers_{days}d.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    results = []
    for ticker in SECTOR_ETFS:
        df = yf.download(ticker, period="1mo", auto_adjust=True, progress=False)
        if df.empty or len(df) < days:
            continue

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        recent = df.tail(days)
        total_return = (recent["Close"].iloc[-1] / recent["Close"].iloc[0] - 1) * 100
        avg_vol = recent["Volume"].mean()
        prior_vol = df.iloc[: -days]["Volume"].mean() if len(df) > days else avg_vol
        vol_ratio = avg_vol / prior_vol if prior_vol > 0 else 1.0

        results.append(
            {
                "ticker": ticker,
                "return_pct": round(float(total_return), 2),
                "avg_volume_ratio": round(float(vol_ratio), 2),
            }
        )

    results.sort(key=lambda x: abs(x["return_pct"]), reverse=True)
    cache_file.write_text(json.dumps(results, indent=2))
    return results


def fetch_ticker_info(ticker: str) -> dict:
    """
    Fetch summary info for a ticker: sector, industry, market cap, P/E, 52-week range.
    """
    cache_file = CACHE_DIR / f"info_{ticker}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    info = yf.Ticker(ticker).info
    summary = {
        "ticker": ticker,
        "name": info.get("longName", ticker),
        "sector": info.get("sector", ""),
        "industry": info.get("industry", ""),
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "analyst_target": info.get("targetMeanPrice"),
    }

    cache_file.write_text(json.dumps(summary, indent=2))
    return summary


def fetch_ticker_news(ticker: str) -> list[dict]:
    """
    Fetch recent news for a specific ticker via yfinance.
    Returns list of {title, publisher, link, providerPublishTime}.
    """
    cache_file = CACHE_DIR / f"ticker_news_{ticker}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    raw = yf.Ticker(ticker).news or []
    articles = [
        {
            "title": a.get("title", ""),
            "publisher": a.get("publisher", ""),
            "link": a.get("link", ""),
            "publishedAt": a.get("providerPublishTime", ""),
        }
        for a in raw
    ]

    cache_file.write_text(json.dumps(articles, indent=2))
    return articles


def fetch_price_window(ticker: str, start: str, end: str) -> list[dict]:
    """
    Fetch OHLCV for a specific date window (used by backtester).
    start/end: "YYYY-MM-DD"
    """
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        return []

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # After flattening, duplicate column names can cause row["Close"] to return a
    # Series instead of a scalar. Use the column Series directly to avoid this.
    closes = df["Close"]
    volumes = df["Volume"]
    if isinstance(closes, pd.DataFrame):
        closes = closes.iloc[:, 0]
    if isinstance(volumes, pd.DataFrame):
        volumes = volumes.iloc[:, 0]

    return [
        {
            "date": str(idx.date()),
            "close": round(float(closes.loc[idx]), 4),
            "volume": int(volumes.loc[idx]) if not pd.isna(volumes.loc[idx]) else 0,
        }
        for idx in df.index
    ]
