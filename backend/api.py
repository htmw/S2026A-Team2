"""
DataWeave Backend API (Flask)

This service exposes REST endpoints for:
- Uploading CSV datasets
- Running the team ETL pipeline
- Querying transformed data from SQLite
- Retrieving schema metadata
- Running pre-built analytics queries
- Executing safe custom SELECT queries

Architecture:
Client (Jupyter / UI) -> Flask API -> Team ETL Pipeline -> SQLite DB

Run:
    python api.py

Then open:
    http://localhost:5000/health
"""

import os
import sys
import sqlite3
import time
import traceback

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, request, Response, stream_with_context, send_file
from flask_cors import CORS

# Add project root to path so main.py and agents can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import run_pipeline  # Team pipeline entry point
from pipeline.graph import build_graph, build_plan_graph, build_execute_graph, build_generate_graph, build_run_graph  # For streaming

load_dotenv()

app = Flask(__name__)
CORS(app)

# In-memory state for the current app session
_last_run = {}
_uploaded_file_path = None
_transformed_data = []  # Full transformed_data from last pipeline run
_last_generated_code_path = None  # Path to the last engineer-generated .py file

# HITL intermediate state: stored after Phase 1 (plan) so Phase 2 (execute) can resume
_pending_plan_state: dict = {}

# HITL intermediate state: stored after Phase 2a (generate) so Phase 2b (run) can resume
_pending_generate_state: dict = {}


# --------------------------------------------------
# Health Check Endpoint
# --------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    """
    Verify that the backend server is running.

    Returns:
        JSON response with service status and project metadata.
    """
    return jsonify({
        "status": "ok",
        "project": "DataWeave",
        "team": "S2026A-Team2"
    })


# --------------------------------------------------
# 1. Upload CSV
# --------------------------------------------------

@app.route("/api/upload", methods=["POST"])
def upload_csv():
    """
    Upload a CSV file and generate a quick column profile.

    Returns:
        - upload status
        - saved file path
        - row count
        - column count
        - per-column metadata:
            * dtype
            * null count
            * unique count
            * sample values
            * numeric summary (min, max, mean) when applicable
    """
    global _uploaded_file_path

    if "file" not in request.files:
        return jsonify({
            "error": "No file provided. Send a CSV as form field 'file'."
        }), 400

    uploaded = request.files["file"]

    if not uploaded.filename or not uploaded.filename.endswith(".csv"):
        return jsonify({
            "error": "Only .csv files are accepted."
        }), 400

    save_path = os.path.join("datasets", uploaded.filename)
    os.makedirs("datasets", exist_ok=True)
    uploaded.save(save_path)
    _uploaded_file_path = save_path

    try:
        df = pd.read_csv(save_path)

        if "Unnamed: 0" in df.columns:
            df = df.drop(columns=["Unnamed: 0"])

        columns = []
        for col in df.columns:
            col_info = {
                "name": col,
                "dtype": str(df[col].dtype),
                "null_count": int(df[col].isnull().sum()),
                "unique_count": int(df[col].nunique()),
                "sample_values": df[col].dropna().head(5).tolist(),
            }

            if pd.api.types.is_numeric_dtype(df[col]):
                col_info["min"] = float(df[col].min())
                col_info["max"] = float(df[col].max())
                col_info["mean"] = round(float(df[col].mean()), 4)

            columns.append(col_info)

        return jsonify({
            "status": "uploaded",
            "filename": uploaded.filename,
            "saved_path": save_path,
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": columns,
        })

    except Exception as e:
        return jsonify({
            "error": f"Failed to read CSV: {str(e)}"
        }), 422


# --------------------------------------------------
# 2. Run ETL Pipeline
# --------------------------------------------------

@app.route("/api/run", methods=["POST"])
def run_pipeline_endpoint():
    """
    Run the full ETL pipeline using the uploaded CSV or a default dataset.

    Request body (optional JSON):
        {
            "source_path": "datasets/coursea_data.csv",
            "target_db_path": "output/etl_output.db",
            "target_table": "courses",
            "if_exists": "replace",
            "user_instructions": "custom transformation instructions"
        }

    Notes:
        - If no source_path is provided, the API uses the most recently uploaded CSV.
        - If no uploaded file exists, it falls back to datasets/coursea_data.csv.
        - This endpoint depends on the team's pipeline implementation from main.py.
        - If the LLM/Ollama layer is unavailable or system resources are low,
          pipeline execution may fail before completion.
    """
    global _last_run

    body = request.get_json(silent=True) or {}

    source_type = body.get("source_type", "csv")
    connection_port = body.get("connection_port")
    user_instructions = body.get("user_instructions", "")

    target_db_path = body.get("target_db_path", "output/etl_output.db")
    target_table = body.get("target_table", "courses")
    if_exists = body.get("if_exists", "replace")
    target_path = body.get("target_path", "")

    if source_type == "csv":
        source_path = body.get("source_path") or _uploaded_file_path or "datasets/coursea_data.csv"
        source_config = {"path": source_path}

    elif source_type == "api":
        source_config = {
            "symbol": body.get("symbol"),
            "interval": body.get("interval", "Daily"),
            "apikey": body.get("apikey"),
        }

        missing = [k for k, v in source_config.items() if not v]
        if missing:
            return jsonify({
            "status": "error",
            "error": f"Missing required API source fields: {missing}"
        }), 400
        source_path = None

    elif source_type == "rdbms":
        connection_string = body.get("connection_string")
        query = body.get("query")
        table = body.get("table")

        if not connection_string:
            return jsonify({
                "status": "error",
                "error": "Missing required field: connection_string"
            }), 400
        if not query and not table:
            return jsonify({
                "status": "error",
                "error": "Provide either 'query' or 'table' for RDBMS source."
            }), 400
        source_config = {
            "connection_string": connection_string,
            "query": query,
            "table": table,
        }
        source_path = None
    else:
        return jsonify({
            "status": "error",
            "error": f"Unsupported source_type '{source_type}'. Use 'csv', 'api', or 'rdbms'."
        }), 400

    os.makedirs("output", exist_ok=True)

    try:
        final_state = run_pipeline(
            source_type=source_type,
            source_config=source_config,
            target_path=target_path,
            target_db={
                "type": "sqlite",
                "path": target_db_path,
                "table": target_table,
                "if_exists": if_exists,
            },
            user_instructions=user_instructions,
            connection_port=connection_port,
        )

        rows_written = _count_rows(target_db_path, target_table)

        result = {
            "status": "success",
            "source_type": source_type,
            "source_path": source_path,
            "target_db_path": target_db_path,
            "target_table": target_table,
            "rows_written": rows_written,
            "agent_outputs": {
                "scout": {
                    "raw_schema": final_state.get("raw_schema", {}),
                    "record_count": len(final_state.get("raw_data") or []),
                    "sample_records": (final_state.get("raw_data") or [])[:5],
                },
                "architect": {
                    "transformation_plan": final_state.get("transformation_plan", ""),
                },
                "engineer": {
                    "transformation_code": final_state.get("transformation_code", ""),
                    "verdict": final_state.get("engineer_verdict", ""),
                    "error": final_state.get("engineer_error", ""),
                    "output_record_count": len(
                        final_state.get("transformed_data") or []
                    ),
                    "sample_output": (final_state.get("transformed_data") or [])[:5],
                },
            },
            "audit_log": final_state.get("audit_log", []),
        }

        _last_run = result
        _transformed_data.clear()
        _transformed_data.extend(final_state.get("transformed_data") or [])
        global _last_generated_code_path
        _last_generated_code_path = final_state.get("generated_code_path")
        return jsonify(result)

    except Exception as e:
        error_result = {
            "status": "error",
            "source_type": source_type,
            "connection_port": connection_port,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        _last_run = error_result
        return jsonify(error_result), 500

# --------------------------------------------------
# 3. Stream Pipeline Execution (SSE)
# --------------------------------------------------

@app.route("/api/run/stream", methods=["POST"])
def run_pipeline_stream():
    """
    Stream pipeline execution events via Server-Sent Events (SSE).
    Emits one event per agent node as it completes.

    Event format:
        data: {"node": "scout"|"architect"|"engineer"|"loader"|"__end__", ...fields}\n\n
    """
    body = request.get_json(silent=True) or {}

    source_type = body.get("source_type", "csv")
    user_instructions = body.get("user_instructions", "")
    target_db_path = body.get("target_db_path", "output/etl_output.db")
    target_table = body.get("target_table", "courses")
    if_exists = body.get("if_exists", "replace")
    target_path = body.get("target_path", "")
    connection_port = body.get("connection_port")

    if source_type == "csv":
        source_path = body.get("source_path") or _uploaded_file_path or "datasets/coursea_data.csv"
        source_config = {"path": source_path}

    elif source_type == "api":
        source_config = {
        "symbol": body.get("symbol"),
        "interval": body.get("interval", "Daily"),
        "apikey": body.get("apikey"),
    }

    elif source_type == "rdbms":
        connection_string = body.get("connection_string")
        query = body.get("query")
        table = body.get("table")

        if not connection_string:
            def err_gen():
                import json as _json
                yield f"data: {_json.dumps({'type': 'error', 'node': '__error__', 'error': 'Missing required field: connection_string'})}\n\n"
            return Response(stream_with_context(err_gen()), mimetype="text/event-stream")

        if not query and not table:
            def err_gen():
                import json as _json
                yield f"data: {_json.dumps({'type': 'error', 'node': '__error__', 'error': 'Provide either query or table for RDBMS source.'})}\n\n"
            return Response(stream_with_context(err_gen()), mimetype="text/event-stream")

        source_config = {
            "connection_string": connection_string,
            "query": query,
            "table": table,
        }
    else:
        def err_gen():
            import json as _json
            yield f"data: {_json.dumps({'node': '__error__', 'error': f'Unsupported source_type: {source_type}'})}\n\n"

        return Response(
            stream_with_context(err_gen()),
            mimetype="text/event-stream"
        )
    
    os.makedirs("output", exist_ok=True)

    initial_state = {
        "source_type": source_type,
        "source_config": source_config,
        "target_path": target_path,
        "target_db": {"type": "sqlite", "path": target_db_path, "table": target_table, "if_exists": if_exists},
        "user_instructions": user_instructions,
        "connection_port": connection_port,
        "raw_data": None,
        "raw_schema": {},
        "transformation_plan": "",
        "transformation_code": "",
        "generated_code_path": "",
        "transformed_data": None,
        "transformation_diff": {},
        "engineer_verdict": "",
        "engineer_error": "",
        "retry_count": 0,
        "max_retries": body.get("max_retries", 3),
        "audit_log": [],
    }

    def generate():
        import json as _json
        try:
            pipeline = build_graph()

            # stream_mode=["messages", "updates"]:
            #   "messages" -> yields LLM tokens as they're generated (token-by-token)
            #   "updates"  -> yields full node state update when a node completes
            for mode, chunk in pipeline.stream(initial_state, stream_mode=["messages", "updates"]):

                if mode == "messages":
                    # chunk is (AIMessageChunk, metadata)
                    msg_chunk, metadata = chunk
                    token = getattr(msg_chunk, "content", "")
                    node_name = metadata.get("langgraph_node", "")
                    # Stream tokens from LLM agents (architect + engineer_generate)
                    if token and node_name in ("architect", "engineer_generate"):
                        yield f"data: {_json.dumps({'type': 'token', 'node': node_name, 'token': token})}\n\n"
                        if node_name == "architect":
                            time.sleep(0.05)  # slower for readability

                elif mode == "updates":
                    # chunk is {node_name: state_update}
                    for node_name, state_update in chunk.items():
                        event = {"type": "node_done", "node": node_name}

                        if node_name == "scout":
                            event["record_count"] = len(state_update.get("raw_data") or [])
                            event["raw_schema"] = state_update.get("raw_schema", {})

                        elif node_name == "architect":
                            event["transformation_plan"] = state_update.get("transformation_plan", "")

                        elif node_name == "engineer_generate":
                            event["transformation_code"] = state_update.get("transformation_code", "")
                            event["generated_code_path"] = state_update.get("generated_code_path", "")
                            # Track the path so /api/download/engineer_code works after streaming
                            global _last_generated_code_path
                            _last_generated_code_path = state_update.get("generated_code_path")

                        elif node_name == "engineer_execute":
                            event["engineer_verdict"] = state_update.get("engineer_verdict", "")
                            event["engineer_error"] = state_update.get("engineer_error", "")
                            event["retry_count"] = state_update.get("retry_count", 0)
                            event["transformed_data"] = state_update.get("transformed_data") or []

                        elif node_name == "loader":
                            event["rows_written"] = _count_rows(target_db_path, target_table)

                        audit = state_update.get("audit_log", [])
                        if audit:
                            event["latest_audit"] = audit[-1]

                        yield f"data: {_json.dumps(event)}\n\n"

            yield f"data: {_json.dumps({'type': 'done', 'node': '__end__', 'status': 'complete'})}\n\n"

        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'node': '__error__', 'error': str(e), 'traceback': traceback.format_exc()})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------
# 3b. HITL Phase 1 — Stream Scout + Architect (plan only)
# --------------------------------------------------
# Endpoints below implement 3-step HITL approval:
#   Phase 1:  POST /api/run/stream/plan      → Scout + Architect → plan_ready event
#   Phase 2a: POST /api/run/stream/generate  → Engineer generate → code_ready event
#   Phase 2b: POST /api/run/stream/run       → Engineer execute + Loader → done event
# --------------------------------------------------

@app.route("/api/run/stream/plan", methods=["POST"])
def run_plan_stream():
    """
    HITL Phase 1: Run Scout → Architect and stream events to the client.

    Stores intermediate pipeline state (raw_data, raw_schema, source config, etc.)
    server-side so Phase 2 can resume without re-extracting the data.

    Event types emitted:
        {"type": "token",     "node": "architect", "token": "..."}   — LLM tokens as they arrive
        {"type": "node_done", "node": "scout",     "record_count": N, "raw_schema": {...}}
        {"type": "node_done", "node": "architect", "transformation_plan": "..."}
        {"type": "plan_ready", "transformation_plan": "..."}         — final signal, plan is ready for review
        {"type": "error",     "node": "__error__",  "error": "..."}

    Request body (same shape as /api/run/stream):
        source_type, source_path / symbol / interval / apikey,
        target_db_path, target_table, if_exists, user_instructions, max_retries
    """
    global _pending_plan_state

    body = request.get_json(silent=True) or {}

    source_type = body.get("source_type", "csv")
    user_instructions = body.get("user_instructions", "")
    target_db_path = body.get("target_db_path", "output/etl_output.db")
    target_table = body.get("target_table", "transformed")
    if_exists = body.get("if_exists", "replace")
    target_path = body.get("target_path", "")
    connection_port = body.get("connection_port")

    if source_type == "csv":
        source_path = body.get("source_path") or _uploaded_file_path or "datasets/coursea_data.csv"
        source_config = {"path": source_path}
    elif source_type == "api":
        source_config = {
            "symbol": body.get("symbol"),
            "interval": body.get("interval", "Daily"),
            "apikey": body.get("apikey"),
        }
    else:
        def _err():
            import json as _j
            yield f"data: {_j.dumps({'type': 'error', 'node': '__error__', 'error': f'Unsupported source_type: {source_type}'})}\n\n"
        return Response(stream_with_context(_err()), mimetype="text/event-stream")

    os.makedirs("output", exist_ok=True)

    initial_state = {
        "source_type": source_type,
        "source_config": source_config,
        "target_path": target_path,
        "target_db": {"type": "sqlite", "path": target_db_path, "table": target_table, "if_exists": if_exists},
        "user_instructions": user_instructions,
        "connection_port": connection_port,
        "raw_data": None,
        "raw_schema": {},
        "transformation_plan": "",
        "transformation_code": "",
        "generated_code_path": "",
        "transformed_data": None,
        "transformation_diff": {},
        "engineer_verdict": "",
        "engineer_error": "",
        "retry_count": 0,
        "max_retries": body.get("max_retries", 3),
        "audit_log": [],
    }

    def generate():
        import json as _json
        final_state = dict(initial_state)
        # Accumulate architect tokens here as a fallback — gemma4 (and some other
        # Ollama models) emit tokens via the messages stream but leave
        # response.content empty in the node's return value.
        architect_tokens: list = []
        try:
            pipeline = build_plan_graph()

            for mode, chunk in pipeline.stream(initial_state, stream_mode=["messages", "updates"]):

                if mode == "messages":
                    msg_chunk, metadata = chunk
                    token = getattr(msg_chunk, "content", "")
                    node_name = metadata.get("langgraph_node", "")
                    if token and node_name == "architect":
                        architect_tokens.append(token)
                        yield f"data: {_json.dumps({'type': 'token', 'node': 'architect', 'token': token})}\n\n"
                        time.sleep(0.05)

                elif mode == "updates":
                    for node_name, state_update in chunk.items():
                        event = {"type": "node_done", "node": node_name}

                        if node_name == "scout":
                            event["record_count"] = len(state_update.get("raw_data") or [])
                            event["raw_schema"] = state_update.get("raw_schema", {})

                        elif node_name == "architect":
                            plan_from_node = state_update.get("transformation_plan", "")
                            # If the node returned an empty plan (gemma4 streaming bug),
                            # fall back to tokens we accumulated from the messages stream.
                            if not plan_from_node and architect_tokens:
                                plan_from_node = "".join(architect_tokens).strip()
                                state_update = dict(state_update)
                                state_update["transformation_plan"] = plan_from_node
                            event["transformation_plan"] = plan_from_node

                        audit = state_update.get("audit_log", [])
                        if audit:
                            event["latest_audit"] = audit[-1]

                        # Merge update into final_state so we can store it after streaming
                        final_state.update(state_update)

                        yield f"data: {_json.dumps(event)}\n\n"

            # Store intermediate state for Phase 2
            global _pending_plan_state
            _pending_plan_state = final_state

            plan = final_state.get("transformation_plan", "") or "".join(architect_tokens).strip()
            # Ensure pending state has the correct plan
            _pending_plan_state["transformation_plan"] = plan
            yield f"data: {_json.dumps({'type': 'plan_ready', 'transformation_plan': plan})}\n\n"

        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'node': '__error__', 'error': str(e), 'traceback': traceback.format_exc()})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------
# 3c. HITL Phase 2 — Stream Engineer + Loader (execute approved plan)
# --------------------------------------------------

@app.route("/api/run/stream/execute", methods=["POST"])
def run_execute_stream():
    """
    HITL Phase 2: Resume pipeline from an approved (or edited) transformation plan.

    Requires /api/run/stream/plan to have run first (stores intermediate state server-side).
    The client sends back the transformation plan — edited or as-is — and this endpoint
    runs Engineer (generate + execute) → Loader, streaming progress events.

    Event types emitted:
        {"type": "token",     "node": "engineer_generate", "token": "..."}
        {"type": "node_done", "node": "engineer_generate", "transformation_code": "...", "generated_code_path": "..."}
        {"type": "node_done", "node": "engineer_execute",  "engineer_verdict": "...", "engineer_error": "...", "transformed_data": [...]}
        {"type": "node_done", "node": "loader",            "rows_written": N}
        {"type": "done",      "node": "__end__",           "status": "complete"}
        {"type": "error",     "node": "__error__",         "error": "..."}

    Request body:
        {
            "transformation_plan": "<approved or edited plan text>"
        }
    """
    global _pending_plan_state, _last_generated_code_path

    if not _pending_plan_state:
        return jsonify({
            "error": "No pending plan state found. Run POST /api/run/stream/plan first."
        }), 400

    body = request.get_json(silent=True) or {}
    transformation_plan = body.get("transformation_plan", _pending_plan_state.get("transformation_plan", ""))

    # Build execute-phase initial state from stored Phase 1 output, override plan
    initial_state = dict(_pending_plan_state)
    initial_state["transformation_plan"] = transformation_plan
    initial_state["transformation_code"] = ""
    initial_state["generated_code_path"] = ""
    initial_state["transformed_data"] = None
    initial_state["transformation_diff"] = {}
    initial_state["engineer_verdict"] = ""
    initial_state["engineer_error"] = ""
    initial_state["retry_count"] = 0

    target_db_info = initial_state.get("target_db", {})
    target_db_path = target_db_info.get("path", "output/etl_output.db")
    target_table = target_db_info.get("table", "transformed")

    os.makedirs("output", exist_ok=True)

    def generate():
        import json as _json
        try:
            pipeline = build_execute_graph()

            for mode, chunk in pipeline.stream(initial_state, stream_mode=["messages", "updates"]):

                if mode == "messages":
                    msg_chunk, metadata = chunk
                    token = getattr(msg_chunk, "content", "")
                    node_name = metadata.get("langgraph_node", "")
                    if token and node_name == "engineer_generate":
                        yield f"data: {_json.dumps({'type': 'token', 'node': 'engineer_generate', 'token': token})}\n\n"

                elif mode == "updates":
                    for node_name, state_update in chunk.items():
                        event = {"type": "node_done", "node": node_name}

                        if node_name == "engineer_generate":
                            event["transformation_code"] = state_update.get("transformation_code", "")
                            event["generated_code_path"] = state_update.get("generated_code_path", "")
                            global _last_generated_code_path
                            _last_generated_code_path = state_update.get("generated_code_path")

                        elif node_name == "engineer_execute":
                            event["engineer_verdict"] = state_update.get("engineer_verdict", "")
                            event["engineer_error"] = state_update.get("engineer_error", "")
                            event["retry_count"] = state_update.get("retry_count", 0)
                            event["transformed_data"] = state_update.get("transformed_data") or []
                            # Update in-memory store for /api/transformed
                            td = state_update.get("transformed_data") or []
                            _transformed_data.clear()
                            _transformed_data.extend(td)

                        elif node_name == "loader":
                            event["rows_written"] = _count_rows(target_db_path, target_table)

                        audit = state_update.get("audit_log", [])
                        if audit:
                            event["latest_audit"] = audit[-1]

                        yield f"data: {_json.dumps(event)}\n\n"

            yield f"data: {_json.dumps({'type': 'done', 'node': '__end__', 'status': 'complete'})}\n\n"

        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'node': '__error__', 'error': str(e), 'traceback': traceback.format_exc()})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------
# 4. Get Results from SQLite
# --------------------------------------------------

@app.route("/api/results", methods=["GET"])
def get_results():
    """
    Query the output SQLite database and return rows as JSON.

    Query parameters:
        db_path (default: output/etl_output.db)
        table   (default: courses)
        limit   (default: 100)
        offset  (default: 0)

    Returns:
        - table name
        - total row count
        - returned row count
        - selected rows
        - column names
    """
    db_path = request.args.get("db_path", "output/etl_output.db")
    table = request.args.get("table", "courses")
    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))

    if not os.path.exists(db_path):
        return jsonify({
            "error": f"Database not found at '{db_path}'. Run /api/run first."
        }), 404

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            f"SELECT * FROM {table} LIMIT ? OFFSET ?",
            (limit, offset)
        )
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        conn.close()

        return jsonify({
            "table": table,
            "total_rows": total,
            "returned": len(rows),
            "limit": limit,
            "offset": offset,
            "columns": columns,
            "rows": rows,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------
# 4. Get Transformed Data (in-memory, pre-load)
# --------------------------------------------------

@app.route("/api/transformed", methods=["GET"])
def get_transformed():
    """
    Return the in-memory transformed_data from the last pipeline run.
    This is the Engineer's output before it was written to SQLite —
    useful for inspecting what was actually loaded.

    Query parameters:
        limit  (default: 100)
        offset (default: 0)
    """
    if not _transformed_data:
        return jsonify({
            "error": "No transformed data available. Run /api/run first."
        }), 404

    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))

    page = _transformed_data[offset: offset + limit]
    columns = list(page[0].keys()) if page else []

    return jsonify({
        "total_rows": len(_transformed_data),
        "returned": len(page),
        "limit": limit,
        "offset": offset,
        "columns": columns,
        "rows": page,
    })


# --------------------------------------------------
# 5. Get Schema / Column Info
# --------------------------------------------------

@app.route("/api/schema", methods=["GET"])
def get_schema():
    """
    Return the schema metadata of the output SQLite table.

    Query parameters:
        db_path (default: output/etl_output.db)
        table   (default: courses)

    Returns:
        - table name
        - row count
        - column-level schema information
    """
    db_path = request.args.get("db_path", "output/etl_output.db")
    table = request.args.get("table", "courses")

    if not os.path.exists(db_path):
        return jsonify({
            "error": f"Database not found at '{db_path}'. Run /api/run first."
        }), 404

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(f"PRAGMA table_info({table})")
        columns = [
            {
                "cid": row[0],
                "name": row[1],
                "type": row[2],
                "notnull": bool(row[3]),
                "pk": bool(row[5]),
            }
            for row in cursor.fetchall()
        ]
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        conn.close()

        return jsonify({
            "table": table,
            "row_count": row_count,
            "columns": columns,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------
# 5. Pre-Built Analytics Queries
# --------------------------------------------------

@app.route("/api/analytics/<query_name>", methods=["GET"])
def analytics(query_name):
    """
    Execute a predefined analytics query against the output database.

    Available query names:
        - avg_rating_by_difficulty
        - top_organizations
        - certificate_distribution
        - rating_distribution
        - enrollment_by_difficulty

    Query parameters:
        db_path (default: output/etl_output.db)
    """
    db_path = request.args.get("db_path", "output/etl_output.db")

    queries = {
        "avg_rating_by_difficulty": """
            SELECT course_difficulty,
                   ROUND(AVG(course_rating), 3) AS avg_rating,
                   COUNT(*) AS course_count
            FROM courses
            GROUP BY course_difficulty
            ORDER BY avg_rating DESC
        """,
        "top_organizations": """
            SELECT course_organization,
                   COUNT(*) AS num_courses,
                   ROUND(AVG(course_rating), 3) AS avg_rating
            FROM courses
            GROUP BY course_organization
            ORDER BY num_courses DESC
            LIMIT 15
        """,
        "certificate_distribution": """
            SELECT course_Certificate_type AS certificate_type,
                   COUNT(*) AS count
            FROM courses
            GROUP BY course_Certificate_type
            ORDER BY count DESC
        """,
        "rating_distribution": """
            SELECT ROUND(course_rating, 1) AS rating_bucket,
                   COUNT(*) AS count
            FROM courses
            WHERE course_rating IS NOT NULL
            GROUP BY rating_bucket
            ORDER BY rating_bucket
        """,
        "enrollment_by_difficulty": """
            SELECT course_difficulty,
                   ROUND(AVG(course_students_enrolled), 0) AS avg_enrollment,
                   COUNT(*) AS course_count
            FROM courses
            GROUP BY course_difficulty
            ORDER BY avg_enrollment DESC
        """,
    }

    if query_name not in queries:
        return jsonify({
            "error": f"Unknown query '{query_name}'.",
            "available": list(queries.keys())
        }), 400

    if not os.path.exists(db_path):
        return jsonify({
            "error": f"Database not found at '{db_path}'. Run /api/run first."
        }), 404

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(queries[query_name])
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()

        return jsonify({
            "query": query_name,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------
# 6. Custom SQL Query
# --------------------------------------------------

@app.route("/api/query", methods=["POST"])
def custom_query():
    """
    Execute a custom read-only SQL query against the SQLite output DB.

    Request body:
        {
            "sql": "SELECT * FROM courses LIMIT 10",
            "db_path": "output/etl_output.db"
        }

    Safety:
        Only SELECT statements are allowed.
    """
    body = request.get_json(silent=True) or {}
    sql = body.get("sql", "").strip()
    db_path = body.get("db_path", "output/etl_output.db")

    if not sql:
        return jsonify({
            "error": "Provide a 'sql' field in the request body."
        }), 400

    if not sql.lower().startswith("select"):
        return jsonify({
            "error": "Only SELECT statements are allowed."
        }), 400

    if not os.path.exists(db_path):
        return jsonify({
            "error": f"Database not found at '{db_path}'."
        }), 404

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()

        return jsonify({
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------
# 3d. HITL Phase 2a — Stream Engineer generate (code only)
# --------------------------------------------------

@app.route("/api/run/stream/generate", methods=["POST"])
def run_generate_stream():
    """
    HITL Phase 2a: Run Engineer generate only and stream the result.

    Requires /api/run/stream/plan to have run first.
    Stores state in _pending_generate_state for Phase 2b to resume.

    Event types emitted:
        {"type": "token",      "node": "engineer_generate", "token": "..."}
        {"type": "node_done",  "node": "engineer_generate", "transformation_code": "...", "generated_code_path": "..."}
        {"type": "code_ready", "transformation_code": "...", "generated_code_path": "..."}
        {"type": "error",      "node": "__error__", "error": "..."}

    Request body:
        {"transformation_plan": "<approved or edited plan text>"}
    """
    global _pending_plan_state, _pending_generate_state, _last_generated_code_path

    if not _pending_plan_state:
        return jsonify({"error": "No pending plan state. Run /api/run/stream/plan first."}), 400

    body = request.get_json(silent=True) or {}
    transformation_plan = body.get("transformation_plan", _pending_plan_state.get("transformation_plan", ""))

    initial_state = dict(_pending_plan_state)
    initial_state["transformation_plan"] = transformation_plan
    initial_state["transformation_code"] = ""
    initial_state["generated_code_path"] = ""

    def generate():
        import json as _json
        final_state = dict(initial_state)
        try:
            pipeline = build_generate_graph()

            for mode, chunk in pipeline.stream(initial_state, stream_mode=["messages", "updates"]):

                if mode == "messages":
                    msg_chunk, metadata = chunk
                    token = getattr(msg_chunk, "content", "")
                    node_name = metadata.get("langgraph_node", "")
                    if token and node_name == "engineer_generate":
                        yield f"data: {_json.dumps({'type': 'token', 'node': 'engineer_generate', 'token': token})}\n\n"

                elif mode == "updates":
                    for node_name, state_update in chunk.items():
                        event = {"type": "node_done", "node": node_name}

                        if node_name == "engineer_generate":
                            event["transformation_code"] = state_update.get("transformation_code", "")
                            event["generated_code_path"] = state_update.get("generated_code_path", "")
                            global _last_generated_code_path
                            _last_generated_code_path = state_update.get("generated_code_path")

                        audit = state_update.get("audit_log", [])
                        if audit:
                            event["latest_audit"] = audit[-1]

                        final_state.update(state_update)
                        yield f"data: {_json.dumps(event)}\n\n"

            # Store state for Phase 2b
            global _pending_generate_state
            _pending_generate_state = final_state

            code = final_state.get("transformation_code", "")
            code_path = final_state.get("generated_code_path", "")
            yield f"data: {_json.dumps({'type': 'code_ready', 'transformation_code': code, 'generated_code_path': code_path})}\n\n"

        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'node': '__error__', 'error': str(e), 'traceback': traceback.format_exc()})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------
# 3e. HITL Phase 2b — Stream Engineer execute + Loader (run approved code)
# --------------------------------------------------

@app.route("/api/run/stream/run", methods=["POST"])
def run_approved_stream():
    """
    HITL Phase 2b: Execute approved code through Engineer execute → Loader.

    Requires /api/run/stream/generate to have run first.
    If engineer_execute fails, auto-retries via engineer_generate without HITL.

    Event types emitted:
        {"type": "token",     "node": "engineer_generate", "token": "..."}  — only on retry regeneration
        {"type": "node_done", "node": "engineer_generate",  "transformation_code": "...", "generated_code_path": "..."}
        {"type": "node_done", "node": "engineer_execute",   "engineer_verdict": "...", "engineer_error": "...", "transformed_data": [...]}
        {"type": "node_done", "node": "loader",             "rows_written": N}
        {"type": "done",      "node": "__end__",            "status": "complete"}
        {"type": "error",     "node": "__error__",          "error": "..."}

    Request body:
        {"transformation_code": "<approved code text>"}
    """
    global _pending_generate_state, _last_generated_code_path

    if not _pending_generate_state:
        return jsonify({"error": "No pending generate state. Run /api/run/stream/generate first."}), 400

    body = request.get_json(silent=True) or {}
    transformation_code = body.get("transformation_code", _pending_generate_state.get("transformation_code", ""))

    initial_state = dict(_pending_generate_state)
    initial_state["transformation_code"] = transformation_code
    initial_state["transformed_data"] = None
    initial_state["transformation_diff"] = {}
    initial_state["engineer_verdict"] = ""
    initial_state["engineer_error"] = ""
    initial_state["retry_count"] = 0

    target_db_info = initial_state.get("target_db", {})
    target_db_path = target_db_info.get("path", "output/etl_output.db")
    target_table = target_db_info.get("table", "transformed")

    os.makedirs("output", exist_ok=True)

    def generate():
        import json as _json
        try:
            pipeline = build_run_graph()

            for mode, chunk in pipeline.stream(initial_state, stream_mode=["messages", "updates"]):

                if mode == "messages":
                    msg_chunk, metadata = chunk
                    token = getattr(msg_chunk, "content", "")
                    node_name = metadata.get("langgraph_node", "")
                    if token and node_name == "engineer_generate":
                        yield f"data: {_json.dumps({'type': 'token', 'node': 'engineer_generate', 'token': token})}\n\n"

                elif mode == "updates":
                    for node_name, state_update in chunk.items():
                        event = {"type": "node_done", "node": node_name}

                        if node_name == "engineer_generate":
                            event["transformation_code"] = state_update.get("transformation_code", "")
                            event["generated_code_path"] = state_update.get("generated_code_path", "")
                            global _last_generated_code_path
                            _last_generated_code_path = state_update.get("generated_code_path")

                        elif node_name == "engineer_execute":
                            event["engineer_verdict"] = state_update.get("engineer_verdict", "")
                            event["engineer_error"] = state_update.get("engineer_error", "")
                            event["retry_count"] = state_update.get("retry_count", 0)
                            event["transformed_data"] = state_update.get("transformed_data") or []
                            td = state_update.get("transformed_data") or []
                            _transformed_data.clear()
                            _transformed_data.extend(td)

                        elif node_name == "loader":
                            event["rows_written"] = _count_rows(target_db_path, target_table)

                        audit = state_update.get("audit_log", [])
                        if audit:
                            event["latest_audit"] = audit[-1]

                        yield f"data: {_json.dumps(event)}\n\n"

            yield f"data: {_json.dumps({'type': 'done', 'node': '__end__', 'status': 'complete'})}\n\n"

        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'node': '__error__', 'error': str(e), 'traceback': traceback.format_exc()})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------
# 6b. HITL — Get pending plan (for frontend pre-population)
# --------------------------------------------------

@app.route("/api/pending/plan", methods=["GET"])
def get_pending_plan():
    """
    Return the transformation plan stored from the last /api/run/stream/plan call.

    Allows the frontend to pre-populate the plan review box without re-running Phase 1.

    Returns:
        - has_pending: bool
        - transformation_plan: str
        - raw_schema: dict
        - record_count: int
    """
    if not _pending_plan_state:
        return jsonify({"has_pending": False, "transformation_plan": "", "raw_schema": {}, "record_count": 0})

    return jsonify({
        "has_pending": True,
        "transformation_plan": _pending_plan_state.get("transformation_plan", ""),
        "raw_schema": _pending_plan_state.get("raw_schema", {}),
        "record_count": len(_pending_plan_state.get("raw_data") or []),
    })


# --------------------------------------------------
# 7. Pipeline Status
# --------------------------------------------------

@app.route("/api/status", methods=["GET"])
def status():
    """
    Return the status of the most recent pipeline execution.

    Returns:
        - success/error/never_run
        - rows written
        - engineer verdict
        - error message if any
    """
    if not _last_run:
        return jsonify({
            "status": "never_run",
            "message": "No pipeline run yet. POST to /api/run."
        })
    return jsonify(_last_run)


# --------------------------------------------------
# 8. Download Engineer-Generated Code
# --------------------------------------------------

@app.route("/api/download/engineer_code", methods=["GET"])
def download_engineer_code():
    """
    Download the Python file generated by the Engineer agent in the last run.

    Returns:
        The .py file as an attachment, or 404 if no pipeline has run yet.
    """
    if not _last_generated_code_path or not os.path.exists(_last_generated_code_path):
        return jsonify({
            "error": "No generated code available. Run /api/run first."
        }), 404

    return send_file(
        _last_generated_code_path,
        mimetype="text/x-python",
        as_attachment=True,
        download_name="engineer_transformation.py",
    )


# --------------------------------------------------
# Helper Functions
# --------------------------------------------------

def _count_rows(db_path: str, table: str):
    """
    Return the row count of a SQLite table.

    Returns:
        int row count if successful, otherwise None.
    """
    try:
        conn = sqlite3.connect(db_path)
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        conn.close()
        return count
    except Exception:
        return None


# --------------------------------------------------
# Entry Point
# --------------------------------------------------

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))

    print("=" * 50)
    print("  DataWeave Backend API")
    print(f"  http://{host}:{port}/health")
    print("=" * 50)

    app.run(host=host, port=port, debug=False)