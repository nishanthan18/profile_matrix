"""Dark / Light theme CSS for the Streamlit app. All text colours are explicitly
set (not left to inherit) so contrast stays correct in both themes, including
inside custom keyword-chip and card components.
"""

LIGHT_CSS = """
<style>
:root {
    --bg-color: #f5f7fa;
    --card-bg: #ffffff;
    --text-color: #1a1f2b;
    --sub-text: #4b5563;
    --accent: #2563eb;
    --accent-soft: #e8effe;
    --border-color: #e2e8f0;
    --chip-bg: #eef2ff;
    --chip-text: #3730a3;
    --success-bg: #dcfce7;
    --success-text: #166534;
    --danger-bg: #fee2e2;
    --danger-text: #991b1b;
}
</style>
"""

DARK_CSS = """
<style>
:root {
    --bg-color: #0f1117;
    --card-bg: #1a1d27;
    --text-color: #f1f5f9;
    --sub-text: #b6bec9;
    --accent: #60a5fa;
    --accent-soft: #1e293b;
    --border-color: #2d3340;
    --chip-bg: #22304a;
    --chip-text: #93c5fd;
    --success-bg: #14351f;
    --success-text: #86efac;
    --danger-bg: #3a1a1a;
    --danger-text: #fca5a5;
}
</style>
"""

BASE_CSS = """
<style>
.stApp {
    background-color: var(--bg-color);
    color: var(--text-color);
}
h1, h2, h3, h4, h5, h6, p, span, label, li, div {
    color: var(--text-color);
}
[data-testid="stSidebar"] {
    background-color: var(--card-bg);
    border-right: 1px solid var(--border-color);
}
.card {
    background-color: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 1.1rem 1.3rem;
    margin-bottom: 1rem;
}
.section-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: var(--accent) !important;
    margin-bottom: 0.6rem;
    border-bottom: 2px solid var(--accent-soft);
    padding-bottom: 0.35rem;
}
.subtle {
    color: var(--sub-text) !important;
    font-size: 0.9rem;
}
.chip {
    display: inline-block;
    background-color: var(--chip-bg);
    color: var(--chip-text) !important;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 600;
    margin: 3px 5px 3px 0;
    border: 1px solid var(--border-color);
}
.badge-yes {
    background-color: var(--success-bg);
    color: var(--success-text) !important;
    padding: 3px 10px;
    border-radius: 8px;
    font-weight: 700;
    font-size: 0.85rem;
}
.badge-no {
    background-color: var(--danger-bg);
    color: var(--danger-text) !important;
    padding: 3px 10px;
    border-radius: 8px;
    font-weight: 700;
    font-size: 0.85rem;
}
.stDataFrame, .stTable {
    border-radius: 10px;
    overflow: hidden;
}
[data-testid="stMetricValue"] {
    color: var(--accent) !important;
}
.stTabs [data-baseweb="tab"] {
    color: var(--text-color);
    font-weight: 600;
}
hr {
    border-color: var(--border-color);
}
</style>
"""


def inject_theme(mode: str):
    import streamlit as st
    st.markdown(DARK_CSS if mode == "Dark" else LIGHT_CSS, unsafe_allow_html=True)
    st.markdown(BASE_CSS, unsafe_allow_html=True)
