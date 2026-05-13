import sys
import pandas as pd


def convert(parquet_path: str, csv_path: str = None):
    if csv_path is None:
        csv_path = parquet_path.replace(".parquet", ".csv")

    print(f"Reading {parquet_path}...")
    df = pd.read_parquet(parquet_path)
    print(f"  {len(df):,} rows, {len(df.columns)} columns")

    print(f"Writing {csv_path}...")
    df.to_csv(csv_path, index=False)
    print("Done.")


if __name__ == "__main__":
    parquet_path = sys.argv[1] if len(sys.argv) > 1 else "datasets/yellow_tripdata_2025-01.parquet"
    csv_path = sys.argv[2] if len(sys.argv) > 2 else None
    convert(parquet_path, csv_path)
