# ETL Agent — Project Notes

Quick reference for what each file and folder does.

---

## Root Files

### `main.py`
Entry point. Defines `run_pipeline()` — the function everything else calls.
Takes `source_type`, `source_config`, `target_path` or `target_db`, `user_instructions`, and `max_retries`.
Builds the initial `ETLState`, invokes the compiled LangGraph, and returns the final state.
Run directly (`python main.py`) for a built-in CSV demo.

### `etl_state.py`
Defines `ETLState` — a `TypedDict` that is the single shared object passed between all agents.
Every agent reads from it and writes back a partial update.
Fields cover: source config, user instructions, raw data, schema, transformation plan, generated code, transformed data, engineer verdict, retry count, and audit log.

### `graph.py`
Assembles the LangGraph `StateGraph`.
Registers the four agent nodes (scout, architect, engineer, loader), sets the entry point, wires the linear edges (scout → architect → engineer), and attaches the conditional router after engineer.
Call `build_graph()` to get the compiled, runnable graph.

### `router.py`
Single function `engineer_router()` that reads `engineer_verdict` from state and returns the next node name.
- `pass` → loader
- `retry` → engineer (loops back)
- `escalate` → architect (loops back further)
- `terminate` → end

### `requirements.txt`
All Python dependencies. Install with `pip install -r requirements.txt`.

### `user_stories_US1_US15.md`
Capstone project spec. 15 user stories defining what the system must do (functional and non-functional).
Also contains the build protocol: verify each feature works before moving to the next.

### `notes.md`
This file.

---

## `agents/`

### `agents/scout.py`
**Deterministic node. No LLM.**
Reads data from the source (CSV or Alpha Vantage API) and detects the schema.
- CSV: uses pandas to read, converts to list of dicts, infers column types.
- API: calls Alpha Vantage, flattens nested JSON (strips numeric prefixes like `"1. open"` → `"open"`).
Writes `raw_data` and `raw_schema` to state. Appends to audit log.

### `agents/architect.py`
**LLM node — qwen2.5:14b-instruct-q4_K_M via Ollama on the tower.**
Receives `raw_data` sample, `raw_schema`, and `user_instructions` provided by the engineer at job start.
Sends to the model with a structured prompt (schema, sample, target, instructions) and produces a numbered plain-English transformation plan.
Writes `transformation_plan` to state. No code is generated here — intent only.
If escalated back from Engineer, generates a revised plan.

### `agents/engineer.py`
**LLM node — same model.**
Receives the transformation plan and data sample. Asks the model to generate executable Python code that transforms `raw_data` into a variable called `result` (list of dicts).
Executes the code with `exec()` in a controlled namespace (pandas and json available).
On success: verdict = `pass`.
On failure: verdict = `retry` (up to max_retries), then `escalate`.
Writes `transformation_code`, `transformed_data`, `engineer_verdict`, and `engineer_error` to state.

### `agents/loader.py`
**Deterministic node. No LLM.**
Writes `transformed_data` to the target destination.
- `target_path` ending in `.csv` → CSV file
- `target_path` ending in `.json` → JSON file
- `target_db` with `type: sqlite` → SQLite database via SQLAlchemy
- `target_db` with `type: postgres` → PostgreSQL via SQLAlchemy (needs `connection_string`)
Appends to audit log.

---

## `tools/`

### `tools/api_tools.py`
Thin wrapper around the Alpha Vantage REST API.
`fetch_alpha_vantage(function, symbol, **kwargs)` — reads `ALPHA_VANTAGE_API_KEY` from env, makes the request, surfaces API-level errors (rate limits, bad symbols).

### `tools/csv_tools.py`
Two utility functions used by Scout:
- `read_csv(path)` — reads a CSV and returns a list of dicts.
- `infer_schema(records)` — returns a dict of `{column: python_type_name}` from the first record.

---

## `datasets/`

### `datasets/coursea_data.csv`
Sample dataset — 891 Coursera courses with title, organization, certificate type, rating, difficulty, and enrollment count.
Used for testing the pipeline. Contains intentionally messy data (`"5.3k"` enrollment strings) that exercises the retry/escalate loop.

---

## How Data Flows

```
source (csv / api)
       ↓
    Scout         → raw_data, raw_schema
       ↓
  Architect       → transformation_plan
       ↓
   Engineer       → transformation_code, transformed_data, verdict
       ↓
  [router]        → pass / retry / escalate / terminate
       ↓
    Loader        → writes to file or database
```

All agents share `ETLState`. Each appends a timestamped entry to `audit_log` so every run is fully traceable.
