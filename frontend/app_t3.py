import base64
import html
import io
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import json as _json
import requests
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from urllib.parse import quote

from dw_landing import enter_app_from_starter, render_starter_page

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:5000")


def _svg_data_uri(svg: str) -> str:
    return "data:image/svg+xml," + quote(svg.strip(), safe="")


# Tab favicon (PNG — avoid emoji favicon in browser chrome)
_DW_FAVICON = Path(__file__).resolve().parent / "dw_favicon.png"
# Full-page background for workspace (not used on marketing landing — see dw_landing.py)
_WORKSPACE_BG_PNG = Path(__file__).resolve().parent / "assets" / "dw_workspace_bg.png"


def _png_data_uri(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")

# Sidebar icon assets (account / live support) — minimal line icons, brand purple
_DW_SVG_ACCOUNT_ICON = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48' fill='none'>"
    "<circle cx='24' cy='17' r='8' stroke='#5b21b6' stroke-width='2.2'/>"
    "<path stroke='#5b21b6' stroke-width='2.2' stroke-linecap='round' "
    "d='M10 41c0-7.7 6.3-14 14-14s14 6.3 14 14'/>"
    "</svg>"
)
_DW_SVG_SUPPORT_ICON = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48' fill='none'>"
    "<path stroke='#5b21b6' stroke-width='2' stroke-linecap='round' "
    "d='M10 24v-3a14 14 0 0128 0v3'/>"
    "<rect x='6' y='22' width='10' height='14' rx='3' stroke='#5b21b6' stroke-width='2' fill='#faf5ff'/>"
    "<rect x='32' y='22' width='10' height='14' rx='3' stroke='#5b21b6' stroke-width='2' fill='#faf5ff'/>"
    "<path stroke='#7c3aed' stroke-width='1.8' stroke-linecap='round' d='M33 32l5 4'/>"
    "</svg>"
)
_DW_ICON_ACCOUNT_URI = _svg_data_uri(_DW_SVG_ACCOUNT_ICON)
_DW_ICON_SUPPORT_URI = _svg_data_uri(_DW_SVG_SUPPORT_ICON)

st.set_page_config(
    page_title="DATA WEAVE · t3",
    page_icon=str(_DW_FAVICON) if _DW_FAVICON.is_file() else "📊",
    layout="wide",
)


# -----------------------------------------------------------------------------
# Theme / style
# -----------------------------------------------------------------------------
def _inject_styles() -> None:
    _bg_uri = _png_data_uri(_WORKSPACE_BG_PNG)
    if _bg_uri:
        _st_app_bg = (
            f"""
            [data-testid="stAppViewContainer"] {{
                background-color: #040a12;
                background-image:
                    linear-gradient(
                        198deg,
                        rgba(2, 5, 12, 0.88) 0%,
                        rgba(4, 12, 22, 0.65) 42%,
                        rgba(3, 6, 11, 0.82) 100%
                    ),
                    url("{_bg_uri}");
                background-size: auto, cover;
                background-position: center, center;
                background-repeat: no-repeat, no-repeat;
                background-attachment: fixed, fixed;
            }}
            """
        )
    else:
        _st_app_bg = """
            [data-testid="stAppViewContainer"] {
                background-color: #030507;
                background-image:
                    radial-gradient(ellipse 96% 70% at 50% -15%, rgba(6, 182, 212, 0.26), transparent 56%),
                    linear-gradient(188deg, #060b0e 0%, #030507 52%, #020304 100%);
                background-attachment: fixed;
            }
            """
    _dw_css = (
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&display=swap');
            @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap');
            html, body, [class*="css"] { font-family: 'DM Sans', system-ui, sans-serif; }
            /* Extra top padding clears Streamlit header so first content (e.g. dw-topbar) isn’t clipped */
            .block-container { padding-top: clamp(2.85rem, 5.5vw, 4rem); padding-bottom: 1.8rem; max-width: 1220px; }
            """
        + _st_app_bg
        + """
            .main .block-container { background: transparent; }

            .dw-hero {
                background:
                    radial-gradient(ellipse 110% 90% at 50% 0%, rgba(6, 182, 212, 0.12), transparent 58%),
                    linear-gradient(148deg, #081216 0%, #050a0c 52%, #040608 100%);
                color: #cffafe;
                padding: 1.25rem 1.4rem;
                border-radius: 0;
                margin-bottom: 1.1rem;
                border: 1px solid rgba(34, 211, 238, 0.52);
                box-shadow:
                    0 0 0 1px rgba(6, 182, 212, 0.15) inset,
                    0 16px 48px rgba(0, 0, 0, 0.55),
                    0 0 40px rgba(6, 182, 212, 0.12);
            }
            .dw-hero h1 { margin: 0; font-size: 1.35rem; font-weight: 700; color: #ecfeff; }
            .dw-hero p { margin: 0.45rem 0 0 0; font-size: 0.92rem; color: #9ddcf0; }
            .dw-badge {
                display: inline-block;
                background: rgba(6, 182, 212, 0.12);
                color: #cffafe;
                padding: 0.2rem 0.6rem;
                border-radius: 0;
                font-size: 0.72rem;
                font-weight: 600;
                margin-bottom: 0.45rem;
                border: 1px solid rgba(34, 211, 238, 0.45);
                box-shadow: 0 0 0 1px rgba(6, 182, 212, 0.12) inset;
            }

            .dw-card {
                background: linear-gradient(180deg, #081216 0%, #05090b 100%);
                border: 1px solid rgba(34, 211, 238, 0.38);
                border-radius: 0;
                padding: 0.85rem 1.05rem;
                margin: 0.75rem 0;
                box-shadow:
                    0 0 0 1px rgba(6, 182, 212, 0.1) inset,
                    0 12px 36px rgba(0, 0, 0, 0.5);
                color: #e0fbff;
            }
            .dw-topbar {
                width: 100%;
                background: linear-gradient(92deg, #071014 0%, rgba(8, 47, 58, 0.85) 45%, rgba(6, 182, 212, 0.22) 100%);
                border-radius: 0;
                padding: 0.45rem 1rem;
                margin: 0.35rem 0 0.85rem 0;
                position: sticky;
                top: 3.5rem;
                z-index: 999;
                border: 1px solid rgba(34, 211, 238, 0.4);
                box-shadow:
                    0 0 0 1px rgba(6, 182, 212, 0.12) inset,
                    0 10px 36px rgba(0, 0, 0, 0.45);
            }
            .dw-topbar-text {
                color: #ffffff;
                font-size: 0.74rem;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }
            .dw-feature-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.7rem;
                margin: 0.35rem 0 0.8rem 0;
            }
            .dw-feature {
                background: linear-gradient(175deg, #081216 0%, #060a0c 100%);
                border: 1px solid rgba(34, 211, 238, 0.32);
                border-radius: 0;
                padding: 0.75rem 0.85rem;
                box-shadow:
                    0 0 0 1px rgba(6, 182, 212, 0.08) inset,
                    0 8px 28px rgba(0, 0, 0, 0.45);
            }
            .dw-feature h4 { margin: 0; font-size: 0.87rem; color: #ecfeff; }
            .dw-feature p { margin: 0.25rem 0 0 0; font-size: 0.78rem; color: #9ddcf0; line-height: 1.35; }
            .dw-upload-panel {
                background: linear-gradient(180deg, #081216 0%, #05090b 100%);
                border: 1px solid rgba(34, 211, 238, 0.38);
                border-radius: 0;
                padding: 0.85rem 0.95rem;
                margin-top: 0.2rem;
                box-shadow: 0 0 0 1px rgba(6, 182, 212, 0.1) inset, 0 10px 32px rgba(0, 0, 0, 0.45);
            }

            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, #020608 0%, #071014 52%, #040608 100%);
            }
            /* Fill sidebar height; pin live-support row to the bottom */
            [data-testid="stSidebar"] .block-container {
                padding-top: 0.35rem !important;
                padding-bottom: 0.85rem !important;
                display: flex !important;
                flex-direction: column !important;
                min-height: calc(100vh - 5.75rem) !important;
                box-sizing: border-box !important;
            }
            [data-testid="stSidebar"] [data-testid="stVerticalBlock"]:has(.st-key-dw_sup_open),
            [data-testid="stSidebar"] [data-testid="stVerticalBlock"]:has(.st-key-dw_sup_restore) {
                margin-top: auto !important;
                border-top: 1px solid rgba(148, 163, 184, 0.35) !important;
                padding-top: 0.85rem !important;
            }
            [data-testid="stSidebar"] label,
            [data-testid="stSidebar"] p,
            [data-testid="stSidebar"] span { color: #e2e8f0 !important; }
            [data-testid="stSidebar"] h1,
            [data-testid="stSidebar"] h2,
            [data-testid="stSidebar"] h3 {
                color: #67e8f9 !important;
            }
            [data-testid="stSidebar"] button[kind="secondary"] {
                border-color: rgba(34, 211, 238, 0.45) !important;
                background: rgba(5, 10, 14, 0.92) !important;
                color: #ccfbf1 !important;
                border-radius: 0 !important;
            }
            [data-testid="stSidebar"] button[kind="secondary"]:hover {
                border-color: rgba(34, 211, 238, 0.72) !important;
                background: rgba(8, 47, 58, 0.45) !important;
            }
            [data-testid="stSidebar"] button[kind="primary"] {
                background: linear-gradient(180deg, #0891b2, #06b6d4) !important;
                border: none !important;
                color: #ecfeff !important;
                border-radius: 0 !important;
            }

            section[data-testid="stMain"] .stButton > button[kind="primary"] {
                background: linear-gradient(180deg, #06b6d4, #0891b2) !important;
                border: 1px solid rgba(165, 243, 252, 0.45) !important;
                border-radius: 0 !important;
                font-weight: 600 !important;
                min-height: 2.35rem !important;
                color: #ecfeff !important;
                box-shadow: 0 0 28px rgba(6, 182, 212, 0.32) !important;
            }
            section[data-testid="stMain"] .stButton > button[kind="primary"]:hover {
                filter: brightness(1.08) !important;
            }
            section[data-testid="stMain"] .stButton > button[kind="secondary"] {
                border-radius: 0 !important;
                min-height: 2.35rem !important;
                border: 1px solid rgba(34, 211, 238, 0.38) !important;
                background: rgba(6, 10, 12, 0.75) !important;
                color: #ccfbf1 !important;
            }
            section[data-testid="stMain"] .stButton > button[kind="secondary"]:hover {
                border-color: rgba(34, 211, 238, 0.65) !important;
                background: rgba(8, 47, 58, 0.35) !important;
            }
            .st-key-dw_regenerate_code_btn button {
                background: #dcfce7 !important;
                border: 1px solid #86efac !important;
                color: #14532d !important;
                margin-top: 0.45rem !important;
            }
            .st-key-dw_regenerate_code_btn button:hover {
                background: #bbf7d0 !important;
                border-color: #4ade80 !important;
                color: #14532d !important;
            }
            .st-key-dw_run_query_btn button {
                background: #fee2e2 !important;
                border: 1px solid #fca5a5 !important;
                color: #7f1d1d !important;
                margin-top: 0.45rem !important;
            }
            .st-key-dw_run_query_btn button:hover {
                background: #fecaca !important;
                border-color: #f87171 !important;
                color: #7f1d1d !important;
            }
            .stButton > button:focus-visible {
                outline: none !important;
                box-shadow: 0 0 0 2px rgba(34, 211, 238, 0.75) !important;
            }

            /* File uploader — visible dropzone frame (dark UI) */
            [data-testid="stFileUploader"] section {
                border-radius: 0 !important;
                border: none;
                background: transparent;
            }
            [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
                border: 2px dashed rgba(34, 211, 238, 0.55) !important;
                border-radius: 0 !important;
                background: rgba(5, 10, 14, 0.95) !important;
                padding: 1rem 1.15rem !important;
                min-height: 7.5rem !important;
                box-shadow:
                    0 0 0 1px rgba(6, 182, 212, 0.22) inset,
                    0 6px 28px rgba(0, 0, 0, 0.45) !important;
            }
            [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]:hover {
                border-color: rgba(103, 232, 249, 0.85) !important;
                background: rgba(8, 24, 32, 0.95) !important;
            }
            [data-testid="stMetric"] {
                border: 1px solid rgba(34, 211, 238, 0.38);
                border-radius: 0 !important;
                background: linear-gradient(180deg, #081216 0%, #05090b 100%);
                padding: 0.4rem 0.6rem;
                box-shadow:
                    0 0 0 1px rgba(6, 182, 212, 0.08) inset,
                    0 8px 24px rgba(0, 0, 0, 0.45);
            }

            [data-testid="stDataFrame"] {
                border: 1px solid rgba(34, 211, 238, 0.35);
                border-radius: 0 !important;
                overflow: hidden;
                box-shadow: 0 4px 18px rgba(0, 0, 0, 0.42);
            }

            [data-baseweb="tab-list"] {
                gap: 0.2rem;
                border-bottom: 1px solid rgba(34, 211, 238, 0.35);
                margin-bottom: 0.4rem;
            }
            [data-baseweb="tab"] {
                height: 2rem;
                border-radius: 0 !important;
                padding: 0 0.85rem;
                font-weight: 600;
                color: #7ddaea;
            }
            [aria-selected="true"][data-baseweb="tab"] {
                color: #ecfeff !important;
                background: rgba(6, 182, 212, 0.22);
                box-shadow: 0 -1px 0 0 rgba(34, 211, 238, 0.6) inset;
            }

            [data-testid="stAlert"] {
                border-radius: 0 !important;
                border-width: 1px;
            }

            .stProgress > div > div > div > div {
                background: linear-gradient(90deg, #0891b2, #22d3ee);
            }

            /* Fix: metric text colors */
            [data-testid="stMetricValue"] { color: #ecfeff !important; }
            [data-testid="stMetricLabel"] { color: #7ddaea !important; }

            /* Fix: text input text color in main area */
            .stTextInput input { color: #1e293b !important; }
            .stTextArea textarea {
                color: #1e293b !important;
                background: #ffffff !important;
                border: 1px solid #cbd5e1 !important;
            }
            .stTextArea textarea::placeholder { color: #94a3b8 !important; }

            /* Fix: disabled textarea — Streamlit dims disabled to ~40% opacity */
            .stTextArea textarea:disabled,
            .stTextArea textarea[disabled] {
                color: #334155 !important;
                -webkit-text-fill-color: #334155 !important;
                opacity: 1 !important;
                background: #f8fafc !important;
            }

            /* Fix: caption text */
            .stCaption p, [data-testid="stCaptionContainer"] p { color: #88d4ea !important; }

            /* Fix: expander summary/header text */
            details > summary { color: #e2e8f0 !important; }
            [data-testid="stExpander"] summary p { color: #e2e8f0 !important; }

            /* Fix: popover content text (Add files menu) */
            [data-testid="stPopoverBody"] { color: #1e293b !important; }
            [data-testid="stPopoverBody"] p,
            [data-testid="stPopoverBody"] label,
            [data-testid="stPopoverBody"] span { color: #1e293b !important; }

            /* Sidebar — login & support inputs stay readable on dark chrome */
            [data-testid="stSidebar"] .stTextInput input,
            [data-testid="stSidebar"] textarea {
                color: #1e293b !important;
                background: #ffffff !important;
                border: 1px solid #cbd5e1 !important;
            }
            [data-testid="stSidebar"] .stTextInput input::placeholder,
            [data-testid="stSidebar"] textarea::placeholder { color: #94a3b8 !important; }
            [data-testid="stSidebar"] [data-testid="stExpander"] summary p { color: #e2e8f0 !important; }

            /* Live support — scope by widget key class (Streamlit adds st-key-<key>) */
            [data-testid="stSidebar"] .st-key-dw_sup_open,
            [data-testid="stSidebar"] .st-key-dw_sup_restore {
                display: flex !important;
                justify-content: flex-end !important;
                width: 100% !important;
            }
            [data-testid="stSidebar"] .st-key-dw_sup_open button,
            [data-testid="stSidebar"] .st-key-dw_sup_restore button {
                font-size: 0 !important;
                line-height: 0 !important;
                color: transparent !important;
                width: 3.35rem !important;
                height: 3.35rem !important;
                min-width: 3.35rem !important;
                min-height: 3.35rem !important;
                padding: 0 !important;
                margin: 0 0 0 auto !important;
                display: block !important;
                border-radius: 50% !important;
                background: #ede9fe url("__DW_ICON_SUPPORT__") center / 70% no-repeat !important;
                border: 2px solid rgba(168, 85, 247, 0.55) !important;
                box-shadow: 0 3px 12px rgba(0, 0, 0, 0.2);
            }
            [data-testid="stSidebar"] .st-key-dw_sup_open button:hover,
            [data-testid="stSidebar"] .st-key-dw_sup_restore button:hover {
                border-color: #a855f7 !important;
                /* Keep background-image — background-color alone drops the glyph under Streamlit hover */
                background: #ddd6fe url("__DW_ICON_SUPPORT__") center / 70% no-repeat !important;
                box-shadow: 0 4px 16px rgba(88, 28, 135, 0.35) !important;
            }
            /* Upload panel support launcher — right edge below Add files */
            section[data-testid="stMain"] .st-key-dw_support_upload_anchor {
                display: block !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            section[data-testid="stMain"] .st-key-dw_support_upload_anchor .st-key-dw_sup_open button,
            section[data-testid="stMain"] .st-key-dw_support_upload_anchor .st-key-dw_sup_restore button {
                position: fixed !important;
                right: clamp(1.15rem, 2.4vw, 2rem) !important;
                bottom: clamp(1.15rem, 3.6vh, 2rem) !important;
                z-index: 2147483000 !important;
                font-size: 0 !important;
                line-height: 0 !important;
                color: transparent !important;
                width: 3.35rem !important;
                height: 3.35rem !important;
                min-width: 3.35rem !important;
                min-height: 3.35rem !important;
                padding: 0 !important;
                margin: 0 !important;
                display: block !important;
                border-radius: 50% !important;
                background: #ede9fe url("__DW_ICON_SUPPORT__") center / 70% no-repeat !important;
                border: 2px solid rgba(168, 85, 247, 0.55) !important;
                box-shadow: 0 3px 12px rgba(0, 0, 0, 0.2);
            }
            section[data-testid="stMain"] .st-key-dw_support_upload_anchor .st-key-dw_sup_open button:hover,
            section[data-testid="stMain"] .st-key-dw_support_upload_anchor .st-key-dw_sup_restore button:hover {
                border-color: #a855f7 !important;
                background: #ddd6fe url("__DW_ICON_SUPPORT__") center / 70% no-repeat !important;
                box-shadow: 0 4px 16px rgba(88, 28, 135, 0.35) !important;
            }
            /* Login / account — top row: icon flush left */
            [data-testid="stSidebar"] .st-key-dw_account_tile {
                display: flex !important;
                justify-content: flex-start !important;
                width: 100% !important;
            }
            [data-testid="stSidebar"] .st-key-dw_account_tile button {
                font-size: 0 !important;
                line-height: 0 !important;
                width: 3.35rem !important;
                height: 3.35rem !important;
                min-width: 3.35rem !important;
                min-height: 3.35rem !important;
                padding: 0 !important;
                margin: 0 !important;
                display: block !important;
                border-radius: 50% !important;
                background: #ede9fe url("__DW_ICON_ACCOUNT__") center / 72% no-repeat !important;
                border: 2px solid rgba(168, 85, 247, 0.45) !important;
                box-shadow: 0 3px 12px rgba(0, 0, 0, 0.22);
            }
            [data-testid="stSidebar"] .st-key-dw_account_tile button:hover,
            [data-testid="stSidebar"] .st-key-dw_account_tile button:focus-visible {
                border-color: #a855f7 !important;
                background: #ddd6fe url("__DW_ICON_ACCOUNT__") center / 72% no-repeat !important;
                box-shadow: 0 4px 16px rgba(88, 28, 135, 0.35) !important;
            }

            /* Live support dialog — mini chatbox, bottom-left */
            [data-testid="stModal"] {
                align-items: flex-end !important;
                justify-content: flex-start !important;
            }
            [data-testid="stModal"] > div {
                width: 100% !important;
                display: flex !important;
                align-items: flex-end !important;
                justify-content: flex-start !important;
                padding: 0 0 14px 14px !important;
            }
            [data-testid="stDialogContent"] {
                width: min(360px, 90vw) !important;
                max-height: min(520px, 70vh) !important;
                overflow-y: auto !important;
                background: #ffffff !important;
                border: 1px solid #e2e8f0 !important;
                border-radius: 16px !important;
                box-shadow: 0 20px 50px rgba(15, 23, 42, 0.18) !important;
                color: #0f172a !important;
                padding-top: 0.35rem !important;
            }
            [data-testid="stDialogContent"] .stMarkdown p,
            [data-testid="stDialogContent"] .stMarkdown li,
            [data-testid="stDialogContent"] label,
            [data-testid="stDialogContent"] [data-testid="stCaptionContainer"] p {
                color: #334155 !important;
            }
            [data-testid="stDialogContent"] .stTextInput input,
            [data-testid="stDialogContent"] textarea {
                color: #1e293b !important;
                background: #ffffff !important;
                border: 1px solid #cbd5e1 !important;
            }
            [data-testid="stDialogContent"] details > summary,
            [data-testid="stDialogContent"] [data-testid="stExpander"] summary p {
                color: #334155 !important;
            }
            /* FAQ pill buttons (secondary) inside support dialog */
            [data-testid="stDialogContent"] button[kind="secondary"] {
                border-radius: 999px !important;
                border: 1px solid rgba(168, 85, 247, 0.55) !important;
                background: #faf5ff !important;
                color: #6b21a8 !important;
                font-weight: 600 !important;
            }
            [data-testid="stDialogContent"] button[kind="secondary"]:hover {
                background: #f3e8ff !important;
                border-color: #a855f7 !important;
            }
            [data-testid="stDialogContent"] [data-testid="stFormSubmitButton"] > button {
                border-radius: 999px !important;
                background: linear-gradient(180deg, #a855f7, #7c3aed) !important;
                color: #ffffff !important;
                border: none !important;
                font-weight: 600 !important;
            }
            [data-testid="stDialogContent"] [data-testid="stFormSubmitButton"] > button:hover {
                background: linear-gradient(180deg, #c084fc, #9333ea) !important;
            }

            /* Account dialog — dark registration / sign-in (anchor inside dialog body) */
            [data-testid="stDialogContent"]:has(#dw-reg-anchor),
            [data-testid="stDialogContent"]:has(#dw-login-anchor) {
                width: min(440px, 94vw) !important;
                max-height: min(640px, 90vh) !important;
                background: linear-gradient(180deg, #081216 0%, #040608 100%) !important;
                border: 1px solid rgba(34, 211, 238, 0.45) !important;
                border-radius: 0 !important;
                color: #ecfeff !important;
                padding: 1rem 1.1rem 1.1rem 1.1rem !important;
                box-shadow: 0 0 40px rgba(6, 182, 212, 0.12) !important;
            }
            [data-testid="stDialogContent"]:has(#dw-reg-anchor) .stMarkdown p,
            [data-testid="stDialogContent"]:has(#dw-login-anchor) .stMarkdown p,
            [data-testid="stDialogContent"]:has(#dw-reg-anchor) label p,
            [data-testid="stDialogContent"]:has(#dw-login-anchor) label p,
            [data-testid="stDialogContent"]:has(#dw-reg-anchor) label span,
            [data-testid="stDialogContent"]:has(#dw-login-anchor) label span,
            [data-testid="stDialogContent"]:has(#dw-reg-anchor) [data-testid="stCaptionContainer"] p,
            [data-testid="stDialogContent"]:has(#dw-login-anchor) [data-testid="stCaptionContainer"] p {
                color: #d1d5db !important;
            }
            [data-testid="stDialogContent"]:has(#dw-reg-anchor) .stTextInput input,
            [data-testid="stDialogContent"]:has(#dw-login-anchor) .stTextInput input {
                background: #2a2538 !important;
                border: 1px solid #3d3554 !important;
                color: #f8fafc !important;
                border-radius: 0 !important;
            }
            [data-testid="stDialogContent"]:has(#dw-reg-anchor) .stTextInput input:focus,
            [data-testid="stDialogContent"]:has(#dw-login-anchor) .stTextInput input:focus {
                border-color: #8b7cc9 !important;
                box-shadow: 0 0 0 1px rgba(109, 88, 183, 0.45) !important;
            }
            [data-testid="stDialogContent"]:has(#dw-reg-anchor) [data-baseweb="checkbox"] span,
            [data-testid="stDialogContent"]:has(#dw-login-anchor) [data-baseweb="checkbox"] span {
                border-color: #6b7280 !important;
            }
            [data-testid="stDialogContent"]:has(#dw-reg-anchor) button[kind="primary"],
            [data-testid="stDialogContent"]:has(#dw-login-anchor) button[kind="primary"] {
                background: linear-gradient(180deg, #0891b2, #06b6d4) !important;
                border: 1px solid rgba(165, 243, 252, 0.45) !important;
                color: #ecfeff !important;
                border-radius: 0 !important;
                font-weight: 600 !important;
                min-height: 2.65rem !important;
            }
            [data-testid="stDialogContent"]:has(#dw-reg-anchor) button[kind="primary"]:hover,
            [data-testid="stDialogContent"]:has(#dw-login-anchor) button[kind="primary"]:hover {
                filter: brightness(1.06) !important;
            }
            [data-testid="stDialogContent"]:has(#dw-reg-anchor) button[kind="secondary"],
            [data-testid="stDialogContent"]:has(#dw-login-anchor) button[kind="secondary"] {
                border-radius: 0 !important;
                border: 1px solid rgba(255, 255, 255, 0.32) !important;
                background: transparent !important;
                color: #f1f5f9 !important;
                font-weight: 600 !important;
            }
            [data-testid="stDialogContent"]:has(#dw-reg-anchor) button[kind="secondary"]:hover,
            [data-testid="stDialogContent"]:has(#dw-login-anchor) button[kind="secondary"]:hover {
                background: rgba(255, 255, 255, 0.06) !important;
                border-color: rgba(255, 255, 255, 0.45) !important;
            }
            [data-testid="stDialogContent"]:has(#dw-reg-anchor) hr,
            [data-testid="stDialogContent"]:has(#dw-login-anchor) hr {
                border-color: #3d3554 !important;
            }
            [data-testid="stDialogContent"]:has(#dw-reg-anchor) [data-testid="stAlert"],
            [data-testid="stDialogContent"]:has(#dw-login-anchor) [data-testid="stAlert"] {
                background: #2a2538 !important;
            }

            /* Fix: selectbox, radio, checkbox label text in main area */
            .main .stRadio label, .main .stCheckbox label, .main .stSelectbox label { color: #9ddcf0 !important; }
            .main .stRadio p, .main .stCheckbox p, .main .stSelectbox p { color: #9ddcf0 !important; }
            .main .stMarkdown p, .main .stMarkdown li { color: #cffafe !important; }
            .main .stMarkdown h1, .main .stMarkdown h2, .main .stMarkdown h3 { color: #ecfeff !important; }

            /* Fix: file uploader drag-and-drop label text */
            [data-testid="stFileUploaderDropzone"] span,
            [data-testid="stFileUploaderDropzone"] p { color: #7ddaea !important; }

            /* Hide duplicate native Browse — file picking is via Add files → Browse files */
            [data-testid="stFileUploader"] button[kind="secondary"] {
                display: none !important;
            }

            /* Schema inference — wireframe board (Mapper) */
            .dw-wf-board {
                border: 1px dashed rgba(34, 211, 238, 0.45);
                border-radius: 0 !important;
                background: linear-gradient(175deg, #081216 0%, #05090b 55%, #040608 100%);
                padding: 16px 18px 20px;
                margin: 0 0 14px 0;
                box-shadow: 0 0 0 1px rgba(6, 182, 212, 0.1) inset, 0 10px 32px rgba(0, 0, 0, 0.45);
            }
            .dw-wf-board-title {
                font-size: 0.68rem;
                letter-spacing: 0.16em;
                font-weight: 700;
                color: #9d94ad;
                text-transform: uppercase;
                margin-bottom: 12px;
            }
            .dw-wf-metrics {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 10px;
            }
            .dw-wf-metric-cell {
                border: 1px solid rgba(34, 211, 238, 0.32);
                background: linear-gradient(180deg, #060f14 0%, #040708 100%);
                padding: 10px 8px;
                text-align: center;
                border-radius: 0 !important;
            }
            .dw-wf-num { display: block; font-size: 1.35rem; font-weight: 700; color: #f8f7fc; line-height: 1.2; }
            .dw-wf-lbl { display: block; font-size: 0.62rem; letter-spacing: 0.1em; color: #b0a8bf; margin-top: 4px; font-weight: 600; }
            .dw-wf-lane-h {
                font-size: 0.65rem;
                letter-spacing: 0.14em;
                font-weight: 800;
                color: #9d94ad;
                text-transform: uppercase;
                margin: 0 0 10px 0;
                padding-bottom: 6px;
                border-bottom: 1px dashed rgba(34, 211, 238, 0.35);
            }
            .dw-wf-lane-h.e { color: #67e8f9; }
            .dw-wf-lane-h.t { color: #b45309; }
            .dw-wf-lane-h.l { color: #15803d; }
            .dw-wf-card {
                border: 1px solid rgba(34, 211, 238, 0.32);
                background: #05090b;
                border-radius: 0 !important;
                padding: 10px 12px 12px;
                margin-bottom: 10px;
                box-shadow: 0 0 0 1px rgba(6, 182, 212, 0.08) inset;
            }
            .dw-wf-card-title { font-weight: 700; font-size: 0.88rem; color: #f8f7fc; margin-bottom: 4px; }
            .dw-wf-meta { font-size: 0.76rem; color: #b0a8bf; margin-bottom: 8px; }
            .dw-wf-code {
                font-family: 'IBM Plex Mono', ui-monospace, monospace;
                font-size: 0.72rem;
                color: #cbd5e1;
                line-height: 1.45;
                margin-bottom: 8px;
                word-break: break-word;
            }
            .dw-wf-keys { font-size: 0.74rem; color: #b0a8bf; margin-bottom: 8px; }
            .dw-wf-keys code { background: #140c1c; padding: 1px 4px; border-radius: 4px; font-size: 0.72rem; color: #d4cee0; }
            .dw-wf-pill {
                display: inline-block;
                font-size: 0.65rem;
                font-weight: 700;
                letter-spacing: 0.04em;
                padding: 3px 8px;
                border-radius: 3px;
                border: 1px dashed rgba(148, 163, 184, 0.45);
            }
            .dw-wf-pill-ok { background: rgba(22, 101, 52, 0.35); color: #86efac; border-color: rgba(34, 197, 94, 0.45); }
            .dw-wf-pill-warn { background: rgba(120, 53, 15, 0.35); color: #fcd34d; border-color: rgba(245, 158, 11, 0.45); }
            .dw-wf-pill-bad { background: rgba(127, 29, 29, 0.35); color: #fca5a5; border-color: rgba(248, 113, 113, 0.45); }
            .dw-wf-ul { margin: 6px 0 0 0; padding-left: 16px; font-size: 0.76rem; color: #cbd5e1; line-height: 1.5; }
            .dw-wf-note {
                font-size: 0.72rem;
                color: #9ddcf0;
                border: 1px solid rgba(34, 211, 238, 0.28);
                background: linear-gradient(180deg, #060f14 0%, #040608 100%);
                padding: 8px 10px;
                border-radius: 0 !important;
                margin-top: 8px;
            }
            /* ERD graphviz — wireframe frame (solid outer border) */
            [data-testid="stGraphvizChart"] {
                border: 1px solid rgba(34, 211, 238, 0.42) !important;
                border-radius: 0 !important;
                padding: 12px !important;
                background: repeating-linear-gradient(
                    0deg, #05090b, #05090b 10px, #081216 11px
                ) !important;
                box-shadow: 0 0 0 1px rgba(6, 182, 212, 0.1) inset !important;
            }

            /* Transform — clickable workflow nav (keyed container #streamlit-key-dw_tf_workflow_nav) */
            div[data-testid="stVerticalBlock"][id="streamlit-key-dw_tf_workflow_nav"],
            div[data-testid="stVerticalBlock"][id^="streamlit-key-dw_tf_workflow_nav"] {
                margin-bottom: 0.35rem;
            }
            div[data-testid="stVerticalBlock"][id="streamlit-key-dw_tf_workflow_nav"] button[kind="secondary"],
            div[data-testid="stVerticalBlock"][id^="streamlit-key-dw_tf_workflow_nav"] button[kind="secondary"] {
                background: #ffffff !important;
                color: #94a3b8 !important;
                border: 1px solid rgba(226, 232, 240, 0.95) !important;
                border-radius: 0 !important;
                font-weight: 600 !important;
                font-size: 0.78rem !important;
                min-height: 2.45rem;
                box-shadow: none !important;
            }
            div[data-testid="stVerticalBlock"][id="streamlit-key-dw_tf_workflow_nav"] button[kind="secondary"]:hover,
            div[data-testid="stVerticalBlock"][id^="streamlit-key-dw_tf_workflow_nav"] button[kind="secondary"]:hover {
                background: #f8fafc !important;
                color: #64748b !important;
            }
            div[data-testid="stVerticalBlock"][id="streamlit-key-dw_tf_workflow_nav"] button[kind="primary"],
            div[data-testid="stVerticalBlock"][id^="streamlit-key-dw_tf_workflow_nav"] button[kind="primary"] {
                background: #dbeafe !important;
                color: #0369a1 !important;
                border: 1px solid #7dd3fc !important;
                border-radius: 0 !important;
                font-weight: 600 !important;
                font-size: 0.78rem !important;
                min-height: 2.45rem;
                box-shadow: 0 1px 4px rgba(56, 189, 248, 0.22) !important;
            }
            div[data-testid="stVerticalBlock"][id="streamlit-key-dw_tf_workflow_nav"] button[kind="primary"]:hover,
            div[data-testid="stVerticalBlock"][id^="streamlit-key-dw_tf_workflow_nav"] button[kind="primary"]:hover {
                filter: brightness(0.97);
            }
            /* Fallback if Streamlit nests id differently */
            [id^="streamlit-key-dw_tf_workflow_nav"] button[kind="secondary"] {
                background: #ffffff !important;
                color: #94a3b8 !important;
                border: 1px solid rgba(226, 232, 240, 0.95) !important;
                border-radius: 0 !important;
                font-weight: 600 !important;
                font-size: 0.78rem !important;
                min-height: 2.45rem;
                box-shadow: none !important;
            }
            [id^="streamlit-key-dw_tf_workflow_nav"] button[kind="primary"] {
                background: #dbeafe !important;
                color: #0369a1 !important;
                border: 1px solid #7dd3fc !important;
                border-radius: 0 !important;
                font-weight: 600 !important;
                font-size: 0.78rem !important;
                min-height: 2.45rem;
                box-shadow: 0 1px 4px rgba(56, 189, 248, 0.22) !important;
            }
            /*
               Step 1 card — Transform instructions only (has textarea, no CSV uploader).
               Avoids clobbering Upload bordered panel or other bordered containers.
             */
            section[data-testid="stMain"]
                [data-testid="stVerticalBlockBorderWrapper"]:has(textarea):not(:has([data-testid="stFileUploader"])) {
                border: 1px solid rgba(34, 211, 238, 0.45) !important;
                border-radius: 0 !important;
                background: linear-gradient(165deg, #081216 0%, #040608 100%) !important;
                box-shadow:
                    0 0 0 1px rgba(6, 182, 212, 0.12) inset,
                    0 0 32px rgba(6, 182, 212, 0.08) !important;
                padding: 0.85rem 1rem 1rem 1rem !important;
            }
            section[data-testid="stMain"]
                [data-testid="stVerticalBlockBorderWrapper"]:has(textarea):not(:has([data-testid="stFileUploader"]))
                [data-testid="stMarkdownContainer"]
                h4 {
                color: #f8fafc !important;
                font-weight: 700 !important;
                margin-bottom: 0.35rem !important;
            }
            section[data-testid="stMain"]
                [data-testid="stVerticalBlockBorderWrapper"]:has(textarea):not(:has([data-testid="stFileUploader"]))
                textarea {
                background: #ffffff !important;
                color: #0f172a !important;
                border-radius: 0 !important;
                border: 1px solid rgba(148, 163, 184, 0.5) !important;
                font-size: 0.92rem !important;
                min-height: 148px !important;
            }
            section[data-testid="stMain"]
                [data-testid="stVerticalBlockBorderWrapper"]:has(textarea):not(:has([data-testid="stFileUploader"]))
                div[data-testid="stButton"]:has(button[kind="primary"]) {
                width: 100%;
            }
            section[data-testid="stMain"]
                [data-testid="stVerticalBlockBorderWrapper"]:has(textarea):not(:has([data-testid="stFileUploader"]))
                div[data-testid="stButton"]:has(button[kind="primary"])
                button[kind="primary"] {
                width: 100%;
                min-height: 2.65rem;
                border-radius: 0 !important;
                font-weight: 600 !important;
                border: none !important;
                background-image: linear-gradient(
                    92deg,
                    #0e7490 0%,
                    #0891b2 38%,
                    #06b6d4 72%,
                    #22d3ee 100%
                ) !important;
                box-shadow: 0 0 28px rgba(6, 182, 212, 0.35) !important;
                color: #ffffff !important;
            }
            section[data-testid="stMain"]
                [data-testid="stVerticalBlockBorderWrapper"]:has(textarea):not(:has([data-testid="stFileUploader"]))
                div[data-testid="stButton"]:has(button[kind="primary"])
                button[kind="primary"]:hover {
                filter: brightness(1.06);
            }

        </style>
        """
    ).replace("__DW_ICON_ACCOUNT__", _DW_ICON_ACCOUNT_URI).replace(
        "__DW_ICON_SUPPORT__", _DW_ICON_SUPPORT_URI
    )
    st.markdown(_dw_css, unsafe_allow_html=True)


def _hero(badge: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="dw-hero">
            <div class="dw-badge">{badge}</div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _trigger_native_file_picker() -> None:
    components.html(
        """
        <script>
        const doc = window.parent.document;
        const box = doc.querySelector('[data-testid="stFileUploader"]');
        const inp = box ? box.querySelector('input[type="file"]') : null;
        if (inp) { inp.click(); }
        </script>
        """,
        height=0,
        width=0,
    )


# -----------------------------------------------------------------------------
# Session state
# -----------------------------------------------------------------------------
if "page_idx" not in st.session_state:
    st.session_state.page_idx = 0
if "uploaded_dfs" not in st.session_state:
    st.session_state.uploaded_dfs: Dict[str, pd.DataFrame] = {}
if "source_mode" not in st.session_state:
    st.session_state.source_mode = "Upload csv"
if "trigger_csv_picker" not in st.session_state:
    st.session_state.trigger_csv_picker = False
if "upload_reset_id" not in st.session_state:
    st.session_state.upload_reset_id = 0
if "mapper_schema" not in st.session_state:
    st.session_state.mapper_schema = {}
if "mapper_source_sig" not in st.session_state:
    st.session_state.mapper_source_sig = None
if "data_dictionary" not in st.session_state:
    st.session_state.data_dictionary: List[Dict] = []
if "transformed_df" not in st.session_state:
    st.session_state.transformed_df = None
if "discarded_df" not in st.session_state:
    st.session_state.discarded_df = None
if "transform_source_sig" not in st.session_state:
    st.session_state.transform_source_sig = None
if "run_logs" not in st.session_state:
    st.session_state.run_logs = []
if "agent_dialogue" not in st.session_state:
    st.session_state.agent_dialogue: Dict[str, str] = {
        "Scout": "Waiting for connection...",
        "Architect": "Waiting for connection...",
        "Engineer": "Waiting for connection...",
    }
if "user_instructions" not in st.session_state:
    st.session_state.user_instructions: str = ""
if "pipeline_run_result" not in st.session_state:
    st.session_state.pipeline_run_result: Optional[Dict] = None
if "transform_activity_log" not in st.session_state:
    st.session_state.transform_activity_log: List[str] = []
if "transform_expander_open" not in st.session_state:
    st.session_state.transform_expander_open = False
if "transform_workflow_step" not in st.session_state:
    st.session_state.transform_workflow_step = 0
if "transform_plan_draft" not in st.session_state:
    st.session_state.transform_plan_draft = ""
if "transform_code_draft" not in st.session_state:
    st.session_state.transform_code_draft = ""
if "dw_logged_in" not in st.session_state:
    st.session_state.dw_logged_in = False
if "dw_user_display" not in st.session_state:
    st.session_state.dw_user_display = ""
if "dw_support_thread" not in st.session_state:
    st.session_state.dw_support_thread: List[Tuple[str, str]] = []
if "dw_support_ui" not in st.session_state:
    st.session_state.dw_support_ui = "closed"  # closed | open | minimized
if "dw_support_faq_pill" not in st.session_state:
    st.session_state.dw_support_faq_pill = None
if "dw_account_ui" not in st.session_state:
    st.session_state.dw_account_ui = "closed"  # closed | open
if "dw_auth_view" not in st.session_state:
    st.session_state.dw_auth_view = "register"  # register | login
if "dw_auth_method" not in st.session_state:
    st.session_state.dw_auth_method = ""
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "auth_username" not in st.session_state:
    st.session_state.auth_username: Optional[str] = None


PAGES = ["Upload", "Mapper", "Transform", "Logs & Downloads"]


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def go_next() -> None:
    st.session_state.page_idx = min(st.session_state.page_idx + 1, len(PAGES) - 1)


def go_back() -> None:
    st.session_state.page_idx = max(st.session_state.page_idx - 1, 0)


def go_to_page(idx: int) -> None:
    st.session_state.page_idx = idx


def _dw_logout_click() -> None:
    st.session_state.authenticated = False
    st.session_state.auth_username = None
    st.session_state.dw_logged_in = False
    st.session_state.dw_user_display = ""
    st.session_state.dw_auth_method = ""
    st.session_state.dw_account_ui = "closed"
    _reset_pipeline_session()


_SUPPORT_FAQ_TOPICS: Dict[str, str] = {
    "Upload & files": (
        "**Upload (Step 1):** Drag and drop CSVs or use **Add files → Browse files**. "
        "Files stay in your session for Mapper through Downloads. Use **Clear** on Upload if you need a fresh start."
    ),
    "Mapper & schema": (
        "**Mapper (Step 2):** Use **Preview** to scan rows, **Column profiling** for stats, **Schema inference** for keys and joins, "
        "**ERD** for a blueprint diagram, and **Data dictionary** for field descriptions."
    ),
    "Transform": (
        "**Transform (Step 3):** Review agent dialogue, adjust instructions, and inspect merged output, discarded rows, and the full transformed table."
    ),
    "Exports & downloads": (
        "**Logs & Downloads (Step 4):** Export the transformed dataset and the data dictionary as CSV when available."
    ),
    "Account (demo)": (
        "**Log in** here is a **session-only demo** (display name). It is not wired to a real identity provider — use it for prototypes and walkthroughs."
    ),
}


def _support_bot_reply(user_text: str) -> str:
    """Lightweight FAQ-style replies from the user's prompt (keyword match)."""
    t = user_text.lower().strip()
    if not t:
        return "Add a short message, then send again."
    keyword_replies: List[Tuple[Tuple[str, ...], str]] = [
        (
            ("upload", "csv", "file", "ingest", "drag"),
            _SUPPORT_FAQ_TOPICS["Upload & files"],
        ),
        (
            ("mapper", "schema", "erd", "dictionary", "profile", "foreign", "primary"),
            _SUPPORT_FAQ_TOPICS["Mapper & schema"],
        ),
        (
            ("transform", "merge", "agent", "pipeline", "discarded"),
            _SUPPORT_FAQ_TOPICS["Transform"],
        ),
        (
            ("download", "export", "csv", "log"),
            _SUPPORT_FAQ_TOPICS["Exports & downloads"],
        ),
        (
            ("login", "sign", "account", "password", "auth"),
            _SUPPORT_FAQ_TOPICS["Account (demo)"],
        ),
    ]
    for keys, msg in keyword_replies:
        if any(k in t for k in keys):
            return msg
    return (
        "Thanks — we’ve noted your message for the DATA WEAVE team. "
        "For faster help, try keywords like **upload**, **mapper**, **transform**, or **download**, "
        "or browse **FAQ topics** in live support. A specialist can follow up when this flow is connected to a real help desk."
    )


def _render_dw_sidebar_account() -> None:
    """Sidebar top-left row: profile icon flush left, account label + name to the right."""
    tip = "Account & sign in" if not st.session_state.dw_logged_in else "Account"
    ic, tx = st.sidebar.columns([1, 3.5])
    with ic:
        if st.button("\u200b", key="dw_account_tile", help=tip, use_container_width=False):
            st.session_state.dw_account_ui = "open"
            st.rerun()
    with tx:
        st.markdown(
            '<div style="font-size:0.65rem;font-weight:700;letter-spacing:0.14em;'
            'color:#9d94ad;margin:0.2rem 0 0.15rem 0;line-height:1.2;">ACCOUNT</div>',
            unsafe_allow_html=True,
        )
        if st.session_state.dw_logged_in:
            safe = html.escape(str(st.session_state.dw_user_display or "User"))
            st.markdown(
                f'<div style="font-size:0.8rem;font-weight:600;color:#f8f7fc;'
                f'margin:0 0 0.65rem 0;line-height:1.25;word-wrap:break-word;">{safe}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="font-size:0.8rem;font-weight:600;color:#f8f7fc;'
                'margin:0 0 0.65rem 0;">Guest</div>',
                unsafe_allow_html=True,
            )


def _dw_support_window_chrome() -> None:
    """Light header: ⋯ · Chat with us! (Streamlit dialog supplies the outer close control)."""
    c1, c2 = st.columns([0.7, 5.2])
    with c1:
        st.markdown(
            '<div style="font-size:1.28rem;line-height:1;color:#94a3b8;padding:6px 0 0 2px;">⋯</div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '<p style="margin:0;padding-top:6px;text-align:center;font-weight:700;'
            'font-size:0.98rem;color:#0f172a;">Chat with us!</p>',
            unsafe_allow_html=True,
        )
    st.markdown(
        '<div style="height:1px;background:#e2e8f0;margin:4px 0 12px 0;"></div>',
        unsafe_allow_html=True,
    )


def _support_faq_pill_key(topic: str) -> str:
    slug = re.sub(r"[^\w]+", "_", topic).strip("_").lower()
    return "dw_pfaq_" + (slug[:44] or "topic")


def _render_dw_support_panel_body() -> None:
    """Chat-style body: agent row, welcome bubble, FAQ pills, thread, message form."""
    a1, a2, a3 = st.columns([1.15, 3.65, 1.2])
    with a1:
        st.markdown(
            """
            <div style="position:relative;width:48px;height:48px;">
              <div style="width:48px;height:48px;border-radius:50%;
                background:linear-gradient(145deg,#6d28d9,#a855f7);
                display:flex;align-items:center;justify-content:center;font-size:1.4rem;
                box-shadow:0 2px 10px rgba(109,40,217,0.35);">🤖</div>
              <div style="position:absolute;top:0;right:1px;width:11px;height:11px;
                background:#22c55e;border-radius:50%;border:2px solid #fff;"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with a2:
        st.markdown(
            '<p style="margin:0;font-weight:700;font-size:0.95rem;color:#0f172a;">WeaveBot</p>',
            unsafe_allow_html=True,
        )
        st.caption("🚀 DATA WEAVE · Pipeline help")
    with a3:
        st.markdown(
            '<div style="display:flex;gap:8px;justify-content:flex-end;padding-top:6px;">'
            '<div title="Helpful" style="width:34px;height:34px;border-radius:10px;'
            'background:#f8fafc;border:1px solid #e2e8f0;display:flex;align-items:center;'
            'justify-content:center;font-size:1rem;">👍</div>'
            '<div title="Not helpful" style="width:34px;height:34px;border-radius:10px;'
            'background:#f8fafc;border:1px solid #e2e8f0;display:flex;align-items:center;'
            'justify-content:center;font-size:1rem;">👎</div>'
            "</div>",
            unsafe_allow_html=True,
        )

    time_s = datetime.now().strftime("%I:%M %p").lstrip("0")
    st.markdown(
        f"""
        <div style="background:linear-gradient(180deg,#f8fafc 0%,#eef2ff 100%);
          border-radius:14px;padding:14px 12px 16px 12px;border:1px solid #e2e8f0;margin-top:2px;">
          <div style="font-size:0.72rem;color:#64748b;margin-bottom:10px;display:flex;align-items:center;gap:6px;">
            <span>🤖</span><span style="font-weight:600;color:#475569;">WeaveBot</span>
            <span style="color:#94a3b8;">{html.escape(time_s)}</span>
          </div>
          <div style="background:#fff;border-radius:14px;padding:12px 14px;
            box-shadow:0 2px 8px rgba(15,23,42,0.06);border:1px solid #f1f5f9;
            color:#334155;font-size:0.88rem;line-height:1.55;">
            Hi 👋 I’m here to help with DATA WEAVE. Choose a quick topic below, or send a message for the team.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<p style="font-size:0.74rem;font-weight:700;color:#64748b;margin:16px 0 8px 0;'
        'letter-spacing:0.04em;">QUICK TOPICS</p>',
        unsafe_allow_html=True,
    )
    for topic in _SUPPORT_FAQ_TOPICS:
        if st.button(
            topic,
            key=_support_faq_pill_key(topic),
            use_container_width=True,
            type="secondary",
        ):
            st.session_state.dw_support_faq_pill = topic
            st.rerun()

    sel = st.session_state.get("dw_support_faq_pill")
    if sel and sel in _SUPPORT_FAQ_TOPICS:
        st.markdown("---")
        st.markdown(_SUPPORT_FAQ_TOPICS[sel])
        _, clr = st.columns([2.2, 1])
        with clr:
            if st.button("Clear", key="dw_pfaq_clear"):
                st.session_state.dw_support_faq_pill = None
                st.rerun()

    if st.session_state.dw_support_thread:
        st.markdown(
            '<p style="font-size:0.74rem;font-weight:700;color:#64748b;margin:14px 0 6px 0;">'
            "MESSAGES</p>",
            unsafe_allow_html=True,
        )
        for role, text in st.session_state.dw_support_thread[-8:]:
            body = html.escape(text).replace("\n", "<br>")
            if role == "user":
                st.markdown(
                    f'<div style="font-size:0.8rem;margin-bottom:8px;text-align:right;">'
                    f'<span style="background:#ede9fe;color:#5b21b6;padding:8px 12px;'
                    f'border-radius:12px 12px 4px 12px;display:inline-block;text-align:left;max-width:92%;">'
                    f"<strong>You</strong><br>{body}</span></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="font-size:0.8rem;margin-bottom:8px;">'
                    f'<span style="background:#faf5ff;color:#334155;padding:8px 12px;'
                    f'border-radius:12px 12px 12px 4px;display:inline-block;max-width:92%;'
                    f'border:1px solid rgba(168,85,247,0.22);">{body}</span></div>',
                    unsafe_allow_html=True,
                )

    with st.form("dw_support_form"):
        st.caption("Leave a message for the team (demo assistant)")
        prompt = st.text_area(
            "support_prompt",
            label_visibility="collapsed",
            height=72,
            placeholder="Type your question…",
        )
        send = st.form_submit_button("Send message", use_container_width=True)
    if send and (prompt or "").strip():
        msg = (prompt or "").strip()
        st.session_state.dw_support_thread.append(("user", msg))
        st.session_state.dw_support_thread.append(("assistant", _support_bot_reply(msg)))
        st.session_state.dw_support_thread = st.session_state.dw_support_thread[-24:]


def _dw_support_dialog_callback() -> None:
    _dw_support_window_chrome()
    _render_dw_support_panel_body()


def _dw_support_dismiss_sync() -> None:
    st.session_state.dw_support_ui = "closed"


def _dw_account_dismiss_sync() -> None:
    st.session_state.dw_account_ui = "closed"
    st.session_state.dw_auth_view = "register"


def _dw_register_dialog_body() -> None:
    st.markdown('<div id="dw-reg-anchor"></div>', unsafe_allow_html=True)
    st.markdown(
        '<h2 style="margin:0 0 0.5rem 0;font-size:1.42rem;font-weight:700;color:#000000;'
        'letter-spacing:-0.02em;">Create an account</h2>',
        unsafe_allow_html=True,
    )
    row1_l, row1_r = st.columns([2.2, 1])
    with row1_l:
        st.markdown(
            '<p style="margin:0;padding-top:0.35rem;color:#334155;font-size:0.88rem;">'
            "Already have an account?</p>",
            unsafe_allow_html=True,
        )
    with row1_r:
        if st.button("Log in", key="dw_reg_switch_login", type="secondary"):
            st.session_state.dw_auth_view = "login"
            st.rerun()

    fn_col, ln_col = st.columns(2)
    with fn_col:
        st.text_input(
            "First name",
            placeholder="First name",
            key="dw_reg_fn",
            label_visibility="collapsed",
        )
    with ln_col:
        st.text_input(
            "Last name",
            placeholder="Last name",
            key="dw_reg_ln",
            label_visibility="collapsed",
        )

    st.text_input(
        "Email",
        placeholder="Email",
        key="dw_reg_email",
        label_visibility="collapsed",
    )

    _pw_show = bool(st.session_state.get("dw_reg_show_pw"))
    st.text_input(
        "Password",
        placeholder="Enter your password",
        type="default" if _pw_show else "password",
        key="dw_reg_pw",
        label_visibility="collapsed",
    )
    st.toggle("Show password", key="dw_reg_show_pw")

    agree = st.checkbox("I agree to the Terms & Conditions (demo)", key="dw_reg_terms")

    if st.button(
        "Create account",
        type="primary",
        use_container_width=True,
        disabled=not agree,
        key="dw_reg_submit",
    ):
        fn = (st.session_state.get("dw_reg_fn") or "").strip()
        ln = (st.session_state.get("dw_reg_ln") or "").strip()
        email = (st.session_state.get("dw_reg_email") or "").strip()
        pw = st.session_state.get("dw_reg_pw") or ""
        if not email or not pw:
            st.warning("Please enter email and password.")
        elif not agree:
            st.warning("Please accept the terms to continue.")
        else:
            display = (f"{fn} {ln}".strip() or (email.split("@", 1)[0] if "@" in email else email))
            enter_app_from_starter(display, "Registered (demo)")

    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;margin:1.1rem 0 0.85rem 0;">'
        '<div style="flex:1;height:1px;background:#cbd5e1;"></div>'
        '<span style="color:#475569;font-size:0.78rem;white-space:nowrap;">Or register with</span>'
        '<div style="flex:1;height:1px;background:#cbd5e1;"></div>'
        "</div>",
        unsafe_allow_html=True,
    )
    soc1, soc2 = st.columns(2)
    with soc1:
        if st.button("Google", key="dw_reg_google", use_container_width=True, type="secondary"):
            enter_app_from_starter("Google user", "Google")
    with soc2:
        if st.button("Apple", key="dw_reg_apple", use_container_width=True, type="secondary"):
            enter_app_from_starter("Apple user", "Apple")


def _dw_login_dialog_body() -> None:
    st.markdown('<div id="dw-login-anchor"></div>', unsafe_allow_html=True)
    st.markdown(
        '<h2 style="margin:0 0 0.35rem 0;font-size:1.35rem;font-weight:700;color:#000000;">Sign in</h2>',
        unsafe_allow_html=True,
    )
    row1_l, row1_r = st.columns([2.2, 1])
    with row1_l:
        st.markdown(
            '<p style="margin:0;padding-top:0.35rem;color:#334155;font-size:0.88rem;">'
            "New here?</p>",
            unsafe_allow_html=True,
        )
    with row1_r:
        if st.button("Create an account", key="dw_log_switch_register", type="secondary"):
            st.session_state.dw_auth_view = "register"
            st.rerun()

    st.caption("Demo only — not connected to real IdPs.")
    if st.button(
        "Continue with Google",
        key="dw_btn_google_demo",
        use_container_width=True,
        type="primary",
    ):
        enter_app_from_starter("Google user", "Google")
    st.caption("OAuth is not wired; this simulates a successful Google sign-in.")
    st.divider()
    st.markdown("**Email sign in**")
    with st.form("dw_login_form"):
        u = st.text_input("Email", placeholder="you@example.com", key="dw_log_email")
        _pw = st.text_input("Password", type="password", placeholder="••••••••", key="dw_log_pw")
        submitted = st.form_submit_button("Sign in with email", use_container_width=True)
    if submitted:
        u_val = (u or "").strip()
        if u_val:
            enter_app_from_starter(
                u_val.split("@", 1)[0] if "@" in u_val else u_val,
                "Email",
            )
        else:
            st.warning("Enter your email to continue.")


def _dw_account_dialog_callback() -> None:
    if st.session_state.get("authenticated"):
        safe = html.escape(str(st.session_state.dw_user_display or "User"))
        method = st.session_state.get("dw_auth_method") or "email"
        st.markdown(f"**Signed in** as {safe}")
        st.caption(f"Method: **{method}** · session demo only")
        st.button(
            "Sign out",
            key="dw_btn_logout",
            on_click=_dw_logout_click,
            use_container_width=True,
        )
    elif st.session_state.get("dw_auth_view") == "login":
        _dw_login_dialog_body()
    else:
        _dw_register_dialog_body()


_open_dw_support_window: Optional[object] = None
_open_dw_account_window: Optional[object] = None
_dlg = getattr(st, "dialog", None)
if _dlg is not None:
    try:
        _open_dw_support_window = _dlg("\u200b", on_dismiss=_dw_support_dismiss_sync)(_dw_support_dialog_callback)
        _open_dw_account_window = _dlg("\u200b", on_dismiss=_dw_account_dismiss_sync)(_dw_account_dialog_callback)
    except TypeError:
        _open_dw_support_window = _dlg("\u200b")(_dw_support_dialog_callback)
        _open_dw_account_window = _dlg("\u200b")(_dw_account_dialog_callback)


def _render_dw_support_launcher() -> None:
    """Render support launcher at current layout location (not sidebar-forced)."""
    ui = st.session_state.get("dw_support_ui", "closed")
    if ui == "minimized":
        key = "dw_sup_restore"
    else:
        key = "dw_sup_open"
    if st.button("\u200b", key=key, use_container_width=False):
        st.session_state.dw_support_ui = "open"
        st.rerun()


def _reset_mapper_outputs() -> None:
    st.session_state.mapper_schema = {}
    st.session_state.mapper_source_sig = None
    st.session_state.data_dictionary = []
    st.session_state.transformed_df = None
    st.session_state.discarded_df = None
    st.session_state.transform_source_sig = None


def _reset_pipeline_session() -> None:
    st.session_state.uploaded_dfs = {}
    _reset_mapper_outputs()
    st.session_state.run_logs = []
    st.session_state.source_mode = "Upload csv"
    st.session_state.trigger_csv_picker = False
    st.session_state.agent_dialogue = {
        "Scout": "Waiting for connection...",
        "Architect": "Waiting for connection...",
        "Engineer": "Waiting for connection...",
    }
    st.session_state.upload_reset_id = int(st.session_state.get("upload_reset_id", 0)) + 1


def _format_session_csv_size(df: pd.DataFrame) -> str:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    b = len(buf.getvalue().encode("utf-8"))
    if b >= 1024 * 1024:
        return f"{b / (1024 * 1024):.1f} MB"
    if b >= 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b} B"


def _humanize_column_name(col: str) -> str:
    s = str(col).strip()
    if "unnamed" in s.lower():
        return "row_index"
    return s


def _humanize_key_list(cols: List[str]) -> List[str]:
    return [_humanize_column_name(c) for c in cols]


def profile_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    profile = []
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


def _preview_search_filter(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """Keep rows where any cell contains the query (case-insensitive, substring)."""
    if df.empty or not (query or "").strip():
        return df
    q = query.strip().lower()
    try:
        mask = df.astype(str).apply(
            lambda s: s.str.lower().str.contains(q, regex=False, na=False)
        ).any(axis=1)
        return df.loc[mask]
    except Exception:
        return df


def _preview_sort_dataframe(df: pd.DataFrame, sort_mode: str) -> pd.DataFrame:
    """Apply named sort for Preview tab (name A–Z, rating high→low)."""
    if df.empty or sort_mode == "default":
        return df
    out = df.copy()
    if sort_mode == "title_az":
        title_col = None
        for c in out.columns:
            cn = str(c).lower()
            if cn in ("course_title", "title", "name") or "title" in cn:
                title_col = c
                break
        if title_col is None:
            for c in out.columns:
                if pd.api.types.is_object_dtype(out[c]) or pd.api.types.is_string_dtype(out[c]):
                    title_col = c
                    break
        if title_col is not None:
            out = out.sort_values(
                by=title_col,
                key=lambda s: s.astype(str).str.lower(),
                na_position="last",
            )
    elif sort_mode == "rating_desc":
        rating_col = None
        for c in out.columns:
            if "rating" in str(c).lower():
                rating_col = c
                break
        if rating_col is None:
            for c in out.columns:
                if pd.api.types.is_numeric_dtype(out[c]):
                    rating_col = c
                    break
        if rating_col is not None:
            out = out.sort_values(by=rating_col, ascending=False, na_position="last")
    return out


def _sort_mode_widget(*, key: str) -> str:
    """Sort popover (or selectbox); returns internal mode for _preview_sort_dataframe."""
    _sort_options = (
        "Default order",
        "Sort by name (A–Z)",
        "Sort by rating (high → low)",
    )
    if hasattr(st, "popover"):
        with st.popover("🔽"):
            sort_choice = st.radio(
                "Order rows",
                _sort_options,
                key=key,
                label_visibility="visible",
            )
    else:
        sort_choice = st.selectbox(
            "Sort",
            _sort_options,
            key=key,
            label_visibility="visible",
        )
    sort_map = {
        "Default order": "default",
        "Sort by name (A–Z)": "title_az",
        "Sort by rating (high → low)": "rating_desc",
    }
    return sort_map.get(sort_choice, "default")


def _render_searchable_dataframe(
    df: pd.DataFrame,
    *,
    key_prefix: str,
    height: Optional[int] = None,
    column_config: Optional[Dict] = None,
    max_display_rows: Optional[int] = 500,
) -> None:
    """Search above the table; keep default row order."""
    safe_key = re.sub(r"[^\w]+", "_", str(key_prefix))[:80]
    search_q = st.text_input(
        "search_table",
        key=f"tbl_search_{safe_key}",
        placeholder="🔍  Search any column or row text…",
        label_visibility="collapsed",
    )
    sort_mode = "default"
    filtered = _preview_search_filter(df, search_q or "")
    view_df = _preview_sort_dataframe(filtered, sort_mode)
    if max_display_rows is not None and len(view_df) > max_display_rows:
        shown = view_df.head(max_display_rows)
    else:
        shown = view_df
    kwargs: Dict = {"use_container_width": True}
    if height is not None:
        kwargs["height"] = height
    if column_config is not None:
        kwargs["column_config"] = column_config
    st.dataframe(shown, **kwargs)
    if df.empty:
        return
    if search_q and search_q.strip():
        st.caption(
            f"**{len(view_df):,}** matching row(s) of **{len(df):,}** total."
            + (
                f" Showing first **{len(shown):,}**."
                if len(view_df) > len(shown)
                else ""
            )
        )
    elif max_display_rows is not None and len(df) > max_display_rows:
        st.caption(
            f"**{len(shown):,}** row(s) shown of **{len(df):,}** "
            f"(cap {max_display_rows}; use search to narrow)."
        )


def _normalize_table_keys(
    df: pd.DataFrame, primary: List[str], foreign: List[str]
) -> Tuple[List[str], List[str]]:
    primary = list(dict.fromkeys(primary))
    foreign = list(dict.fromkeys(foreign))
    foreign = [c for c in foreign if c not in primary]

    if len(primary) <= 1:
        return primary, foreign

    def _pk_rank(col: str) -> Tuple[int, int, int, str]:
        lc = str(col).lower()
        tier = 0 if lc == "id" else (1 if lc.endswith("_id") else 2)
        try:
            full = bool(df[col].notna().all() and df[col].nunique() == len(df))
        except Exception:
            full = False
        uniq_tier = 0 if full else 1
        return (tier, uniq_tier, len(str(col)), col)

    ranked = sorted(primary, key=_pk_rank)
    winner = ranked[0]
    new_primary = [winner]
    for c in ranked[1:]:
        lc = str(c).lower()
        if lc.endswith("_id") or lc == "id":
            if c not in foreign:
                foreign.append(c)
    foreign = [c for c in foreign if c not in new_primary]
    return new_primary, list(dict.fromkeys(foreign))


def enrich_cross_table_foreign_keys(
    dfs: Dict[str, pd.DataFrame],
    schema_guess: Dict[str, Dict[str, List[str]]],
) -> Dict[str, Dict[str, List[str]]]:
    out: Dict[str, Dict[str, List[str]]] = {
        k: {
            "primary_keys": list(v.get("primary_keys", [])),
            "foreign_keys": list(v.get("foreign_keys", [])),
        }
        for k, v in schema_guess.items()
    }
    names = list(dfs.keys())
    if len(names) < 2:
        return out

    for t in names:
        for col in dfs[t].columns:
            if col in out[t]["primary_keys"]:
                continue
            lc = str(col).lower()
            if not (lc.endswith("_id") or lc == "id"):
                continue
            for other in names:
                if other == t:
                    continue
                if col not in dfs[other].columns:
                    continue
                if col in out[other]["primary_keys"]:
                    if col not in out[t]["foreign_keys"]:
                        out[t]["foreign_keys"].append(col)
        out[t]["foreign_keys"] = [
            c
            for c in dict.fromkeys(out[t]["foreign_keys"])
            if c not in out[t]["primary_keys"]
        ]
    return out


def guess_keys(dfs: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, List[str]]]:
    def table_tokens(table_name: str) -> List[str]:
        stem = table_name.rsplit(".", 1)[0].lower()
        parts = [p for p in re.split(r"[^a-z0-9]+", stem) if p]
        tokens = set(parts)
        for p in parts:
            if p.endswith("ies") and len(p) > 3:
                tokens.add(p[:-3] + "y")
            elif p.endswith("s") and len(p) > 2:
                tokens.add(p[:-1])
        return [t for t in tokens if len(t) > 1]

    result: Dict[str, Dict[str, List[str]]] = {}

    tokens_by_table = {name: table_tokens(name) for name in dfs.keys()}

    for name, df in dfs.items():
        primary: List[str] = []
        foreign: List[str] = []
        tok = set(tokens_by_table[name])
        for col in df.columns:
            lc = col.lower().strip()
            if "_" in lc:
                head = lc.split("_", 1)[0]
                if len(head) > 1:
                    tok.add(head)
            if lc.endswith("_id") and len(lc) > 3:
                tok.add(lc[:-3])
        table_tokens_current = tok

        for col in df.columns:
            lc = col.lower().strip()
            if lc == "id":
                primary.append(col)
                continue

            if lc.endswith("_id"):
                prefix = lc[:-3]
                if prefix in table_tokens_current or lc in {
                    f"{t}_id" for t in table_tokens_current
                }:
                    primary.append(col)
                else:
                    foreign.append(col)
                continue

            if any(lc == f"{t}id" for t in table_tokens_current):
                primary.append(col)
                continue

            if lc.endswith("_id"):
                foreign.append(col)

        primary = list(dict.fromkeys(primary))
        foreign = [c for c in dict.fromkeys(foreign) if c not in primary]

        if not primary and len(df) > 0:

            def _surrogate_name(col) -> bool:
                lc = str(col).lower().strip()
                return (
                    lc == "id"
                    or lc.endswith("_id")
                    or "unnamed" in lc
                    or lc in ("index", "idx", "row", "row_id")
                )

            for col in df.columns:
                if not _surrogate_name(col):
                    continue
                try:
                    if df[col].notna().all() and df[col].nunique() == len(df):
                        primary.append(col)
                        break
                except Exception:
                    continue
        if not primary and len(df) > 0:
            for col in df.columns:
                try:
                    if df[col].notna().all() and df[col].nunique() == len(df):
                        primary.append(col)
                        break
                except Exception:
                    continue

        primary = list(dict.fromkeys(primary))
        foreign = [c for c in dict.fromkeys(foreign) if c not in primary]
        primary, foreign = _normalize_table_keys(df, primary, foreign)
        result[name] = {"primary_keys": primary, "foreign_keys": foreign}

    return result


def infer_relationships(schema_guess: Dict[str, Dict[str, List[str]]]) -> List[Tuple[str, str, str]]:
    def table_tokens(table_name: str) -> List[str]:
        stem = table_name.rsplit(".", 1)[0].lower()
        parts = [p for p in re.split(r"[^a-z0-9]+", stem) if p]
        tokens = set(parts)
        for p in parts:
            if p.endswith("ies") and len(p) > 3:
                tokens.add(p[:-3] + "y")
            elif p.endswith("s") and len(p) > 2:
                tokens.add(p[:-1])
        return [t for t in tokens if len(t) > 1]

    tokens_by_table = {t: table_tokens(t) for t in schema_guess.keys()}
    relationships: List[Tuple[str, str, str]] = []

    for child_table, keys in schema_guess.items():
        for fk in keys["foreign_keys"]:
            fk_lc = fk.lower()
            fk_prefix = fk_lc[:-3] if fk_lc.endswith("_id") else fk_lc

            for parent_table, parent_keys in schema_guess.items():
                if parent_table == child_table:
                    continue

                parent_tokens = tokens_by_table[parent_table]
                parent_pk_lc = {pk.lower() for pk in parent_keys["primary_keys"]}

                token_match = fk_prefix in parent_tokens
                pk_match = fk_lc in parent_pk_lc

                if token_match or pk_match:
                    relationships.append((parent_table, child_table, fk))
                    break

    return list(dict.fromkeys(relationships))


def infer_column_description(
    table: str,
    col: str,
    series: pd.Series,
    schema_guess: Dict[str, Dict[str, List[str]]],
) -> str:
    lc = col.lower().strip().replace(" ", "_")
    keys = schema_guess.get(table, {"primary_keys": [], "foreign_keys": []})
    pks = set(keys.get("primary_keys", []))
    fks = set(keys.get("foreign_keys", []))

    if col in pks:
        if "unnamed" in str(col).lower():
            return (
                f"Surrogate primary key (`row_index` / inferred from export) for `{table}`; "
                "uniquely identifies each row."
            )
        return f"Primary key for `{table}`; uniquely identifies each row."
    if col in fks:
        return "Foreign key; links this table to another entity for joins."

    parts: List[str] = []

    if any(x in lc for x in ["email", "e_mail", "mail"]):
        parts.append("Contact email address.")
    elif "phone" in lc or "mobile" in lc or "tel" in lc:
        parts.append("Phone or contact number.")
    elif "name" in lc and "user" not in lc:
        parts.append("Display or legal name.")
    elif lc in {"first_name", "firstname", "given_name"}:
        parts.append("Given name of a person or entity.")
    elif lc in {"last_name", "lastname", "surname", "family_name"}:
        parts.append("Family or surname.")
    elif "address" in lc or "street" in lc or "city" in lc or "zip" in lc or "postal" in lc:
        parts.append("Location or address component.")
    elif "country" in lc or "region" in lc or "state" in lc:
        parts.append("Geographic region or territory.")
    elif any(x in lc for x in ["date", "time", "timestamp", "created", "updated", "at"]):
        parts.append("Temporal field (event or record time).")
    elif any(x in lc for x in ["amount", "price", "total", "cost", "revenue", "mrr", "arr"]):
        parts.append("Monetary or numeric measure.")
    elif any(x in lc for x in ["qty", "quantity", "count", "units"]):
        parts.append("Count or quantity measure.")
    elif "status" in lc or "state" in lc or "phase" in lc:
        parts.append("Lifecycle or workflow status.")
    elif "id" in lc and col not in fks:
        parts.append("Identifier; may reference another record.")
    elif any(x in lc for x in ["sku", "product", "item"]):
        parts.append("Product or catalog reference.")
    elif any(x in lc for x in ["subscription", "plan", "tier"]):
        parts.append("Subscription or billing plan context.")
    elif any(x in lc for x in ["org", "company", "account", "facility", "site"]):
        parts.append("Organization or site context.")
    elif any(x in lc for x in ["event", "action", "type", "category"]):
        parts.append("Event type or categorical label.")

    dtype = str(series.dtype)
    null_pct = round(series.isna().mean() * 100, 1)
    uniq = series.nunique(dropna=True)

    if not parts:
        if "int" in dtype or "float" in dtype:
            parts.append("Numeric measure or code.")
        elif "bool" in dtype:
            parts.append("Boolean flag.")
        elif "datetime" in dtype:
            parts.append("Date/time value.")
        else:
            parts.append("Text or categorical field.")

    if null_pct > 15:
        parts.append(f"~{null_pct}% nulls — may need imputation or optional handling.")
    if uniq <= 5 and series.notna().any():
        parts.append(f"Low cardinality (~{uniq} distinct values).")

    return " ".join(parts)


def _dtype_word(series: pd.Series) -> str:
    s = str(series.dtype)
    if "int" in s:
        return "int"
    if "float" in s:
        return "float"
    if "bool" in s:
        return "bool"
    if "datetime" in s:
        return "datetime"
    return "string"


def _erd_table_id(table_name: str) -> str:
    stem = table_name.rsplit(".", 1)[0]
    return "t_" + re.sub(r"[^a-zA-Z0-9]", "_", stem)


def _assign_columns_to_logical_entities(
    df: pd.DataFrame, keys: Dict[str, List[str]]
) -> List[Tuple[str, List[str]]]:
    cols = list(df.columns)
    pks = set(keys.get("primary_keys", []))
    fks = set(keys.get("foreign_keys", []))
    assigned = set()

    def bucket(name: str, pred) -> Tuple[str, List[str]]:
        got: List[str] = []
        for c in cols:
            if c in assigned:
                continue
            if pred(c):
                got.append(c)
                assigned.add(c)
        return (name, got)

    groups: List[Tuple[str, List[str]]] = []

    key_ordered = [c for c in cols if c in pks] + [
        c for c in cols if c in fks and c not in pks
    ]
    for c in key_ordered:
        assigned.add(c)
    if key_ordered:
        groups.append(("ENTITY · KEYS (PK / FK)", key_ordered))

    def core_p(c: str) -> bool:
        lc = c.lower()
        if lc in ("id", "course_id", "product_id", "order_id", "account_id"):
            return True
        if "unnamed" in lc:
            return True
        if "title" in lc or lc in ("url", "link", "name", "sku"):
            return True
        if lc.endswith("_id"):
            pref = lc.rsplit("_", 1)[0]
            return pref in ("course", "product", "order", "account", "user", "org")
        return False
    commerce_p = lambda c: any(
        x in c.lower() for x in ("paid", "price", "cost", "amount", "mrr", "currency")
    )
    metrics_p = lambda c: any(
        x in c.lower()
        for x in ("num_", "subscriber", "review", "lecture", "rating", "count", "qty", "score")
    )
    content_p = lambda c: any(
        x in c.lower()
        for x in (
            "date",
            "time",
            "duration",
            "level",
            "subject",
            "category",
            "tag",
            "description",
            "published",
            "created",
            "updated",
        )
    )

    for title, pred in [
        ("ENTITY · CORE / IDENTITY", core_p),
        ("ENTITY · COMMERCE", commerce_p),
        ("ENTITY · METRICS", metrics_p),
        ("ENTITY · CONTENT & TIME", content_p),
    ]:
        name, got = bucket(title, pred)
        if got:
            groups.append((name, got))

    rest = [c for c in cols if c not in assigned]
    if rest:
        groups.append(("ENTITY · ATTRIBUTES (remaining)", rest))

    while len(groups) < 4 and any(len(g[1]) > 2 for g in groups):
        for i, (nm, gcols) in enumerate(groups):
            if len(gcols) <= 2:
                continue
            mid = len(gcols) // 2
            a, b = gcols[:mid], gcols[mid:]
            groups[i] = (nm + " (a)", a)
            groups.insert(i + 1, (nm + " (b)", b))
            break

    if len(groups) < 2:
        groups = []
        chunk = max(1, (len(cols) + 3) // 4)
        for i in range(0, len(cols), chunk):
            part = cols[i : i + chunk]
            groups.append((f"ENTITY · PART {len(groups) + 1}", part))

    return groups


def _logical_entity_box_label(
    group_title: str,
    columns: List[str],
    keys: Dict[str, List[str]],
    table_file: str,
    df: Optional[pd.DataFrame] = None,
) -> str:
    pks = set(keys.get("primary_keys", []))
    fks = set(keys.get("foreign_keys", []))
    n = len(columns)
    lines = [
        group_title,
        f"from: {table_file}",
        f"{n} field(s) · same CSV row",
        "────────",
    ]
    for c in columns:
        cd = _humanize_column_name(c)
        meta = ""
        if df is not None and c in df.columns:
            try:
                dt = _dtype_word(df[c])
                nullp = round(100.0 * float(df[c].isna().mean()), 1)
                meta = f"  ({dt})"
                if nullp > 0:
                    meta += f" · {nullp}% null"
            except Exception:
                meta = ""
        if c in pks:
            lines.append(f"*{cd}{meta}  [PK]")
        elif c in fks:
            lines.append(f"+{cd}{meta}  [FK]")
        else:
            lines.append(f"  {cd}{meta}")
    text = "\\n".join(lines)
    return text.replace('"', '\\"')


def generate_dataset_erd_dot(
    dfs: Dict[str, pd.DataFrame],
    schema_guess: Dict[str, Dict[str, List[str]]],
) -> str:
    if not dfs:
        return 'digraph X { label="No datasets"; bgcolor="#f8fafc"; }'

    rels = infer_relationships(schema_guess)
    total_rows = sum(len(df) for df in dfs.values())
    total_cols = sum(len(df.columns) for df in dfs.values())

    main_name = max(dfs.keys(), key=lambda n: len(dfs[n].columns))
    main_df = dfs[main_name]
    main_keys = schema_guess.get(main_name, {"primary_keys": [], "foreign_keys": []})

    groups = _assign_columns_to_logical_entities(main_df, main_keys)

    pk_list = main_keys.get("primary_keys", [])[:5]
    fk_list = main_keys.get("foreign_keys", [])[:6]
    pk_txt = ", ".join(_humanize_key_list(pk_list)) if pk_list else "none inferred"
    n_files = len(dfs)
    if fk_list:
        fk_txt = ", ".join(_humanize_key_list(fk_list))
    else:
        fk_txt = "— (no FK columns in file)" if n_files == 1 else "— (none)"
    if n_files == 1:
        rel_txt = f"{len(rels)} (needs 2+ CSVs for links)"
    else:
        rel_txt = f"{len(rels)} cross-table FK link(s)"

    shared_lab = (
        "Shared schema state\\n────────\\n"
        f"PK: {pk_txt}\\n"
        f"FK: {fk_txt}\\n"
        f"Cross-table links: {rel_txt}\\n"
        f"Profiled: {n_files} file(s), {total_cols} cols"
    ).replace('"', '\\"')

    graph_title = (
        "Wireframe ERD — layered logical model (blueprint view)"
    ).replace('"', '\\"')

    lines = [
        "digraph ERDLayered {",
        "  compound=true;",
        '  rankdir=TB;',
        '  splines=polyline;',
        '  nodesep=0.45;',
        '  ranksep=0.85;',
        f'  graph [fontname="Helvetica", fontsize=11, labelloc=t, label="{graph_title}", bgcolor="#fafafa", pad=0.5, fontcolor="#334155"];',
        '  node [fontname="Helvetica", fontsize=8];',
        '  edge [fontname="Helvetica", fontsize=7, color="#64748b", penwidth=1.0];',
        "",
    ]

    lines.extend(
        [
            '  subgraph cluster_entry {',
            '    label="①  Entry / ingest"; labelloc=t;',
            '    style="rounded,filled"; fillcolor="#f0f9ff"; color="#64748b"; fontcolor="#334155";',
            "",
        ]
    )
    for fname, df in dfs.items():
        tid = _erd_table_id(fname)
        fn_esc = fname.replace('"', '\\"')
        lines.append(
            f'    {tid} [label="SOURCE\\n{fn_esc}\\n{len(df):,} rows · {len(df.columns)} cols", '
            f'shape=note, style=filled, fillcolor="#ffffff", color="#64748b", fontcolor="#0f172a", margin=0.12, penwidth=1.1];'
        )
    lines.append("  }")
    lines.append("")

    lines.extend(
        [
            '  subgraph cluster_entities {',
            '    label="②  Logical entities — dtype & null rate per field"; labelloc=t;',
            '    style="rounded,filled"; fillcolor="#f0fdf4"; color="#64748b"; fontcolor="#334155";',
            "",
        ]
    )
    ent_ids: List[str] = []
    for i, (gtitle, gcols) in enumerate(groups):
        eid = f"ent_{i}"
        ent_ids.append(eid)
        lab = _logical_entity_box_label(gtitle, gcols, main_keys, main_name, main_df)
        lines.append(
            f'    {eid} [label="{lab}", shape=box, style="rounded,filled", fillcolor="#ffffff", '
            f'color="#15803d", penwidth=1.2, fontcolor="#14532d", margin=0.14];'
        )
    lines.append("  }")
    lines.append("")

    lines.extend(
        [
            '  subgraph cluster_shared {',
            '    label="③  Shared keys & relationships"; labelloc=t;',
            '    style="rounded,filled"; fillcolor="#faf5ff"; color="#64748b"; fontcolor="#334155";',
            f'    shared_keys [label="{shared_lab}", shape=box, style="rounded,filled", fillcolor="#f5f3ff", color="#6d28d9", penwidth=1.2, fontcolor="#4c1d95", margin=0.16];',
            "  }",
            "",
        ]
    )

    art_rows = f"{total_rows:,}"
    lines.extend(
        [
            '  subgraph cluster_artifacts {',
            '    label="④  Artifacts & target (ERD outputs)"; labelloc=t;',
            '    style="rounded,filled"; fillcolor="#fffbeb"; color="#64748b"; fontcolor="#334155";',
            f'    art_dict [label="Data dictionary\\n{total_cols} fields described", shape=box, style="rounded,filled", fillcolor="#ffffff", color="#ca8a04", margin=0.1];',
            '    art_mermaid [label="Mermaid ERD text\\nexport for docs", shape=box, style="rounded,filled", fillcolor="#ffffff", color="#ca8a04", margin=0.1];',
            f'    art_target [label="Profiled dataset\\n{art_rows} rows\\nready for load", shape=box, style="rounded,filled", fillcolor="#fffbeb", color="#b45309", margin=0.1];',
            "  }",
            "",
        ]
    )

    for parent, child, fk in rels:
        pid = _erd_table_id(parent)
        cid = _erd_table_id(child)
        fk_esc = fk.replace('"', '\\"')
        lines.append(
            f'  {pid} -> {cid} [label="{fk_esc} (FK)", color="#a855f7", penwidth=1.1, arrowsize=0.9, '
            f'constraint=false];'
        )

    for fname in dfs:
        tid = _erd_table_id(fname)
        for j in range(len(ent_ids)):
            lines.append(
                f'  {tid} -> ent_{j} [label="columns", color="#64748b", penwidth=1.0];'
            )

    for j, eid in enumerate(ent_ids):
        lines.append(
            f'  {eid} -> shared_keys [label="infer keys", color="#7c3aed", penwidth=1.05];'
        )

    lines.extend(
        [
            '  shared_keys -> art_dict [label="feeds", color="#b45309", penwidth=1.1];',
            '  shared_keys -> art_mermaid [label="feeds", color="#b45309", penwidth=1.1];',
            '  shared_keys -> art_target [label="feeds", color="#b45309", penwidth=1.1];',
            "",
        ]
    )

    for j in range(len(ent_ids) - 1):
        lines.append(
            f'  ent_{j} -> ent_{j + 1} [label="1:1 via row", color="#16a34a", '
            f'constraint=false, fontsize=7, penwidth=0.9];'
        )

    lines.append("}")
    return "\n".join(lines)


def _quality_tag(df: pd.DataFrame) -> str:
    if df.empty:
        return "Needs review"
    null_ratio = float(df.isna().sum().sum()) / float(max(1, df.shape[0] * max(1, df.shape[1])))
    if null_ratio < 0.03:
        return "Ready"
    if null_ratio < 0.12:
        return "Watch"
    return "Needs review"


def planned_transforms_named(df: pd.DataFrame) -> List[str]:
    cols = list(df.columns)
    steps: List[str] = []
    date_cols = [
        c
        for c in cols
        if any(
            x in c.lower()
            for x in ["date", "time", "timestamp", "created", "updated", "_at"]
        )
    ]
    if date_cols:
        steps.append(f"Parse & normalize dates: {', '.join(date_cols[:6])}")
    id_cols = [c for c in cols if c.lower().endswith("_id") or c.lower() == "id"]
    if id_cols:
        steps.append(f"Treat as join keys: {', '.join(id_cols[:8])}")
    nulls = df.isna().sum()
    bad = [c for c in cols if nulls[c] > 0]
    if bad:
        steps.append(f"Impute or flag nulls in: {', '.join(bad[:6])}")
    if len(steps) < 3:
        if len(cols) <= 10:
            steps.append(f"Coerce dtypes for: {', '.join(cols)}")
        else:
            steps.append(
                f"Coerce dtypes for **{len(cols)}** columns (e.g. {', '.join(cols[:5])}, …)"
            )
    return steps[:4]


def _html_strip_md_bold(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s)


def render_schema_pipeline_layout_v2(
    dfs: Dict[str, pd.DataFrame],
    schema_guess: Optional[Dict[str, Dict[str, List[str]]]] = None,
) -> None:
    if not dfs:
        st.info("Upload datasets first to preview pipeline layout.")
        return

    if schema_guess is None:
        schema_guess = guess_keys(dfs)
    relationships = infer_relationships(schema_guess)
    source_names = list(dfs.keys())
    total_rows = sum(len(df) for df in dfs.values())
    total_cols = sum(len(df.columns) for df in dfs.values())

    pk_all: List[str] = []
    fk_all: List[str] = []
    for t in schema_guess.values():
        pk_all.extend(t.get("primary_keys", []))
        fk_all.extend(t.get("foreign_keys", []))
    pk_unique = list(dict.fromkeys(pk_all))
    fk_unique = list(dict.fromkeys(fk_all))

    h = html.escape

    st.markdown(
        f"""
<div class="dw-wf-board">
  <div class="dw-wf-board-title">Schema inference · wireframe blueprint</div>
  <div class="dw-wf-metrics">
    <div class="dw-wf-metric-cell"><span class="dw-wf-num">{len(source_names)}</span><span class="dw-wf-lbl">SOURCES</span></div>
    <div class="dw-wf-metric-cell"><span class="dw-wf-num">{len(relationships)}</span><span class="dw-wf-lbl">CROSS-TABLE LINKS</span></div>
    <div class="dw-wf-metric-cell"><span class="dw-wf-num">{total_cols}</span><span class="dw-wf-lbl">FIELDS PROFILED</span></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    lane_e, lane_t, lane_l = st.columns([1, 1.15, 1])

    extract_cards: List[str] = []
    for name in source_names[:3]:
        df = dfs[name]
        sg = schema_guess.get(name, {"primary_keys": [], "foreign_keys": []})
        pk_str = ", ".join(_humanize_key_list(sg["primary_keys"])) or "—"
        fk_str = ", ".join(_humanize_key_list(sg["foreign_keys"])) or "—"
        cols_preview = ", ".join(f"<code>{h(str(c))}</code>" for c in list(df.columns)[:8])
        if len(df.columns) > 8:
            cols_preview += f" … +{len(df.columns) - 8}"
        q = _quality_tag(df)
        qcls = "dw-wf-pill-ok" if q == "Ready" else ("dw-wf-pill-warn" if q == "Watch" else "dw-wf-pill-bad")
        extract_cards.append(
            f"""
<div class="dw-wf-card">
  <div class="dw-wf-card-title">{h(name)}</div>
  <div class="dw-wf-meta">{len(df):,} rows · {len(df.columns)} cols</div>
  <div class="dw-wf-code">{cols_preview}</div>
  <div class="dw-wf-keys">PK <code>{h(pk_str)}</code> · FK <code>{h(fk_str)}</code></div>
  <span class="dw-wf-pill {qcls}">{h(q)}</span>
</div>
"""
        )
    with lane_e:
        st.markdown(
            '<div class="dw-wf-lane-h e">Extract · sources</div>',
            unsafe_allow_html=True,
        )
        st.markdown("".join(extract_cards), unsafe_allow_html=True)

    first_table = source_names[0]
    first_df = dfs[first_table]
    inf_rows: List[str] = []
    for tname in source_names[:4]:
        sg = schema_guess.get(tname, {"primary_keys": [], "foreign_keys": []})
        pk_h = ", ".join(_humanize_key_list(sg["primary_keys"])) or "—"
        fk_h = ", ".join(_humanize_key_list(sg["foreign_keys"])) or "—"
        inf_rows.append(
            f"<li><strong>{h(tname)}</strong> — PK <code>{h(pk_h)}</code> · FK <code>{h(fk_h)}</code></li>"
        )
    if relationships:
        rel_rows = "".join(
            f"<li>{h(parent)} <span style=\"color:#64748b\">—[{h(fk)}]→</span> {h(child)}</li>"
            for parent, child, fk in relationships[:6]
        )
        join_note = (
            f'<div class="dw-wf-note"><strong>Inferred joins</strong><ul class="dw-wf-ul">{rel_rows}</ul></div>'
        )
    else:
        join_note = (
            '<div class="dw-wf-note">No cross-table joins inferred — single file or no matching FK column names.</div>'
        )

    plan_lis = "".join(
        f"<li>{h(_html_strip_md_bold(step))}</li>" for step in planned_transforms_named(first_df)
    )
    pk_hint = ", ".join(_humanize_key_list(pk_unique[:4])) if pk_unique else "—"
    fk_hint = ", ".join(_humanize_key_list(fk_unique[:4])) if fk_unique else "—"

    transform_html = f"""
<div class="dw-wf-card">
  <div class="dw-wf-card-title">Inference · keys & joins</div>
  <ul class="dw-wf-ul">{"".join(inf_rows)}</ul>
  {join_note}
  <span class="dw-wf-pill dw-wf-pill-ok" style="margin-top:8px;">Status: inferred</span>
</div>
<div class="dw-wf-card">
  <div class="dw-wf-card-title">Planned transforms · {h(first_table)}</div>
  <ul class="dw-wf-ul">{plan_lis}</ul>
  <div class="dw-wf-note">Preview — heuristic list only. Aggregator applies merges; full transform engine is not run here.</div>
</div>
<div class="dw-wf-card">
  <div class="dw-wf-card-title">HITL gate</div>
  <div class="dw-wf-keys">PK <code>{h(pk_hint)}</code> · FK <code>{h(fk_hint)}</code></div>
  <div class="dw-wf-meta">Confirm in <strong>Transform</strong> (step 3) before running guided transforms.</div>
  <span class="dw-wf-pill dw-wf-pill-ok">Ready for review → Transform</span>
</div>
"""
    with lane_t:
        st.markdown(
            '<div class="dw-wf-lane-h t">Transform · inference & plan</div>',
            unsafe_allow_html=True,
        )
        st.markdown(transform_html, unsafe_allow_html=True)

    names_short = ", ".join(source_names[:3])
    if len(source_names) > 3:
        names_short += " …"
    load_html = f"""
<div class="dw-wf-card">
  <div class="dw-wf-card-title">Artifacts & load</div>
  <div class="dw-wf-meta">ERD edges: <strong>{len(relationships)}</strong> — tables {h(names_short)}</div>
  <div class="dw-wf-meta">Data dictionary: <strong>{total_cols}</strong> fields · <strong>{len(dfs)}</strong> table(s)</div>
  <div class="dw-wf-meta">Rows profiled: <strong>{total_rows:,}</strong></div>
  <span class="dw-wf-pill dw-wf-pill-ok">Export-ready</span>
</div>
"""
    with lane_l:
        st.markdown(
            '<div class="dw-wf-lane-h l">Load · outputs</div>',
            unsafe_allow_html=True,
        )
        st.markdown(load_html, unsafe_allow_html=True)


def make_data_dictionary(dfs: Dict[str, pd.DataFrame], schema: Dict[str, Dict[str, List[str]]]) -> List[Dict]:
    rows: List[Dict] = []
    for table, df in dfs.items():
        keys = schema.get(table, {"primary_keys": [], "foreign_keys": []})
        for col in df.columns:
            role = "attribute"
            if col in keys["primary_keys"]:
                role = "primary_key"
            elif col in keys["foreign_keys"]:
                role = "foreign_key"
            rows.append(
                {
                    "table": table,
                    "column": col,
                    "dtype": str(df[col].dtype),
                    "role": role,
                    "null_pct": round(df[col].isna().mean() * 100, 2),
                    "description": infer_column_description(table, str(col), df[col], schema),
                }
            )
    return rows


def run_transform(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    if not dfs:
        return pd.DataFrame()
    items = list(dfs.items())
    base = items[0][1].copy()
    for _, df in items[1:]:
        common = list(set(base.columns) & set(df.columns))
        keys = [c for c in common if str(c).lower() == "id" or str(c).lower().endswith("_id")]
        if keys:
            base = base.merge(df, on=keys[0], how="left", suffixes=("", "_r"))
    return base


def _agent_dialogue_text(dialogue: Dict[str, str]) -> str:
    raw_lines = [str(msg).strip() for msg in dialogue.values() if str(msg).strip()]
    seen = set()
    lines = []
    for line in raw_lines:
        if line not in seen:
            seen.add(line)
            lines.append(line)
    return "\n\n".join(lines) if lines else "Waiting for connection..."


def _agent_dialogue_html(dialogue: Dict[str, str]) -> str:
    escaped = html.escape(_agent_dialogue_text(dialogue)).replace("\n", "<br>")
    return (
        '<div style="border:1px solid rgba(34,211,238,0.45);border-radius:0;'
        'background:linear-gradient(180deg,#081216,#05090b);padding:12px 14px;min-height:260px;'
        'box-shadow:0 0 0 1px rgba(6,182,212,0.15) inset,0 0 24px rgba(6,182,212,0.06);">'
        '<div style="font-size:0.84rem;color:#e2e8f0;line-height:1.6;'
        "font-family:'IBM Plex Mono',monospace;word-break:break-word;white-space:normal;\">"
        + escaped
        + "</div></div>"
    )


def _set_transform_workflow_step(step: int) -> None:
    st.session_state.transform_workflow_step = int(step)


def _render_transform_workflow_nav() -> None:
    """Clickable workflow strip (Instructions → Complete)."""
    if "transform_workflow_step" not in st.session_state:
        st.session_state.transform_workflow_step = 0
    step = int(st.session_state.transform_workflow_step)
    if step < 0 or step > 3:
        st.session_state.transform_workflow_step = 0
        step = 0

    labels: List[Tuple[str, int]] = []
    for idx, base in enumerate(["Instructions", "Approve plan", "Approve code", "Complete"]):
        if idx < step:
            labels.append((f"✓ {base}", idx))
        elif idx == step:
            labels.append((f"▸ {base}", idx))
        else:
            labels.append((base, idx))

    with st.container(key="dw_tf_workflow_nav"):
        col0, col1, col2, col3 = st.columns(4)
        for col, (txt, idx) in zip([col0, col1, col2, col3], labels):
            with col:
                st.button(
                    txt,
                    key=f"dw_tf_nav_{idx}",
                    type="primary" if step == idx else "secondary",
                    use_container_width=True,
                    on_click=_set_transform_workflow_step,
                    args=(idx,),
                )


def _transform_activity_log_markdown(lines: List[str]) -> str:
    if not lines:
        return "*No activity yet. Run the pipeline to stream Scout + Architect progress here.*"
    return "\n\n".join(lines)


def render_agent_dialogue_box(placeholder: Optional[object] = None) -> None:
    st.markdown("**Process code**")
    target = placeholder if placeholder is not None else st
    target.markdown(_agent_dialogue_html(st.session_state.agent_dialogue), unsafe_allow_html=True)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Data")
    return buf.getvalue()


def to_pdf_bytes(df: pd.DataFrame, title: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    max_cols = 8
    cols = [str(c) for c in df.columns[:max_cols]]
    trimmed = len(df.columns) > max_cols
    if trimmed:
        cols.append("...")
    rows = [cols]
    for _, row in df.head(60).iterrows():
        vals = [str(row[c]) if c in row.index else "" for c in df.columns[:max_cols]]
        if trimmed:
            vals.append("...")
        rows.append(vals)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    table = Table(rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ede9fe")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ]
        )
    )
    elems = [
        Paragraph(title, styles["Heading3"]),
        Spacer(1, 6),
        Paragraph(f"Rows exported: {len(df):,} | Columns exported: {min(len(df.columns), max_cols)}", styles["Normal"]),
        Spacer(1, 8),
        table,
    ]
    doc.build(elems)
    return buf.getvalue()

# -----------------------------------------------------------------------------
# Header + stepper
# -----------------------------------------------------------------------------
_inject_styles()

if not st.session_state.get("authenticated"):
    render_starter_page()
    st.stop()

_render_dw_sidebar_account()
st.sidebar.title("Navigation")
for idx, page_name in enumerate(PAGES):
    label = f"{idx + 1}. {page_name}"
    st.sidebar.button(
        label,
        key=f"sidebar_step_{idx}",
        on_click=go_to_page,
        args=(idx,),
        use_container_width=True,
        type="primary" if st.session_state.page_idx == idx else "secondary",
    )

current = PAGES[st.session_state.page_idx]

st.markdown(
    """
    <div class="dw-topbar">
        <div class="dw-topbar-text">DATA WEAVE</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.session_state.get("dw_account_ui") == "open":
    if _open_dw_account_window is not None:
        _open_dw_account_window()
    else:
        with st.expander("Account", expanded=True):
            _dw_account_dialog_callback()

if st.session_state.get("dw_support_ui") == "open":
    if _open_dw_support_window is not None:
        _open_dw_support_window()
    else:
        with st.expander("Live support", expanded=True):
            _dw_support_window_chrome()
            _render_dw_support_panel_body()


# -----------------------------------------------------------------------------
# Page 1: Upload / dashboard
# -----------------------------------------------------------------------------
if current == "Upload":
    _hero("Step 1", "Upload", "Upload csv, URL API, or Google Drive source")
    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        st.metric("Sources in session", len(st.session_state.uploaded_dfs))
    with mc2:
        total_rows = sum(len(df) for df in st.session_state.uploaded_dfs.values()) if st.session_state.uploaded_dfs else 0
        st.metric("Rows available", f"{total_rows:,}")
    with mc3:
        st.metric("Pipeline step", "Ingest")

    mode = st.session_state.source_mode

    def _add_files_menu() -> None:
        with st.popover("Add files", use_container_width=False):
            st.caption("Select how to add data")
            if st.button("Browse files", key="add_menu_browse", use_container_width=True):
                st.session_state.source_mode = "Upload csv"
                st.session_state.trigger_csv_picker = True
                st.rerun()
            if st.button("Upload url api", key="add_menu_api", use_container_width=True):
                st.session_state.source_mode = "Upload url api"
                st.rerun()
            if st.button("Connect google drive", key="add_menu_drive", use_container_width=True):
                st.session_state.source_mode = "Connect google drive"
                st.rerun()

    st.markdown(
        """
        <style>
        section[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid rgba(34, 211, 238, 0.38) !important;
            border-radius: 0 !important;
            background: linear-gradient(175deg, rgba(8, 18, 22, 0.96) 0%, rgba(4, 6, 8, 0.95) 100%) !important;
            padding: 0.6rem 0.65rem 0.8rem !important;
            margin-bottom: 0.35rem !important;
            box-shadow: 0 0 0 1px rgba(6, 182, 212, 0.1) inset, 0 10px 32px rgba(0, 0, 0, 0.42) !important;
        }
        section[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] div[data-testid="column"]:nth-child(1),
        section[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child {
            background: linear-gradient(180deg, #0a2830 0%, #081216 50%, #05090b 100%) !important;
            border-radius: 0 !important;
            padding: 0.5rem 0.65rem 0.6rem !important;
            margin: 0.1rem 0.15rem 0.1rem 0.1rem !important;
            box-shadow: inset 0 1px 0 rgba(103, 232, 249, 0.06) !important;
            border: 1px solid rgba(34, 211, 238, 0.32) !important;
        }
        section[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] div[data-testid="column"]:nth-child(2),
        section[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child {
            background: linear-gradient(180deg, #081216 0%, #05090b 100%) !important;
            border-radius: 0 !important;
            padding: 0.35rem 0.4rem !important;
            margin: 0.1rem 0.1rem 0.1rem 0 !important;
            box-shadow: 0 0 0 1px rgba(6, 182, 212, 0.06) inset, 0 6px 20px rgba(0, 0, 0, 0.4) !important;
            border: 1px solid rgba(34, 211, 238, 0.28) !important;
            align-self: flex-start !important;
        }
        section[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stFileUploader"] section {
            background: transparent !important;
        }
        section[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
            border: 2px dashed rgba(34, 211, 238, 0.52) !important;
            border-radius: 0 !important;
            background: rgba(4, 8, 10, 0.96) !important;
            padding: 1rem 1.2rem !important;
            min-height: 7.5rem !important;
            box-shadow:
                0 0 0 1px rgba(6, 182, 212, 0.2) inset,
                0 4px 20px rgba(0, 0, 0, 0.45) !important;
        }
        section[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] .stTextInput input {
            border-radius: 0 !important;
            border: 1px solid rgba(34, 211, 238, 0.32) !important;
            background: #05090b !important;
            color: #ecfeff !important;
            padding: 0.55rem 0.65rem !important;
        }
        section[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] .stTextInput label p {
            font-size: 0.72rem !important;
            font-weight: 700 !important;
            letter-spacing: 0.04em !important;
            color: #7ddaea !important;
            text-transform: uppercase;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    files = None
    with st.container(border=True):
        row = st.columns([4, 1])
        with row[0]:
            if mode == "Upload csv":
                st.caption("Select CSV file(s) from this device")
                files = st.file_uploader(
                    "csv_upload",
                    type=["csv"],
                    accept_multiple_files=True,
                    label_visibility="collapsed",
                    key=f"dw_csv_uploader_{st.session_state.upload_reset_id}",
                )
                if st.session_state.uploaded_dfs and not files:
                    st.markdown("---")
                    st.markdown("**Files in session**")
                    for fname, df in st.session_state.uploaded_dfs.items():
                        sz = _format_session_csv_size(df)
                        st.markdown(f"- 📄 `{fname}` · **{sz}** · {len(df):,} rows")
            elif mode == "Upload url api":
                st.caption("Paste your API endpoint URL")
                st.text_input(
                    "API URL",
                    key="upload_api_url_field",
                    placeholder="https://api.example.com/data",
                )
            else:
                st.caption("Paste a Google Drive file or folder link")
                st.text_input(
                    "Google Drive file/folder link",
                    key="upload_drive_link_field",
                    placeholder="https://drive.google.com/file/d/...",
                )
                st.link_button("Open Google Drive", "https://drive.google.com/", use_container_width=True)
        with row[1]:
            st.markdown("<br/>", unsafe_allow_html=True)
            _add_files_menu()
            with st.container(key="dw_support_upload_anchor"):
                _render_dw_support_launcher()
        if mode == "Upload url api":
            if st.button("Submit API URL", key="upload_submit_api", use_container_width=True):
                _reset_mapper_outputs()
                st.session_state.run_logs = []
                st.session_state.uploaded_dfs = {
                    "api_data.csv": pd.DataFrame({"id": [1, 2], "value": [100, 200]})
                }
        elif mode == "Connect google drive":
            if st.button("Use Google Drive link", key="upload_submit_drive", use_container_width=True):
                _reset_mapper_outputs()
                st.session_state.run_logs = []
                st.session_state.uploaded_dfs = {
                    "drive_data.csv": pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
                }

    if mode == "Upload csv":
        if st.session_state.trigger_csv_picker:
            _trigger_native_file_picker()
            st.session_state.trigger_csv_picker = False
        if files:
            _reset_mapper_outputs()
            st.session_state.run_logs = []
            st.session_state.uploaded_dfs = {}
            for f in files:
                st.session_state.uploaded_dfs[f.name] = pd.read_csv(f)

    if st.session_state.uploaded_dfs:
        n = len(st.session_state.uploaded_dfs)
        st.success(
            f"**{n}** file(s) in session — kept while you use steps 2–4. "
            "Upload again to **replace**; use **Clear** below to remove."
        )
        c_clear, _ = st.columns([1, 3])
        with c_clear:
            if st.button("🗑 Clear uploaded data & reset pipeline", type="secondary"):
                _reset_pipeline_session()
                st.rerun()
        st.caption("Data source is ready. Click **Next** to continue to Mapper.")

    c1, c2, _ = st.columns([1, 1, 6])
    with c1:
        st.button("Back", disabled=True)
    with c2:
        st.button("Next", on_click=go_next, type="primary")


# -----------------------------------------------------------------------------
# Page 2: Mapper
# -----------------------------------------------------------------------------
elif current == "Mapper":
    _hero("Step 2", "Mapper", "Preview, schema inference, ERD, and data dictionary")

    if not st.session_state.uploaded_dfs:
        st.warning("No uploaded data found. Go back to Upload page.")
    else:
        mk1, mk2, mk3 = st.columns(3)
        with mk1:
            st.metric("Tables", len(st.session_state.uploaded_dfs))
        with mk2:
            st.metric("Total fields", sum(len(df.columns) for df in st.session_state.uploaded_dfs.values()))
        with mk3:
            st.metric("Step status", "Auto-mapped")

        source_sig = tuple(
            sorted((name, len(df), len(df.columns)) for name, df in st.session_state.uploaded_dfs.items())
        )
        if st.session_state.mapper_source_sig != source_sig:
            schema_guess = guess_keys(st.session_state.uploaded_dfs)
            schema = enrich_cross_table_foreign_keys(st.session_state.uploaded_dfs, schema_guess)
            st.session_state.mapper_schema = schema
            st.session_state.data_dictionary = make_data_dictionary(st.session_state.uploaded_dfs, schema)
            st.session_state.mapper_source_sig = source_sig
            st.session_state.run_logs.append({"stage": "Mapper", "status": "completed"})

        t1, t2, t3, t4, t5 = st.tabs(
            ["Preview", "Column profiling", "Schema inference", "ERD", "DATA DICTIONARY"]
        )

        with t1:
            for name, df in st.session_state.uploaded_dfs.items():
                sk = re.sub(r"[^\w]+", "_", name)[:80]
                title_col, tools_col = st.columns([1, 2])
                with title_col:
                    st.markdown(f"### 📄 {name}")
                with tools_col:
                    search_q = st.text_input(
                        "search_preview",
                        key=f"pv_search_{sk}",
                        placeholder="🔍  Search any column or row text…",
                        label_visibility="collapsed",
                    )
                    sort_mode = "default"

                filtered = _preview_search_filter(df, search_q or "")
                view_df = _preview_sort_dataframe(filtered, sort_mode)
                max_preview = 500
                shown = view_df.head(max_preview)
                st.dataframe(shown, use_container_width=True, height=420)
                if search_q and search_q.strip():
                    st.caption(
                        f"**{len(view_df):,}** matching row(s) of **{len(df):,}** total."
                        + (f" Showing first **{len(shown):,}**." if len(view_df) > max_preview else "")
                    )
                else:
                    st.caption(
                        f"**{len(shown):,}** row(s) shown"
                        + (f" of **{len(df):,}** (cap {max_preview}; use search to narrow)." if len(df) > max_preview else ".")
                    )
        with t2:
            for name, df in st.session_state.uploaded_dfs.items():
                sk = re.sub(r"[^\w]+", "_", name)[:80]
                st.markdown(f"### 📄 {name}")
                _render_searchable_dataframe(
                    profile_dataframe(df),
                    key_prefix=f"prof_{sk}",
                    height=340,
                )
        with t3:
            if st.session_state.mapper_schema:
                render_schema_pipeline_layout_v2(
                    st.session_state.uploaded_dfs,
                    st.session_state.mapper_schema,
                )
                with st.expander("Raw schema JSON", expanded=False):
                    st.json(st.session_state.mapper_schema)
                st.markdown("**Inferred relationships**")
                rels = infer_relationships(st.session_state.mapper_schema)
                rel_df = (
                    pd.DataFrame(rels, columns=["parent_table", "child_table", "fk_column"])
                    if rels
                    else pd.DataFrame(columns=["parent_table", "child_table", "fk_column"])
                )
                _render_searchable_dataframe(rel_df, key_prefix="infer_rels")
            else:
                st.info("Schema inference not available.")
        with t4:
            if st.session_state.mapper_schema:
                st.markdown("##### Layered ERD — wireframe blueprint")
                st.caption(
                    "Dashed clusters & edges = blueprint style (not a final DB diagram). "
                    "Ingest → logical entities → shared keys → artifacts."
                )
                dot_layered = generate_dataset_erd_dot(
                    st.session_state.uploaded_dfs,
                    st.session_state.mapper_schema,
                )
                st.graphviz_chart(dot_layered, use_container_width=True)
            else:
                st.info("ERD not available.")
        with t5:
            if st.session_state.data_dictionary:
                _render_searchable_dataframe(
                    pd.DataFrame(st.session_state.data_dictionary),
                    key_prefix="data_dict",
                    column_config={
                        "description": st.column_config.TextColumn(
                            "Description",
                            width="large",
                            help="Heuristic summary from name, dtype, PK/FK, nulls.",
                        ),
                    },
                )
                st.info("Review outputs, then continue to **Transform** (step 3).")
            else:
                st.info("Data dictionary not available.")

    c1, c2, _ = st.columns([1, 1, 6])
    with c1:
        st.button("Back", on_click=go_back)
    with c2:
        st.button("Next", on_click=go_next, type="primary")


# -----------------------------------------------------------------------------
# Page 3: Transform
# -----------------------------------------------------------------------------
elif current == "Transform":
    _hero("Step 3", "Transform", "Transformation run + table preview")

    if not st.session_state.uploaded_dfs:
        st.warning("No uploaded data found. Go back to Upload.")
    else:
        transform_sig = (
            tuple(sorted((name, len(df), len(df.columns)) for name, df in st.session_state.uploaded_dfs.items())),
            st.session_state.mapper_source_sig,
        )
        if st.session_state.transform_source_sig != transform_sig:
            st.session_state.transformed_df = run_transform(st.session_state.uploaded_dfs)
            st.session_state.transform_source_sig = transform_sig
            st.session_state.run_logs.append(
                {"stage": "Transform", "status": "completed", "notes": "Auto-transform on page load"}
            )

        t1, t2, t3 = st.tabs(["Transform", "Discarded Data", "Transformed data"])
        with t1:
            _render_transform_workflow_nav()
            step = int(st.session_state.get("transform_workflow_step", 0))

            if step == 0:
                with st.container(border=True):
                    st.markdown("#### Step 1 — Instructions")
                    st.caption(
                        "Describe the transformation rules, then click Run. Scout and Architect will run automatically."
                    )
                    user_instructions = st.text_area(
                        "Instructions for the pipeline",
                        value=st.session_state.user_instructions,
                        placeholder=(
                            "e.g. Drop all rows where course titles are not in English and only grab "
                            "the first 20 courses for each Alphabet."
                        ),
                        height=180,
                        key="user_instructions_input",
                        label_visibility="collapsed",
                    )
                    st.session_state.user_instructions = user_instructions

                    run_clicked = st.button(
                        "Run pipeline",
                        type="primary",
                        key="run_pipeline_btn",
                        use_container_width=True,
                    )

                if run_clicked:
                    if not st.session_state.uploaded_dfs:
                        st.error("Upload a dataset first before running the pipeline.")
                    else:
                        st.session_state.pipeline_run_result = None
                        st.session_state.transform_workflow_step = 0
                        st.session_state.transform_expander_open = True
                        st.session_state.transform_activity_log = ["Uploading data and starting pipeline..."]
                        st.session_state.transform_plan_draft = _default_plan_from_instructions(
                            st.session_state.user_instructions
                        )
                        st.session_state.transform_code_draft = ""

                        source_name = next(iter(st.session_state.uploaded_dfs))
                        payload = {
                            "source_type": "csv",
                            "source_path": f"datasets/{source_name}",
                            "user_instructions": st.session_state.user_instructions,
                            "target_db_path": "output/etl_output.db",
                            "target_table": "courses",
                            "if_exists": "replace",
                        }

                        streaming_dialogue: Dict[str, str] = {
                            "Scout": "Connecting…",
                            "Architect": "Waiting…",
                            "Engineer": "Waiting…",
                        }
                        st.session_state.agent_dialogue = streaming_dialogue

                        token_buf: Dict[str, str] = {"architect": "", "engineer": ""}

                        try:
                            with requests.post(
                                f"{BACKEND_URL}/api/run/stream",
                                json=payload,
                                stream=True,
                                timeout=300,
                            ) as resp:
                                for raw_line in resp.iter_lines():
                                    if not raw_line:
                                        continue
                                    line = raw_line.decode("utf-8")
                                    if not line.startswith("data: "):
                                        continue
                                    try:
                                        event = _json.loads(line[6:])
                                    except _json.JSONDecodeError:
                                        continue

                                    etype = event.get("type", "")
                                    node = event.get("node", "")

                                    if etype == "token":
                                        if node in token_buf:
                                            token_buf[node] += event.get("token", "")
                                            key = node.capitalize()
                                            streaming_dialogue[key] = token_buf[node]
                                            if node == "architect":
                                                st.session_state.transform_plan_draft = token_buf[node]
                                            if node == "engineer":
                                                st.session_state.transform_code_draft = token_buf[node]

                                    elif etype == "node_done":
                                        if node == "scout":
                                            count = event.get("record_count", "?")
                                            streaming_dialogue["Scout"] = f"Done — {count} records ingested."
                                            st.session_state.transform_activity_log.append(streaming_dialogue["Scout"])
                                        elif node == "architect":
                                            plan = event.get("transformation_plan", "")
                                            st.session_state.transform_plan_draft = plan.strip() or st.session_state.transform_plan_draft
                                            streaming_dialogue["Architect"] = plan.strip() or "Plan generated."
                                            token_buf["architect"] = ""
                                        elif node == "engineer":
                                            verdict = event.get("engineer_verdict", "")
                                            err = event.get("engineer_error", "")
                                            streaming_dialogue["Engineer"] = (
                                                f"Verdict: {verdict}" + (f"\nError: {err}" if err else "")
                                            )
                                            token_buf["engineer"] = ""
                                        elif node == "loader":
                                            rows = event.get("rows_written", "?")
                                            streaming_dialogue["Scout"] += f"\nLoaded: {rows} rows to DB."

                                        audit = event.get("latest_audit")
                                        if audit:
                                            aline = (
                                                f"[{audit.get('agent')}] {audit.get('action')} — "
                                                f"{audit.get('summary')}"
                                            )
                                            st.session_state.transform_activity_log.append(aline)

                                    elif etype == "done":
                                        st.session_state.agent_dialogue = streaming_dialogue
                                        st.session_state.pipeline_run_result = {"status": "success"}
                                        st.session_state.transform_workflow_step = 1
                                        if not st.session_state.transform_code_draft.strip():
                                            st.session_state.transform_code_draft = _default_code_from_plan(
                                                st.session_state.transform_plan_draft
                                            )
                                        st.session_state.run_logs.append(
                                            {"stage": "Pipeline run", "status": "success"}
                                        )
                                        st.session_state.transform_activity_log.append("Pipeline complete!")
                                        break

                                    elif etype == "error":
                                        err_msg = f"Pipeline error: {event.get('error', 'unknown')}"
                                        st.session_state.transform_activity_log.append(err_msg)
                                        break

                        except requests.exceptions.ConnectionError:
                            msg = f"Cannot reach backend at {BACKEND_URL}. Is the API server running?"
                            st.session_state.transform_activity_log.append(msg)
                            st.error(msg)
                        except Exception as exc:
                            msg = f"Unexpected error: {exc}"
                            st.session_state.transform_activity_log.append(msg)
                            st.error(msg)

                        st.rerun()

            elif step == 1:
                st.warning("⏳ Waiting for your approval — review the Architect's plan below")
                with st.container(border=True):
                    st.markdown("#### Step 2 — Approve transformation plan")
                    st.caption(
                        "The Architect mapped out the transform. Edit if needed, then approve to generate code."
                    )
                    st.session_state.transform_plan_draft = st.text_area(
                        "Plan draft",
                        value=st.session_state.transform_plan_draft,
                        key="transform_plan_draft_input",
                        height=260,
                        label_visibility="collapsed",
                    )
                    cpa, csr = st.columns([3, 1])
                    with cpa:
                        if st.button("Approve plan — generate code", type="primary", use_container_width=True):
                            if not st.session_state.transform_code_draft.strip():
                                st.session_state.transform_code_draft = _default_code_from_plan(
                                    st.session_state.transform_plan_draft
                                )
                            st.session_state.transform_workflow_step = 2
                            st.rerun()
                    with csr:
                        if st.button("Start over", use_container_width=True):
                            st.session_state.transform_workflow_step = 0
                            st.rerun()

            elif step == 2:
                st.warning("⏳ Waiting for your approval — review the Engineer's code below")
                with st.container(border=True):
                    st.markdown("#### Step 3 — Approve transformation code")
                    st.caption("The Engineer wrote this script. Download to inspect locally, then approve to execute.")
                    code_preview = st.session_state.transform_code_draft or _default_code_from_plan(
                        st.session_state.transform_plan_draft
                    )
                    st.code(code_preview, language="python")
                    cdl, cap, csr = st.columns([1.3, 1.3, 1])
                    with cdl:
                        st.download_button(
                            "Download .py",
                            data=code_preview.encode("utf-8"),
                            file_name="transform_pipeline.py",
                            mime="text/x-python",
                            use_container_width=True,
                            key="dw_tf_download_code",
                        )
                    with cap:
                        if st.button("Approve & execute", type="primary", use_container_width=True):
                            st.session_state.transform_workflow_step = 3
                            st.rerun()
                    with csr:
                        if st.button("Start over", use_container_width=True, key="dw_tf_start_over_code"):
                            st.session_state.transform_workflow_step = 0
                            st.rerun()

            else:
                with st.container(border=True):
                    st.markdown("#### Complete")
                    if st.session_state.transformed_df is not None and not st.session_state.transformed_df.empty:
                        st.dataframe(st.session_state.transformed_df.head(20), use_container_width=True, height=260)
                        st.caption("Go to the Transformed data tab or Logs & Downloads for full export.")
                    else:
                        st.info("No transformed output available yet.")

                    if st.button("Run again", key="dw_tf_run_again"):
                        st.session_state.transform_workflow_step = 0
                        st.rerun()

            if step in (0, 1, 2):
                _tf_exp_open = bool(st.session_state.transform_expander_open) or bool(
                    st.session_state.transform_activity_log
                )
                with st.expander("Running Scout + Architect...", expanded=_tf_exp_open):
                    st.markdown(_transform_activity_log_markdown(st.session_state.transform_activity_log))

            st.markdown("##### Agent dialogue")
            st.markdown(_agent_dialogue_html(st.session_state.agent_dialogue), unsafe_allow_html=True)

        with t2:
            st.markdown("##### Discarded Data")
            discarded = st.session_state.discarded_df
            if discarded is not None and not discarded.empty:
                _render_searchable_dataframe(
                    discarded,
                    key_prefix="discarded_rows",
                    height=520,
                )
                st.caption(f"{len(discarded):,} rows · {len(discarded.columns)} columns")
            else:
                st.info(
                    "No discarded rows are in session yet. When the transform pipeline records "
                    "dropped or rejected records, they will show here."
                )
        with t3:
            st.markdown("##### Transformed data")
            if st.session_state.transformed_df is not None and not st.session_state.transformed_df.empty:
                _render_searchable_dataframe(
                    st.session_state.transformed_df,
                    key_prefix="transformed_full",
                    height=520,
                )
                st.caption(
                    f"{len(st.session_state.transformed_df):,} rows · "
                    f"{len(st.session_state.transformed_df.columns)} columns"
                )
            else:
                st.info("No transformed table yet. Complete **Upload** and **Mapper**, then return here.")

    c1, c2, _ = st.columns([1, 1, 6])
    with c1:
        st.button("Back", on_click=go_back)
    with c2:
        st.button("Next", on_click=go_next, type="primary")


# -----------------------------------------------------------------------------
# Page 4: Logs & Downloads
# -----------------------------------------------------------------------------
elif current == "Logs & Downloads":
    _hero("Step 4", "Logs & Downloads", "Session audit trail and export options")

    col_log, col_dl = st.columns([1, 1])

    with col_log:
        st.subheader("Run log")
        if st.session_state.run_logs:
            st.json(st.session_state.run_logs)
        else:
            st.info("No events yet.")

    with col_dl:
        st.subheader("Downloads")
        if st.session_state.transformed_df is not None and not st.session_state.transformed_df.empty:
            with st.popover("⬇ Transformed dataset", use_container_width=True):
                st.download_button(
                    label="Download CSV",
                    data=to_csv_bytes(st.session_state.transformed_df),
                    file_name="dataweave_transformed.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="dw_dl_tfm_csv",
                )
                st.download_button(
                    label="Download PDF",
                    data=to_pdf_bytes(st.session_state.transformed_df, "Transformed dataset"),
                    file_name="dataweave_transformed.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="dw_dl_tfm_pdf",
                )
                st.download_button(
                    label="Download XLS (sheets)",
                    data=to_xlsx_bytes(st.session_state.transformed_df),
                    file_name="dataweave_transformed.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="dw_dl_tfm_xls",
                )
        else:
            st.caption("Complete Transform to enable dataset export.")

        if st.session_state.data_dictionary:
            dd_df = pd.DataFrame(st.session_state.data_dictionary)
            with st.popover("⬇ Data dictionary", use_container_width=True):
                st.download_button(
                    label="Download CSV",
                    data=to_csv_bytes(dd_df),
                    file_name="dataweaver_data_dictionary.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="dw_dl_dd_csv",
                )
                st.download_button(
                    label="Download PDF",
                    data=to_pdf_bytes(dd_df, "Data dictionary"),
                    file_name="dataweaver_data_dictionary.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="dw_dl_dd_pdf",
                )
                st.download_button(
                    label="Download XLS (sheets)",
                    data=to_xlsx_bytes(dd_df),
                    file_name="dataweaver_data_dictionary.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="dw_dl_dd_xls",
                )
        else:
            st.caption("Complete Mapper to enable dictionary export.")

    c1, c2, _ = st.columns([1, 1, 6])
    with c1:
        st.button("Back", on_click=go_back)
    with c2:
        st.button("Next", disabled=True)

st.markdown(
    '<p style="text-align:center;color:#94a3b8;font-size:0.8rem;margin-top:2rem;">DATA WEAVE · Capstone</p>',
    unsafe_allow_html=True,
)

