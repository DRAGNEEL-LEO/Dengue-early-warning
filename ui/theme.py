"""Design system for the dark surveillance dashboard: colour tokens, CSS and the shared Plotly template.

Everything is local: the Inter font is served from static/fonts (SIL OFL), textures and the header silhouette are
inline SVG, so the interface makes no external requests.
"""
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ---- tokens ------------------------------------------------------------------------------------------------
BG = "#0D0D0E"
PANEL = "#17171A"
PANEL_2 = "#1E1E22"
BORDER = "#2B2A2E"
BORDER_HI = "#3A3833"
TEXT = "#ECE7DF"
TEXT_2 = "#A39E96"
MUTED = "#6E6A64"
AMBER = "#F2A33A"
ORANGE = "#E8772E"
YELLOW = "#E9C46A"
RED = "#E5484D"
GREEN = "#7FB069"
GRID = "#26252A"

RISK = {"Low": GREEN, "Medium": YELLOW, "High": ORANGE, "Critical": RED}
RISK_BG = {"Low": "#1F2A1B", "Medium": "#2D2715", "High": "#33200F", "Critical": "#361516"}
RISK_FG = {"Low": "#A7CF8E", "Medium": "#F0D58C", "High": "#F5A26B", "Critical": "#F28B8E"}
TIERS = ("Low", "Medium", "High", "Critical")
FONT = "Inter, 'Segoe UI', system-ui, -apple-system, Roboto, Arial, sans-serif"

# Abstract layered ridges for the header (pure SVG, no image file)
_RIDGES = (
    "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1440 220' preserveAspectRatio='none'>"
    "<defs><linearGradient id='g' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='%23FFFFFF' stop-opacity='0.16'/>"
    "<stop offset='1' stop-color='%23FFFFFF' stop-opacity='0'/></linearGradient></defs>"
    "<path d='M0 150 C 180 90 300 120 430 95 C 560 70 640 30 760 55 C 900 85 980 20 1110 40 C 1240 60 1330 25 1440 45 L1440 220 L0 220Z' fill='url(%23g)'/>"
    "<path d='M0 175 C 200 130 330 160 470 135 C 610 110 720 80 860 105 C 1000 130 1080 70 1210 90 C 1320 105 1390 85 1440 95 L1440 220 L0 220Z' fill='%23FFFFFF' fill-opacity='0.07'/>"
    "<path d='M0 60 C 240 40 420 70 640 52 C 860 34 1040 10 1440 22' fill='none' stroke='%23FFFFFF' stroke-opacity='0.11' stroke-width='1.2'/>"
    "</svg>")
_NOISE = (
    "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'>"
    "<feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/></filter>"
    "<rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.05'/></svg>")

CSS = f"""
<style>
html, body, .stApp, [class*="css"] {{ font-family: {FONT}; }}
.stApp {{ background-color:{BG};
  background-image: url("{_NOISE}"), radial-gradient(1200px 500px at 70% -10%, rgba(255,255,255,0.045), transparent 60%),
                    radial-gradient(900px 600px at 0% 100%, rgba(242,163,58,0.035), transparent 60%); }}
.block-container {{ padding-top: 1.0rem; padding-bottom: 2.2rem; max-width: 1480px; }}
header[data-testid="stHeader"] {{ background: transparent; }}

/* ---------- surveillance header ---------- */
.surv {{ position:relative; padding:22px 4px 30px 4px; margin:0 0 10px 0; overflow:hidden; }}
.surv:before {{ content:""; position:absolute; inset:-10px -40px 0 22%; background:url("{_RIDGES}") no-repeat bottom/100% 100%;
  opacity:.95; pointer-events:none; -webkit-mask-image:linear-gradient(90deg, transparent 0%, #000 35%, #000 85%, transparent 100%);
  mask-image:linear-gradient(90deg, transparent 0%, #000 35%, #000 85%, transparent 100%); }}
.surv h1 {{ position:relative; font-size:30px; font-weight:500; letter-spacing:1.2px; text-transform:uppercase; color:{TEXT};
  margin:0 0 6px 0; padding:0; line-height:1.15; }}
.surv p {{ position:relative; max-width:760px; font-size:13.5px; line-height:1.55; color:{TEXT_2}; margin:0; }}
.surv .meta {{ position:relative; margin-top:10px; display:flex; gap:8px; flex-wrap:wrap; }}
.chip {{ display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border:1px solid {BORDER}; border-radius:4px;
  background:rgba(23,23,26,.85); color:{TEXT_2}; font-size:11.5px; letter-spacing:.2px; white-space:nowrap; }}
.chip b {{ color:{TEXT}; font-weight:500; }}
.chip .dot {{ width:7px; height:7px; border-radius:50%; background:{AMBER}; box-shadow:0 0 8px {AMBER}; }}
.chip.ok .dot {{ background:{GREEN}; box-shadow:0 0 8px {GREEN}; }}
.chip.off .dot {{ background:{ORANGE}; box-shadow:0 0 8px {ORANGE}; }}

/* ---------- panels ---------- */
div[class*="st-key-card_"] {{ background:linear-gradient(180deg, rgba(30,30,34,.92), rgba(23,23,26,.96));
  border:1px solid {BORDER} !important; border-radius:6px; }}
.ptitle {{ display:flex; justify-content:space-between; align-items:center; gap:10px; margin:0 0 10px 0; }}
.ptitle .t {{ font-size:19px; font-weight:400; color:{TEXT}; letter-spacing:.2px; }}
.ptitle .t small {{ font-size:12px; color:{MUTED}; margin-left:8px; }}
.ptitle .r {{ display:inline-flex; align-items:center; gap:6px; padding:3px 9px; border:1px solid {BORDER_HI};
  border-radius:4px; font-size:11.5px; color:{TEXT_2}; background:rgba(13,13,14,.6); text-transform:uppercase; letter-spacing:.5px; }}
.ptitle .r b {{ color:{TEXT}; font-weight:600; }}
.ptitle .r .dot {{ width:8px; height:8px; border-radius:50%; background:{ORANGE}; box-shadow:0 0 8px {ORANGE}; }}

/* ---------- gauges ---------- */
.gauges {{ display:grid; grid-template-columns:repeat(3,1fr); gap:0; }}
.gauge {{ text-align:center; padding:4px 6px; border-right:1px solid {BORDER}; }}
.gauge:last-child {{ border-right:none; }}
.gauge svg {{ width:100%; max-width:192px; height:auto; display:block; margin:0 auto; overflow:visible; }}
.gauge .lab {{ font-size:12.5px; color:{TEXT_2}; margin-top:-2px; }}
.gauge .sub {{ font-size:11px; color:{MUTED}; margin-top:0; white-space:nowrap; }}
.delta {{ font-size:13px; font-weight:500; }}
.delta.up {{ color:{ORANGE}; }} .delta.down {{ color:{GREEN}; }} .delta.flat {{ color:{MUTED}; }}

/* ---------- bar rows (trends / sources) ---------- */
.rows {{ display:flex; flex-direction:column; gap:12px; }}
.row {{ display:grid; grid-template-columns: 132px 1fr 62px 84px; align-items:center; gap:12px; font-size:13.5px; }}
.rows.compact .row {{ grid-template-columns: 74px 1fr 48px 58px; gap:8px; font-size:12.5px; }}
.rows.compact .row .v {{ font-size:15px; }}
.row .n {{ color:{TEXT}; display:flex; align-items:center; gap:8px; white-space:nowrap; }}
.row .n i {{ width:8px; height:8px; border-radius:50%; display:inline-block; }}
.row .track {{ height:6px; background:#232228; border-radius:3px; overflow:hidden; }}
.row .fill {{ height:100%; border-radius:3px; }}
.row .p {{ font-size:12.5px; text-align:left; }}
.row .v {{ text-align:right; color:{TEXT}; font-size:17px; font-weight:300; }}
.row .v small {{ font-size:10.5px; color:{MUTED}; margin-left:3px; }}
.src {{ display:grid; grid-template-columns:1fr auto; gap:9px 12px; font-size:13px; }}
.src .k {{ color:{TEXT_2}; }} .src .k:before {{ content:"· "; color:{MUTED}; }}
.src .k.hi {{ color:{AMBER}; }}
.src .v {{ text-align:right; color:{TEXT}; font-weight:500; }}
.src .v.hi {{ color:{AMBER}; }}

/* ---------- big numbers ---------- */
.bign {{ font-size:34px; font-weight:300; color:{TEXT}; line-height:1.1; letter-spacing:.3px; }}
.bign.amber {{ color:{AMBER}; }}
.bign small {{ font-size:14px; color:{MUTED}; font-weight:400; }}
.bigl {{ font-size:12.5px; color:{TEXT_2}; margin-top:2px; }}
.stat-box {{ border:1px solid {BORDER}; border-radius:6px; padding:12px 14px; background:rgba(13,13,14,.45); }}

/* ---------- kpi (secondary pages) ---------- */
.kpi {{ border:1px solid {BORDER}; border-radius:6px; padding:12px 14px; background:linear-gradient(180deg,#1C1C20,#17171A);
  min-height:104px; position:relative; margin-bottom:10px; }}
.kpi:after {{ content:""; position:absolute; left:14px; right:14px; bottom:0; height:2px; background:var(--accent);
  box-shadow:0 0 10px var(--accent); opacity:.85; }}
.kpi .label {{ font-size:11.5px; color:{TEXT_2}; text-transform:uppercase; letter-spacing:.6px; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }}
.kpi .value {{ font-size:30px; font-weight:300; color:{TEXT}; line-height:1.25; margin-top:4px; }}
.kpi .value small {{ font-size:14px; color:{MUTED}; }}
.kpi .foot {{ font-size:11.5px; color:{MUTED}; margin-top:2px; }}

/* ---------- alerts ---------- */
.alert {{ border-radius:6px; padding:10px 14px; border:1px solid; display:flex; gap:10px; align-items:flex-start;
  margin-bottom:10px; background:rgba(13,13,14,.55); }}
.alert .ic {{ width:8px; height:8px; margin-top:6px; border-radius:50%; flex:0 0 8px; }}
.alert .t {{ font-weight:500; font-size:13.5px; color:{TEXT}; }}
.alert .d {{ font-size:12.5px; color:{TEXT_2}; margin-top:2px; }}
.alert.critical {{ border-color:#5A2326; }} .alert.critical .ic {{ background:{RED}; box-shadow:0 0 10px {RED}; }}
.alert.warning {{ border-color:#5A3A1C; }} .alert.warning .ic {{ background:{ORANGE}; box-shadow:0 0 10px {ORANGE}; }}
.alert.info {{ border-color:{BORDER_HI}; }} .alert.info .ic {{ background:{AMBER}; box-shadow:0 0 10px {AMBER}; }}
.alert.ok {{ border-color:#2E3B27; }} .alert.ok .ic {{ background:{GREEN}; box-shadow:0 0 10px {GREEN}; }}

/* ---------- badges / tags ---------- */
.badge {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:11.5px; font-weight:500; }}
.tag {{ display:inline-block; padding:2px 7px; border-radius:4px; font-size:10.5px; font-weight:500; text-transform:uppercase;
  letter-spacing:.6px; border:1px solid {BORDER_HI}; color:{TEXT_2}; background:rgba(13,13,14,.6); vertical-align:middle; }}
.tag.sim {{ color:{YELLOW}; border-color:#4A3F1E; }}
.tag.demo {{ color:{ORANGE}; border-color:#4D3018; }}
.tag.real {{ color:{AMBER}; border-color:#4D3A1C; }}
.tag.gen {{ color:{TEXT_2}; }}

/* ---------- forecast cards ---------- */
.fc {{ border:1px solid {BORDER}; border-radius:6px; padding:14px 16px; background:linear-gradient(180deg,#1C1C20,#17171A); }}
.fc .h {{ font-size:11.5px; color:{TEXT_2}; text-transform:uppercase; letter-spacing:.6px; }}
.fc .w {{ font-size:12.5px; color:{MUTED}; margin-bottom:8px; }}
.fc .n {{ font-size:40px; font-weight:300; color:{TEXT}; line-height:1.05; }}
.fc .n small {{ font-size:13px; color:{MUTED}; }}
.fc .r {{ font-size:12.5px; color:{TEXT_2}; margin-top:6px; }}
.fc .tier {{ display:inline-block; margin-top:10px; padding:4px 10px; border-radius:4px; font-weight:500; font-size:13px; }}
.kv {{ display:grid; grid-template-columns:1fr auto; gap:7px 12px; font-size:13px; }}
.kv .k {{ color:{TEXT_2}; }} .kv .v {{ color:{TEXT}; text-align:right; font-weight:500; }}
.msg {{ border:1px solid {BORDER}; border-radius:6px; padding:12px 14px; white-space:pre-wrap; font-size:12.5px;
  line-height:1.55; color:{TEXT}; background:rgba(13,13,14,.6); font-family: ui-monospace, Consolas, monospace; }}
.msg-h {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; font-size:12px; color:{TEXT_2}; }}
.foot-note {{ font-size:11.5px; color:{MUTED}; }}
.side-foot {{ font-size:11.5px; color:#8E877D; line-height:1.55; }}
.side-foot b {{ color:{TEXT}; font-weight:500; }}
.side-brand {{ font-size:12px; letter-spacing:1.6px; text-transform:uppercase; color:{AMBER}; font-weight:600; }}

/* ---------- streamlit details ---------- */
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] {{
  background:rgba(242,163,58,.08); box-shadow: inset 2px 0 0 {AMBER}; }}
section[data-testid="stSidebar"] [data-testid="stNavSectionHeader"] {{ color:{MUTED}; letter-spacing:1.4px; font-size:10.5px;
  text-transform:uppercase; }}
button[data-baseweb="tab"] p {{ font-weight:500; letter-spacing:.2px; }}
div[data-testid="stMetricValue"] {{ font-weight:300; }}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


# ---- Plotly template ----------------------------------------------------------------------------------------
_t = go.layout.Template()
_t.layout = go.Layout(
    font=dict(family=FONT, size=12, color=TEXT_2),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    colorway=[AMBER, ORANGE, YELLOW, RED, GREEN, "#C9B79C", "#8E877D"],
    margin=dict(l=8, r=8, t=30, b=8),
    xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=BORDER, ticks="", automargin=True,
               tickfont=dict(color=MUTED)),
    yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=BORDER, ticks="", automargin=True,
               tickfont=dict(color=MUTED)),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None,
                font=dict(size=11.5, color=TEXT_2), traceorder="normal", bgcolor="rgba(0,0,0,0)"),
    hoverlabel=dict(bgcolor=PANEL_2, bordercolor=BORDER_HI, font=dict(family=FONT, color=TEXT, size=12)),
    bargap=0.3,
)
pio.templates["surv"] = _t
pio.templates.default = "surv"

# ---- names used by page modules (mapped onto the surveillance palette) ----------------------------------------
BLUE, CYAN, SLATE, LIGHT_SLATE = AMBER, YELLOW, "#8E877D", "#3A3833"
CARD = PANEL
