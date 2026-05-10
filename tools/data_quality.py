"""Data quality validation utilities (US22).

Validates dataset quality before processing by checking:
- missing values
- duplicate rows
- column data type consistency
- summary metrics for the dataset
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd


def _normalize_type_name(value: Any) -> str:
    """Return a simple, stable type name for validation reporting."""
    if pd.isna(value):
        return "missing"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    return type(value).__name__


def _expected_type_for_series(series: pd.Series) -> str:
    """Infer expected type from the non-missing values in a column."""
    non_missing = series.dropna()
    if non_missing.empty:
        return "unknown"

    type_counts = non_missing.map(_normalize_type_name).value_counts()
    expected = str(type_counts.idxmax())

    # Treat int + float together as numeric to avoid false invalids.
    if expected in {"int", "float"}:
        return "numeric"
    return expected


def validate_dataframe_quality(df: pd.DataFrame, expected_schema: dict | None = None) -> dict:
    """Validate a pandas DataFrame and return a JSON-serializable quality report.

    Args:
        df: Dataset to validate.
        expected_schema: Optional mapping of column -> expected type. If not provided,
            the validator infers the expected type from majority non-null values.

    Returns:
        Dictionary containing missing values, duplicate rows, data type validation,
        and a compact validation summary.
    """
    expected_schema = expected_schema or {}
    total_rows = int(len(df))
    total_columns = int(len(df.columns))

    missing_by_column = {
        col: int(df[col].isna().sum()) for col in df.columns
    }
    total_missing_values = int(sum(missing_by_column.values()))

    duplicate_mask = df.duplicated(keep=False)
    duplicate_row_count = int(df.duplicated().sum())
    duplicate_row_indices = [int(i) for i in df.index[duplicate_mask].tolist()[:25]]

    column_type_checks = {}
    invalid_type_total = 0

    for col in df.columns:
        series = df[col]
        expected_type = expected_schema.get(col) or _expected_type_for_series(series)
        invalid_examples = []
        invalid_count = 0

        for idx, value in series.items():
            actual_type = _normalize_type_name(value)
            if actual_type == "missing":
                continue

            is_valid = True
            if expected_type == "numeric":
                is_valid = actual_type in {"int", "float"}
            elif expected_type not in {"unknown", "Any", "any"}:
                is_valid = actual_type == expected_type

            if not is_valid:
                invalid_count += 1
                if len(invalid_examples) < 5:
                    invalid_examples.append({
                        "row_index": int(idx),
                        "value": str(value),
                        "actual_type": actual_type,
                    })

        invalid_type_total += invalid_count
        column_type_checks[col] = {
            "expected_type": expected_type,
            "actual_pandas_dtype": str(series.dtype),
            "invalid_count": int(invalid_count),
            "invalid_examples": invalid_examples,
        }

    has_issues = bool(total_missing_values or duplicate_row_count or invalid_type_total)

    return {
        "validated_at_utc": datetime.utcnow().isoformat(),
        "row_count": total_rows,
        "column_count": total_columns,
        "missing_values": {
            "total_missing_values": total_missing_values,
            "missing_by_column": missing_by_column,
        },
        "duplicate_rows": {
            "duplicate_row_count": duplicate_row_count,
            "duplicate_row_indices_sample": duplicate_row_indices,
        },
        "column_type_validation": column_type_checks,
        "summary": {
            "status": "failed" if has_issues else "passed",
            "has_missing_values": total_missing_values > 0,
            "has_duplicate_rows": duplicate_row_count > 0,
            "has_invalid_data_types": invalid_type_total > 0,
            "total_issues": int(total_missing_values + duplicate_row_count + invalid_type_total),
        },
    }


def validate_dataset_quality(records: list[dict], expected_schema: dict | None = None) -> dict:
    """Validate list-of-dict records used by the DataWeave pipeline."""
    df = pd.DataFrame(records or [])
    return validate_dataframe_quality(df, expected_schema=expected_schema)
