"""Design system: colour tokens, typography, CSS and the shared Plotly template.

Fonts use the system stack on purpose: a web font would have to be downloaded and would fail during the offline
kill-switch test.
"""
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ---- colour tokens -----------------------------------------------------------------------------------------
NAVY = "#0B1F3A"
BG = "#F4F6F9"
CARD = "#FFFFFF"
BORDER = "#E3E8EF"
TEXT = "#0F172A"
MUTED = "#475569"
FAINT = "#94A3B8"
BLUE = "#1F6FEB"
CYAN = "#06B6D4"
GREEN = "#16A34A"
AMBER = "#CA8A04"
ORANGE = "#EA580C"
RED = "#DC2626"
SLATE = "#64748B"
LIGHT_SLATE = "#CBD5E1"

RISK = {"Low": GREEN, "Medium": AMBER, "High": ORANGE, "Critical": RED}
RISK_BG = {"Low": "#DCFCE7", "Medium": "#FEF9C3", "High": "#FFEDD5", "Critical": "#FEE2E2"}
RISK_FG = {"Low": "#166534", "Medium": "#854D0E", "High": "#9A3412", "Critical": "#991B1B"}
TIERS = ("Low", "Medium", "High", "Critical")

FONT = "'Segoe UI', 'Inter', system-ui, -apple-system, Roboto, 'Helvetica Neue', Arial, sans-serif"

CSS = f"""
<style>
html, body, [class*="css"], .stApp {{ font-family: {FONT}; }}
.block-container {{ padding-top: 1.2rem; padding-bottom: 2.5rem; max-width: 1440px; }}
header[data-testid="stHeader"] {{ background: transparent; }}

/* ---------- app header ---------- */
.app-header {{ display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px;
  background:{CARD}; border:1px solid {BORDER}; border-radius:10px; padding:10px 16px; margin-bottom:12px;
  box-shadow:0 1px 2px rgba(15,23,42,.04); }}
.app-header .brand {{ font-size:15px; font-weight:700; color:{TEXT}; letter-spacing:.1px; }}
.app-header .brand small {{ display:block; font-size:12px; font-weight:500; color:{MUTED}; }}
.app-header .meta {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; }}
.pill {{ display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:999px; font-size:12px;
  font-weight:600; border:1px solid {BORDER}; background:#F8FAFC; color:{MUTED}; white-space:nowrap; }}
.pill b {{ color:{TEXT}; font-weight:700; }}
.pill.ok {{ background:#ECFDF5; border-color:#A7F3D0; color:#065F46; }}
.pill.warn {{ background:#FFF7ED; border-color:#FED7AA; color:#9A3412; }}
.pill.info {{ background:#EFF6FF; border-color:#BFDBFE; color:#1E40AF; }}
.dot {{ width:7px; height:7px; border-radius:50%; display:inline-block; }}

/* ---------- page title ---------- */
.page-title {{ margin:6px 0 2px 0; font-size:22px; font-weight:700; color:{TEXT}; }}
.page-sub {{ margin:0 0 14px 0; font-size:13.5px; color:{MUTED}; }}
.section {{ font-size:15px; font-weight:650; color:{TEXT}; margin:18px 0 8px 0; display:flex; align-items:center; gap:8px; }}
.section .hint {{ font-size:12px; font-weight:500; color:{FAINT}; }}

/* ---------- KPI cards ---------- */
.kpi {{ background:{CARD}; border:1px solid {BORDER}; border-radius:10px; padding:14px 16px 12px 16px;
  box-shadow:0 1px 2px rgba(15,23,42,.05); min-height:112px; position:relative; overflow:hidden;
  margin-bottom:12px; }}
.kpi:before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:4px; background:var(--accent); }}
.kpi .label {{ font-size:12px; font-weight:600; color:{MUTED}; text-transform:uppercase; letter-spacing:.4px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.kpi .value {{ font-size:28px; font-weight:750; color:{TEXT}; line-height:1.25; margin-top:4px; }}
.kpi .value small {{ font-size:15px; font-weight:600; color:{FAINT}; }}
.kpi .foot {{ font-size:12px; color:{MUTED}; margin-top:2px; }}

/* ---------- alerts ---------- */
.alert {{ border-radius:10px; padding:12px 14px; border:1px solid; display:flex; gap:10px; align-items:flex-start;
  margin-bottom:10px; background:{CARD}; }}
.alert .ic {{ font-size:18px; line-height:1.1; }}
.alert .t {{ font-weight:700; font-size:13.5px; }}
.alert .d {{ font-size:13px; color:{MUTED}; margin-top:2px; }}
.alert.critical {{ border-color:#FCA5A5; background:#FEF2F2; }} .alert.critical .t {{ color:#991B1B; }}
.alert.warning {{ border-color:#FDBA74; background:#FFF7ED; }} .alert.warning .t {{ color:#9A3412; }}
.alert.info {{ border-color:#BFDBFE; background:#EFF6FF; }} .alert.info .t {{ color:#1E40AF; }}
.alert.ok {{ border-color:#A7F3D0; background:#ECFDF5; }} .alert.ok .t {{ color:#065F46; }}

/* ---------- badges ---------- */
.badge {{ display:inline-block; padding:2px 9px; border-radius:6px; font-size:12px; font-weight:700; }}
.tag {{ display:inline-block; padding:2px 8px; border-radius:6px; font-size:11px; font-weight:700;
  text-transform:uppercase; letter-spacing:.4px; border:1px dashed; }}
.tag.sim {{ color:#6D28D9; border-color:#C4B5FD; background:#F5F3FF; }}
.tag.demo {{ color:#9A3412; border-color:#FDBA74; background:#FFF7ED; }}
.tag.real {{ color:#1E40AF; border-color:#BFDBFE; background:#EFF6FF; }}
.tag.gen {{ color:#334155; border-color:#CBD5E1; background:#F8FAFC; }}

/* ---------- forecast cards ---------- */
.fc {{ background:{CARD}; border:1px solid {BORDER}; border-radius:10px; padding:16px; box-shadow:0 1px 2px rgba(15,23,42,.05); }}
.fc .h {{ font-size:12px; font-weight:600; color:{MUTED}; text-transform:uppercase; letter-spacing:.4px; }}
.fc .w {{ font-size:13px; color:{MUTED}; margin-bottom:10px; }}
.fc .n {{ font-size:34px; font-weight:750; color:{TEXT}; line-height:1.1; }}
.fc .n small {{ font-size:14px; color:{MUTED}; font-weight:500; }}
.fc .r {{ font-size:12.5px; color:{MUTED}; margin-top:6px; }}
.fc .tier {{ display:inline-block; margin-top:10px; padding:5px 12px; border-radius:6px; font-weight:750; font-size:14px; }}

/* ---------- key-value list ---------- */
.kv {{ display:grid; grid-template-columns: 1fr auto; gap:6px 12px; font-size:13px; }}
.kv .k {{ color:{MUTED}; }} .kv .v {{ color:{TEXT}; font-weight:650; text-align:right; }}

/* ---------- message preview ---------- */
.msg {{ background:{CARD}; border:1px solid {BORDER}; border-radius:10px; padding:12px 14px; white-space:pre-wrap;
  font-size:13px; line-height:1.5; color:{TEXT}; font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace; }}
.msg-h {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; font-size:12.5px; color:{MUTED}; }}

/* ---------- Streamlit components ---------- */
div[class*="st-key-card_"], div.st-key-scenario_bar {{ background:{CARD}; box-shadow:0 1px 2px rgba(15,23,42,.05); }}
section[data-testid="stSidebar"] {{ border-right:1px solid #1E3A5F; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] {{ background:#13294B;
  box-shadow: inset 3px 0 0 #38BDF8; }}
section[data-testid="stSidebar"] [data-testid="stNavSectionHeader"] {{ color:#7C93B3; letter-spacing:.8px; font-size:11px; }}
.side-foot {{ font-size:11.5px; color:#8AA0BD; line-height:1.5; margin-top:8px; }}
.side-foot b {{ color:#DCE6F2; }}
button[data-baseweb="tab"] p {{ font-weight:600; }}
div[data-testid="stMetricValue"] {{ font-size:26px; }}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


# ---- Plotly template ---------------------------------------------------------------------------------------
_template = go.layout.Template()
_template.layout = go.Layout(
    font=dict(family=FONT, size=12.5, color=TEXT),
    paper_bgcolor=CARD, plot_bgcolor=CARD,
    colorway=[BLUE, CYAN, ORANGE, GREEN, "#8B5CF6", RED, AMBER, SLATE],
    margin=dict(l=10, r=10, t=36, b=10),
    title=dict(font=dict(size=14, color=TEXT), x=0, xanchor="left"),
    xaxis=dict(gridcolor="#EEF2F6", zerolinecolor=BORDER, linecolor=BORDER, ticks="", automargin=True),
    yaxis=dict(gridcolor="#EEF2F6", zerolinecolor=BORDER, linecolor=BORDER, ticks="", automargin=True),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None,
                font=dict(size=12), traceorder="normal"),
    hoverlabel=dict(bgcolor=CARD, bordercolor=BORDER, font=dict(family=FONT, color=TEXT)),
    bargap=0.25,
)
pio.templates["dews"] = _template
pio.templates.default = "dews"
