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


def risk_treemap(fc, value_col, risk_col, height=430):
    """Treemap: city -> ward. Tile area = forecast cases, colour = risk tier. Shows where cases concentrate.
    Not geographic: the dataset has no coordinates or boundaries."""
    d = fc.sort_values(["city", "ward_id"])
    total = float(d[value_col].clip(lower=0).sum())
    # tiny floor so near-zero wards stay visible; labels always show the real forecast
    size = d[value_col].clip(lower=0).clip(lower=max(total, 1) * 0.002)
    ids, labels, parents, values, colors, text, hover, fcol = [], [], [], [], [], [], [], []
    for city, g in d.groupby("city", sort=True):
        sz = size[g.index]
        ids.append(city); labels.append(city); parents.append(""); values.append(float(sz.sum()))
        colors.append("#F1F5F9")
        fcol.append(T.TEXT)
        n_hc = int(g[risk_col].isin(["High", "Critical"]).sum())
        text.append(f"{g[value_col].sum():.0f} cases · {n_hc} High/Critical")
        hover.append(f"<b>{city}</b><br>{g[value_col].sum():.0f} forecast cases<br>{len(g)} wards, {n_hc} High/Critical")
    for i, r in d.iterrows():
        ids.append(r["ward_id"]); labels.append(r["ward_id"].replace("_Ward_", " ")); parents.append(r["city"])
        values.append(float(size[i])); colors.append(T.RISK[r[risk_col]]); fcol.append("#FFFFFF")
        text.append(f"{r[value_col]:.1f}")
        hover.append(f"<b>{r['ward_id']}</b> ({r['city']})<br>Risk: {r[risk_col]}<br>Forecast: {r[value_col]:.1f} cases")
    fig = go.Figure(go.Treemap(
        ids=ids, labels=labels, parents=parents, values=values, branchvalues="total", text=text,
        hovertext=hover, hoverinfo="text", textinfo="label+text", sort=True,
        marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2), pad=dict(t=24, l=3, r=3, b=3)),
        textfont=dict(family=T.FONT, size=12, color=fcol),
        outsidetextfont=dict(family=T.FONT, color=T.TEXT, size=13),
        pathbar=dict(visible=False), tiling=dict(packing="squarify")))
    for tier in T.TIERS:
        fig.add_scatter(x=[None], y=[None], mode="markers", name=tier,
                        marker=dict(size=12, symbol="square", color=T.RISK[tier]))
    fig.update_layout(height=height, margin=dict(l=2, r=2, t=6, b=36),
                      xaxis=dict(visible=False), yaxis=dict(visible=False),
                      legend=dict(orientation="h", y=-0.02, yanchor="top", x=0))
    return fig


def risk_matrix(df, value_col, risk_col, tiers, size_col=None, selected=None, height=430):
    """Bubble chart: population density (x) vs forecast cases (y), bubble = bed demand, colour = risk tier.
    Top-right = high risk AND dense, which is what the allocation priority favours."""
    fig = go.Figure()
    sz = df[size_col] if size_col else pd.Series(1, index=df.index)
    smax = max(float(sz.max()), 1.0)
    for tier in T.TIERS:
        g = df[df[risk_col] == tier]
        if g.empty:
            fig.add_scatter(x=[None], y=[None], mode="markers", name=tier,
                            marker=dict(size=12, color=T.RISK[tier]))
            continue
        s = sz[g.index]
        fig.add_scatter(
            x=g["population_density_sqkm"], y=g[value_col], mode="markers", name=tier, customdata=g["ward_id"],
            marker=dict(size=10 + 26 * (s / smax) ** 0.5, color=T.RISK[tier], opacity=0.85,
                        line=dict(color="#FFFFFF", width=1.5)),
            text=[f"<b>{w}</b> ({c})<br>Risk: {tier}<br>Forecast: {v:.1f} cases<br>Density: {d:,.0f}/km²"
                  + (f"<br>Bed demand: {b:.0f}" if size_col else "")
                  for w, c, v, d, b in zip(g["ward_id"], g["city"], g[value_col], g["population_density_sqkm"], s)],
            hoverinfo="text")
    if selected is not None and selected in set(df["ward_id"]):
        r = df[df["ward_id"] == selected].iloc[0]
        right_half = r["population_density_sqkm"] > df["population_density_sqkm"].median()
        fig.add_scatter(x=[r["population_density_sqkm"]], y=[r[value_col]], mode="markers+text",
                        text=[f"{selected}   " if right_half else f"   {selected}"],
                        textposition="middle left" if right_half else "middle right", showlegend=False,
                        hoverinfo="skip",
                        textfont=dict(size=12, color=T.TEXT),
                        marker=dict(size=40, color="rgba(0,0,0,0)", line=dict(color=T.TEXT, width=2.5)))
    for tier in ("High", "Critical"):
        fig.add_hline(y=tiers[tier], line=dict(color=T.RISK[tier], width=1, dash="dot"),
                      annotation_text=f"{tier} ≥ {tiers[tier]:g}", annotation_position="top left",
                      annotation_font=dict(size=11, color=T.RISK[tier]))
    fig.update_layout(height=height, xaxis_title="Population density (people per km²)",
                      yaxis_title="Forecast cases per week", hovermode="closest", dragmode=False,
                      xaxis=dict(tickformat=",.0f"))
    return fig


def tier_counts(df, by, risk_col):
    return (pd.crosstab(df[by], df[risk_col]).reindex(columns=list(T.TIERS), fill_value=0))
