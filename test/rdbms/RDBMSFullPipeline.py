# run_pipeline.py — run from project root
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from main import run_pipeline, print_audit_log

print("Running ETL pipeline")
print("Source: PostgreSQL → Target: PostgreSQL")
print("=" * 50)
 
final = run_pipeline(
    source_type="rdbms",
    source_config={
        "connection_string": "postgresql://postgres:Ov96@localhost:5432/postgres",
        "table": "employees",
    },
    user_instructions="Clean the data. Ensure salary is a float. Drop any rows with missing values.",
    target_db={
        "type": "postgres",
        "connection_string": "postgresql://postgres:Ov96@localhost:5432/testdb",
        "table": "employees_cleaned",
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
