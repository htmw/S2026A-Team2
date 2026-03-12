import io
import json
from typing import Dict, List

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="DataWeaver – Distributed Agentic Data Pipeline",
    layout="wide",
)

# ------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------
def profile_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Basic profiling for each column."""
    profile = []
    n_rows = len(df)
    for col in df.columns:
        series = df[col]
        profile.append(
            {
                "column": col,
                "dtype": str(series.dtype),
                "non_null_count": series.notna().sum(),
                "null_count": series.isna().sum(),
                "null_pct": round(series.isna().mean() * 100, 2),
                "unique_values": series.nunique(dropna=True),
                "sample_values": ", ".join(map(str, series.dropna().unique()[:5])),
            }
        )
    return pd.DataFrame(profile)


def guess_keys(dfs: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, List[str]]]:
    """
    Naive key guessing based on column name patterns.
    This is a placeholder for your Mapper agent.
    """
    key_patterns = ["id", "_id", "Id", "ID"]
    result = {}
    for name, df in dfs.items():
        primary = []
        foreign = []
        for col in df.columns:
            lc = col.lower()
            if lc == "id" or lc.endswith("_id"):
                primary.append(col)
            elif any(p in col for p in key_patterns):
                foreign.append(col)
        result[name] = {"primary_keys": primary, "foreign_keys": foreign}
    return result


def generate_mermaid_erd(schema_guess: Dict[str, Dict[str, List[str]]]) -> str:
    """
    Generate a very simple Mermaid ER diagram based on guessed keys.
    This is illustrative; your real Mapper would output a richer ERD.
    """
    lines = ["erDiagram"]
    # Entities
    for table, keys in schema_guess.items():
        lines.append(f"    {table} {{")
        for pk in keys["primary_keys"]:
            lines.append(f"        INT {pk}")
        for fk in keys["foreign_keys"]:
            lines.append(f"        INT {fk}")
        if not keys["primary_keys"] and not keys["foreign_keys"]:
            lines.append("        STRING column")
        lines.append("    }")

    # Naive relationships: fk columns referencing other tables' PKs by name
    table_names = list(schema_guess.keys())
    for t1 in table_names:
        for fk in schema_guess[t1]["foreign_keys"]:
            for t2 in table_names:
                if t2 == t1:
                    continue
                if fk in schema_guess[t2]["primary_keys"]:
                    # one-to-many t2 -> t1
                    lines.append(f"    {t2} ||--o{{ {t1} : \"{fk}\"")

    return "\n".join(lines)


def run_naive_aggregator(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Very naive join logic:
    - If there is a common 'id' or '<name>_id', perform left joins in sequence.
    This is just a placeholder for your Engineer agent.
    """
    if not dfs:
        return pd.DataFrame()

    items = list(dfs.items())
    base_name, base_df = items[0]
    joined = base_df.copy()
    source_rows = len(joined)

    for name, df in items[1:]:
        common_cols = list(set(joined.columns) & set(df.columns))
        key_candidates = [c for c in common_cols if c.lower() == "id" or c.lower().endswith("_id")]
        if not key_candidates:
            # Skip if we don't know how to join
            continue
        key = key_candidates[0]
        joined = joined.merge(df, on=key, how="left", suffixes=("", f"_{name}"))

    # Invariant check: R_final <= product of source sizes (always true for left joins, but we compute anyway)
    final_rows = len(joined)
    product_rows = 1
    for _, df in dfs.items():
        product_rows *= max(1, len(df))

    invariant_ok = final_rows <= product_rows

    return joined, {
        "R_final": final_rows,
        "R_product_sources": product_rows,
        "invariant_ok": invariant_ok,
        "source_rows_first_table": source_rows,
    }


def to_csv_download(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


# ------------------------------------------------------------------------------------
# Sidebar – Navigation
# ------------------------------------------------------------------------------------
st.sidebar.title("DataWeaver – Sprint 0 MVP")
page = st.sidebar.radio(
    "Navigate",
    [
        "1. Upload & Profiling",
        "2. Mapper (Architect) View",
        "3. HITL Checkpoint #1",
        "4. Aggregator (Engineer) Run",
        "5. HITL Checkpoint #2",
        "6. Logs & Downloads",
    ],
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Status**: Sprint 0 UI Prototype")


# ------------------------------------------------------------------------------------
# Session State
# ------------------------------------------------------------------------------------
if "uploaded_dfs" not in st.session_state:
    st.session_state.uploaded_dfs: Dict[str, pd.DataFrame] = {}

if "mapper_output" not in st.session_state:
    st.session_state.mapper_output = None  # JSON-like structure

if "mapper_approved" not in st.session_state:
    st.session_state.mapper_approved = False

if "aggregator_output" not in st.session_state:
    st.session_state.aggregator_output = None  # DataFrame

if "aggregator_report" not in st.session_state:
    st.session_state.aggregator_report = None  # Dict

if "run_logs" not in st.session_state:
    st.session_state.run_logs = []  # List of dicts


# ------------------------------------------------------------------------------------
# 1. Upload & Profiling
# ------------------------------------------------------------------------------------
if page == "1. Upload & Profiling":
    st.title("CSV Upload & Profiling")

    st.markdown(
        """
        Upload **multiple CSVs** from fragmented legacy systems.
        The app performs basic profiling as the **foundational cataloging step**.
        """
    )

    uploaded_files = st.file_uploader(
        "Upload one or more CSV files",
        type=["csv"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        st.session_state.uploaded_dfs = {}
        for f in uploaded_files:
            df = pd.read_csv(f)
            st.session_state.uploaded_dfs[f.name] = df

        st.success(f"Loaded {len(st.session_state.uploaded_dfs)} file(s).")

        for name, df in st.session_state.uploaded_dfs.items():
            st.subheader(f"File: {name}")
            with st.expander("Preview (first 10 rows)", expanded=False):
                st.dataframe(df.head(10), use_container_width=True)

            with st.expander("Column profiling", expanded=False):
                profile = profile_dataframe(df)
                st.dataframe(profile, use_container_width=True)

        st.info("Proceed to **Mapper (Architect) View** once profiling looks correct.")

# ------------------------------------------------------------------------------------
# 2. Mapper (Architect) View
# ------------------------------------------------------------------------------------
elif page == "2. Mapper (Architect) View":
    st.title("Mapper (Architect) – Schema & ERD")

    if not st.session_state.uploaded_dfs:
        st.warning("No CSVs uploaded yet. Go to **1. Upload & Profiling** first.")
    else:
        st.markdown(
            """
            The **Mapper agent** infers:
            - Primary and foreign keys  
            - Table relationships and ERD  
            - A standardized data dictionary  
            
            Below is a **placeholder / mock** of what your real agent will produce.
            """
        )

        if st.button("Run Mapper (mock)"):
            schema_guess = guess_keys(st.session_state.uploaded_dfs)
            mermaid_erd = generate_mermaid_erd(schema_guess)

            # Simple data dictionary mock
            data_dict = []
            for name, df in st.session_state.uploaded_dfs.items():
                for col in df.columns:
                    data_dict.append(
                        {
                            "table": name,
                            "column": col,
                            "dtype": str(df[col].dtype),
                            "description": "",  # to be completed by Mapper/HITL
                        }
                    )
            mapper_output = {
                "schema_guess": schema_guess,
                "mermaid_erd": mermaid_erd,
                "data_dictionary": data_dict,
            }
            st.session_state.mapper_output = mapper_output
            st.session_state.mapper_approved = False

        if st.session_state.mapper_output:
            st.subheader("Inferred schema (mock)")
            st.json(st.session_state.mapper_output["schema_guess"])

            st.subheader("ERD (Mermaid)")
            st.markdown(
                "```mermaid\n" + st.session_state.mapper_output["mermaid_erd"] + "\n```"
            )

            st.subheader("Data Dictionary (mock)")
            dd_df = pd.DataFrame(st.session_state.mapper_output["data_dictionary"])
            st.dataframe(dd_df, use_container_width=True)

            st.info("Review these mappings, then proceed to **HITL Checkpoint #1**.")

# ------------------------------------------------------------------------------------
# 3. HITL Checkpoint #1
# ------------------------------------------------------------------------------------
elif page == "3. HITL Checkpoint #1":
    st.title("Human-in-the-Loop Checkpoint #1")

    if not st.session_state.mapper_output:
        st.warning("Mapper output not available. Run Mapper on page 2 first.")
    else:
        st.markdown(
            """
            Validate the **inferred ERD and mappings** before any execution  
            to prevent semantic hallucinations.
            """
        )

        st.subheader("Mapper Output (read-only preview)")
        st.json(st.session_state.mapper_output["schema_guess"])

        st.subheader("Approval")
        approved = st.checkbox(
            "I confirm that the inferred ERD and mappings look correct (or acceptable for a test run).",
            value=st.session_state.mapper_approved,
        )

        if st.button("Save Decision"):
            st.session_state.mapper_approved = approved
            log_entry = {
                "stage": "HITL #1",
                "approved": approved,
            }
            st.session_state.run_logs.append(log_entry)

            if approved:
                st.success("Mappings approved. You can now proceed to Aggregator (Engineer) Run.")
            else:
                st.warning("Mappings NOT approved. Please adjust Mapper config or inputs before running Aggregator.")

# ------------------------------------------------------------------------------------
# 4. Aggregator (Engineer) Run
# ------------------------------------------------------------------------------------
elif page == "4. Aggregator (Engineer) Run":
    st.title("Aggregator (Engineer) – Execution & Invariants")

    if not st.session_state.uploaded_dfs:
        st.warning("No CSVs uploaded yet. Go to **1. Upload & Profiling** first.")
    elif not st.session_state.mapper_output:
        st.warning("Mapper output not available. Run Mapper on page 2 first.")
    elif not st.session_state.mapper_approved:
        st.warning(
            "Mappings are not yet approved in HITL #1. Approve them on page 3 before executing."
        )
    else:
        st.markdown(
            """
            The **Engineer agent** translates validated mappings into executable code,
            runs joins and cleaning, and enforces **deterministic invariants**.
            """
        )

        if st.button("Run Aggregator (mock)"):
            df_joined, report = run_naive_aggregator(st.session_state.uploaded_dfs)
            st.session_state.aggregator_output = df_joined
            st.session_state.aggregator_report = report

            log_entry = {
                "stage": "Aggregator",
                "report": report,
            }
            st.session_state.run_logs.append(log_entry)

        if st.session_state.aggregator_output is not None:
            st.subheader("Validation Report (mock)")
            st.json(st.session_state.aggregator_report)

            if st.session_state.aggregator_report["invariant_ok"]:
                st.success("Row-count invariant satisfied.")
            else:
                st.error("Row-count invariant violated! Move to HITL Checkpoint #2.")

            st.subheader("Cleaned / Aggregated Dataset (preview)")
            st.dataframe(
                st.session_state.aggregator_output.head(20),
                use_container_width=True,
            )

# ------------------------------------------------------------------------------------
# 5. HITL Checkpoint #2
# ------------------------------------------------------------------------------------
elif page == "5. HITL Checkpoint #2":
    st.title("Human-in-the-Loop Checkpoint #2")

    if st.session_state.aggregator_report is None:
        st.warning("No Aggregator run found. Execute Aggregator on page 4 first.")
    else:
        st.markdown(
            """
            If **invariants fail**, review logs and (in the full system)  
            generated code before re-running to avoid infinite agent loops.
            """
        )

        st.subheader("Invariant Report")
        st.json(st.session_state.aggregator_report)

        decision = st.radio(
            "Decision",
            [
                "Accept current output",
                "Reject and request manual correction",
            ],
        )

        if st.button("Record HITL #2 Decision"):
            log_entry = {
                "stage": "HITL #2",
                "decision": decision,
            }
            st.session_state.run_logs.append(log_entry)
            st.success("Decision recorded.")

# ------------------------------------------------------------------------------------
# 6. Logs & Downloads
# ------------------------------------------------------------------------------------
elif page == "6. Logs & Downloads":
    st.title("Run Logging & Downloads")

    st.markdown(
        """
        Persist run metadata and provide **downloadable datasets** and a
        **data dictionary** (mock). In production, this would write to SQLite/PostgreSQL.
        """
    )

    st.subheader("Run Logs (current session only)")
    if st.session_state.run_logs:
        st.json(st.session_state.run_logs)
    else:
        st.info("No logs recorded yet.")

    if st.session_state.aggregator_output is not None:
        st.subheader("Download Cleaned Dataset")
        csv_bytes = to_csv_download(st.session_state.aggregator_output)
        st.download_button(
            label="Download cleaned CSV",
            data=csv_bytes,
            file_name="dataweaver_cleaned.csv",
            mime="text/csv",
        )
    else:
        st.info("No cleaned dataset available yet. Run Aggregator on page 4 first.")

    if st.session_state.mapper_output is not None:
        st.subheader("Download Data Dictionary (mock)")
        dd_df = pd.DataFrame(st.session_state.mapper_output["data_dictionary"])
        csv_bytes = to_csv_download(dd_df)
        st.download_button(
            label="Download data dictionary CSV",
            data=csv_bytes,
            file_name="dataweaver_data_dictionary.csv",
            mime="text/csv",
        )
    else:
        st.info("No data dictionary available yet. Run Mapper on page 2 first.")