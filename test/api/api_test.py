# test_url_api.py — run from project root
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from main import run_pipeline, print_audit_log

print("Running ETL pipeline — External API source")
print("=" * 50)
 
final = run_pipeline(
    source_type="url_api",
    source_config={
        "url": "https://www.alphavantage.co/query",
        "headers": {},
        "params": {
            "function": "TIME_SERIES_DAILY",
            "symbol": "IBM",
            "apikey": "CZK26ODQ5RI3003Y",
        },
    },
    user_instructions="Keep only the id, title, and body fields. Drop any rows where title is empty.",
    target_db={
        "type": "postgres",
        "connection_string": "postgresql://postgres:Ov96@localhost:5432/testdb",
        "table": "api_results",
        "if_exists": "replace",
    },
)

print("\n" + "=" * 50)
print_audit_log(final.get("audit_log", []))
print(f"\nVerdict:  {final.get('engineer_verdict')}")
print(f"Records:  {len(final.get('transformed_data') or [])}")
print(f"Error:    {final.get('engineer_error') or 'none'}")
print("\nSample output:")
for row in (final.get("transformed_data") or [])[:3]:
    print(" ", row)
