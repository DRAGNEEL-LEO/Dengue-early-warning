"""Reusable UI building blocks for the dark surveillance design. Pages compose these; no business logic here."""
import html
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui import theme as T

PLOTLY_CONFIG = {"displaylogo": False, "displayModeBar": False}


def esc(x):
    return html.escape(str(x))


# ---------------------------------------------------------------- cards
_card_n = [0]


def reset_cards():
    _card_n[0] = 0


def card():
    """Dark bordered panel. A stable per-run key gives it the CSS class st-key-card_N."""
    _card_n[0] += 1
    return st.container(border=True, key=f"card_{_card_n[0]}")


# ---------------------------------------------------------------- header and titles
def surv_header(title, subtitle, chips=()):
    chip_html = "".join(f"<span class='chip {cls}'>{'<span class=dot></span>' if dot else ''}{txt}</span>"
                        for txt, cls, dot in chips)
    st.markdown(f"<div class='surv'><h1>{esc(title)}</h1><p>{subtitle}</p>"
                f"{'<div class=meta>' + chip_html + '</div>' if chips else ''}</div>", unsafe_allow_html=True)


def panel_title(title, right=None, sub=None, dot=False):
    r = ""
    if right:
        r = f"<span class='r'>{'<span class=dot></span>' if dot else ''}{right}</span>"
    s = f"<small>{esc(sub)}</small>" if sub else ""
    st.markdown(f"<div class='ptitle'><span class='t'>{esc(title)}{s}</span>{r}</div>", unsafe_allow_html=True)


TAG_TEXT = {"sim": "Simulated estimate", "demo": "Demo assumption", "real": "Model forecast",
            "gen": "Generated", "scenario": "Scenario"}


def tag(kind, text=None):
    cls = "sim" if kind == "scenario" else kind
    return f"<span class='tag {cls}'>{esc(text or TAG_TEXT.get(kind, kind))}</span>"


def risk_badge(tier):
    return f"<span class='badge' style='background:{T.RISK_BG[tier]};color:{T.RISK_FG[tier]}'>{esc(tier)}</span>"


# ---------------------------------------------------------------- gauges
GAUGE_STOPS = {"amber": (T.YELLOW, T.AMBER, T.ORANGE), "gold": ("#C9B04F", T.YELLOW, T.AMBER),
               "red": (T.ORANGE, "#EE5F3E", T.RED)}


def _pt(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def gauge_svg(value_text, frac, label, delta_text="", delta_cls="flat", palette="amber", uid="g"):
    """270-degree arc gauge with a soft glow. frac in [0, 1]."""
    frac = max(0.0, min(1.0, float(frac)))
    cx, cy, r, w = 100, 96, 78, 9
    start, sweep = 135, 270
    x0, y0 = _pt(cx, cy, r, start)
    x1, y1 = _pt(cx, cy, r, start + sweep)
    track = f"M{x0:.1f},{y0:.1f} A{r},{r} 0 1 1 {x1:.1f},{y1:.1f}"
    arc = ""
    if frac > 0.002:
        xe, ye = _pt(cx, cy, r, start + sweep * frac)
        large = 1 if sweep * frac > 180 else 0
        arc = (f"<path d='M{x0:.1f},{y0:.1f} A{r},{r} 0 {large} 1 {xe:.1f},{ye:.1f}' fill='none' "
               f"stroke='url(#gr{uid})' stroke-width='{w}' stroke-linecap='round' filter='url(#gl{uid})'/>"
               f"<circle cx='{xe:.1f}' cy='{ye:.1f}' r='5.5' fill='{GAUGE_STOPS[palette][2]}' filter='url(#gl{uid})'/>")
    c1, c2, c3 = GAUGE_STOPS[palette]
    return (f"<svg viewBox='0 0 200 178' xmlns='http://www.w3.org/2000/svg'>"
            f"<defs><linearGradient id='gr{uid}' x1='0' y1='1' x2='1' y2='0'><stop offset='0' stop-color='{c1}'/>"
            f"<stop offset='.55' stop-color='{c2}'/><stop offset='1' stop-color='{c3}'/></linearGradient>"
            f"<filter id='gl{uid}' x='-30%' y='-30%' width='160%' height='160%'><feGaussianBlur stdDeviation='3.2' "
            f"result='b'/><feMerge><feMergeNode in='b'/><feMergeNode in='SourceGraphic'/></feMerge></filter></defs>"
            f"<path d='{track}' fill='none' stroke='#2A292E' stroke-width='{w}' stroke-linecap='round'/>{arc}"
            f"<text x='100' y='100' text-anchor='middle' font-family='Inter, sans-serif' font-size='38' font-weight='300' "
            f"fill='{T.TEXT}'>{esc(value_text)}</text>"
            f"<text x='100' y='126' text-anchor='middle' font-family='Inter, sans-serif' font-size='15' "
            f"fill='{T.TEXT_2}'>{esc(label)}</text>"
            f"<text x='100' y='150' text-anchor='middle' class='delta {delta_cls}' font-family='Inter, sans-serif' "
            f"font-size='17' font-weight='500' fill='{dict(up=T.ORANGE, down=T.GREEN, flat=T.MUTED)[delta_cls]}'>"
            f"{esc(delta_text)}</text></svg>")


def gauges(items):
    """items: list of dicts(value, frac, label, delta, delta_cls, palette, sub)."""
    cells = "".join(
        f"<div class='gauge'>{gauge_svg(it['value'], it['frac'], it['label'], it.get('delta', ''), it.get('delta_cls', 'flat'), it.get('palette', 'amber'), f'g{i}')}"
        f"<div class='sub'>{it.get('sub', '')}</div></div>" for i, it in enumerate(items))
    st.markdown(f"<div class='gauges'>{cells}</div>", unsafe_allow_html=True)


def pct_change(new, old):
    """(text, css class) for a change versus a previous value, or a neutral marker."""
    if old is None or old == 0 or pd.isna(old):
        return ("new" if new else "–"), "flat"
    p = 100 * (new - old) / old
    if abs(p) < 0.5:
        return "0%", "flat"
    return (f"▲ {abs(p):.0f}%" if p > 0 else f"▼ {abs(p):.0f}%"), ("up" if p > 0 else "down")


# ---------------------------------------------------------------- rows, lists, numbers
def bar_rows(rows, max_value=None, compact=False):
    """rows: dicts(name, value, delta, delta_cls, color, unit). Bar length relative to max_value."""
    mx = max_value or max([r["value"] for r in rows] + [1e-9])
    out = []
    for r in rows:
        w = 0 if mx <= 0 else max(2, 100 * r["value"] / mx)
        col = r.get("color", T.AMBER)
        dcls = {"up": T.ORANGE, "down": T.GREEN, "flat": T.MUTED}[r.get("delta_cls", "flat")]
        vtxt = r.get("value_text") or f"{r['value']:,.0f}"
        out.append(
            f"<div class='row'><span class='n'><i style='background:{col};box-shadow:0 0 6px {col}'></i>{esc(r['name'])}</span>"
            f"<span class='track'><span class='fill' style='display:block;width:{w:.0f}%;"
            f"background:linear-gradient(90deg,{col}66,{col});box-shadow:0 0 8px {col}88'></span></span>"
            f"<span class='p' style='color:{dcls}'>{esc(r.get('delta', ''))}</span>"
            f"<span class='v'>{vtxt}<small>{esc(r.get('unit', ''))}</small></span></div>")
    st.markdown(f"<div class='rows {'compact' if compact else ''}'>{''.join(out)}</div>", unsafe_allow_html=True)


def source_list(items):
    """items: (label, value_text, highlight)."""
    cells = "".join(f"<span class='k {'hi' if hi else ''}'>{esc(k)}</span><span class='v {'hi' if hi else ''}'>{v}</span>"
                    for k, v, hi in items)
    st.markdown(f"<div class='src'>{cells}</div>", unsafe_allow_html=True)


def big_number(col, value, label, delta="", delta_cls="flat", amber=False):
    d = f"<br><span class='delta {delta_cls}' style='font-size:13px'>{esc(delta)}</span>" if delta else ""
    col.markdown(f"<div class='bign {'amber' if amber else ''}'>{value}</div><div class='bigl'>{esc(label)}{d}</div>",
                 unsafe_allow_html=True)


def kpi(col, label, value, foot="", accent=T.AMBER, unit=""):
    u = f" <small>{esc(unit)}</small>" if unit else ""
    col.markdown(f"<div class='kpi' style='--accent:{accent}'><div class='label' title='{esc(label)}'>{esc(label)}</div>"
                 f"<div class='value'>{value}{u}</div><div class='foot'>{foot}&nbsp;</div></div>", unsafe_allow_html=True)


def kpi_row(items):
    cols = st.columns(len(items))
    for col, it in zip(cols, items):
        kpi(col, **it)


def alert(kind, title, detail="", target=None):
    (target or st).markdown(f"<div class='alert {kind}'><span class='ic'></span><div><div class='t'>{title}</div>"
                            f"<div class='d'>{detail}</div></div></div>", unsafe_allow_html=True)


def kv_list(pairs, target=None):
    rows = "".join(f"<div class='k'>{esc(k)}</div><div class='v'>{v}</div>" for k, v in pairs)
    (target or st).markdown(f"<div class='kv'>{rows}</div>", unsafe_allow_html=True)


def empty_state(text):
    alert("info", text)


def page_header(title, subtitle=None, tags=()):
    """Secondary pages: same uppercase header style, smaller ridge band."""
    tag_html = " ".join(tag(*t) if isinstance(t, tuple) else tag(t) for t in tags)
    st.markdown(f"<div class='surv' style='padding-bottom:14px'><h1 style='font-size:26px'>{esc(title)} {tag_html}</h1>"
                f"<p>{subtitle or ''}</p></div>", unsafe_allow_html=True)


def section(title, hint=None):
    panel_title(title, sub=hint)


# ---------------------------------------------------------------- tables
def risk_table(df, risk_col="Risk", height=None, column_config=None, fmt=None):
    sty = df.style.map(lambda v: f"color:{T.RISK_FG[v]};font-weight:500" if v in T.RISK_FG else "",
                       subset=[risk_col] if risk_col in df.columns else [])
    if "Status" in df.columns:
        sty = sty.map(lambda v: f"color:{T.RED};font-weight:500" if str(v).startswith("Shortage") or str(v).startswith("⚠")
                      else (f"color:{T.GREEN}" if str(v).startswith("Supplied") or str(v).startswith("✓") else ""),
                      subset=["Status"])
    if fmt:
        sty = sty.format(fmt)
    kw = {"hide_index": True, "width": "stretch", "column_config": column_config or {}}
    if height:
        kw["height"] = height
    st.dataframe(sty, **kw)


def num(label, fmt="%d", help=None):
    return st.column_config.NumberColumn(label, format=fmt, help=help)


def bar(label, fmt="%.0f%%", maxv=100):
    return st.column_config.ProgressColumn(label, format=fmt, min_value=0, max_value=maxv)


# ---------------------------------------------------------------- charts
def chart(fig, key=None, height=None, select=False):
    fig.update_layout(template="surv")
    if height:
        fig.update_layout(height=height)
    kw = {"theme": None, "config": PLOTLY_CONFIG, "width": "stretch", "key": key}
    if select:
        kw.update(on_select="rerun", selection_mode="points")
    return st.plotly_chart(fig, **kw)


def glow_line(fig, x, y, color, name, show_points=True, width=2.2, dash=None, legend=True):
    """A line with a soft glow: wide translucent strokes underneath, then the line and luminous points."""
    for w, a in ((14, 0.06), (8, 0.12)):
        fig.add_scatter(x=x, y=y, mode="lines", line=dict(color=_rgba(color, a), width=w, shape="spline", smoothing=0.6),
                        hoverinfo="skip", showlegend=False)
    fig.add_scatter(x=x, y=y, mode="lines+markers" if show_points else "lines", name=name, showlegend=legend,
                    line=dict(color=color, width=width, shape="spline", smoothing=0.6, dash=dash),
                    marker=dict(size=7, color=color, line=dict(color=_rgba("#FFFFFF", 0.35), width=1)))
    return fig


def _rgba(hex_color, a):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{a})"


def hbar(df, y, series, colors, title=None, height=None, xtitle=None, stacked=True, hover_fmt=",.0f"):
    fig = go.Figure()
    for s, c in zip(series, colors):
        fig.add_bar(y=df[y], x=df[s], name=s, orientation="h", marker=dict(color=c, line=dict(width=0)),
                    hovertemplate=f"%{{y}}<br>{s}: %{{x:{hover_fmt}}}<extra></extra>")
    fig.update_layout(barmode="stack" if stacked else "group", title=title,
                      height=height or max(220, 26 * len(df) + 80),
                      yaxis=dict(autorange="reversed", title=None), xaxis=dict(title=xtitle))
    return fig


def tier_counts(df, by, risk_col):
    return pd.crosstab(df[by], df[risk_col]).reindex(columns=list(T.TIERS), fill_value=0)
