"""Loader agent — deterministic data writer (US2).

Supports writing to:
  - CSV  (default, target_path ends in .csv)
  - JSON (target_path ends in .json)
  - SQLite    (target_db["type"] = "sqlite")
  - PostgreSQL (target_db["type"] = "postgres")
"""
import json
import os
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine


def _write_file(df: pd.DataFrame, target_path: str):
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    ext = os.path.splitext(target_path)[-1].lower()
    if ext == ".json":
        with open(target_path, "w") as f:
            json.dump(df.to_dict(orient="records"), f, indent=2, default=str)
    else:
        df.to_csv(target_path, index=False)


def _write_db(df: pd.DataFrame, target_db: dict):
    connection_string = target_db.get("connection_string")
    table = target_db.get("table", "etl_output")
    if_exists = target_db.get("if_exists", "replace")

    if not connection_string:
        db_type = target_db.get("type", "sqlite")
        if db_type == "sqlite":
            path = target_db.get("path", "etl_output.db")
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            connection_string = f"sqlite:///{path}"
        else:
            raise ValueError("postgres target_db requires a 'connection_string'.")

    engine = create_engine(connection_string)
    with engine.begin() as conn:
        df.to_sql(table, con=conn, if_exists=if_exists, index=False)


def loader_node(state: dict) -> dict:
    transformed_data = state.get("transformed_data", [])
    target_path = state.get("target_path", "")
    target_db = state.get("target_db") or {}
    audit_log = list(state.get("audit_log", []))

    if not transformed_data:
        raise ValueError("Loader received empty transformed_data.")

    df = pd.DataFrame(transformed_data)

    if target_db:
        db_type = target_db.get("type", "sqlite")
        table = target_db.get("table", "etl_output")
        _write_db(df, target_db)
        destination = f"{db_type} → table '{table}'"
    elif target_path:
        _write_file(df, target_path)
        destination = target_path
    else:
        raise ValueError("Loader requires either target_path or target_db.")

    audit_log.append({
        "timestamp": datetime.utcnow().isoformat(),
        "agent": "Loader",
        "action": "load",
        "summary": f"Wrote {len(transformed_data)} records to {destination}",
    })

    return {"audit_log": audit_log}
