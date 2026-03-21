"""Architect agent — LLM schema analysis and transformation planning (US2, US5)."""
import json
import os
from datetime import datetime

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage


SYSTEM_PROMPT = """You are the Architect agent in a 4-agent ETL pipeline.
Your job is to analyze raw data and its schema, then produce a clear, step-by-step transformation plan.

Rules:
- Be concise and specific. List numbered steps.
- Each step should describe a single transformation action (e.g. rename column, cast type, filter nulls, normalize values).
- Do NOT write code. Write a human-readable plan only.
- End with a line: VERDICT: ready"""

USER_PROMPT_TEMPLATE = """Analyze the following raw data sample and schema

INSTRUCTIONS FROM ENGINEER:
{user_instructions}

SCHEMA:
{schema}

SAMPLE (first 3 records):
{sample}

TARGET PATH: {target_path}

Produce a numbered transformation plan."""


def _get_llm() -> ChatOllama:
    base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    return ChatOllama(
        model="qwen2.5:14b-instruct-q4_K_M",
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

    sample = raw_data[:3] if raw_data else []

    user_msg = USER_PROMPT_TEMPLATE.format(
        user_instructions=user_instructions,
        schema=json.dumps(raw_schema, indent=2),
        sample=json.dumps(sample, indent=2),
        target_path=target_path,
    )

    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ])
    transformation_plan = response.content.strip()

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
