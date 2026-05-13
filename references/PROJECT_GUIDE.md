# ETL Agent — Project Guide

A reference for understanding the concepts, architecture, and file dependencies in this project.

---

## Table of Contents

1. [Core Concepts](#1-core-concepts)
   - [ETL](#11-etl)
   - [Agents](#12-agents)
   - [LangChain](#13-langchain)
   - [LangGraph](#14-langgraph)
   - [Ollama](#15-ollama)
   - [State](#16-state-the-glue-between-agents)
2. [How This Project Uses These Concepts](#2-how-this-project-uses-these-concepts)
3. [File Map & Dependency Path](#3-file-map--dependency-path)
4. [Execution Flow (Step by Step)](#4-execution-flow-step-by-step)
5. [Retry & Escalation Logic](#5-retry--escalation-logic)
6. [Data Flow Through State](#6-data-flow-through-state)
7. [Environment & Configuration](#7-environment--configuration)

---

## 1. Core Concepts

### 1.1 ETL

**ETL** stands for **Extract, Transform, Load** — a classic data engineering pipeline pattern:

| Phase | What it does | Who does it here |
|-------|-------------|-----------------|
| **Extract** | Pull raw data from a source (CSV file, API, database) | `Scout` agent |
| **Transform** | Clean, reshape, and process the data | `Architect` + `Engineer` agents |
| **Load** | Write the processed data to a destination | `Loader` agent |

### 1.2 Agents

In AI/LLM context, an **agent** is a unit of work that:
- Receives some input (here: a shared state dict)
- Performs a task (either deterministic Python or an LLM call)
- Returns updated state

This project has 4 agents: Scout, Architect, Engineer, Loader. Two of them (Architect, Engineer) use a language model; two (Scout, Loader) are plain Python.

### 1.3 LangChain

**LangChain** is a Python framework for building LLM-powered applications. Think of it as a toolkit that wraps raw LLM APIs and gives you:

- **`ChatOllama`** — a client that talks to a locally-running Ollama LLM server
- **`SystemMessage` / `HumanMessage`** — structured prompt objects (instead of raw strings)
- **Prompt templates** — reusable, parameterized prompts

In this project, LangChain is used *only* inside the Architect and Engineer agents to send prompts and receive text back from the LLM.

**Minimal example of what LangChain does here:**
```python
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

llm = ChatOllama(model="qwen2.5:14b-instruct-q4_K_M", base_url="http://...")
response = llm.invoke([
    SystemMessage(content="You are a data engineer."),
    HumanMessage(content="Plan a transformation for this schema: ..."),
])
plan = response.content  # plain text
```

### 1.4 LangGraph

**LangGraph** is a LangChain extension for building **stateful, multi-step agent workflows as a graph**.

Key ideas:

| Concept | What it means |
|---------|--------------|
| **StateGraph** | The graph object that holds all nodes and edges |
| **Node** | A Python function that takes state → returns updated state |
| **Edge** | A fixed connection: "after node A, always go to node B" |
| **Conditional Edge** | "after node A, call a router function to decide which node to go to next" |
| **Compile** | Turns the graph definition into a runnable object |
| **Invoke** | Runs the graph from the entry point with an initial state |

**Minimal example:**
```python
from langgraph.graph import StateGraph, END
from typing import TypedDict

class MyState(TypedDict):
    value: int

def node_a(state): return {"value": state["value"] + 1}
def node_b(state): return {"value": state["value"] * 2}

graph = StateGraph(MyState)
graph.add_node("a", node_a)
graph.add_node("b", node_b)
graph.add_edge("a", "b")          # always go a → b
graph.add_edge("b", END)
graph.set_entry_point("a")

pipeline = graph.compile()
result = pipeline.invoke({"value": 5})  # → {"value": 12}
```

LangGraph handles execution order, state merging between nodes, and loop detection.

### 1.5 Ollama

**Ollama** is a local LLM server. Instead of calling OpenAI's cloud API, you run a model on your own machine (or a GPU server). Here the model is `qwen2.5:14b-instruct-q4_K_M` running on a remote GPU reachable via Tailscale VPN at `OLLAMA_HOST`.

LangChain's `ChatOllama` is the client that talks to it.

### 1.6 State — The Glue Between Agents

Rather than passing arguments between functions directly, LangGraph uses a **shared state dict** that flows through every node. Each node reads what it needs and returns only the fields it updates.

```
Initial State ──► Scout ──► Architect ──► Engineer ──► Loader ──► Final State
                   adds        adds          adds         adds
               raw_data   plan          code,result    (writes
               raw_schema                verdict       to disk/db)
```

---

## 2. How This Project Uses These Concepts

```
LangGraph orchestrates the graph
    └─ 4 nodes (agents) connected by edges
    └─ 1 conditional edge (the router after Engineer)
    └─ Shared ETLState flows through all nodes

LangChain is used inside 2 of the 4 nodes
    └─ Architect: LLM generates a plain-text transformation plan
    └─ Engineer: LLM generates Python code, then exec() runs it

Ollama serves the LLM
    └─ Model: qwen2.5:14b on a remote GPU
    └─ Connected via OLLAMA_HOST env var
```

---

## 3. File Map & Dependency Path

### Directory Overview

```
ETL_Agent/
├── main.py           ← Entry point. Call run_pipeline() here.
├── graph.py          ← Assembles the LangGraph StateGraph
├── etl_state.py      ← Defines the shared ETLState TypedDict
├── router.py         ← Routing logic after Engineer node
├── agents/
│   ├── scout.py      ← Node 1: Extract raw data
│   ├── architect.py  ← Node 2: LLM plans transformation
│   ├── engineer.py   ← Node 3: LLM writes + runs code
│   └── loader.py     ← Node 4: Write output to file/db
├── tools/
│   ├── csv_tools.py  ← Helper: read CSV, infer schema
│   └── api_tools.py  ← Helper: fetch Alpha Vantage API
├── script.py         ← Demo: runs pipeline on Coursera CSV
├── datasets/
│   └── coursea_data.csv  ← Sample dataset
└── requirements.txt  ← Python dependencies
```

### Who Imports Who

```
script.py
  └─ imports main.py → run_pipeline()

main.py
  ├─ imports etl_state.py → ETLState
  └─ imports graph.py → build_graph()

graph.py
  ├─ imports etl_state.py → ETLState
  ├─ imports agents/scout.py → scout_node
  ├─ imports agents/architect.py → architect_node
  ├─ imports agents/engineer.py → engineer_node
  ├─ imports agents/loader.py → loader_node
  └─ imports router.py → engineer_router

agents/scout.py
  ├─ imports tools/csv_tools.py → read_csv, infer_schema
  └─ imports tools/api_tools.py → fetch_alpha_vantage

agents/architect.py
  └─ imports langchain_ollama → ChatOllama (external library)

agents/engineer.py
  └─ imports langchain_ollama → ChatOllama (external library)

agents/loader.py
  └─ imports sqlalchemy → create_engine (external library)

tools/csv_tools.py
  └─ imports pandas (external library)

tools/api_tools.py
  └─ imports requests (external library)
```

### Dependency Tree (Visual)

```
main.py ──────────────── graph.py ─────────────── router.py
   │                         │
   │                         ├── agents/scout.py ──── tools/csv_tools.py (pandas)
   │                         │                   └─── tools/api_tools.py (requests)
   │                         │
   │                         ├── agents/architect.py ─ langchain_ollama (ChatOllama)
   │                         │                         langchain_core (Messages)
   │                         │
   │                         ├── agents/engineer.py ── langchain_ollama (ChatOllama)
   │                         │
   │                         └── agents/loader.py ──── sqlalchemy
   │                                                    pandas
   │
   └── etl_state.py (ETLState TypedDict — used by ALL files above)
```

---

## 4. Execution Flow (Step by Step)

**Starting point:** `script.py` or `python main.py`

```
1. script.py
   └─ calls run_pipeline() in main.py

2. main.py: run_pipeline()
   ├─ builds initial ETLState dict (all fields, most empty)
   └─ calls build_graph() from graph.py
      └─ returns a compiled LangGraph pipeline

3. pipeline.invoke(initial_state)
   │
   ▼
┌─────────────────────────────────────────────────────┐
│                   SCOUT NODE                        │
│  agents/scout.py → scout_node(state)                │
│                                                     │
│  IF source_type == "csv":                           │
│    tools/csv_tools.py: read_csv(path)               │
│       → pandas.read_csv() → list of dicts           │
│  IF source_type == "api":                           │
│    tools/api_tools.py: fetch_alpha_vantage(...)     │
│       → requests.get(Alpha Vantage URL)             │
│       → _flatten_alpha_vantage() cleans nested JSON │
│                                                     │
│  tools/csv_tools.py: infer_schema(records)          │
│       → {column_name: "int"/"str"/"float"/...}      │
│                                                     │
│  State updated: raw_data, raw_schema, audit_log     │
└──────────────────────────┬──────────────────────────┘
                           │ (fixed edge: always goes to Architect)
                           ▼
┌─────────────────────────────────────────────────────┐
│                 ARCHITECT NODE                      │
│  agents/architect.py → architect_node(state)        │
│                                                     │
│  Reads: raw_schema, raw_data (first 3 rows),        │
│         target_path, user_instructions              │
│                                                     │
│  Calls ChatOllama (Qwen2.5 via Ollama)              │
│    → SystemMessage: "You are a data engineer..."    │
│    → HumanMessage: schema + sample rows + goal      │
│    → LLM returns: plain-text numbered steps         │
│                                                     │
│  State updated: transformation_plan, audit_log      │
└──────────────────────────┬──────────────────────────┘
                           │ (fixed edge: always goes to Engineer)
                           ▼
┌─────────────────────────────────────────────────────┐
│                 ENGINEER NODE                       │
│  agents/engineer.py → engineer_node(state)          │
│                                                     │
│  Reads: transformation_plan, raw_data, raw_schema,  │
│         retry_count, max_retries                    │
│                                                     │
│  Calls ChatOllama (temp=0.0 for determinism)        │
│    → LLM returns: Python code as a string           │
│                                                     │
│  _extract_code() strips markdown fences             │
│                                                     │
│  exec(code, namespace)  ← actually runs the code!  │
│    namespace = {raw_data, pd, json, result=None}    │
│    code must assign output to `result`              │
│                                                     │
│  If success:  engineer_verdict = "pass"             │
│  If error + retries left: verdict = "retry"         │
│  If error + no retries:   verdict = "escalate"      │
│                                                     │
│  State updated: transformation_code, transformed_data│
│                 engineer_verdict, retry_count        │
└──────────────────────────┬──────────────────────────┘
                           │ (CONDITIONAL edge)
                           ▼
                    ┌─────────────┐
                    │   ROUTER    │
                    │ router.py   │
                    │engineer_    │
                    │router(state)│
                    └──────┬──────┘
           ┌───────────────┼────────────────┐
           │               │                │
        "pass"          "retry"        "escalate"    "terminate"
           │               │                │              │
           ▼               ▼                ▼              ▼
       LOADER          ENGINEER        ARCHITECT         END
       (below)         (loops back)    (loops back)    (abort)

┌─────────────────────────────────────────────────────┐
│                   LOADER NODE                       │
│  agents/loader.py → loader_node(state)              │
│                                                     │
│  Reads: transformed_data, target_path, target_db    │
│                                                     │
│  IF target_db is set:                               │
│    SQLite: sqlalchemy engine + pandas.to_sql()      │
│    PostgreSQL: connection_string + pandas.to_sql()  │
│                                                     │
│  IF target_path is set:                             │
│    .csv → pandas.to_csv()                           │
│    .json → json.dump()                              │
│                                                     │
│  State updated: audit_log                           │
└──────────────────────────┬──────────────────────────┘
                           │ (fixed edge: → END)
                           ▼
                       PIPELINE END
                  returns final ETLState
```

---

## 5. Retry & Escalation Logic

The Engineer node can fail (e.g., the LLM generates bad code). Here's what happens:

```
Engineer runs generated code
        │
        ├── SUCCESS ────────────────────────────► verdict = "pass" → Loader
        │
        └── EXCEPTION (code crashes)
                │
                ├── retry_count < max_retries ──► verdict = "retry"
                │      retry_count += 1             │
                │                                   └─► back to Engineer
                │                                       (same plan, new code attempt)
                │
                └── retry_count >= max_retries ──► verdict = "escalate"
                                                    │
                                                    └─► back to Architect
                                                        (generate a new plan,
                                                         then Engineer tries again)
```

`max_retries` is set in `run_pipeline()` and stored in the state.

---

## 6. Data Flow Through State

`ETLState` is a TypedDict (a typed Python dict). Each field is written by one agent and read by the next:

```
Field                 Written by    Read by
─────────────────────────────────────────────────
source_type           main.py       scout
source_config         main.py       scout
user_instructions     main.py       architect
target_path           main.py       architect, loader
target_db             main.py       loader
max_retries           main.py       engineer

raw_data              scout         architect, engineer
raw_schema            scout         architect, engineer

transformation_plan   architect     engineer

transformation_code   engineer      (logged only)
transformed_data      engineer      loader
engineer_verdict      engineer      router
engineer_error        engineer      (logged only)
retry_count           main.py/eng.  engineer

audit_log             all agents    (append-only, returned at end)
```

---

## 7. Environment & Configuration

### Required: `.env` file

```bash
OLLAMA_HOST=http://<gpu-server-ip>:11434   # Ollama LLM server address
ALPHA_VANTAGE_API_KEY=<your-key>           # Only needed for API source mode
```

### Python Dependencies (`requirements.txt`)

| Package | Role |
|---------|------|
| `langgraph` | Graph orchestration (runs the pipeline) |
| `langchain` | LLM framework (prompts, message types) |
| `langchain-ollama` | ChatOllama client for local LLM |
| `langchain-core` | Core message types (SystemMessage, HumanMessage) |
| `python-dotenv` | Loads `.env` into environment |
| `pandas` | CSV reading, data manipulation, writing to SQL |
| `requests` | HTTP calls to Alpha Vantage API |
| `sqlalchemy` | Database connection (SQLite/PostgreSQL) |

### Running the Pipeline

```bash
# Install dependencies
pip install -r requirements.txt

# Run the demo on Coursera CSV → SQLite
python script.py

# Or run the built-in stock price demo
python main.py
```

---

## Quick Reference: Which File Does What

| File | One-liner |
|------|-----------|
| `main.py` | Entry point; builds initial state and runs the graph |
| `graph.py` | Wires all 4 nodes and edges into a LangGraph StateGraph |
| `etl_state.py` | Defines every field that flows between agents |
| `router.py` | Decides where to go after Engineer (pass/retry/escalate) |
| `agents/scout.py` | Extracts raw data from CSV or Alpha Vantage API |
| `agents/architect.py` | Asks LLM to produce a plain-text transformation plan |
| `agents/engineer.py` | Asks LLM to write Python code, then executes it |
| `agents/loader.py` | Writes transformed data to a file or database |
| `tools/csv_tools.py` | `read_csv()` and `infer_schema()` helpers for Scout |
| `tools/api_tools.py` | `fetch_alpha_vantage()` HTTP helper for Scout |
| `script.py` | Demo script: Coursera CSV → SQLite |
| `datasets/coursea_data.csv` | Sample messy dataset for testing |
