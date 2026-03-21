"""CSV reader tool (US1)."""
import pandas as pd
from typing import Any


def read_csv(path: str) -> list[dict]:
    """Read a CSV file and return as a list of dicts."""
    df = pd.read_csv(path)
    return df.to_dict(orient="records")


def infer_schema(records: list[dict]) -> dict:
    """Infer column names and types from a list of records."""
    if not records:
        return {}
    sample = records[0]
    return {col: type(val).__name__ for col, val in sample.items()}
