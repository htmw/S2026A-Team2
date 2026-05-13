"""Architect agent — LLM schema analysis and transformation planning (US2, US5)."""
import json
import os
from datetime import datetime

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage


SYSTEM_PROMPT = """You are the Architect agent in a data pipeline.
Your ONLY job is to translate the USER INSTRUCTIONS into a short numbered list of data transformation steps.

Rules:
- Read the USER INSTRUCTIONS carefully. Your plan must implement exactly what the user asked for — nothing more, nothing less.
- Do NOT invent steps that were not requested. Do NOT add sorting, filtering, or renaming unless the user asked for it.
- Each step describes ONE action on the data: drop rows, keep rows, rename a column, cast a type, fill nulls, normalize values, etc.
- Do NOT write code. Plain English only.
- Do NOT mention file paths, directories, saving files, or any I/O.
- Keep steps short. Example: "Drop rows where course_title contains non-ASCII characters."
- End your response with exactly: VERDICT: ready"""

USER_PROMPT_TEMPLATE = """/no_think
USER INSTRUCTIONS (implement these exactly):
{user_instructions}

Column names and types (for reference):
{schema}

Sample rows (to understand the data shape — do NOT base your plan on patterns you see here, only on the USER INSTRUCTIONS above):
{sample}

Write a numbered plan that implements only what the USER INSTRUCTIONS say."""


def _get_llm() -> ChatOllama:
    base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    return ChatOllama(
        model="qwen3:14b",
        base_url=base_url,
        temperature=0.1,
    )


def architect_node(state: dict) -> dict:
    """Analyze schema and produce a transformation plan."""
    raw_data = state.get("raw_data", [])
    raw_schema = state.get("raw_schema", {})
    target_path = state.get("target_path", "output.csv")
    user_instructions = state.get("user_instructions", "No specific instructions provided.")
    audit_log = list(state.get("audit_log", []))

    user_msg = USER_PROMPT_TEMPLATE.format(
        user_instructions=user_instructions,
        schema=json.dumps(raw_schema, indent=2),
        sample=json.dumps(raw_data[:10], indent=2),
    )

    llm = _get_llm()
    full_content = ""
    for chunk in llm.stream([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ]):
        full_content += chunk.content or ""
    # Strip <think>...</think> blocks in case Qwen3 thinking mode leaks through
    import re
    transformation_plan = re.sub(r"<think>.*?</think>", "", full_content, flags=re.DOTALL).strip()

    audit_log.append({
        "timestamp": datetime.utcnow().isoformat(),
        "agent": "Architect",
        "action": "plan",
        "summary": f"Transformation plan generated ({len(transformation_plan)} chars).",
    })

    return {
        "transformation_plan": transformation_plan,
        "audit_log": audit_log,
    }