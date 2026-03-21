"""ETL Agent — entry point (US1–US14)."""
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from graph import build_graph


def run_pipeline(source_type: str, source_config: dict, target_path: str = "", target_db: dict = None, max_retries: int = 3, user_instructions: str = ""):
    """Run the full ETL pipeline and return final state."""
    initial_state = {
        "source_type": source_type,
        "source_config": source_config,
        "target_path": target_path,
        "target_db": target_db or {},
        "user_instructions": user_instructions,
        "raw_data": None,
        "raw_schema": {},
        "transformation_plan": "",
        "transformation_code": "",
        "transformed_data": None,
        "engineer_verdict": "",
        "engineer_error": "",
        "retry_count": 0,
        "max_retries": max_retries,
        "audit_log": [],
    }

    pipeline = build_graph()
    final_state = pipeline.invoke(initial_state)
    return final_state


def print_audit_log(audit_log: list):
    print("\n=== Audit Log ===")
    for entry in audit_log:
        print(f"[{entry['timestamp']}] {entry['agent']:10s} | {entry['action']:20s} | {entry['summary']}")


if __name__ == "__main__":
    # Default demo: CSV mode using a sample file
    import tempfile, csv

    # Create a demo CSV
    demo_path = "/tmp/demo_etl_input.csv"
    with open(demo_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "symbol", "open", "close", "volume"])
        writer.writeheader()
        rows = [
            {"date": "2024-01-01", "symbol": "AAPL", "open": "149.0", "close": "150.5", "volume": "1200000"},
            {"date": "2024-01-02", "symbol": "AAPL", "open": "150.5", "close": "152.0", "volume": "980000"},
            {"date": "2024-01-03", "symbol": "AAPL", "open": "152.0", "close": "151.0", "volume": "870000"},
        ]
        writer.writerows(rows)

    print("Running ETL pipeline (CSV demo)...")
    final = run_pipeline(
        source_type="csv",
        source_config={"path": demo_path},
        target_path="/tmp/demo_etl_output.csv",
    )

    print_audit_log(final.get("audit_log", []))
    print(f"\nOutput written to: /tmp/demo_etl_output.csv")
    print(f"Records: {len(final.get('transformed_data') or [])}")
    print(f"Final verdict: {final.get('engineer_verdict')}")
