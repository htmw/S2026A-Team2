from typing import TypedDict, Any, Optional


class ETLState(TypedDict):
    # --- Input config ---
    source_type: str          # "api" or "csv"
    source_config: dict       # API params or {"path": "..."}
    user_instructions: str    # engineer-provided instructions passed to the Architect

    # --- Output config (file-based) ---
    target_path: str          # output file path (csv or json)

    # --- Output config (database) ---
    # Optional. If set, Loader writes to DB instead of file.
    # {
    #   "type": "sqlite" | "postgres",
    #   "connection_string": "sqlite:///path.db" | "postgresql://user:pass@host/db",
    #   "table": "table_name",
    #   "if_exists": "replace" | "append" | "fail"   (default: replace)
    # }
    target_db: dict

    # --- Scout outputs ---
    raw_data: Any             # extracted data (list of dicts)
    raw_schema: dict          # detected column types

    # --- Architect outputs ---
    transformation_plan: str  # LLM-generated plan text

    # --- Engineer outputs ---
    transformation_code: str  # LLM-generated Python code
    transformed_data: Any     # result after code execution
    engineer_verdict: str     # "pass" | "retry" | "escalate" | "terminate"
    engineer_error: str       # error message on failure

    # --- Control flow ---
    retry_count: int
    max_retries: int

    # --- Audit log ---
    audit_log: list           # list of {timestamp, agent, action, summary}
