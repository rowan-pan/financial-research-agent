"""
tools/fundamentals.py
Fetch earnings, sector performance, and company overviews via Alpha Vantage.
Enforces rate limiting: 5 requests/minute on the free tier.
Returns plain data — no reasoning, no formatting.
"""

import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

CACHE_DIR = Path(__file__).parent.parent / "data"
CACHE_DIR.mkdir(exist_ok=True)

BASE_URL = "https://www.alphavantage.co/query"
_last_request_times: list[float] = []


def _rate_limited_get(params: dict) -> dict:
    """Enforce 5 requests/minute for Alpha Vantage free tier."""
    global _last_request_times
    now = time.time()
    _last_request_times = [t for t in _last_request_times if now - t < 60]
    if len(_last_request_times) >= 5:
        wait = 60 - (now - _last_request_times[0])
        if wait > 0:
            time.sleep(wait)
    params["apikey"] = os.getenv("ALPHA_VANTAGE_KEY")
    response = requests.get(BASE_URL, params=params, timeout=15)
    _last_request_times.append(time.time())
    return response.json()


def fetch_company_overview(ticker: str) -> dict:
    """
    Fetch company overview: sector, PE, EPS, revenue, profit margin.
    """
    cache_file = CACHE_DIR / f"av_overview_{ticker}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    data = _rate_limited_get({"function": "OVERVIEW", "symbol": ticker})
    result = {
        "ticker": ticker,
        "name": data.get("Name", ""),
        "sector": data.get("Sector", ""),
        "industry": data.get("Industry", ""),
        "pe_ratio": data.get("PERatio"),
        "forward_pe": data.get("ForwardPE"),
        "eps": data.get("EPS"),
        "revenue_ttm": data.get("RevenueTTM"),
        "profit_margin": data.get("ProfitMargin"),
        "analyst_target": data.get("AnalystTargetPrice"),
        "beta": data.get("Beta"),
    }

    cache_file.write_text(json.dumps(result, indent=2))
    return result


def fetch_earnings(ticker: str) -> dict:
    """
    Fetch quarterly and annual earnings surprises.
    """
    cache_file = CACHE_DIR / f"av_earnings_{ticker}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    data = _rate_limited_get({"function": "EARNINGS", "symbol": ticker})
    result = {
        "ticker": ticker,
        "quarterly": data.get("quarterlyEarnings", [])[:8],
        "annual": data.get("annualEarnings", [])[:4],
    }

    cache_file.write_text(json.dumps(result, indent=2))
    return result


def fetch_sector_performance() -> dict:
    """
    Fetch real-time sector performance snapshot (US market).
    Returns performance over 1d, 5d, 1m, 3m, ytd, 1y per sector.
    """
    cache_file = CACHE_DIR / "av_sector_performance.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    data = _rate_limited_get({"function": "SECTOR"})
    result = {
        "1d": data.get("Rank A: Real-Time Performance", {}),
        "5d": data.get("Rank B: 1 Day Performance", {}),
        "1m": data.get("Rank C: 5 Day Performance", {}),
        "3m": data.get("Rank D: 1 Month Performance", {}),
        "ytd": data.get("Rank E: 3 Month Performance", {}),
        "1y": data.get("Rank F: Year-to-Date (YTD) Performance", {}),
    }

    cache_file.write_text(json.dumps(result, indent=2))
    return result
