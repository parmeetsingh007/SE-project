"""Visual theme for the Streamlit UI: a warm, document-like palette — cream
background, a serif heading face, terracotta accent, earthy status/risk
colors — meant to read as approachable professional software, not a
corporate dashboard or a "hacker" security tool.

Pure presentation — no agent or data-model logic lives here.
"""

from __future__ import annotations

CSS = """
<style>
:root {
    --bg: #F7F1E7;
    --bg-card: #FFFDF9;
    --border: #E7DCC9;
    --text: #2E2A24;
    --text-muted: #8A8072;
    --accent: #BF5B3A;
    --accent-hover: #A84C2E;
    --accent-soft: rgba(191,91,58,0.12);
}

html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background-color: var(--bg) !important;
    color: var(--text);
    font-family: 'Inter', -apple-system, sans-serif;
}
[data-testid="stHeader"] { background-color: transparent !important; }
[data-testid="stSidebar"] { background-color: var(--bg-card); border-right: 1px solid var(--border); }

h1, h2, h3, h4 {
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 500;
    color: var(--text);
    letter-spacing: -0.01em;
}
p, label, span, div { color: var(--text); }
[data-testid="stCaptionContainer"], .stMarkdown small { color: var(--text-muted) !important; }
[data-testid="stExpander"] summary p { color: var(--text) !important; font-weight: 500; }

.app-header {
    padding: 1.5rem 0 1.1rem 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1.75rem;
}
.app-header h1 {
    font-size: 2rem;
    margin: 0;
    display: flex;
    align-items: center;
    gap: 0.6rem;
}
.app-header p {
    color: var(--text-muted);
    margin: 0.4rem 0 0 0;
    font-size: 1rem;
    font-family: 'Inter', sans-serif;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: var(--bg-card);
    border: 1px solid var(--border) !important;
    border-radius: 14px !important;
    box-shadow: 0 1px 3px rgba(46,42,36,0.06), 0 1px 2px rgba(46,42,36,0.04);
}

[data-testid="stMultiSelect"] [data-baseweb="select"] > div,
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stMultiSelect"] [role="group"][data-rac] {
    background-color: var(--bg-card) !important;
    border-color: var(--border) !important;
}
[data-testid="stMultiSelectTagsContainer"] span[data-tag] {
    background-color: var(--accent-soft) !important;
    color: var(--accent-hover) !important;
}
[data-testid="stMultiSelectTagsContainer"] span[data-tag] button svg {
    fill: var(--accent-hover) !important;
}
div[data-baseweb="popover"] li {
    background-color: var(--bg-card) !important;
    color: var(--text) !important;
}

[data-testid="stTextArea"] textarea, [data-testid="stFileUploaderDropzone"] {
    background-color: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    color: var(--text) !important;
    border-radius: 10px !important;
}

.stTabs [data-baseweb="tab-list"] { border-bottom: 1px solid var(--border); gap: 1.5rem; }
.stTabs [data-baseweb="tab"] { color: var(--text-muted); font-weight: 500; }
.stTabs [aria-selected="true"] { color: var(--accent) !important; }
.stTabs [data-baseweb="tab-highlight"] { background-color: var(--accent) !important; }

.stButton>button {
    border-radius: 8px;
    border: 1px solid var(--border);
    background-color: var(--bg-card);
    color: var(--text);
    font-weight: 500;
    transition: all 0.15s ease;
}
.stButton>button:hover {
    border-color: var(--accent);
    color: var(--accent-hover);
    background-color: var(--accent-soft);
}
.stButton>button[kind="primary"] {
    background-color: var(--accent);
    border-color: var(--accent);
    color: #FFFDF9;
}
.stButton>button[kind="primary"]:hover { background-color: var(--accent-hover); border-color: var(--accent-hover); }

[data-testid="stMetric"] {
    background-color: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 0.85rem 1.1rem;
}
[data-testid="stMetricLabel"] { color: var(--text-muted) !important; }

[data-testid="stAlert"] { border-radius: 10px; }

.badge {
    display: inline-block;
    padding: 0.2rem 0.7rem;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    margin-right: 0.4rem;
    white-space: nowrap;
    font-family: 'Inter', sans-serif;
}
.badge-approved { background: #E4EEE2; color: #3F6B4F; }
.badge-needs_revision { background: #F5E8D2; color: #A5732A; }
.badge-rejected { background: #F3E1DB; color: #A5442C; }
.badge-pending { background: #EEE9DF; color: #8A8072; }

.badge-risk-high { background: #F3E1DB; color: #A5442C; }
.badge-risk-medium { background: #F5E8D2; color: #A5732A; }
.badge-risk-low { background: #E4EEE2; color: #3F6B4F; }
.badge-risk-unscored { background: #EEE9DF; color: #8A8072; }

.badge-category { background: var(--accent-soft); color: var(--accent-hover); }
.badge-batch { background: #EEE9DF; color: #8A8072; font-weight: 500; }

.req-statement {
    font-size: 1.08rem;
    font-weight: 500;
    margin: 0.6rem 0 0.4rem 0;
    line-height: 1.45;
    font-family: 'Fraunces', Georgia, serif;
}

.sdlc-card {
    background-color: var(--bg-card);
    border: 1px solid var(--border);
    border-left: 4px solid var(--accent);
    border-radius: 10px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.8rem;
    box-shadow: 0 1px 2px rgba(46,42,36,0.05);
}
.sdlc-card h4 { margin: 0 0 0.4rem 0; font-family: 'Fraunces', Georgia, serif; }
.sdlc-card p { color: var(--text-muted); margin: 0; }
.sdlc-card .confidence { color: var(--accent); font-weight: 700; }
</style>
"""

def status_badge(status: str) -> str:
    return f'<span class="badge badge-{status}">{status.replace("_", " ")}</span>'


def risk_badge(risk: str) -> str:
    return f'<span class="badge badge-risk-{risk}">risk: {risk}</span>'


def batch_badge(label: str) -> str:
    return f'<span class="badge badge-batch">{label}</span>'


def category_badges(categories: list[str]) -> str:
    if not categories:
        return '<span class="badge badge-category">uncategorized</span>'
    return "".join(f'<span class="badge badge-category">{c}</span>' for c in categories)
