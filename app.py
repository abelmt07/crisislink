"""
app.py : CrisisLink Command Center (Streamlit front end)

Design read: investor-facing disaster-response operations console, dark radar
language with restrained neo-brutalist details (hard offset shadows on primary
actions, uppercase wide-tracked headings, monospace data). No official design
system fits this brief, so the look is native CSS layered over Streamlit.
Dials: DESIGN_VARIANCE 5, MOTION_INTENSITY 5, VISUAL_DENSITY 3.

This file only IMPORTS from the existing backend (db_sql, db_nosql, models,
utils). It never edits those files and contains no SQL.

Run:   streamlit run app.py
Needs: pip install streamlit
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from datetime import datetime
from decimal import Decimal
from html import escape
from urllib.parse import quote

import streamlit as st

import db_nosql
import db_sql
from models import Organization, Request, Supply
from utils import (
    new_event_id,
    setup_logging,
    validate_email,
    validate_enum,
    validate_phone,
    validate_positive_int,
)

# ---------------------------------------------------------------------------
# Page setup (must be the first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CrisisLink Command Center",
    page_icon=":material/radar:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RESOURCE_TYPES = ["FOOD", "MEDICINE", "WATER", "SHELTER", "CLOTHING", "EQUIPMENT", "OTHER"]
URGENCY_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
URGENCY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
ORG_TYPES = ["NGO", "GOVT", "VOLUNTEER", "HOSPITAL", "CORPORATE"]

# Navigation: key -> (label, material icon name)
PAGES = {
    "dashboard": ("Live Dashboard", "monitoring"),
    "add": ("Add Data", "add_circle"),
    "match": ("Run Auto-Match", "bolt"),
    "sql": ("SQL Reports", "database"),
    "mongo": ("MongoDB Logs", "data_object"),
    "tables": ("Browse Tables", "table_view"),
}

SQL_REPORTS = {
    "Match Report (JOIN)": (db_sql.get_all_matches, "Joins matches, requests, supplies and both organizations"),
    "Zone Summary (GROUP BY)": (db_sql.get_zone_summary, "Requested against confirmed quantity, grouped by zone"),
    "Unmet Requests (Sub-query)": (db_sql.get_unmet_requests, "Open requests with no confirmed match, most urgent first"),
}

MONGO_VIEWS = [
    "Field Reports by Zone (Aggregation)",
    "Critical Reports with Events (Lookup)",
    "Recent System Events",
]

# Browse Tables page: each entry uses ONLY a public function from the existing backend.
# No SQL is written in app.py and no private helpers are called.
BROWSE_SOURCES = {
    "requests (all columns)": db_sql.get_all_requests,
    "supplies (all columns)": db_sql.get_all_supplies,
    "matches (joined report)": db_sql.get_all_matches,
    "organizations (active, summary)": db_sql.get_all_organizations,
}
ROW_LIMITS = [50, 200, 1000]

ENTITY_COLORS = {
    "REQUEST": "#FF4B4B",
    "SUPPLY": "#66BB6A",
    "MATCH": "#3FE0D0",
    "ORG": "#9AAAB7",
}


# ---------------------------------------------------------------------------
# Background art (generated once): radar rings + faint topographic contours,
# and a fine grain layer. Both are decorative and sit behind all content.
# ---------------------------------------------------------------------------
def _radar_background() -> str:
    """SVG data URI: concentric range rings, tick ring and map-like contours."""
    w, h = 1900, 1200
    teal = "rgb(63,224,208)"
    slate = "rgb(130,170,200)"
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' "
           f"viewBox='0 0 {w} {h}' fill='none'>"]

    # Range rings, centred upper right
    cx, cy = 1420, 330
    for i, r in enumerate(range(120, 840, 120)):
        out.append(f"<circle cx='{cx}' cy='{cy}' r='{r}' stroke='{teal}' "
                   f"stroke-opacity='{max(0.05, 0.17 - i * 0.02):.3f}' stroke-width='1'/>")
    # Tick ring
    r_out = 840
    for deg in range(0, 360, 6):
        a = math.radians(deg)
        ln = 14 if deg % 30 == 0 else 6
        x1, y1 = cx + r_out * math.cos(a), cy + r_out * math.sin(a)
        x2, y2 = cx + (r_out - ln) * math.cos(a), cy + (r_out - ln) * math.sin(a)
        out.append(f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' "
                   f"stroke='{teal}' stroke-opacity='0.12' stroke-width='1'/>")

    # Topographic contours, lower left. Wobbly closed curves, deterministic.
    tx, ty = 330, 860
    for i in range(11):
        base = 70 + i * 48
        p1, p2, p3 = i * 0.7, i * 1.3 + 1.0, i * 0.4 + 2.2
        pts = []
        for k in range(121):
            t = 2 * math.pi * k / 120
            rr = base * (1 + 0.10 * math.sin(2 * t + p1) + 0.06 * math.sin(3 * t + p2)
                         + 0.035 * math.sin(5 * t + p3))
            pts.append(f"{tx + rr * 1.25 * math.cos(t):.1f},{ty + rr * 0.9 * math.sin(t):.1f}")
        out.append(f"<polyline points='{' '.join(pts)}' stroke='{slate}' "
                   f"stroke-opacity='{max(0.04, 0.12 - i * 0.007):.3f}' stroke-width='1'/>")

    out.append("</svg>")
    return "data:image/svg+xml," + quote("".join(out))


def _grain_background() -> str:
    """SVG data URI: monochrome fractal noise tile."""
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'>"
           "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' "
           "numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/>"
           "</filter><rect width='100%' height='100%' filter='url(#n)'/></svg>")
    return "data:image/svg+xml," + quote(svg)

# ---------------------------------------------------------------------------
# Global stylesheet
# Type system:  Archivo (display, expanded width) / Geist (body) / JetBrains Mono (data)
# Shape lock:   4px controls, 8px cards and dialogs, full pill for tags
# Layers:       0 background, 1 content, 5 grain; Streamlit owns modal layers
# Motion:       transform + opacity only; everything is disabled under reduced motion
# ---------------------------------------------------------------------------
CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,100..900&family=Geist:wght@300..700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg: #0A0F14;
  --s1: #0F161E;
  --s2: #141E28;
  --s3: #1A2733;
  --line: #22323F;
  --line-strong: #2E4454;
  --ink: #05080B;
  --t1: #E8EEF2;
  --t2: #9AAAB7;
  --t3: #7B8D9C;
  --accent: #3FE0D0;
  --accent-dim: #1F7F78;
  --accent-deep: #0F4A46;
  --accent-soft: rgba(63,224,208,.10);
  --critical: #FF4B4B;
  --high: #FFA726;
  --medium: #FFEB3B;
  --low: #66BB6A;
  --f-display: 'Archivo', 'Geist', system-ui, sans-serif;
  --f-body: 'Geist', system-ui, -apple-system, 'Segoe UI', sans-serif;
  --f-mono: 'JetBrains Mono', ui-monospace, 'Cascadia Mono', Consolas, monospace;
  --ease: cubic-bezier(.16, 1, .3, 1);
  --shadow-1: 0 14px 34px -18px rgba(2, 8, 14, .9);
}

@property --n { syntax: '<integer>'; initial-value: 0; inherits: false; }

/* ---------- Base ---------- */
html, body { background: var(--bg); }
.stApp *:not([data-testid="stIconMaterial"]):not(.ms) { font-family: var(--f-body); }
.stApp { color: var(--t1); background-color: var(--bg) !important; background-image: none !important; isolation: isolate; }
.stApp::before {
  content: ""; position: fixed; inset: 0; z-index: -1; pointer-events: none;
  background-image:
    url("__RADAR__"),
    radial-gradient(60% 45% at 6% 0%, rgba(63,224,208,.075), transparent 70%),
    radial-gradient(45% 40% at 100% 100%, rgba(255,75,75,.04), transparent 70%);
  background-repeat: no-repeat;
  background-position: right -140px top -80px, 0 0, 0 0;
}
.stApp::after {
  content: ""; position: fixed; inset: 0; z-index: 5; pointer-events: none;
  background-image: url("__GRAIN__"); opacity: .05;
}
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stHeader"] { background: transparent !important; }
[data-testid="stMainBlockContainer"], .block-container {
  max-width: 1360px; padding: 32px 40px 56px !important;
}
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] { gap: 1.75rem; }

/* Hide default Streamlit chrome */
#MainMenu, footer, [data-testid="stMainMenu"], [data-testid="stDecoration"],
[data-testid="stToolbar"], [data-testid="stAppDeployButton"], [data-testid="stStatusWidget"] { display: none !important; }
[data-testid="stHeader"] { height: 0; min-height: 0; }

/* Icons rendered in custom HTML */
.ms {
  font-family: 'Material Symbols Rounded' !important; font-weight: 400; font-style: normal;
  font-size: 20px; line-height: 1; letter-spacing: normal; text-transform: none;
  display: inline-block; white-space: nowrap; direction: ltr;
  font-feature-settings: 'liga'; -webkit-font-feature-settings: 'liga';
  font-variation-settings: 'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 24;
  user-select: none;
}

/* ---------- Typography ---------- */
.disp { font-family: var(--f-display) !important; font-stretch: 112%; text-transform: uppercase; }
.mono { font-family: var(--f-mono) !important; font-variant-numeric: tabular-nums; }
.lbl {
  font-size: 11px; line-height: 16px; font-weight: 600; letter-spacing: .14em;
  text-transform: uppercase; color: var(--t2);
}
.page-head { display: flex; flex-direction: column; gap: 8px; }
.crumb { font-size: 11px; letter-spacing: .16em; font-weight: 600; text-transform: uppercase; color: var(--t3); }
.h1 { font-size: 32px; line-height: 38px; font-weight: 700; letter-spacing: .1em; color: var(--t1); margin: 0; }
.h1-sub { font-size: 15px; line-height: 24px; color: var(--t2); max-width: 62ch; margin: 0; }
.h2 { font-size: 18px; line-height: 26px; font-weight: 700; letter-spacing: .1em; color: var(--t1); margin: 0; }
.h3 { font-size: 17px; line-height: 24px; font-weight: 600; color: var(--t1); }
.small { font-size: 13px; line-height: 20px; color: var(--t2); }
.muted { color: var(--t3); }

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] {
  background: var(--s1) !important; border-right: 1px solid var(--line);
  width: 264px !important; min-width: 264px !important; max-width: 264px !important;
}
[data-testid="stSidebarHeader"], [data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"],
[data-testid="stSidebarResizeHandle"] { display: none !important; }
[data-testid="stSidebarContent"] { padding: 0 !important; }
[data-testid="stSidebarUserContent"] { padding: 28px 16px 20px !important; }
[data-testid="stSidebarUserContent"] > [data-testid="stVerticalBlock"] { min-height: calc(100dvh - 48px); gap: .5rem; }
.st-key-side_bottom { margin-top: auto; }

.brand { display: flex; align-items: center; gap: 12px; padding: 0 6px 22px; }
.brand-mark {
  position: relative; width: 38px; height: 38px; flex: none; border-radius: 50%; border: 1.5px solid rgba(63,224,208,.85);
  background: radial-gradient(circle, transparent 0 5px, rgba(63,224,208,.32) 5px 6px, transparent 6px 11px, rgba(63,224,208,.45) 11px 12px, transparent 12px);
}
.bm-sweep { position: absolute; inset: 0; border-radius: 50%; animation: spin 6s linear infinite;
  background: conic-gradient(from 0deg, rgba(63,224,208,0) 0deg, rgba(63,224,208,.5) 62deg, rgba(63,224,208,0) 64deg, rgba(63,224,208,0) 360deg); }
.bm-sweep::after { content: ""; position: absolute; left: 50%; top: 2px; width: 1.5px; height: 17px; margin-left: -.75px; background: var(--accent); border-radius: 1px; }
.bm-blip { position: absolute; left: 25px; top: 8px; width: 4px; height: 4px; border-radius: 50%; background: var(--critical); }
.brand-name { font-size: 17px; font-weight: 800; letter-spacing: .16em; color: var(--t1); line-height: 1.1; }
.brand-sub { font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: var(--t3); margin-top: 4px; line-height: 1.3; }

@keyframes spin { to { transform: rotate(360deg); } }

/* Nav: radio restyled as a menu (Streamlit 1.5x/1.6x radio markup: stRadioGroup > stRadioOption) */
.st-key-nav [data-testid="stWidgetLabel"] { display: none !important; }
.st-key-nav [data-testid="stRadioGroup"] { gap: 4px; }
.st-key-nav [data-testid="stRadioGroup"] > div { width: 100%; }
.st-key-nav [data-testid="stRadioOption"] {
  position: relative; padding: 12px 14px !important; border-radius: 4px; border: 1px solid transparent;
  transition: background-color .2s var(--ease), border-color .2s var(--ease); cursor: pointer; width: 100%;
  margin: 0 !important; display: flex; align-items: center;
}
.st-key-nav [data-testid="stRadioOption"] > div > div:first-child:not([data-testid]) { display: none !important; }
.st-key-nav [data-testid="stRadioOption"] p { font-size: 14px; font-weight: 500; color: var(--t2); letter-spacing: .01em; display: flex; align-items: center; gap: 12px; margin: 0; }
.st-key-nav [data-testid="stRadioOption"]:hover { background: rgba(63,224,208,.05); }
.st-key-nav [data-testid="stRadioOption"]:hover p { color: var(--t1); }
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] { background: var(--accent-soft); border-color: rgba(63,224,208,.28); }
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] p { color: var(--t1); font-weight: 600; }
.st-key-nav [data-testid="stRadioOption"][data-selected="true"]::before {
  content: ""; position: absolute; left: -1px; top: 8px; bottom: 8px; width: 3px; border-radius: 0 3px 3px 0;
  background: var(--accent); box-shadow: 0 0 14px rgba(63,224,208,.55);
}
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] [data-testid="stIconMaterial"],
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] p span[role="img"] { color: var(--accent); }
.st-key-nav p span[role="img"] { font-size: 21px; color: var(--t3); }

/* Sidebar system status */
.sys { border-top: 1px solid var(--line); padding: 16px 6px 6px; display: flex; flex-direction: column; gap: 10px; }
.sys-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.sys-name { display: flex; align-items: center; gap: 9px; font-size: 11px; letter-spacing: .14em; text-transform: uppercase; font-weight: 600; color: var(--t2); }
.sys-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--low); box-shadow: 0 0 8px rgba(102,187,106,.7); }
.sys-dot.down { background: var(--critical); box-shadow: 0 0 8px rgba(255,75,75,.7); }
.sys-ms { font-size: 12px; color: var(--t3); }

/* Rail (collapsed sidebar) toggle button */
.st-key-rail_toggle button {
  width: 100%; justify-content: center; background: transparent !important; border: 1px solid var(--line) !important;
  color: var(--t2) !important; min-height: 36px; border-radius: 4px !important;
}
.st-key-rail_toggle button:hover { background: var(--s3) !important; color: var(--t1) !important; }

/* ---------- Buttons ---------- */
button[data-testid^="stBaseButton"] {
  font-family: var(--f-display) !important; font-stretch: 108%; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; font-size: 13px; border-radius: 4px !important; min-height: 44px; padding: 0 20px;
  transition: transform .15s var(--ease), box-shadow .15s var(--ease), background-color .2s var(--ease), border-color .2s var(--ease);
}
button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-primaryFormSubmit"] {
  background: var(--accent) !important; color: var(--ink) !important; border: 1px solid var(--accent) !important;
  box-shadow: 4px 4px 0 0 var(--accent-deep);
}
button[data-testid="stBaseButton-primary"] p, button[data-testid="stBaseButton-primaryFormSubmit"] p { color: var(--ink) !important; }
button[data-testid="stBaseButton-primary"]:hover, button[data-testid="stBaseButton-primaryFormSubmit"]:hover {
  transform: translate(-1px, -1px); box-shadow: 5px 5px 0 0 var(--accent-deep);
}
button[data-testid="stBaseButton-primary"]:active, button[data-testid="stBaseButton-primaryFormSubmit"]:active {
  transform: translate(3px, 3px); box-shadow: 0 0 0 0 var(--accent-deep);
}
button[data-testid="stBaseButton-secondary"], button[data-testid="stBaseButton-secondaryFormSubmit"] {
  background: transparent !important; color: var(--accent) !important; border: 1px solid rgba(63,224,208,.55) !important;
}
button[data-testid="stBaseButton-secondary"] p, button[data-testid="stBaseButton-secondaryFormSubmit"] p { color: var(--accent) !important; }
button[data-testid="stBaseButton-secondary"]:hover, button[data-testid="stBaseButton-secondaryFormSubmit"]:hover {
  background: rgba(63,224,208,.09) !important; border-color: var(--accent) !important;
}
button[data-testid="stBaseButton-secondary"]:active, button[data-testid="stBaseButton-secondaryFormSubmit"]:active { transform: translateY(1px); }
button[data-testid="stBaseButton-tertiary"] {
  background: transparent !important; color: var(--t2) !important; border: 1px solid transparent !important; font-weight: 600;
}
button[data-testid="stBaseButton-tertiary"]:hover { background: var(--s3) !important; color: var(--t1) !important; }
button[data-testid^="stBaseButton"]:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
button[data-testid^="stBaseButton"] [data-testid="stIconMaterial"] { font-size: 18px; }

/* ---------- Inputs (Streamlit 1.6x markup) ---------- */
[data-testid="stWidgetLabel"] p, label[data-testid="stWidgetLabel"] {
  font-size: 11px !important; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: var(--t2) !important;
}
[data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"], [data-testid="stTextAreaRootElement"],
[data-testid="stSelectbox"] [role="group"] {
  background-color: var(--s3) !important; border: 1px solid var(--line-strong) !important; border-radius: 4px !important; min-height: 44px;
  transition: border-color .2s var(--ease), box-shadow .2s var(--ease);
}
[data-testid="stTextInputField"], [data-testid="stNumberInputField"], [data-testid="stTextAreaRootElement"] textarea,
[data-testid="stSelectbox"] input, [data-testid="stSelectbox"] [role="group"] { color: var(--t1) !important; font-size: 15px; }
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within,
[data-testid="stTextAreaRootElement"]:focus-within, [data-testid="stSelectbox"] [role="group"]:focus-within {
  border-color: var(--accent) !important; box-shadow: 0 0 0 3px rgba(63,224,208,.18) !important;
}
input::placeholder, textarea::placeholder { color: var(--t3) !important; opacity: 1; }
[data-testid="stNumberInputStepDown"], [data-testid="stNumberInputStepUp"] { display: none !important; }
[data-testid="stForm"] { border: 0 !important; padding: 0 !important; background: transparent !important; }
ul[role="listbox"], [data-testid="stSelectboxVirtualDropdown"] { background: var(--s2) !important; border: 1px solid var(--line-strong); border-radius: 4px; }
[role="option"] { color: var(--t1); }
[role="option"][aria-selected="true"], [role="option"]:hover, [role="option"][data-focused="true"] { background: var(--accent-soft) !important; }
[data-baseweb="popover"] > div { background: var(--s2) !important; border-radius: 4px !important; }

/* Segmented urgency control: role=radio buttons, aria-checked marks the selection */
[data-testid="stButtonGroup"] [role="radiogroup"] { display: flex; gap: 0; }
[data-testid="stButtonGroup"] button[role="radio"] {
  min-height: 44px; border-radius: 0 !important; border: 1px solid var(--line-strong) !important; margin-left: -1px;
  background: var(--s3) !important; color: var(--t2) !important; padding: 0 18px; box-shadow: none; cursor: pointer;
  font-family: var(--f-mono) !important; font-size: 11px; letter-spacing: .1em; text-transform: uppercase;
  transition: background-color .2s var(--ease), color .2s var(--ease);
}
[data-testid="stButtonGroup"] button[role="radio"] * { font-family: var(--f-mono) !important; color: inherit !important; font-size: 11px !important; letter-spacing: .1em; text-transform: uppercase; }
[data-testid="stButtonGroup"] button[role="radio"]:first-child { border-radius: 4px 0 0 4px !important; margin-left: 0; }
[data-testid="stButtonGroup"] button[role="radio"]:last-child { border-radius: 0 4px 4px 0 !important; }
[data-testid="stButtonGroup"] button[role="radio"]:hover { background: var(--s1) !important; color: var(--t1) !important; }
[data-testid="stButtonGroup"] button[role="radio"][aria-checked="true"] { position: relative; z-index: 1; font-weight: 600; }
[data-testid="stButtonGroup"] button[role="radio"]:nth-child(1)[aria-checked="true"] { background: rgba(102,187,106,.16) !important; color: var(--low) !important; border-color: rgba(102,187,106,.65) !important; }
[data-testid="stButtonGroup"] button[role="radio"]:nth-child(2)[aria-checked="true"] { background: rgba(255,235,59,.12) !important; color: var(--medium) !important; border-color: rgba(255,235,59,.55) !important; }
[data-testid="stButtonGroup"] button[role="radio"]:nth-child(3)[aria-checked="true"] { background: rgba(255,167,38,.15) !important; color: var(--high) !important; border-color: rgba(255,167,38,.65) !important; }
[data-testid="stButtonGroup"] button[role="radio"]:nth-child(4)[aria-checked="true"] { background: rgba(255,75,75,.16) !important; color: var(--critical) !important; border-color: rgba(255,75,75,.7) !important; }

/* ---------- Surfaces ---------- */
.card {
  background: var(--s2); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow-1);
  transition: transform .25s var(--ease), border-color .25s var(--ease);
}
.card:hover { transform: translateY(-2px); border-color: rgba(63,224,208,.38); }

/* KPI row */
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 20px; }
.kpi { padding: 22px 24px 20px; min-height: 148px; display: flex; flex-direction: column; justify-content: space-between; position: relative; }
.kpi-top { display: flex; justify-content: space-between; align-items: center; color: var(--t3); }
.kpi-val { font-family: var(--f-display) !important; font-stretch: 108%; font-size: 46px; line-height: 52px; font-weight: 800; letter-spacing: .02em; color: var(--t1); font-variant-numeric: tabular-nums; margin-top: 14px; }
.kpi-val .na { font-size: 26px; letter-spacing: .08em; color: var(--t3); }
.kpi-cap { font-size: 13px; color: var(--t3); margin-top: 6px; }
.kpi.crit { border-color: rgba(255,75,75,.4); }
.kpi.crit .kpi-val { color: var(--critical); }
.kpi.crit::after {
  content: ""; position: absolute; inset: -1px; border-radius: 8px; border: 1px solid var(--critical); pointer-events: none;
  animation: ring 2.4s ease-out infinite;
}
@keyframes ring { 0% { opacity: .55; transform: scale(1); } 100% { opacity: 0; transform: scale(1.03); } }

.cnt { --n: 0; counter-reset: cnt var(--n); }
.cnt::after { content: counter(cnt); }
@media (prefers-reduced-motion: no-preference) {
  .cnt { animation: cnt-up .9s var(--ease) both; }
}
@keyframes cnt-up { from { --n: 0; } to { --n: var(--t); } }
@media (prefers-reduced-motion: reduce) { .cnt { --n: var(--t); } }


.card.static:hover { transform: none; border-color: var(--line); }
.panel { padding: 6px 22px; }
.st-key-sync_box { align-items: flex-end; gap: 2px; }
.st-key-sync_box [data-testid="stElementContainer"] { width: auto; }

/* Section heads */
.sec { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin: 4px 0 -4px; }

/* Zone cards */
.zones { display: grid; grid-template-columns: repeat(auto-fill, minmax(206px, 1fr)); gap: 20px; }
.zone { padding: 22px 24px; display: flex; flex-direction: column; gap: 20px; min-height: 176px; }
.zone-top { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.zone-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.zone-stat .lbl { font-size: 10px; letter-spacing: .1em; }
.zone-stat .v { font-size: 22px; line-height: 28px; color: var(--t1); font-weight: 500; }
.fill { display: flex; flex-direction: column; gap: 8px; margin-top: auto; }
.fill-row { display: flex; align-items: center; gap: 12px; }
.fill-bar { height: 3px; border-radius: 2px; flex: none; }
.fill-num { font-size: 13px; color: var(--t1); }

/* Pills */
.pill {
  position: relative; display: inline-flex; align-items: center; height: 22px; padding: 0 10px; border-radius: 999px;
  font-family: var(--f-mono) !important; font-size: 10px; font-weight: 500; letter-spacing: .12em; text-transform: uppercase;
  border: 1px solid; white-space: nowrap; vertical-align: middle;
}
.pill-CRITICAL { color: var(--critical); background: rgba(255,75,75,.12); border-color: rgba(255,75,75,.5); box-shadow: 0 0 14px -2px rgba(255,75,75,.45); }
.pill-HIGH { color: var(--high); background: rgba(255,167,38,.12); border-color: rgba(255,167,38,.5); box-shadow: 0 0 10px -3px rgba(255,167,38,.4); }
.pill-MEDIUM { color: var(--medium); background: rgba(255,235,59,.10); border-color: rgba(255,235,59,.42); }
.pill-LOW { color: var(--low); background: rgba(102,187,106,.12); border-color: rgba(102,187,106,.42); }
.pill-CRITICAL::after { content: ""; position: absolute; inset: -1px; border-radius: 999px; border: 1px solid var(--critical); pointer-events: none; animation: ring 1.8s ease-out infinite; }
.chip { display: inline-flex; align-items: center; height: 22px; padding: 0 9px; border-radius: 4px; border: 1px solid var(--line-strong); font-family: var(--f-mono) !important; font-size: 10.5px; letter-spacing: .08em; text-transform: uppercase; color: var(--t2); white-space: nowrap; }
.chip.ok { color: var(--low); border-color: rgba(102,187,106,.45); }
.chip.warn { color: var(--high); border-color: rgba(255,167,38,.45); }
.chip.bad { color: var(--critical); border-color: rgba(255,75,75,.45); }
.chip.info { color: var(--accent); border-color: rgba(63,224,208,.4); }
.tag { display: inline-flex; align-items: center; height: 22px; padding: 0 9px; border-radius: 4px; background: var(--s3); font-family: var(--f-mono) !important; font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase; color: var(--t2); }

/* Event timeline */
.tl { list-style: none !important; margin: 0 !important; padding: 0 !important; position: relative; display: flex; flex-direction: column; }
.tl::before { content: ""; position: absolute; left: 5px; top: 18px; bottom: 18px; width: 1px; background: var(--line-strong); }
.tl li { position: relative; display: grid; grid-template-columns: 1fr; gap: 3px; padding: 12px 0 12px 28px; margin: 0; }
.tl.wide li { grid-template-columns: 1fr auto; gap: 4px 16px; }
.tl-node { position: absolute; left: 0; top: 18px; width: 11px; height: 11px; border-radius: 50%; background: var(--bg); border: 2px solid var(--c, var(--t2)); }
.tl-title { font-size: 15px; font-weight: 600; color: var(--t1); }
.tl-sub { font-size: 13px; color: var(--t2); grid-column: 1; }
.tl-time { font-size: 12px; color: var(--t3); white-space: nowrap; margin-top: 2px; }
.tl.wide .tl-time { grid-row: 1; grid-column: 2; text-align: right; padding-top: 3px; margin: 0; }
.tl li.fresh .tl-node::after { content: ""; position: absolute; inset: -5px; border-radius: 50%; border: 1px solid var(--c); animation: blip 1.2s ease-out 1 both; }
@keyframes blip { 0% { opacity: .9; transform: scale(.6); } 100% { opacity: 0; transform: scale(1.8); } }

/* Queue rows */
.queue { display: flex; flex-direction: column; gap: 10px; }
.q { padding: 14px 16px; display: grid; grid-template-columns: 1fr auto; gap: 6px 12px; align-items: center; }
.q-title { font-size: 15px; font-weight: 600; color: var(--t1); }
.q-sub { font-size: 13px; color: var(--t2); grid-column: 1; }
.q .pill { grid-row: 1 / span 2; grid-column: 2; }

/* Tables */
.tbl-meta { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; font-size: 12px; color: var(--t3); }
.tbl-meta .sep { width: 1px; height: 14px; background: var(--line-strong); }
.tbl-wrap { max-height: 620px; overflow: auto; background: var(--s2); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow-1); }
.tbl { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 14px; }
.tbl th {
  position: sticky; top: 0; z-index: 1; background: var(--s3); text-align: left; padding: 14px 18px; white-space: nowrap;
  font-size: 11px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: var(--t2); border-bottom: 1px solid var(--line-strong);
}
.tbl td { padding: 15px 18px; color: var(--t1); white-space: nowrap; }
.tbl tr:nth-child(even) td { background: rgba(255,255,255,.018); }
.tbl tbody tr:hover td { background: rgba(63,224,208,.06); }
.tbl tbody tr:hover td:first-child { box-shadow: inset 2px 0 0 var(--accent); }
.tbl .num { text-align: right; font-family: var(--f-mono) !important; font-variant-numeric: tabular-nums; }
.tbl th.num { text-align: right; }
.tbl .idc { font-family: var(--f-mono) !important; color: var(--t3); }
.tbl .wrap { white-space: normal; min-width: 240px; color: var(--t2); }
.score { display: inline-flex; align-items: center; gap: 10px; justify-content: flex-end; }
.score i { display: block; height: 3px; border-radius: 2px; background: var(--accent); }

/* Style-only containers should take no space */
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style) { display: none; }

/* Invalid inputs: any field directly above a rendered field error turns red */
[data-testid="stElementContainer"]:has(+ [data-testid="stElementContainer"] .field-error)
  :is([data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"], [data-testid="stTextAreaRootElement"], [data-testid="stSelectbox"] [role="group"]) { border-color: #FF4B4B !important; }
[data-testid="stElementContainer"]:has(+ [data-testid="stElementContainer"] .field-error) [data-testid="stButtonGroup"] button[role="radio"] { border-color: rgba(255,75,75,.7) !important; }

/* Banners and field errors */
.banner { display: flex; gap: 12px; align-items: flex-start; padding: 12px 16px; border-radius: 4px; border-left: 3px solid var(--c); background: var(--bg-tint); font-size: 14px; color: var(--t1); line-height: 22px; }
.banner .ms { color: var(--c); font-size: 20px; margin-top: 1px; }
.banner.ok { --c: var(--low); --bg-tint: rgba(102,187,106,.10); }
.banner.err { --c: var(--critical); --bg-tint: rgba(255,75,75,.10); }
.banner.info { --c: var(--accent); --bg-tint: rgba(63,224,208,.08); }
.banner.warn { --c: var(--high); --bg-tint: rgba(255,167,38,.10); }
.field-error { display: flex; align-items: center; gap: 6px; margin-top: -6px; font-size: 13px; color: #FF7B7B; }
.field-error .ms { font-size: 16px; }

.empty { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 44px 24px; text-align: center; background: var(--s2); border: 1px dashed var(--line-strong); border-radius: 8px; }
.empty .ms { font-size: 34px; color: var(--t3); }
.empty p { margin: 0; color: var(--t2); max-width: 46ch; font-size: 15px; line-height: 24px; }

/* Add data tiles */
.st-key-tile_org, .st-key-tile_req, .st-key-tile_sup {
  background: var(--s2); border: 1px solid var(--line); border-radius: 8px; padding: 26px 26px 24px; box-shadow: var(--shadow-1);
  transition: transform .25s var(--ease), border-color .25s var(--ease);
}
.st-key-tile_org:hover, .st-key-tile_req:hover, .st-key-tile_sup:hover { transform: translateY(-2px); border-color: rgba(63,224,208,.4); }
.st-key-tile_org, .st-key-tile_req, .st-key-tile_sup { min-height: 296px; }
.st-key-tile_org > [data-testid="stElementContainer"]:last-child,
.st-key-tile_req > [data-testid="stElementContainer"]:last-child,
.st-key-tile_sup > [data-testid="stElementContainer"]:last-child { margin-top: auto; }
.tile-icon { width: 44px; height: 44px; display: grid; place-items: center; border-radius: 4px; background: var(--accent-soft); border: 1px solid rgba(63,224,208,.3); color: var(--accent); margin-bottom: 18px; }
.tile-count { font-size: 12px; color: var(--t3); margin-top: 10px; }

/* Auto-match hero */
.st-key-hero {
  position: relative; overflow: hidden; min-height: 440px; border: 1px solid var(--line); border-radius: 8px;
  background: radial-gradient(60% 70% at 50% 50%, rgba(63,224,208,.07), transparent 70%), var(--s2);
  box-shadow: var(--shadow-1); display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 24px;
  --sweep: 6s;
}
.st-key-hero > * { position: relative; z-index: 1; width: auto; }
.st-key-hero::before {
  content: ""; position: absolute; left: 50%; top: 50%; width: 600px; height: 600px; margin: -300px 0 0 -300px; border-radius: 50%;
  background:
    conic-gradient(from 0deg, rgba(63,224,208,0) 0deg, rgba(63,224,208,.30) 58deg, rgba(63,224,208,0) 60deg, rgba(63,224,208,0) 360deg),
    repeating-radial-gradient(circle, transparent 0 74px, rgba(63,224,208,.13) 74px 75px);
  animation: spin var(--sweep) linear infinite; pointer-events: none;
}
.st-key-hero::after { content: ""; position: absolute; inset: 0; background: radial-gradient(circle at 50% 50%, transparent 38%, var(--s2) 78%); pointer-events: none; }
.hero-copy { text-align: center; display: flex; flex-direction: column; gap: 8px; align-items: center; margin-bottom: 18px; }
.hero-copy .h2 { font-size: 22px; }
.hero-copy p { margin: 0; color: var(--t2); font-size: 14px; line-height: 22px; max-width: 60ch; }
.st-key-hero button[data-testid="stBaseButton-primary"] { min-height: 52px; padding: 0 34px; font-size: 14px; }

.result { display: grid; grid-template-columns: auto 1fr; gap: 6px 34px; align-items: center; padding: 28px 32px; border: 1px solid rgba(63,224,208,.35); border-radius: 8px; background: linear-gradient(135deg, rgba(63,224,208,.09), rgba(20,30,40,.9) 60%); box-shadow: var(--shadow-1); }
.result-num { grid-row: 1 / span 3; font-family: var(--f-display) !important; font-stretch: 112%; font-size: 76px; line-height: 80px; font-weight: 800; color: var(--accent); font-variant-numeric: tabular-nums; }
.result-t { font-size: 18px; font-weight: 600; color: var(--t1); }
.result-s { font-size: 14px; color: var(--t2); }
.result-m { font-size: 12px; color: var(--t3); }

/* JSON viewer */
.json { background: #070B10; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.json-bar { display: flex; justify-content: space-between; align-items: center; padding: 10px 16px; border-bottom: 1px solid var(--line); background: var(--s1); }
.json pre { margin: 0; padding: 18px 20px; max-height: 560px; overflow: auto; font-family: var(--f-mono) !important; font-size: 13px; line-height: 22px; color: rgba(232,238,242,.88); }
.json pre span, .json pre code { font-family: var(--f-mono) !important; }
.j-k { color: var(--accent); } .j-s { color: rgba(232,238,242,.88); } .j-n { color: var(--high); } .j-b { color: #B794F6; } .j-p { color: var(--t3); }
.ln { display: inline-block; width: 34px; color: var(--t3); user-select: none; opacity: .7; }

/* Report list (Mongo) */
.st-key-reports [data-testid="stVerticalBlock"] { gap: 12px; }
.rep { padding: 4px 2px 2px; display: flex; flex-direction: column; gap: 8px; }
.rep-top { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.rep-desc { font-size: 14px; line-height: 22px; color: var(--t2); }
.rep-meta { font-size: 12px; color: var(--t3); }
[class*="st-key-rep_"] { background: var(--s2); border: 1px solid var(--line); border-radius: 8px; padding: 18px 18px 14px; transition: border-color .25s var(--ease); }
[class*="st-key-rep_"]:has(.on) { border-color: rgba(63,224,208,.6); background: linear-gradient(135deg, rgba(63,224,208,.07), var(--s2)); }

/* ---------- Native widgets restyled ---------- */
[data-testid="stToast"], [data-testid="stToastContainer"] > div {
  background: var(--s2) !important; border: 1px solid var(--line-strong) !important; border-left: 3px solid var(--accent) !important;
  border-radius: 8px !important; box-shadow: var(--shadow-1) !important; color: var(--t1) !important; width: 340px;
}
[data-testid="stToastContainer"] { top: auto !important; right: 24px !important; bottom: 24px !important; left: auto !important; }
[data-testid="stToastContainer"] ol { justify-content: flex-end; }
[data-testid="stExpander"] { border: 0 !important; background: transparent; }
[data-testid="stExpander"] details { border: 1px solid var(--line) !important; border-radius: 8px !important; background: var(--s2); }
[data-testid="stExpander"] summary { color: var(--t2); font-size: 13px; letter-spacing: .1em; text-transform: uppercase; font-weight: 600; }
[data-testid="stSpinner"] p, [data-testid="stSpinner"] { color: var(--t2); }
[data-testid="stAlert"] { border-radius: 4px; }

/* Dialog (Streamlit 1.6x: stDialog overlay > card div > section[role=dialog]) */
[data-testid="stDialog"] { background: rgba(5,8,11,.80) !important; }
[data-testid="stDialog"] > div {
  background: var(--s2) !important; border: 1px solid var(--line-strong) !important; border-radius: 8px !important;
  width: 680px !important; max-width: calc(100vw - 32px) !important;
  box-shadow: 8px 8px 0 0 rgba(63,224,208,.10), 0 30px 60px -20px rgba(0,0,0,.8) !important;
}
[data-testid="stDialog"] section[role="dialog"] { padding: 8px 12px 12px; }
[data-testid="stDialog"] h2 { font-family: var(--f-display) !important; font-stretch: 110%; text-transform: uppercase; letter-spacing: .1em; font-size: 20px; font-weight: 700; color: var(--t1); }
[data-testid="stDialog"] h2 * { font-family: var(--f-display) !important; }

.footer { margin-top: 28px; padding: 18px 0 0; text-align: center; border-top: 1px solid var(--line); font-size: 11px; letter-spacing: .16em; text-transform: uppercase; color: var(--t3); }

/* Live sync indicator */
.sync { display: inline-flex; align-items: center; gap: 10px; font-size: 12px; color: var(--t3); }
.sync b { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); animation: ping 2s ease-in-out infinite; }
@keyframes ping { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }

/* ---------- Reduced motion ---------- */
@media (prefers-reduced-motion: reduce) {
  .bm-sweep, .st-key-hero::before, .sync b, .pill-CRITICAL::after, .kpi.crit::after, .tl li.fresh .tl-node::after { animation: none !important; }
  .card, .st-key-tile_org, .st-key-tile_req, .st-key-tile_sup { transition: none; }
}
@media (max-width: 900px) {
  [data-testid="stMainBlockContainer"], .block-container { padding: 24px 18px 40px !important; }
  .h1 { font-size: 24px; line-height: 30px; }
  .kpi-val { font-size: 38px; }
  [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] { display: flex !important; }
}
"""

# Extra rules applied only while the sidebar is collapsed to a rail.
RAIL_CSS = r"""
section[data-testid="stSidebar"] { width: 76px !important; min-width: 76px !important; max-width: 76px !important; }
[data-testid="stSidebarUserContent"] { padding: 28px 10px 20px !important; }
.brand { justify-content: center; padding: 0 0 22px; }
.brand-text, .sys-name span.t, .sys-ms { display: none; }
.sys { align-items: center; padding: 14px 0 6px; }
.sys-row { justify-content: center; }
.st-key-nav [data-testid="stRadioOption"] { justify-content: center; padding: 12px 0 !important; }
.st-key-nav [data-testid="stRadioOption"] p { font-size: 0 !important; gap: 0; }
.st-key-nav [data-testid="stRadioOption"] p span[role="img"] { font-size: 22px !important; }
.st-key-rail_toggle p { display: none; }
"""

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def _json_default(obj):
    """Make Mongo/SQL values (datetime, ObjectId, Decimal) JSON safe."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


def fmt_dt(value, with_seconds: bool = False) -> str:
    """Short human date, e.g. '18 Oct, 14:02'."""
    if isinstance(value, datetime):
        return value.strftime("%d %b, %H:%M:%S" if with_seconds else "%d %b, %H:%M")
    return str(value) if value is not None else "n/a"


def _is_num(v) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def fmt_num(v) -> str:
    """Thousands-separated number; trims pointless decimals."""
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return f"{v:,}"


def icon(name: str, size: int | None = None) -> str:
    """Material Symbols glyph for custom HTML (same family Streamlit ships)."""
    style = f' style="font-size:{size}px"' if size else ""
    return f'<span class="ms" aria-hidden="true"{style}>{name}</span>'


def pill(level) -> str:
    """Urgency tag. CRITICAL pulses, HIGH glows, MEDIUM and LOW stay calm."""
    lvl = str(level).upper()
    if lvl not in URGENCY_RANK:
        return f'<span class="chip">{escape(str(level))}</span>'
    return f'<span class="pill pill-{lvl}">{lvl}</span>'


def banner(kind: str, text: str) -> str:
    """Inline message. kind: ok | err | info | warn."""
    glyph = {"ok": "check_circle", "err": "error", "info": "info", "warn": "warning"}[kind]
    return f'<div class="banner {kind}">{icon(glyph)}<div>{text}</div></div>'


def page_header(crumb: str, title: str, sub: str) -> str:
    return (f'<div class="page-head"><div class="crumb">{escape(crumb)}</div>'
            f'<h1 class="h1 disp">{escape(title)}</h1><p class="h1-sub">{escape(sub)}</p></div>')


def section_title(text: str) -> None:
    st.html(f'<div class="sec"><h2 class="h2 disp">{escape(text)}</h2></div>')


def empty_state(glyph: str, text: str) -> str:
    return f'<div class="empty">{icon(glyph)}<p>{escape(text)}</p></div>'


# Services that already failed during this script run (module is re-executed on every
# rerun, so this resets itself). Keeps the page to one banner per service.
_SEEN: set[str] = set()


def safe_call(fn, *args, label: str = "Database", **kwargs):
    """Run a backend call. On failure show ONE inline red banner per service and return None."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - UI must never crash on a DB error
        logging.exception("%s call failed", label)
        if label not in _SEEN:
            _SEEN.add(label)
            short = escape(str(exc)[:160])
            st.html(banner("err", f"<b>{escape(label)} unavailable.</b> {short}. "
                                  "Check that Docker is running, then press Refresh."))
        return None


# ---------------------------------------------------------------------------
# Component builders (return HTML strings; one line per element keeps the
# markdown parser out of the way)
# ---------------------------------------------------------------------------
def brand_html() -> str:
    """Radar mark drawn in pure CSS (st.html strips inline SVG)."""
    return ('<div class="brand"><div class="brand-mark"><i class="bm-sweep"></i><i class="bm-blip"></i></div>'
            '<div class="brand-text"><div class="brand-name disp">CRISISLINK</div>'
            '<div class="brand-sub">Disaster Resource Coordination</div></div></div>')


def status_html(health: dict) -> str:
    rows = []
    for key, label in (("mysql", "MySQL"), ("mongo", "MongoDB")):
        ok, ms = health.get(key, (False, None))
        cls = "" if ok else " down"
        ms_txt = f"{ms} ms" if ok and ms is not None else "offline"
        rows.append(f'<div class="sys-row"><div class="sys-name"><span class="sys-dot{cls}"></span>'
                    f'<span class="t">{label}</span></div><span class="sys-ms mono">{ms_txt}</span></div>')
    return f'<div class="sys">{"".join(rows)}</div>'


def kpi_html(items: list[dict]) -> str:
    cards = []
    for it in items:
        raw = it["value"]
        if raw is None:  # data source unavailable: say so instead of showing a fake zero
            v, num = 0, '<span class="na">n/a</span>'
        else:
            v = int(raw)
            num = (f'<span class="cnt" style="--t:{v}" role="img" aria-label="{v}"></span>'
                   if v < 1000 else f"{v:,}")
        crit = " crit" if it.get("crit") and v > 0 else ""
        cards.append(
            f'<div class="card kpi{crit}"><div class="kpi-top"><span class="lbl">{escape(it["label"])}</span>'
            f'{icon(it["icon"], 18)}</div><div><div class="kpi-val">{num}</div>'
            f'<div class="kpi-cap">{escape(it["caption"])}</div></div></div>')
    return f'<div class="kpis">{"".join(cards)}</div>'


def _health_color(pct: float) -> str:
    if pct < 40:
        return "#FF4B4B"
    if pct < 70:
        return "#FFA726"
    if pct < 90:
        return "#FFEB3B"
    return "#66BB6A"


def build_zones(situation: list, summary: list, requests: list) -> list[dict]:
    """Merge the situation view, zone summary and request list into one model per zone."""
    pct_by_zone = {r["zone"]: float(r.get("fulfillment_pct") or 0) for r in summary}
    worst: dict[str, str] = {}
    for r in requests:
        if r.get("status") in ("DELIVERED", "CANCELLED"):
            continue
        z, u = r.get("zone"), str(r.get("urgency", "")).upper()
        if URGENCY_RANK.get(u, 0) > URGENCY_RANK.get(worst.get(z, ""), 0):
            worst[z] = u
    zones = []
    for r in situation:
        z = r["zone"]
        zones.append({
            "zone": z,
            "open": int(r.get("open_requests") or 0),
            "critical": int(r.get("critical_requests") or 0),
            "matches": int(r.get("active_matches") or 0),
            "pct": min(pct_by_zone.get(z, 0.0), 100.0),
            "worst": "CRITICAL" if int(r.get("critical_requests") or 0) else worst.get(z, "LOW"),
        })
    return zones


def zones_html(zones: list[dict]) -> str:
    cards = []
    for z in zones:
        color = _health_color(z["pct"])
        cards.append(
            f'<div class="card zone"><div class="zone-top"><div class="h3">{escape(z["zone"])}</div>{pill(z["worst"])}</div>'
            f'<div class="zone-stats">'
            f'<div class="zone-stat"><div class="lbl">Open</div><div class="v mono">{z["open"]}</div></div>'
            f'<div class="zone-stat"><div class="lbl">Critical</div><div class="v mono">{z["critical"]}</div></div>'
            f'<div class="zone-stat"><div class="lbl">Matches</div><div class="v mono">{z["matches"]}</div></div></div>'
            f'<div class="fill"><div class="lbl">Fulfilled</div><div class="fill-row">'
            f'<span class="fill-bar" style="width:{max(z["pct"], 2) * 0.8:.0f}%;background:{color}"></span>'
            f'<span class="fill-num mono">{z["pct"]:.0f}%</span></div></div></div>')
    return f'<div class="zones">{"".join(cards)}</div>'


def timeline_html(events: list, wide: bool = False) -> str:
    if not events:
        return empty_state("sensors", "No events yet. Activity appears here as soon as data is added.")
    now = datetime.now()
    items = []
    for ev in events:
        etype = str(ev.get("entity_type", "")).upper()
        ts = ev.get("timestamp")
        fresh = " fresh" if isinstance(ts, datetime) and 0 <= (now - ts).total_seconds() < 90 else ""
        title = f"{str(ev.get('action', '')).title()} {etype.lower()} #{ev.get('entity_id', '')}"
        sub = f"{ev.get('actor_name', '')}, {ev.get('zone', '')}"
        items.append(
            f'<li class="{fresh.strip()}" style="--c:{ENTITY_COLORS.get(etype, "#9AAAB7")}"><span class="tl-node"></span>'
            f'<div class="tl-title">{escape(title)}</div><div class="tl-sub">{escape(sub)}</div>'
            f'<div class="tl-time mono">{escape(fmt_dt(ts))}</div></li>')
    return f'<ol class="tl{" wide" if wide else ""}">{"".join(items)}</ol>'


def queue_html(rows: list) -> str:
    if not rows:
        return empty_state("task_alt", "Every open request has a confirmed match.")
    items = []
    for r in rows:
        title = f"{r.get('resource_name', '')}, {fmt_num(r.get('quantity', 0))}"
        sub = f"{r.get('org_name', '')}, {r.get('zone', '')}"
        items.append(f'<div class="card q"><div class="q-title">{escape(title)}</div>'
                     f'<div class="q-sub">{escape(sub)}</div>{pill(r.get("urgency", ""))}</div>')
    return f'<div class="queue">{"".join(items)}</div>'


# Status chips: value -> colour class
_CHIP = {
    "OPEN": "info", "MATCHED": "info", "PARTIAL": "warn", "DISPATCHED": "warn", "DELIVERED": "ok", "CANCELLED": "bad",    "AVAILABLE": "ok", "RESERVED": "warn", "DEPLETED": "bad",
    "PENDING": "warn", "CONFIRMED": "ok", "REJECTED": "bad", "COMPLETED": "ok",
}
_SCORE_COLS = {"match_score", "fulfillment_pct"}


def _cell(col: str, v) -> tuple[str, str]:
    """Return (css class, inner html) for one table cell."""
    if v is None:
        return "muted", "n/a"
    if col == "urgency":
        return "", pill(v)
    if col.endswith("status"):
        return "", f'<span class="chip {_CHIP.get(str(v).upper(), "")}">{escape(str(v))}</span>'
    if col in _SCORE_COLS and _is_num(v):
        f = float(v)
        bar = f'<i style="width:{max(min(f, 100), 0) * 0.6:.0f}px"></i>'
        return "num", f'<span class="score">{bar}<span>{fmt_num(v)}</span></span>'
    if col == "id" or col.endswith("_id"):
        return "idc", f"#{escape(str(v))}"
    if isinstance(v, datetime):
        return "mono", escape(fmt_dt(v))
    if _is_num(v):
        return "num", fmt_num(v)
    if isinstance(v, (list, tuple, set)):
        return "", " ".join(f'<span class="tag">{escape(str(i))}</span>' for i in v)
    if col == "description":
        return "wrap", escape(str(v))
    return "", escape(str(v))


def table_html(rows: list, name: str, note: str = "") -> str:
    """Custom table: sticky header, mono numerals, urgency pills, trackless score bars."""
    if not rows:
        return empty_state("table_rows", "No records yet. Add data and run the auto-match to fill this report.")
    cols = list(rows[0].keys())
    num_cols = {c for c in cols if all(_is_num(r.get(c)) or r.get(c) is None for r in rows)
                and not (c == "id" or c.endswith("_id"))}
    head = "".join(
        f'<th class="{"num" if (c in num_cols or c in _SCORE_COLS) else ""}">{escape(c.replace("_", " "))}</th>'
        for c in cols)
    body = []
    for r in rows:
        tds = []
        for c in cols:
            cls, inner = _cell(c, r.get(c))
            tds.append(f'<td class="{cls}">{inner}</td>')
        body.append(f'<tr>{"".join(tds)}</tr>')
    meta = (f'<div class="tbl-meta"><span class="mono">{len(rows)} rows</span><span class="sep"></span>'
            f'<span class="mono">{escape(name)}</span><span class="sep"></span>'
            f'<span>Generated {datetime.now().strftime("%H:%M:%S")}</span>'
            + (f'<span class="sep"></span><span>{escape(note)}</span>' if note else "") + '</div>')
    return (f'{meta}<div class="tbl-wrap"><table class="tbl"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


_JSON_TOKEN = re.compile(
    r'("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)')


def _hl_json_line(line: str) -> str:
    out, pos = [], 0
    for m in _JSON_TOKEN.finditer(line):
        out.append(escape(line[pos:m.start()]))
        s, colon, lit, num = m.groups()
        if s is not None and colon:
            out.append(f'<span class="j-k">{escape(s)}</span><span class="j-p">{escape(colon)}</span>')
        elif s is not None:
            out.append(f'<span class="j-s">{escape(s)}</span>')
        elif lit:
            out.append(f'<span class="j-b">{lit}</span>')
        else:
            out.append(f'<span class="j-n">{num}</span>')
        pos = m.end()
    out.append(escape(line[pos:]))
    return "".join(out)


def json_html(obj, title: str) -> str:
    """Syntax-highlighted JSON viewer with line numbers."""
    text = json.dumps(obj, indent=2, default=_json_default)
    lines = [f'<span class="ln">{i}</span>{_hl_json_line(l)}' for i, l in enumerate(text.splitlines(), 1)]
    return (f'<div class="json"><div class="json-bar"><span class="lbl">{escape(title)}</span>'
            f'<span class="mono muted" style="font-size:12px">{len(lines)} lines</span></div>'
            f'<pre>{chr(10).join(lines)}</pre></div>')


# ---------------------------------------------------------------------------
# Cached health probe for the sidebar status block (keeps reruns snappy)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=8, show_spinner=False)
def probe_health() -> dict:
    out = {}
    for key, fn, args in (("mysql", db_sql.get_situation_report, ()),
                          ("mongo", db_nosql.get_recent_events, (1,))):
        t0 = time.perf_counter()
        try:
            fn(*args)
            out[key] = (True, int((time.perf_counter() - t0) * 1000))
        except Exception:  # noqa: BLE001
            out[key] = (False, None)
    return out


def log_event(entity_type, entity_id, action, actor_org_id, actor_name, details, zone) -> bool:
    """Write an audit event to MongoDB via db_nosql.insert_event."""
    event = {
        "event_id": new_event_id(), "entity_type": entity_type, "entity_id": entity_id,
        "action": action, "actor_org_id": actor_org_id, "actor_name": actor_name,
        "details": details, "timestamp": datetime.now(), "zone": zone,
    }
    try:
        db_nosql.insert_event(event)
        return True
    except Exception:  # noqa: BLE001
        logging.exception("Audit event failed")
        return False

# ---------------------------------------------------------------------------
# Add Data dialogs (st.dialog on modern Streamlit, expander on older versions)
# ---------------------------------------------------------------------------
def _modal(title: str):
    if hasattr(st, "dialog"):
        for kwargs in ({"width": "medium", "on_dismiss": "rerun"}, {"width": "medium"}, {}):
            try:  # newest options first; fall back for older Streamlit releases
                return st.dialog(title, **kwargs)
            except Exception:  # noqa: BLE001
                continue

    def decorator(fn):
        def wrapper(*args, **kwargs):
            with st.expander(title, expanded=True):
                return fn(*args, **kwargs)
        return wrapper
    return decorator


class FormState:
    """Collects per-field errors and renders them under the offending inputs."""

    def __init__(self) -> None:
        self.slots: dict[str, object] = {}
        self.errors: dict[str, str] = {}

    def slot(self, key: str) -> None:
        """Reserve a spot directly under the input that uses widget key `key`."""
        self.slots[key] = st.empty()

    def fail(self, key: str, message: str) -> None:
        self.errors[key] = message

    def show(self, banner_slot) -> bool:
        """Render errors. Returns True when there is at least one."""
        if not self.errors:
            return False
        n = len(self.errors)
        banner_slot.html(banner("err", f"<b>{n} field{'s' if n != 1 else ''} need attention.</b> "
                                       "Your entries are kept, fix them and submit again."))
        for key, msg in self.errors.items():
            self.slots[key].html(f'<div class="field-error">{icon("error")}<span>{escape(msg)}</span></div>')
        return True


def _action_row(submit_label: str):
    """Right-aligned Cancel + primary submit inside a form. Returns (cancel, submit)."""
    _, c_cancel, c_submit = st.columns([2, 1, 1.5])
    cancel = c_cancel.form_submit_button("Cancel", use_container_width=True)
    submit = c_submit.form_submit_button(submit_label, type="primary", use_container_width=True)
    return cancel, submit


def _after_insert(kind: str, new_id: int, banner_slot, audit_ok: bool, title: str) -> None:
    msg = f"<b>{escape(title)}</b> saved with ID {new_id}."
    banner_slot.html(banner("ok", msg))
    if not audit_ok:
        st.html(banner("warn", "Saved to SQL, but the MongoDB audit event could not be written."))
    st.toast(f"{kind} saved (ID {new_id})", icon=":material/check_circle:")


@_modal("Register organization")
def dialog_org() -> None:
    banner_slot = st.empty()
    fs = FormState()
    with st.form("form_org"):
        name = st.text_input("Organization name", key="org_name", placeholder="Goonj Foundation")
        fs.slot("org_name")
        c1, c2 = st.columns(2)
        with c1:
            org_type = st.selectbox("Type", ORG_TYPES, key="org_type")
        with c2:
            zone = st.text_input("Zone", key="org_zone", placeholder="Zone-A")
            fs.slot("org_zone")
        contact = st.text_input("Contact person", key="org_contact", placeholder="Ravi Sharma")
        fs.slot("org_contact")
        c3, c4 = st.columns(2)
        with c3:
            phone = st.text_input("Phone (10 digits)", key="org_phone", max_chars=10, placeholder="9876543210")
            fs.slot("org_phone")
        with c4:
            email = st.text_input("Email", key="org_email", placeholder="name@organization.org")
            fs.slot("org_email")
        cancel, submit = _action_row("Register")

    if cancel:
        st.rerun()
    if not submit:
        return
    name, zone, contact, phone, email = (s.strip() for s in (name, zone, contact, phone, email))
    if not name:
        fs.fail("org_name", "Organization name is required.")
    if not zone:
        fs.fail("org_zone", "Zone is required.")
    if not contact:
        fs.fail("org_contact", "Contact person is required.")
    if not validate_phone(phone):
        fs.fail("org_phone", "Phone must be exactly 10 digits.")
    if not validate_email(email):
        fs.fail("org_email", "Enter a valid email address.")
    if fs.show(banner_slot):
        return
    try:
        org_id = db_sql.insert_organization(Organization(None, name, org_type, contact, phone, email, zone))
    except Exception as exc:  # noqa: BLE001
        logging.exception("insert_organization failed")
        banner_slot.html(banner("err", f"<b>Could not save organization.</b> {escape(str(exc)[:160])}"))
        return
    audit_ok = log_event("ORG", org_id, "CREATED", org_id, name, {"org_type": org_type}, zone)
    _after_insert("Organization", org_id, banner_slot, audit_ok, name)


def _org_picker(label: str, key: str):
    orgs = safe_call(db_sql.get_all_organizations, label="SQL") or []
    if not orgs:
        st.html(banner("warn", "Register an organization first, then come back to add this record."))
        return None
    return st.selectbox(label, orgs, key=key, format_func=lambda o: f"{o['org_name']} ({o['zone']})")


@_modal("Submit request")
def dialog_request() -> None:
    banner_slot = st.empty()
    fs = FormState()
    org = _org_picker("Requesting organization", "req_org")
    if org is None:
        return
    with st.form("form_request"):
        c1, c2 = st.columns(2)
        with c1:
            rtype = st.selectbox("Resource type", RESOURCE_TYPES, key="req_type")
        with c2:
            rname = st.text_input("Resource name", key="req_name", placeholder="Cooked meal packets")
            fs.slot("req_name")
        c3, c4 = st.columns(2)
        with c3:
            qty = st.number_input("Quantity", min_value=0, value=1, step=1, key="req_qty")
            fs.slot("req_qty")
        with c4:
            unit = st.text_input("Unit", key="req_unit", value="units")
        urgency = st.segmented_control("Urgency", URGENCY_LEVELS, default="HIGH", key="req_urg")
        fs.slot("req_urg")
        zone = st.text_input("Zone", key="req_zone", placeholder="Zone-A")
        fs.slot("req_zone")
        desc = st.text_area("Description", key="req_desc", height=88, placeholder="What is needed and why")
        cancel, submit = _action_row("Submit request")

    if cancel:
        st.rerun()
    if not submit:
        return
    rname, zone, unit, desc = rname.strip(), zone.strip(), unit.strip() or "units", desc.strip()
    if not rname:
        fs.fail("req_name", "Resource name is required.")
    if not validate_positive_int(qty):
        fs.fail("req_qty", "Quantity must be a positive whole number.")
    if not urgency or not validate_enum(urgency, URGENCY_LEVELS):
        fs.fail("req_urg", "Choose an urgency level.")
    if not zone:
        fs.fail("req_zone", "Zone is required.")
    if fs.show(banner_slot):
        return
    try:
        req_id = db_sql.insert_request(Request(None, org["org_id"], rtype, rname, int(qty), unit, urgency, zone, "OPEN", desc))
    except Exception as exc:  # noqa: BLE001
        logging.exception("insert_request failed")
        banner_slot.html(banner("err", f"<b>Could not save request.</b> {escape(str(exc)[:160])}"))
        return
    audit_ok = log_event("REQUEST", req_id, "CREATED", org["org_id"], org["org_name"],
                         {"resource_name": rname, "quantity": int(qty), "urgency": urgency}, zone)
    _after_insert("Request", req_id, banner_slot, audit_ok, rname)


@_modal("List supply")
def dialog_supply() -> None:
    banner_slot = st.empty()
    fs = FormState()
    org = _org_picker("Supplying organization", "sup_org")
    if org is None:
        return
    with st.form("form_supply"):
        c1, c2 = st.columns(2)
        with c1:
            rtype = st.selectbox("Resource type", RESOURCE_TYPES, key="sup_type")
        with c2:
            rname = st.text_input("Resource name", key="sup_name", placeholder="Drinking water cans")
            fs.slot("sup_name")
        c3, c4 = st.columns(2)
        with c3:
            qty = st.number_input("Quantity available", min_value=0, value=1, step=1, key="sup_qty")
            fs.slot("sup_qty")
        with c4:
            unit = st.text_input("Unit", key="sup_unit", value="units")
        zone = st.text_input("Zone", key="sup_zone", placeholder="Zone-A")
        fs.slot("sup_zone")
        cancel, submit = _action_row("List supply")

    if cancel:
        st.rerun()
    if not submit:
        return
    rname, zone, unit = rname.strip(), zone.strip(), unit.strip() or "units"
    if not rname:
        fs.fail("sup_name", "Resource name is required.")
    if not validate_positive_int(qty):
        fs.fail("sup_qty", "Quantity must be a positive whole number.")
    if not zone:
        fs.fail("sup_zone", "Zone is required.")
    if fs.show(banner_slot):
        return
    try:
        sup_id = db_sql.insert_supply(Supply(None, org["org_id"], rtype, rname, int(qty), unit, zone))
    except Exception as exc:  # noqa: BLE001
        logging.exception("insert_supply failed")
        banner_slot.html(banner("err", f"<b>Could not save supply.</b> {escape(str(exc)[:160])}"))
        return
    audit_ok = log_event("SUPPLY", sup_id, "CREATED", org["org_id"], org["org_name"],
                         {"resource_name": rname, "quantity": int(qty)}, zone)
    _after_insert("Supply", sup_id, banner_slot, audit_ok, rname)

# ---------------------------------------------------------------------------
# Navigation callbacks
# ---------------------------------------------------------------------------
def _goto(page_key: str, **state) -> None:
    st.session_state["nav"] = page_key
    for k, v in state.items():
        st.session_state[k] = v


def _toggle_rail() -> None:
    st.session_state["rail"] = not st.session_state.get("rail", False)


def _select_report(report_id: str) -> None:
    st.session_state["sel_report"] = report_id


def _panel(inner: str) -> str:
    return f'<div class="card static panel">{inner}</div>'


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def page_dashboard() -> None:
    st.session_state["last_sync"] = datetime.now().strftime("%H:%M:%S")

    head, side = st.columns([5, 2], vertical_alignment="center")
    with head:
        st.html(page_header("Command / Live dashboard", "Live Dashboard",
                            "Open needs, matches and recent activity across every zone."))
    with side:
        with st.container(key="sync_box"):
            st.html(f'<div class="sync"><b></b><span class="mono">Synced {st.session_state["last_sync"]}</span></div>')
            st.button("Refresh", icon=":material/refresh:", key="refresh", type="tertiary",
                      on_click=probe_health.clear)

    situation = safe_call(db_sql.get_situation_report, label="SQL") or []
    summary = safe_call(db_sql.get_zone_summary, label="SQL") or []
    requests = safe_call(db_sql.get_all_requests, label="SQL") or []
    unmet = safe_call(db_sql.get_unmet_requests, label="SQL") or []
    events = safe_call(db_nosql.get_recent_events, 3, label="MongoDB") or []

    sql_down = "SQL" in _SEEN
    open_req = None if sql_down else sum(int(r.get("open_requests") or 0) for r in situation)
    crit = None if sql_down else sum(int(r.get("critical_requests") or 0) for r in situation)
    active = None if sql_down else sum(int(r.get("active_matches") or 0) for r in situation)
    matched = None if sql_down else sum(int(r.get("total_matched_qty") or 0) for r in situation)
    n_zones = len(situation)
    zone_txt = "database offline" if sql_down else f"across {n_zones} zone{'s' if n_zones != 1 else ''}"

    st.html(kpi_html([
        {"label": "Open requests", "icon": "inbox", "value": open_req, "caption": zone_txt},
        {"label": "Critical requests", "icon": "emergency_home", "value": crit,
         "caption": "database offline" if sql_down else ("need action now" if crit else "nothing critical"), "crit": True},
        {"label": "Active matches", "icon": "hub", "value": active, "caption": "database offline" if sql_down else "pending or confirmed"},
        {"label": "Resources matched", "icon": "inventory_2", "value": matched, "caption": "database offline" if sql_down else "units committed"},
    ]))

    main, rail = st.columns([8, 4], gap="large")
    with main:
        section_title("Zone situation")
        zones = build_zones(situation, summary, requests)
        if zones:
            st.html(zones_html(zones))
        elif sql_down:
            st.html(empty_state("cloud_off", "Unavailable while MySQL is offline."))
        else:
            st.html(empty_state("map", "No zone data yet. Register an organization and submit a request "
                                       "to see the situation build up."))
            st.button("Add data", key="empty_add", type="secondary", on_click=_goto, args=("add",))
        with st.expander("Raw situation view"):
            st.html(table_html(situation, "v_situation_report"))
    with rail:
        section_title("Recent events")
        if "MongoDB" in _SEEN:
            st.html(empty_state("cloud_off", "Unavailable while MongoDB is offline."))
        else:
            st.html(_panel(timeline_html(events)))
        section_title("Priority queue")
        if sql_down:
            st.html(empty_state("cloud_off", "Unavailable while MySQL is offline."))
        else:
            st.html(queue_html(unmet[:5]))


def page_add() -> None:
    st.html(page_header("Command / Add data", "Add Data",
                        "Register who is involved, what is needed and what is available."))
    n_org = len(safe_call(db_sql.get_all_organizations, label="SQL") or [])
    n_req = len(safe_call(db_sql.get_all_requests, label="SQL") or [])
    n_sup = len(safe_call(db_sql.get_all_supplies, label="SQL") or [])

    tiles = [
        ("tile_org", "apartment", "Organization", "NGOs, agencies, hospitals and volunteer groups.",
         n_org, "on record", "Add organization", dialog_org),
        ("tile_req", "emergency", "Request", "A shortage in a zone, with urgency and quantity.",
         n_req, "logged", "Add request", dialog_request),
        ("tile_sup", "inventory_2", "Supply", "Stock a donor can release to a zone.",
         n_sup, "listed", "Add supply", dialog_supply),
    ]
    for col, (key, glyph, title, desc, count, word, label, dlg) in zip(st.columns(3, gap="large"), tiles):
        with col:
            with st.container(key=key):
                st.html(f'<div class="tile-icon">{icon(glyph, 22)}</div><div class="h2 disp">{title}</div>'
                        f'<p class="small" style="margin:8px 0 0">{desc}</p>'
                        f'<div class="tile-count mono">{count} {word}</div>')
                if st.button(label, key=f"open_{key}", type="secondary", use_container_width=True):
                    dlg()

    section_title("Latest requests")
    latest = safe_call(db_sql.get_all_requests, label="SQL") or []
    cols = ("request_id", "resource_name", "quantity", "unit", "urgency", "zone", "status")
    st.html(table_html([{c: r.get(c) for c in cols} for r in latest[:5]], "get_all_requests", "Five most recent"))


def page_match() -> None:
    st.html(page_header("Command / Auto-match", "Run Auto-Match",
                        "Pair open requests with available supplies of the same resource type."))
    with st.container(key="hero"):
        st.html('<div class="hero-copy"><div class="h2 disp">Matching engine</div>'
                '<p>Same-zone pairings score highest. Critical requests are matched first.</p></div>')
        sql_ok = probe_health().get("mysql", (False, None))[0]
        run = st.button("Run auto-match algorithm", type="primary", key="run_match", disabled=not sql_ok)
        status = st.empty()
        if not sql_ok:
            st.html(banner("err", "<b>MySQL is offline.</b> Start Docker, then press Refresh on the dashboard."))
        if run and sql_ok:
            status.markdown("<style>.st-key-hero{--sweep:1.4s}</style>", unsafe_allow_html=True)
            with st.spinner("Matching requests to available supplies..."):
                before = safe_call(db_sql.get_all_matches, label="SQL")
                returned = safe_call(db_sql.run_auto_match, label="Auto-match")
                time.sleep(0.7)  # short minimum so the scanning state is perceptible
                after = safe_call(db_sql.get_all_matches, label="SQL")
            if returned is not None:
                # Count real new rows in `matches` (the procedure's own counter reports
                # updated requests, which can differ from inserted matches).
                if before is not None and after is not None:
                    created = max(len(after) - len(before), 0)
                else:
                    created = int(returned)
                st.session_state["last_match"] = {"created": created, "at": datetime.now().strftime("%H:%M:%S")}
                st.toast(f"{created} {'match' if created == 1 else 'matches'} created", icon=":material/bolt:")
            status.empty()

    last = st.session_state.get("last_match")
    if not last:
        return
    if last["created"] > 0:
        n = last["created"]
        num = (f'<span class="cnt" style="--t:{n}" role="img" aria-label="{n}"></span>' if n < 1000 else f"{n:,}")
        st.html(f'<div class="result"><div class="result-num">{num}</div>'
                f'<div class="result-t">{"match" if n == 1 else "matches"} created</div>'
                f'<div class="result-s">Matched requests moved to MATCHED status.</div>'
                f'<div class="result-m mono">Run at {last["at"]}</div></div>')
        st.button("View match report", key="goto_report", type="secondary", icon=":material/arrow_forward:",
                  on_click=_goto, args=("sql",), kwargs={"sql_report": "Match Report (JOIN)"})
    else:
        st.html(banner("info", "No new matches. Either nothing is open or no compatible supplies are available."))


def page_sql() -> None:
    head, pick = st.columns([5, 3], vertical_alignment="bottom")
    with head:
        st.html(page_header("Command / SQL reports", "SQL Reports", "Query results straight from MySQL."))
    with pick:
        choice = st.selectbox("Report", list(SQL_REPORTS), key="sql_report")
    fn, note = SQL_REPORTS[choice]
    rows = safe_call(fn, label="SQL")
    if rows is not None:
        st.html(table_html(rows, fn.__name__, note))


def _mongo_zone_cards(rows: list) -> str:
    cards = []
    for r in rows:
        crit = int(r.get("critical_reports") or 0)
        tags = "".join(f'<span class="tag">{escape(str(t))}</span>' for t in (r.get("report_types") or []))
        cards.append(
            f'<div class="card zone"><div class="zone-top"><div class="h3">{escape(str(r.get("zone", "")))}</div>'
            f'{pill("CRITICAL") if crit else ""}</div>'
            f'<div class="zone-stats" style="grid-template-columns:repeat(2,1fr)">'
            f'<div class="zone-stat"><div class="lbl">Reports</div><div class="v mono">{int(r.get("total_reports") or 0)}</div></div>'
            f'<div class="zone-stat"><div class="lbl">Critical</div><div class="v mono">{crit}</div></div></div>'
            f'<div class="fill"><div class="lbl">Types</div><div style="display:flex;gap:6px;flex-wrap:wrap">{tags}</div>'
            f'<div class="small muted mono" style="margin-top:4px">Latest {escape(fmt_dt(r.get("latest_report")))}</div></div></div>')
    return f'<div class="zones">{"".join(cards)}</div>'


def page_mongo() -> None:
    head, pick = st.columns([5, 3], vertical_alignment="bottom")
    with head:
        st.html(page_header("Command / MongoDB logs", "MongoDB Logs",
                            "Aggregations and the audit trail from the NoSQL layer."))
    with pick:
        choice = st.selectbox("View", MONGO_VIEWS, key="mongo_view")

    if choice == MONGO_VIEWS[0]:
        rows = safe_call(db_nosql.get_field_reports_by_zone, label="MongoDB")
        if rows is not None:
            st.html(_mongo_zone_cards(rows) if rows else empty_state("sensors", "No field reports in range."))

    elif choice == MONGO_VIEWS[1]:
        rows = safe_call(db_nosql.get_critical_reports_with_events, label="MongoDB")
        if rows is None:
            return
        if not rows:
            st.html(empty_state("fact_check", "No critical reports found."))
            return
        ids = [str(r.get("report_id")) for r in rows]
        sel = st.session_state.get("sel_report")
        if sel not in ids:
            sel = ids[0]
        left, right = st.columns([5, 7], gap="large")
        with left:
            with st.container(key="reports"):
                for i, r in enumerate(rows):
                    rid = str(r.get("report_id"))
                    with st.container(key=f"rep_{i}"):
                        desc = str(r.get("description", ""))
                        desc = desc if len(desc) <= 130 else desc[:127] + "..."
                        st.html(f'<div class="rep">{"<span class=on></span>" if rid == sel else ""}'
                                f'<div class="rep-top"><span class="h3 mono">{escape(rid)}</span>{pill(r.get("severity", ""))}</div>'
                                f'<div class="rep-desc">{escape(desc)}</div>'
                                f'<div class="rep-meta mono">{escape(str(r.get("zone", "")))}, '
                                f'{int(r.get("event_count") or 0)} related events</div></div>')
                        st.button("Inspect", key=f"inspect_{i}", type="tertiary", icon=":material/data_object:",
                                  on_click=_select_report, args=(rid,))
        with right:
            chosen = next(r for r in rows if str(r.get("report_id")) == sel)
            st.html(json_html(chosen, "field_reports + event_stream"))
            st.download_button("Download JSON", data=json.dumps(chosen, indent=2, default=_json_default),
                               file_name=f"{sel}.json", mime="application/json", type="tertiary",
                               icon=":material/download:", key="dl_json")

    else:
        rows = safe_call(db_nosql.get_recent_events, 20, label="MongoDB")
        if rows is not None:
            st.html(_panel(timeline_html(rows, wide=True)))


def page_tables() -> None:
    head, pick = st.columns([5, 4], vertical_alignment="bottom")
    with head:
        st.html(page_header("Command / Browse tables", "Browse Tables",
                            "Full rows from the backend's public read functions, newest first."))
    with pick:
        choice = st.selectbox("Table", list(BROWSE_SOURCES), key="browse_table")
        limit = st.selectbox("Rows", ROW_LIMITS, index=1, key="browse_limit")

    rows = safe_call(BROWSE_SOURCES[choice], label="SQL")
    if rows is not None:
        shown = rows[:int(limit)]
        st.html(table_html(shown, choice.split(" (")[0],
                           f"{len(rows)} total, showing {len(shown)}"))


PAGE_FUNCS = {
    "dashboard": page_dashboard,
    "add": page_add,
    "match": page_match,
    "sql": page_sql,
    "mongo": page_mongo,
    "tables": page_tables,
}

RADAR_URI = _radar_background()
GRAIN_URI = _grain_background()


def main() -> None:
    if "logging_ready" not in st.session_state:
        setup_logging()
        st.session_state["logging_ready"] = True
    st.session_state.setdefault("rail", False)

    try:
        too_old = tuple(int(x) for x in st.__version__.split(".")[:2]) < (1, 50)
    except ValueError:
        too_old = False

    css = CSS.replace("__RADAR__", RADAR_URI).replace("__GRAIN__", GRAIN_URI)
    if st.session_state["rail"]:
        css += RAIL_CSS
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    with st.sidebar:
        st.html(brand_html())
        page = st.radio("Navigation", list(PAGES), key="nav", label_visibility="collapsed",
                        format_func=lambda k: f":material/{PAGES[k][1]}: {PAGES[k][0]}")
        with st.container(key="side_bottom"):
            st.html(status_html(probe_health()))
            rail = st.session_state["rail"]
            st.button("" if rail else "Collapse", key="rail_toggle", on_click=_toggle_rail, type="tertiary",
                      icon=":material/chevron_right:" if rail else ":material/chevron_left:")

    if too_old:
        st.html(banner("warn", f"<b>Streamlit {escape(st.__version__)} detected.</b> This design is built for "
                               "1.50 or newer. Run <span class='mono'>pip install -U streamlit</span> for the intended look."))
    PAGE_FUNCS[page]()

    st.html('<div class="footer">CrisisLink | SDG 11 &amp; 17 | Database Concepts Lab</div>')


main()
