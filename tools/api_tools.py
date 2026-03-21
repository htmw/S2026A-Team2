"""Alpha Vantage API connector (US1)."""
import os
import requests
from typing import Any


ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"


def fetch_alpha_vantage(function: str, symbol: str, **kwargs) -> Any:
    """Fetch data from Alpha Vantage. Returns parsed JSON."""
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise ValueError("ALPHA_VANTAGE_API_KEY not set in environment")

    params = {
        "function": function,
        "symbol": symbol,
        "apikey": api_key,
        **kwargs,
    }
    resp = requests.get(ALPHA_VANTAGE_BASE, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # Surface API-level errors
    if "Error Message" in data:
        raise ValueError(f"Alpha Vantage error: {data['Error Message']}")
    if "Note" in data:
        raise RuntimeError(f"Alpha Vantage rate limit: {data['Note']}")

    return data
