"""
tools/edgar.py
Fetch SEC EDGAR filings (8-K, 10-K) for US-listed companies.
No API key required. Returns plain data — no reasoning, no formatting.
"""

import json
import time
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).parent.parent / "data"
CACHE_DIR.mkdir(exist_ok=True)

HEADERS = {"User-Agent": "financial-research-agent contact@example.com"}
EDGAR_BASE = "https://efts.sec.gov/LATEST/search-index"
COMPANY_BASE = "https://data.sec.gov/submissions"


def _get_cik(ticker: str) -> str | None:
    """Resolve ticker to SEC CIK number."""
    cache_file = CACHE_DIR / f"cik_{ticker}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text()).get("cik")

    url = "https://efts.sec.gov/LATEST/search-index?q=%22{}%22&dateRange=custom&startdt=2020-01-01&forms=10-K".format(ticker)
    resp = requests.get(
        "https://www.sec.gov/cgi-bin/browse-edgar",
        params={"action": "getcompany", "company": "", "CIK": ticker, "type": "", "dateb": "", "owner": "include", "count": "1", "search_text": ""},
        headers=HEADERS,
        timeout=15,
    )
    # Parse CIK from redirect URL or response
    if resp.history:
        for r in resp.history:
            location = r.headers.get("Location", "")
            if "/cgi-bin/browse-edgar?action=getcompany&CIK=" in location:
                cik = location.split("CIK=")[1].split("&")[0].lstrip("0")
                cache_file.write_text(json.dumps({"cik": cik}))
                return cik
    return None


def fetch_recent_filings(ticker: str, form_type: str = "8-K", count: int = 5) -> list[dict]:
    """
    Fetch recent SEC filings for a ticker.
    form_type: "8-K" (material events) or "10-K" (annual report)
    Returns list of {form, filingDate, reportDate, accessionNumber, primaryDocument, description}
    """
    cache_file = CACHE_DIR / f"edgar_{ticker}_{form_type}_{count}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    # Use EDGAR full-text search
    url = "https://efts.sec.gov/LATEST/search-index"
    params = {
        "q": f'"{ticker}"',
        "forms": form_type,
        "dateRange": "custom",
        "startdt": "2023-01-01",
    }
    resp = requests.get(
        "https://efts.sec.gov/LATEST/search-index",
        params={"q": ticker, "forms": form_type},
        headers=HEADERS,
        timeout=15,
    )

    # Fall back to company submissions API
    cik_resp = requests.get(
        f"https://data.sec.gov/submissions/CIK{ticker.upper()}.json",
        headers=HEADERS,
        timeout=15,
    )

    filings = []
    if cik_resp.ok:
        data = cik_resp.json()
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        descriptions = recent.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if form == form_type and len(filings) < count:
                filings.append({
                    "form": form,
                    "filingDate": dates[i] if i < len(dates) else "",
                    "accessionNumber": accessions[i] if i < len(accessions) else "",
                    "primaryDocument": descriptions[i] if i < len(descriptions) else "",
                })

    cache_file.write_text(json.dumps(filings, indent=2))
    return filings


def fetch_filing_summary(ticker: str, form_type: str = "8-K") -> str:
    """
    Return a plain-text summary of recent filings suitable for Claude to reason over.
    """
    filings = fetch_recent_filings(ticker, form_type)
    if not filings:
        return f"No recent {form_type} filings found for {ticker}."

    lines = [f"Recent {form_type} filings for {ticker}:"]
    for f in filings:
        lines.append(f"  - {f['filingDate']}: {f.get('primaryDocument', 'N/A')} (Accession: {f['accessionNumber']})")
    return "\n".join(lines)
