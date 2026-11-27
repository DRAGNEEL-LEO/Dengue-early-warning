"""Reusable UI building blocks. Pages compose these; no business logic lives here."""
import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui import theme as T

PLOTLY_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
                 "toImageButtonOptions": {"format": "png", "scale": 2}}


def esc(x):
    return html.escape(str(x))


# ---------------------------------------------------------------- cards
_card_n = [0]


def reset_cards():
    _card_n[0] = 0


def card():
    """White bordered card. A stable per-run key gives it the CSS class st-key-card_N."""
    _card_n[0] += 1
    return st.container(border=True, key=f"card_{_card_n[0]}")


# ---------------------------------------------------------------- text blocks
def page_header(title, subtitle=None, tags=()):
    tag_html = " ".join(tag(*t) if isinstance(t, tuple) else tag(t) for t in tags)
    st.markdown(f"<div class='page-title'>{esc(title)} {tag_html}</div>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<div class='page-sub'>{subtitle}</div>", unsafe_allow_html=True)


def section(title, hint=None):
    h = f"<span class='hint'>{esc(hint)}</span>" if hint else ""
    st.markdown(f"<div class='section'>{esc(title)} {h}</div>", unsafe_allow_html=True)


TAG_TEXT = {"sim": "Simulated estimate", "demo": "Demo assumption", "real": "Model forecast",
            "gen": "Generated · not sent", "scenario": "Scenario"}


def tag(kind, text=None):
    cls = "sim" if kind == "scenario" else kind
    return f"<span class='tag {cls}'>{esc(text or TAG_TEXT.get(kind, kind))}</span>"


def risk_badge(tier):
    return (f"<span class='badge' style='background:{T.RISK_BG[tier]};color:{T.RISK_FG[tier]}'>"
            f"{esc(tier)}</span>")


def pill(text, kind=""):
    return f"<span class='pill {kind}'>{text}</span>"


# ---------------------------------------------------------------- KPI cards and alerts
def kpi(col, label, value, foot="", accent=T.BLUE, unit=""):
    unit_html = f" <small>{esc(unit)}</small>" if unit else ""
    col.markdown(f"<div class='kpi' style='--accent:{accent}'><div class='label' title='{esc(label)}'>"
                 f"{esc(label)}</div><div class='value'>{value}{unit_html}</div>"
                 f"<div class='foot'>{foot}&nbsp;</div></div>", unsafe_allow_html=True)


def kpi_row(items):
    """items: list of dicts with label, value and optional foot, accent, unit."""
    cols = st.columns(len(items))
    for col, it in zip(cols, items):
        kpi(col, **it)


ALERT_ICON = {"critical": "⛔", "warning": "⚠️", "info": "ℹ️", "ok": "✅"}


def alert(kind, title, detail="", target=None):
    box = target or st
    box.markdown(f"<div class='alert {kind}'><div class='ic'>{ALERT_ICON[kind]}</div><div>"
                 f"<div class='t'>{title}</div><div class='d'>{detail}</div></div></div>", unsafe_allow_html=True)


def kv_list(pairs, target=None):
    box = target or st
    rows = "".join(f"<div class='k'>{esc(k)}</div><div class='v'>{v}</div>" for k, v in pairs)
    box.markdown(f"<div class='kv'>{rows}</div>", unsafe_allow_html=True)


def empty_state(text):
    st.markdown(f"<div class='alert info'><div class='ic'>ℹ️</div><div><div class='d' style='margin:0'>"
                f"{text}</div></div></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------- tables
def risk_table(df, risk_col="Risk", height=None, column_config=None, fmt=None):
    sty = df.style.map(lambda v: f"background-color:{T.RISK_BG[v]};color:{T.RISK_FG[v]};font-weight:600"
                       if v in T.RISK_BG else "", subset=[risk_col] if risk_col in df.columns else [])
    if "Status" in df.columns:
        sty = sty.map(lambda v: "color:#B91C1C;font-weight:600" if str(v).startswith("⚠")
                      else ("color:#15803D;font-weight:600" if str(v).startswith("✓") else ""), subset=["Status"])
    if fmt:
        sty = sty.format(fmt)
    kwargs = {"hide_index": True, "width": "stretch", "column_config": column_config or {}}
    if height:
        kwargs["height"] = height
    st.dataframe(sty, **kwargs)


def num(label, fmt="%d", help=None):
    return st.column_config.NumberColumn(label, format=fmt, help=help)


def bar(label, fmt="%.0f%%", maxv=100):
    return st.column_config.ProgressColumn(label, format=fmt, min_value=0, max_value=maxv)


# ---------------------------------------------------------------- charts
def chart(fig, key=None, height=None, select=False):
    fig.update_layout(template="dews", paper_bgcolor=T.CARD, plot_bgcolor=T.CARD)
    if height:
        fig.update_layout(height=height)
    kwargs = {"theme": None, "config": PLOTLY_CONFIG, "width": "stretch", "key": key}
    if select:
        kwargs.update(on_select="rerun", selection_mode="points")
    return st.plotly_chart(fig, **kwargs)


def hbar(df, y, series, colors, title=None, height=None, xtitle=None, stacked=True, hover_fmt=",.0f"):
    """Horizontal bars, first row of df on top."""
    fig = go.Figure()
    for s, c in zip(series, colors):
        fig.add_bar(y=df[y], x=df[s], name=s, orientation="h", marker_color=c,
                    hovertemplate=f"%{{y}}<br>{s}: %{{x:{hover_fmt}}}<extra></extra>")
    fig.update_layout(barmode="stack" if stacked else "group", title=title,
                      height=height or max(220, 30 * len(df) + 80),
                      yaxis=dict(autorange="reversed", title=None), xaxis=dict(title=xtitle))
    return fig


def ward_grid(fc, value_col, risk_col, selected=None, title=None, width_px=1280, max_units=None):
    """Schematic ward grid: one square tile per ward, grouped by city in ward-ID order, coloured by risk tier.
    City blocks wrap onto a new row when they would exceed max_units. NOT geographic: the dataset has no
    coordinates or boundaries."""
    cities = list(dict.fromkeys(fc.sort_values(["city", "ward_id"])["city"]))
    ncol = 5 if len(cities) > 1 else 10
    gap = 0.9
    # lay out city blocks, wrapping rows of blocks
    blocks, x_off, y_off, row_h, widest = [], 0.0, 0.0, 0, 0.0
    for city in cities:
        n = int((fc["city"] == city).sum())
        cols = min(ncol, n)
        rows = -(-n // cols)
        if max_units and x_off > 0 and x_off + cols > max_units:
            y_off -= row_h + 1.0
            x_off, row_h = 0.0, 0
        blocks.append((city, x_off, y_off, cols))
        widest = max(widest, x_off + cols)
        x_off += cols + gap
        row_h = max(row_h, rows)
    shapes, xs, ys, texts, hover, custom, annots = [], [], [], [], [], [], []
    for city, bx, by, cols in blocks:
        g = fc[fc["city"] == city].sort_values("ward_id").reset_index(drop=True)
        for i, r in g.iterrows():
            cx, cy = bx + (i % cols), by - (i // cols)
            tier = r[risk_col]
            line = dict(color=T.TEXT, width=3) if r["ward_id"] == selected else dict(color="#FFFFFF", width=2)
            shapes.append(dict(type="rect", x0=cx + 0.03, x1=cx + 0.97, y0=cy - 0.97, y1=cy - 0.03,
                               fillcolor=T.RISK[tier], line=line, layer="below"))
            xs.append(cx + 0.5)
            ys.append(cy - 0.5)
            texts.append(f"<b>{r['ward_id'].split('_')[-1]}</b><br>{r[value_col]:.0f}")
            hover.append(f"<b>{r['ward_id']}</b> ({city})<br>Risk: {tier}<br>Forecast: {r[value_col]:.1f} cases")
            custom.append(r["ward_id"])
        annots.append(dict(x=bx, y=by + 0.05, text=f"<b>{city}</b>", showarrow=False, xanchor="left",
                           yanchor="bottom", font=dict(size=12.5, color=T.MUTED)))
    unit = width_px / max(widest, 1)
    fig = go.Figure(go.Scatter(
        x=xs, y=ys, mode="markers+text", text=texts, customdata=custom, hovertext=hover, hoverinfo="text",
        textfont=dict(color="#FFFFFF", size=11 if unit > 38 else 9.5),
        marker=dict(size=max(18, int(unit * 0.8)), color="rgba(0,0,0,0.01)", symbol="square"), showlegend=False))
    for tier in T.TIERS:
        fig.add_scatter(x=[None], y=[None], mode="markers", name=tier,
                        marker=dict(size=12, symbol="square", color=T.RISK[tier]))
    y_min = min(by - (-(-int((fc["city"] == c).sum()) // cols)) for c, bx, by, cols in blocks)
    span_y = 0.75 - y_min
    fig.update_layout(shapes=shapes, annotations=annots, title=title, dragmode=False,
                      height=int(span_y * unit + 70),
                      xaxis=dict(visible=False, range=[-0.05, widest + 0.05], fixedrange=True),
                      yaxis=dict(visible=False, range=[y_min - 0.05, 0.75], scaleanchor="x", scaleratio=1,
                                 fixedrange=True),
                      legend=dict(orientation="h", y=-0.01, yanchor="top", x=0), margin=dict(l=4, r=4, t=8, b=34))
    return fig


def tier_counts(df, by, risk_col):
    return (pd.crosstab(df[by], df[risk_col]).reindex(columns=list(T.TIERS), fill_value=0))
