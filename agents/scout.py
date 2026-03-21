"""Scout agent — deterministic data extraction node (US1, US2)."""
import json
from datetime import datetime
from typing import Any

from tools.api_tools import fetch_alpha_vantage
from tools.csv_tools import read_csv, infer_schema


def _flatten_alpha_vantage(raw: dict) -> list[dict]:
    """Flatten nested Alpha Vantage JSON into a list of records."""
    # Find the first key that contains time-series data
    for key, value in raw.items():
        if isinstance(value, dict) and key != "Meta Data":
            records = []
            for timestamp, fields in value.items():
                row = {"timestamp": timestamp}
                # Strip numeric prefixes like "1. open" -> "open"
                for field_key, field_val in fields.items():
                    clean_key = field_key.split(". ", 1)[-1].replace(" ", "_")
                    row[clean_key] = field_val
                records.append(row)
            return records
    return []


def scout_node(state: dict) -> dict:
    """Extract raw data and detect schema. Updates state with raw_data and raw_schema."""
    source_type = state["source_type"]
    source_config = state["source_config"]
    audit_log = list(state.get("audit_log", []))

    raw_data: Any = None
    raw_schema: dict = {}

    try:
        if source_type == "api":
            raw_json = fetch_alpha_vantage(**source_config)
            raw_data = _flatten_alpha_vantage(raw_json)
            raw_schema = infer_schema(raw_data) if raw_data else {}

        elif source_type == "csv":
            raw_data = read_csv(source_config["path"])
            raw_schema = infer_schema(raw_data)

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
