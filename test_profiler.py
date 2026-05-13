"""Quick smoke test for the profiler node against a CSV file."""
import sys
import time
import pandas as pd
from tools.csv_tools import infer_schema
from agents.profiler import profiler_node, _CUDA_AVAILABLE, GPU_THRESHOLD

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "datasets/yellow_tripdata_2025-01.csv"

print(f"CUDA available : {_CUDA_AVAILABLE}")
print(f"GPU threshold  : {GPU_THRESHOLD:,} rows\n")

print(f"Loading {CSV_PATH}...")
t0 = time.time()
df = pd.read_csv(CSV_PATH)
raw_data = df.to_dict(orient="records")
raw_schema = infer_schema(raw_data)
print(f"Loaded {len(raw_data):,} rows in {time.time() - t0:.1f}s\n")

state = {"raw_data": raw_data, "raw_schema": raw_schema, "audit_log": []}

print("Running profiler...")
t1 = time.time()
result = profiler_node(state)
elapsed = time.time() - t1

profile = result["data_profile"]
print(f"Profiled via   : {profile['backend'].upper()}")
print(f"Time           : {elapsed:.2f}s")
print(f"Rows           : {profile['row_count']:,}")
print()

print("=== Column Profile ===")
for col, stats in profile["columns"].items():
    parts = [f"type={stats['type']}"]
    if "null_count" in stats:
        parts.append(f"nulls={stats['null_count']:,}")
    if stats.get("min") is not None:
        parts.append(f"min={stats['min']:.2f}  max={stats['max']:.2f}  mean={stats['mean']:.2f}")
    if "unique_count" in stats:
        parts.append(f"unique={stats['unique_count']:,}")
    print(f"  {col:35s} {', '.join(parts)}")
