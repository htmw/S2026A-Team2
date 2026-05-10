"""Alpha Vantage API connector (US1)."""
import os
import requests
from typing import Any

def fetch_url(url: str, headers: dict = None, params: dict = None) -> Any:
    """
    Fetch any external REST API endpoint that returns JSON.
    Handles top-level list or dict responses.
    """
    resp = requests.get(url, headers=headers or {}, params=params or {}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data
 
