"""Engineer agent — LLM code generation + execution (US2, US4, US5)."""
import json
import os
import traceback
from datetime import datetime

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage


SYSTEM_PROMPT = """You are the Engineer agent in a 4-agent ETL pipeline.
Your job is to write Python code that transforms raw_data according to the Architect's plan.

Rules:
- raw_data is available as a Python variable: a list of dicts.
- pandas is available as pd.
- Your code MUST assign the final result to a variable called: result
- result must be a list of dicts (use df.to_dict(orient='records') if you use pandas).
- Write ONLY executable Python code. No markdown fences, no explanations.
- Do not import anything other than pandas (already imported as pd) and json (already imported).
- If you cannot complete the transformation safely, write: result = raw_data"""

USER_PROMPT_TEMPLATE = """Write Python code to transform raw_data using this plan:

TRANSFORMATION PLAN:
{plan}

SCHEMA:
{schema}

SAMPLE (first 3 records):
{sample}

Remember: assign final output to `result` as a list of dicts."""


def _get_llm() -> ChatOllama:
    base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    return ChatOllama(
        model="qwen2.5:14b-instruct-q4_K_M",
        base_url=base_url,
        temperature=0.0,
    )


def _extract_code(text: str) -> str:
    """Strip markdown code fences if model adds them."""
    lines = text.strip().splitlines()
    # Remove ```python / ``` wrappers
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def engineer_node(state: dict) -> dict:
    """Generate transformation code and execute it. Returns verdict."""
    raw_data = state.get("raw_data", [])
    raw_schema = state.get("raw_schema", {})
    transformation_plan = state.get("transformation_plan", "")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)
    audit_log = list(state.get("audit_log", []))

    sample = raw_data[:3] if raw_data else []

    user_msg = USER_PROMPT_TEMPLATE.format(
        plan=transformation_plan,
        schema=json.dumps(raw_schema, indent=2),
        sample=json.dumps(sample, indent=2),
    )

    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ])
    raw_code = response.content.strip()
    transformation_code = _extract_code(raw_code)

    # Execute the generated code in a controlled namespace
    import pandas as pd  # noqa: F401 — available in exec namespace

    namespace = {
        "raw_data": raw_data,
        "pd": pd,
        "json": json,
        "result": None,
    }

    verdict = "pass"
    transformed_data = None
    error_msg = ""

    try:
        exec(transformation_code, namespace)  # noqa: S102
        transformed_data = namespace.get("result")
        if transformed_data is None:
            raise ValueError("Code executed but 'result' was never assigned.")
        if not isinstance(transformed_data, list):
            raise TypeError(f"'result' must be a list of dicts, got {type(transformed_data).__name__}")

        audit_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "agent": "Engineer",
            "action": "execute",
            "summary": f"Code executed successfully. {len(transformed_data)} records produced.",
        })

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        if retry_count < max_retries:
            verdict = "retry"
        else:
            verdict = "escalate"

        audit_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "agent": "Engineer",
            "action": "execute_error",
            "summary": f"Execution failed (retry {retry_count}/{max_retries}): {exc}",
        })

    return {
        "transformation_code": transformation_code,
        "transformed_data": transformed_data,
        "engineer_verdict": verdict,
        "engineer_error": error_msg,
        "retry_count": retry_count + (1 if verdict == "retry" else 0),
        "audit_log": audit_log,
    }
