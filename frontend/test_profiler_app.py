"""
DataWeaver — GPU Profiler Demo
Standalone test app. Loads the NYC taxi parquet directly, runs the Profiler
node, and displays results. No backend required.

Run from project root:
    streamlit run frontend/test_profiler_app.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import time
import pandas as pd
import streamlit as st

from tools.csv_tools import infer_schema
from agents.profiler import profiler_node, _CUDA_AVAILABLE, GPU_THRESHOLD

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DataWeaver · GPU Profiler Demo",
    layout="wide",
)

# ── Styles (lifted from app_t3) ───────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap');

    html, body, [class*="css"] { font-family: 'DM Sans', system-ui, sans-serif; }
    .block-container { padding-top: 2.5rem; padding-bottom: 1.8rem; max-width: 1200px; }

    [data-testid="stAppViewContainer"] {
        background-color: #0b0114;
        background-image:
            linear-gradient(rgba(255,255,255,0.018) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.018) 1px, transparent 1px),
            radial-gradient(ellipse 95% 70% at 50% -12%, rgba(124,58,237,0.26), transparent 56%),
            linear-gradient(188deg, #160d22 0%, #0b0114 45%, #07030c 100%);
        background-size: 52px 52px, 52px 52px, auto, auto;
        background-attachment: fixed;
    }

    .dw-hero {
        background: radial-gradient(ellipse 110% 90% at 50% 0%, rgba(168,85,247,0.14), transparent 58%),
                    linear-gradient(148deg, #22182e 0%, #1a1224 50%, #17101f 100%);
        color: #d4cee0; padding: 1.25rem 1.4rem; border-radius: 16px;
        margin-bottom: 1.1rem; border: 1px solid rgba(45,27,78,0.85);
        box-shadow: 0 0 0 1px rgba(255,255,255,0.04) inset, 0 16px 48px rgba(0,0,0,0.48);
    }
    .dw-hero h1 { margin: 0; font-size: 1.35rem; font-weight: 700; color: #ffffff; }
    .dw-hero p  { margin: 0.45rem 0 0 0; font-size: 0.92rem; color: #b0a8bf; }

    .dw-badge {
        display: inline-block; background: rgba(168,85,247,0.16); color: #e9d5ff;
        padding: 0.2rem 0.6rem; border-radius: 8px; font-size: 0.72rem; font-weight: 600;
        margin-bottom: 0.45rem; border: 1px solid rgba(45,27,78,0.65);
    }
    .dw-badge-gpu {
        display: inline-block; background: rgba(34,197,94,0.15); color: #86efac;
        padding: 0.2rem 0.6rem; border-radius: 8px; font-size: 0.72rem; font-weight: 700;
        border: 1px solid rgba(34,197,94,0.4); letter-spacing: 0.05em;
    }
    .dw-badge-cpu {
        display: inline-block; background: rgba(251,191,36,0.15); color: #fcd34d;
        padding: 0.2rem 0.6rem; border-radius: 8px; font-size: 0.72rem; font-weight: 700;
        border: 1px solid rgba(251,191,36,0.4); letter-spacing: 0.05em;
    }

    .dw-card {
        background: linear-gradient(180deg, #1f1528 0%, #1a1224 100%);
        border: 1px solid rgba(45,27,78,0.82); border-radius: 14px;
        padding: 0.85rem 1.05rem; margin: 0.75rem 0;
        box-shadow: 0 0 0 1px rgba(255,255,255,0.035) inset, 0 12px 36px rgba(0,0,0,0.42);
        color: #d4cee0;
    }

    .dw-stat-grid {
        display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.7rem; margin-bottom: 1rem;
    }
    .dw-stat {
        background: linear-gradient(180deg, #1f1528 0%, #1a1224 100%);
        border: 1px solid rgba(45,27,78,0.75); border-radius: 14px;
        padding: 0.75rem 1rem; text-align: center;
        box-shadow: 0 0 0 1px rgba(255,255,255,0.03) inset;
    }
    .dw-stat-val { font-size: 1.5rem; font-weight: 700; color: #f8f7fc; }
    .dw-stat-lbl { font-size: 0.7rem; color: #b0a8bf; font-weight: 600;
                   letter-spacing: 0.08em; text-transform: uppercase; margin-top: 0.2rem; }

    .dw-col-row {
        display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 0.6rem;
        border-bottom: 1px solid rgba(45,27,78,0.45); font-size: 0.83rem;
    }
    .dw-col-name { font-weight: 600; color: #e9d5ff; width: 200px; flex-shrink: 0;
                   font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; }
    .dw-col-type { color: #a78bfa; width: 60px; font-size: 0.75rem; }
    .dw-col-val  { color: #cbd5e1; flex: 1; font-size: 0.8rem; }
    .dw-null-hi  { color: #f87171; font-weight: 600; }
    .dw-null-ok  { color: #86efac; }

    [data-testid="stMetric"] {
        border: 1px solid rgba(45,27,78,0.75); border-radius: 14px;
        background: linear-gradient(180deg, #1f1528 0%, #1a1224 100%);
        padding: 0.4rem 0.6rem;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(180deg, #a855f7, #7c3aed);
        border: none; font-weight: 600; border-radius: 12px;
        min-height: 2.35rem; color: #ffffff;
        box-shadow: 0 4px 18px rgba(168,85,247,0.35);
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(180deg, #c084fc, #9333ea);
    }
    .main .stMarkdown p, .main .stMarkdown li { color: #d4cee0 !important; }
    .main .stMarkdown h1, .main .stMarkdown h2, .main .stMarkdown h3 { color: #f8f7fc !important; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
gpu_badge = (
    '<span class="dw-badge-gpu">CUDA GPU</span>'
    if _CUDA_AVAILABLE else
    '<span class="dw-badge-cpu">CPU fallback</span>'
)
st.markdown(f"""
<div class="dw-hero">
    <div class="dw-badge">DataWeaver · Profiler Demo</div>
    <h1>GPU-Accelerated Data Profiler</h1>
    <p>Parallel column statistics via Numba CUDA kernels &nbsp;·&nbsp; {gpu_badge}
       &nbsp;·&nbsp; GPU threshold: <strong>{GPU_THRESHOLD:,}</strong> rows
    </p>
</div>
""", unsafe_allow_html=True)

# ── Dataset selector ──────────────────────────────────────────────────────────
DEFAULT_PARQUET = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "datasets", "yellow_tripdata_2025-01.parquet")
)

with st.sidebar:
    st.markdown("### Dataset")
    dataset_choice = st.radio(
        "Source",
        ["NYC Taxi (parquet — Jan 2025)", "Upload CSV"],
        label_visibility="collapsed",
    )
    uploaded_csv = None
    if dataset_choice == "Upload CSV":
        uploaded_csv = st.file_uploader("Upload CSV", type=["csv"])

    st.markdown("---")
    st.markdown("### About")
    st.markdown(
        "Profiler runs **CUDA kernels** when row count ≥ "
        f"`{GPU_THRESHOLD:,}` and a GPU is available. "
        "Otherwise falls back to NumPy."
    )
    if _CUDA_AVAILABLE:
        st.success("CUDA detected — GPU path active")
    else:
        st.warning("No CUDA device — using CPU path")

# ── Load & run ────────────────────────────────────────────────────────────────
run = st.button("Run Profiler", type="primary", use_container_width=False)

if run:
    # Load data
    with st.spinner("Loading dataset..."):
        t_load = time.time()
        if dataset_choice == "NYC Taxi (parquet — Jan 2025)":
            if not os.path.exists(DEFAULT_PARQUET):
                st.error(f"Parquet file not found at `{DEFAULT_PARQUET}`. "
                         "Make sure the file is in the `datasets/` folder.")
                st.stop()
            df = pd.read_parquet(DEFAULT_PARQUET)
        else:
            if uploaded_csv is None:
                st.warning("Please upload a CSV file first.")
                st.stop()
            df = pd.read_csv(uploaded_csv)

        raw_data = df.to_dict(orient="records")
        raw_schema = infer_schema(raw_data)
        load_time = time.time() - t_load

    st.success(f"Loaded **{len(raw_data):,}** rows in `{load_time:.1f}s`")

    # Run profiler
    with st.spinner("Running profiler..."):
        state = {"raw_data": raw_data, "raw_schema": raw_schema, "audit_log": []}
        t_profile = time.time()
        result = profiler_node(state)
        profile_time = time.time() - t_profile

    profile = result["data_profile"]
    backend = profile["backend"].upper()
    n_rows = profile["row_count"]
    n_cols = len(profile["columns"])

    # ── Summary stats ─────────────────────────────────────────────────────────
    backend_badge = (
        '<span class="dw-badge-gpu">CUDA GPU</span>'
        if profile["backend"] == "cuda" else
        '<span class="dw-badge-cpu">CPU</span>'
    )
    st.markdown(f"""
    <div class="dw-stat-grid">
        <div class="dw-stat">
            <div class="dw-stat-val">{n_rows:,}</div>
            <div class="dw-stat-lbl">Rows profiled</div>
        </div>
        <div class="dw-stat">
            <div class="dw-stat-val">{n_cols}</div>
            <div class="dw-stat-lbl">Columns</div>
        </div>
        <div class="dw-stat">
            <div class="dw-stat-val">{profile_time:.2f}s</div>
            <div class="dw-stat-lbl">Profile time</div>
        </div>
        <div class="dw-stat">
            <div class="dw-stat-val">{backend_badge}</div>
            <div class="dw-stat-lbl">Backend</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Per-column table ──────────────────────────────────────────────────────
    st.markdown("#### Column Statistics")
    st.markdown('<div class="dw-card">', unsafe_allow_html=True)

    rows_html = []
    for col, stats in profile["columns"].items():
        dtype = stats.get("type", "?")
        null_count = stats.get("null_count", 0)
        null_pct = (null_count / n_rows * 100) if n_rows else 0
        null_cls = "dw-null-hi" if null_pct > 5 else "dw-null-ok"

        if dtype in ("int", "float"):
            mn = stats.get("min")
            mx = stats.get("max")
            mean = stats.get("mean")
            detail = (
                f"min <strong>{mn:.2f}</strong> &nbsp;·&nbsp; "
                f"max <strong>{mx:.2f}</strong> &nbsp;·&nbsp; "
                f"mean <strong>{mean:.2f}</strong>"
            ) if mn is not None else "all null"
        else:
            unique = stats.get("unique_count", "—")
            detail = f"unique values: <strong>{unique:,}</strong>" if isinstance(unique, int) else "—"

        rows_html.append(f"""
        <div class="dw-col-row">
            <span class="dw-col-name">{col}</span>
            <span class="dw-col-type">{dtype}</span>
            <span class="dw-col-val">{detail}</span>
            <span class="dw-col-val {null_cls}">
                {null_count:,} nulls ({null_pct:.1f}%)
            </span>
        </div>
        """)

    st.markdown("".join(rows_html), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Audit log ─────────────────────────────────────────────────────────────
    with st.expander("Audit log"):
        st.json(result["audit_log"])
