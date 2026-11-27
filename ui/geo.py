"""Offline map of the project area: real district boundaries (BBS / UN OCHA via geoBoundaries, CC BY 3.0 IGO)
drawn as shapes, with one glowing marker per city corporation.

The dataset has no ward coordinates, so markers sit at the approximate city-corporation office locations in
data/geo/city_markers.csv (each checked to lie inside its district) and are labelled approximate. If an
authoritative data/geo/ward_points.csv (ward_id, lat, lon) is added, wards are plotted too.
"""
import json
import math
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui import theme as T

GEO_DIR = Path(__file__).resolve().parent.parent / "data" / "geo"
ATTRIBUTION = "District boundaries: BBS / UN OCHA via geoBoundaries (CC BY 3.0 IGO). City markers approximate."
DISTRICT_OF = {"Dhaka North": "Dhaka", "Dhaka South": "Dhaka", "Gazipur": "Gazipur", "Narayanganj": "Narayanganj",
               "Chattogram": "Chittagong"}
# label offsets (pixels) so the four Dhaka-area labels do not collide
LABEL_OFFSET = {"Dhaka North": (-70, -34), "Dhaka South": (-78, 26), "Gazipur": (8, -44),
                "Narayanganj": (66, 22), "Chattogram": (70, -18)}
RANGE = {"lon": (89.78, 92.22), "lat": (21.98, 24.42)}
ASPECT = 1 / math.cos(math.radians(23.2))      # keep shapes undistorted at this latitude


@st.cache_data(show_spinner=False)
def load_geo():
    d = json.loads((GEO_DIR / "bd_districts.json").read_text())
    markers = pd.read_csv(GEO_DIR / "city_markers.csv")
    wp = GEO_DIR / "ward_points.csv"
    wards = pd.read_csv(wp) if wp.exists() else None
    return d["districts"], markers, wards


def _rgba(hex_color, a):
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def _district_traces(fig, districts, fill_for=None, line_hi=True):
    """Background districts in one trace; the four project districts individually (with hover)."""
    xs, ys = [], []
    for dct in districts:
        if dct["focus"]:
            continue
        for ring in dct["rings"]:
            xs += [p[0] for p in ring] + [None]
            ys += [p[1] for p in ring] + [None]
    fig.add_scatter(x=xs, y=ys, mode="lines", fill="toself", fillcolor="#141416",
                    line=dict(color="#2A2827", width=0.7), hoverinfo="skip", showlegend=False)
    for dct in districts:
        if not dct["focus"]:
            continue
        fx, fy = [], []
        for ring in dct["rings"]:
            fx += [p[0] for p in ring] + [None]
            fy += [p[1] for p in ring] + [None]
        fill = fill_for(dct["name"]) if fill_for else "rgba(242,163,58,0.09)"
        fig.add_scatter(x=fx, y=fy, mode="lines", fill="toself", fillcolor=fill,
                        line=dict(color=_rgba(T.AMBER, 0.55 if line_hi else 0.35), width=1.1),
                        hoverinfo="text", hoveron="fills", text=f"{dct['name']} district", showlegend=False)


def _layout(fig, height, mini=False):
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=0, b=0), dragmode=False, showlegend=not mini,
        xaxis=dict(visible=False, range=list(RANGE["lon"]), fixedrange=True),
        yaxis=dict(visible=False, range=list(RANGE["lat"]), scaleanchor="x", scaleratio=ASPECT, fixedrange=True),
        legend=dict(orientation="h", x=0.01, y=0.01, yanchor="bottom", bgcolor="rgba(13,13,14,0.6)",
                    font=dict(size=11, color=T.TEXT_2)),
        hovermode="closest")
    return fig


def city_map(city_stats, selected=None, height=560):
    """city_stats: DataFrame with city, cases, risk (worst tier), n_high_crit, wards."""
    districts, markers, ward_pts = load_geo()
    fig = go.Figure()
    _district_traces(fig, districts)
    m = markers.merge(city_stats, on="city", how="inner")
    mx = max(float(m["cases"].max()), 1.0)
    for r in m.itertuples():
        col = T.RISK.get(r.risk, T.AMBER)
        core = 12 + 26 * math.sqrt(max(r.cases, 0) / mx)
        for mult, a in ((3.4, 0.05), (2.4, 0.09), (1.6, 0.18)):     # glow halo
            fig.add_scatter(x=[r.lon], y=[r.lat], mode="markers", hoverinfo="skip", showlegend=False,
                            marker=dict(size=core * mult, color=_rgba(col, a), line=dict(width=0)))
        if r.city == selected:
            fig.add_scatter(x=[r.lon], y=[r.lat], mode="markers", hoverinfo="skip", showlegend=False,
                            marker=dict(size=core + 16, color="rgba(0,0,0,0)", line=dict(color=T.TEXT, width=1.6)))
        dx, dy = LABEL_OFFSET.get(r.city, (40, -20))
        fig.add_annotation(x=r.lon, y=r.lat, ax=dx, ay=dy, text=f"<b>{r.city}</b>  {r.cases:,.0f}",
                           showarrow=True, arrowhead=0, arrowwidth=0.8, arrowcolor=_rgba(T.TEXT_2, 0.45),
                           font=dict(size=11.5, color=T.TEXT), bgcolor="rgba(13,13,14,0.72)",
                           bordercolor=T.BORDER, borderwidth=1, borderpad=3)
    fig.add_scatter(
        x=m["lon"], y=m["lat"], mode="markers", customdata=m["city"], showlegend=False,
        marker=dict(size=[12 + 26 * math.sqrt(max(c, 0) / mx) for c in m["cases"]],
                    color=[T.RISK.get(x, T.AMBER) for x in m["risk"]], opacity=0.95,
                    line=dict(color=_rgba("#FFFFFF", 0.55), width=1)),
        hovertext=[f"<b>{c}</b><br>Forecast: {v:,.0f} cases<br>Highest ward risk: {k}<br>"
                   f"High/Critical wards: {h} of {w}<br><i>approximate city-corporation location</i>"
                   for c, v, k, h, w in zip(m["city"], m["cases"], m["risk"], m["n_high_crit"], m["wards"])],
        hoverinfo="text")
    if ward_pts is not None and "ward_risk" in city_stats.attrs:      # optional authoritative ward points
        wr = ward_pts.merge(city_stats.attrs["ward_risk"], on="ward_id", how="inner")
        fig.add_scatter(x=wr["lon"], y=wr["lat"], mode="markers", name="Wards", customdata=wr["city"],
                        marker=dict(size=6, color=[T.RISK.get(x, T.AMBER) for x in wr["risk"]]),
                        hovertext=wr["ward_id"], hoverinfo="text")
    for tier in T.TIERS:
        fig.add_scatter(x=[None], y=[None], mode="markers", name=tier,
                        marker=dict(size=9, color=T.RISK[tier]))
    return _layout(fig, height)


def spread_map(values, height=250):
    """Small district map shaded by forecast cases per district (Dhaka = North + South)."""
    districts, _, _ = load_geo()
    mx = max(values.values()) if values else 1.0

    def fill(name):
        v = values.get(name, 0) / mx if mx else 0
        r = int(60 + (232 - 60) * v)
        g = int(52 + (119 - 52) * v)
        b = int(40 + (46 - 40) * v)
        return f"rgba({r},{g},{b},{0.35 + 0.6 * v:.2f})"
    fig = go.Figure()
    _district_traces(fig, districts, fill_for=fill, line_hi=False)
    for dct in districts:
        if dct["focus"] and dct["name"] in values:
            xs = [p[0] for p in dct["rings"][0]]
            ys = [p[1] for p in dct["rings"][0]]
            fig.add_annotation(x=sum(xs) / len(xs), y=sum(ys) / len(ys), showarrow=False,
                               text=f"{values[dct['name']]:,.0f}", font=dict(size=10.5, color=T.TEXT))
    return _layout(fig, height, mini=True)
