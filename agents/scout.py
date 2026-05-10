"""Scout agent — deterministic data extraction node."""
import json
from datetime import datetime
from typing import Any

from tools.api_tools import fetch_url
from tools.csv_tools import read_csv, infer_schema

def _flatten_json(raw: Any) -> list[dict]:
    """
    Normalize any JSON response into a flat list of dicts.
    Handles:
      - top-level list
      - dict with a list under a common envelope key
      - nested time-series dicts (Alpha Vantage style)
      - single dict record
    """
    if isinstance(raw, list):
        return raw

    if isinstance(raw, dict):
        # Common envelope keys
        for key in ("data", "results", "items", "records", "rows"):
            if isinstance(raw.get(key), list):
                return raw[key]

        # Time-series style: dict of dicts (Alpha Vantage, etc.)
        first_non_meta = {
            k: v for k, v in raw.items()
            if isinstance(v, dict) and k != "Meta Data"
        }
        if first_non_meta:
            key = next(iter(first_non_meta))
            records = []
            for timestamp, fields in raw[key].items():
                row = {"timestamp": timestamp}
                for field_key, field_val in fields.items():
                    clean_key = field_key.split(". ", 1)[-1].replace(" ", "_")
                    row[clean_key] = field_val
                records.append(row)
            return records

        # Single dict — wrap as one record
        return [raw]

    return []

def scout_node(state: dict) -> dict:
    """Extract raw data and detect schema."""
    source_type = state["source_type"]
    source_config = state["source_config"]
    audit_log = list(state.get("audit_log", []))
 
    raw_data: Any = None
    raw_schema: dict = {}

    try:
        if source_type == "url_api":
            raw_json = fetch_url(
                url=source_config["url"],
                headers=source_config.get("headers", {}),
                params=source_config.get("params", {}),
            )
            raw_data = _flatten_json(raw_json)
            raw_schema = infer_schema(raw_data) if raw_data else {}

        elif source_type == "csv":
            raw_data = read_csv(source_config["path"])
            raw_schema = infer_schema(raw_data)

        elif source_type == "rdbms":
            from sqlalchemy import create_engine, text
            conn_str = source_config.get("connection_string")
            query = source_config.get("query") or f"SELECT * FROM {source_config['table']}"
            engine = create_engine(conn_str)
            with engine.connect() as conn:
                result = conn.execute(text(query))
                raw_data = [dict(row._mapping) for row in result]
            raw_schema = infer_schema(raw_data) if raw_data else {}

        else:
            raise ValueError(f"Unknown source_type: {source_type!r}")

        audit_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "agent": "Scout",
            "action": "extract",
            "summary": f"Extracted {len(raw_data)} records via {source_type}. Schema: {list(raw_schema.keys())}",
        })

    except Exception as exc:
        audit_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "agent": "Scout",
            "action": "extract_error",
            "summary": str(exc),
        })
        raise

    return {
        "raw_data": raw_data,
        "raw_schema": raw_schema,
        "audit_log": audit_log,
    }
