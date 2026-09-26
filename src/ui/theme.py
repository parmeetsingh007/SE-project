"""Visual theme for the Streamlit UI: a fintech/security palette (deep navy +
a single accent), color-coded status/risk badges, and category icons.

Pure presentation — no agent or data-model logic lives here.
"""

from __future__ import annotations

CSS = """
<style>
:root {
    --bg: #0b1120;
    --bg-card: #141b2d;
    --border: #232d45;
    --text: #e6ebf5;
    --text-muted: #8b96ab;
    --accent: #4f8cff;
    --accent-hover: #6fa0ff;
}

.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background-color: var(--bg);
    color: var(--text);
}
[data-testid="stSidebar"] { background-color: var(--bg-card); }

h1, h2, h3, h4, p, label, span, div { color: var(--text); }
[data-testid="stCaptionContainer"], .stMarkdown small { color: var(--text-muted) !important; }

.app-header {
    padding: 1.25rem 0 0.5rem 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1.5rem;
}
.app-header h1 {
    font-size: 1.6rem;
    margin: 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.app-header p {
    color: var(--text-muted);
    margin: 0.25rem 0 0 0;
    font-size: 0.95rem;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: var(--bg-card);
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
}

.stButton>button {
    border-radius: 6px;
    border: 1px solid var(--border);
    background-color: var(--bg-card);
    color: var(--text);
}
.stButton>button:hover {
    border-color: var(--accent);
    color: var(--accent-hover);
}
.stButton>button[kind="primary"] {
    background-color: var(--accent);
    border-color: var(--accent);
    color: white;
}
.stButton>button[kind="primary"]:hover { background-color: var(--accent-hover); }

[data-testid="stMetric"] {
    background-color: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.75rem 1rem;
}

.badge {
    display: inline-block;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    margin-right: 0.35rem;
    white-space: nowrap;
}
.badge-approved { background: rgba(34,197,94,0.16); color: #4ade80; }
.badge-needs_revision { background: rgba(245,158,11,0.16); color: #fbbf24; }
.badge-rejected { background: rgba(239,68,68,0.16); color: #f87171; }
.badge-pending { background: rgba(100,116,139,0.20); color: #a3b0c2; }

.badge-risk-high { background: rgba(239,68,68,0.16); color: #f87171; }
.badge-risk-medium { background: rgba(245,158,11,0.16); color: #fbbf24; }
.badge-risk-low { background: rgba(34,197,94,0.16); color: #4ade80; }
.badge-risk-unscored { background: rgba(100,116,139,0.20); color: #a3b0c2; }

.badge-category {
    background: rgba(79,140,255,0.14);
    color: #9dbfff;
}

.req-statement { font-size: 1.02rem; font-weight: 500; margin: 0.5rem 0 0.35rem 0; }

.sdlc-card {
    background-color: var(--bg-card);
    border: 1px solid var(--border);
    border-left: 4px solid var(--accent);
    border-radius: 8px;
    padding: 0.9rem 1.1rem;
    margin-bottom: 0.75rem;
}
.sdlc-card h4 { margin: 0 0 0.35rem 0; }
.sdlc-card .confidence { color: var(--accent-hover); font-weight: 700; }
</style>
"""

CATEGORY_ICONS = {
    "functional": "⚙️",
    "security": "🔒",
    "compliance": "📋",
    "performance": "⚡",
    "usability": "🎯",
    "other": "🏷️",
}


def status_badge(status: str) -> str:
    return f'<span class="badge badge-{status}">{status.replace("_", " ")}</span>'


def risk_badge(risk: str) -> str:
    return f'<span class="badge badge-risk-{risk}">risk: {risk}</span>'


def category_badges(categories: list[str]) -> str:
    if not categories:
        return '<span class="badge badge-category">uncategorized</span>'
    return "".join(
        f'<span class="badge badge-category">{CATEGORY_ICONS.get(c, "🏷️")} {c}</span>'
        for c in categories
    )
