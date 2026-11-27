import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import HORIZON_NAME, RESOURCE_LABEL, RESOURCES
from ui import components as C
from ui import geo
from ui import theme as T
from ui.state import ctx

c = ctx()
h = c.horizon
cases_col, risk_col = f"cases_{h}", f"risk_{h}"
fc = c.forecast.copy()
plan = c.plan.set_index("ward_id")
order = {t: i for i, t in enumerate(T.TIERS)}

C.page_header("Geographic Risk Intelligence",
              f"Where dengue risk concentrates {c.hname} ahead (week of {c.target_week}). Click a city on the map to "
              "open its wards.", tags=["real"])

tiers_sel = st.multiselect("Risk tiers shown", list(T.TIERS), default=list(T.TIERS), key="ri_tiers")
if not tiers_sel:
    C.empty_state("Select at least one risk tier.")
    st.stop()
fcv = fc[fc[risk_col].isin(tiers_sel)]
if fcv.empty:
    C.empty_state("No ward in this scope is in the selected risk tiers.")
    st.stop()

city = fcv.groupby("city").agg(cases=(cases_col, "sum"), wards=("ward_id", "count"),
                               n_high_crit=(risk_col, lambda r: int(r.isin(["High", "Critical"]).sum()))).reset_index()
city["risk"] = fcv.groupby("city")[risk_col].agg(lambda r: max(r, key=order.get)).values
if st.session_state.get("ri_city") not in set(city["city"]):
    st.session_state["ri_city"] = city.sort_values("cases", ascending=False)["city"].iloc[0]
sel_city = st.session_state["ri_city"]

left, right = st.columns([1.45, 1], gap="small")
with left:
    with C.card():
        C.panel_title("Ward Risk Map", right=f"<b>{int(city['n_high_crit'].sum())}</b>&nbsp;High / Critical", dot=True)
        ev = C.chart(geo.city_map(city, selected=sel_city, height=560), key="ri_map", select=True)
        pts = (ev or {}).get("selection", {}).get("points", []) if ev else []
        if pts and pts[0].get("customdata") and pts[0]["customdata"] != sel_city:
            st.session_state["ri_city"] = pts[0]["customdata"]
            st.rerun()
        st.markdown(f"<div class='foot-note'>{geo.ATTRIBUTION} Ward boundaries are not in the dataset, so wards are "
                    "listed beside the map instead of placed on it.</div>", unsafe_allow_html=True)

with right:
    with C.card():
        cities = sorted(city["city"])
        st.selectbox("City", cities, key="ri_city")
        sel_city = st.session_state["ri_city"]
        cw = fcv[fcv["city"] == sel_city].sort_values(cases_col, ascending=False)
        C.panel_title(f"{sel_city} · ward risk indicators", right=f"{len(cw)} wards")
        top = cw.head(12)
        C.bar_rows([dict(name=w.replace("_Ward_", " "), value=v, value_text=f"{v:.1f}", unit="",
                         delta=t, delta_cls="flat", color=T.RISK[t])
                    for w, v, t in zip(top["ward_id"], top[cases_col], top[risk_col])],
                   max_value=float(fcv[cases_col].max()))
        if len(cw) > len(top):
            st.markdown(f"<div class='foot-note' style='margin-top:8px'>Top {len(top)} of {len(cw)} wards by forecast; "
                        "all wards are in the ward detail list and the ranking below.</div>", unsafe_allow_html=True)

with C.card():
    a, b = st.columns([1, 1.25], gap="large")
    with a:
        wards = list(cw["ward_id"])
        if st.session_state.get("ri_ward") not in wards:
            st.session_state["ri_ward"] = wards[0]
        ward = st.selectbox("Ward detail", wards, key="ri_ward")
        r = fc.set_index("ward_id").loc[ward]
        p = plan.loc[ward]
        x, y = st.columns(2)
        for col, hh in ((x, "2w"), (y, "4w")):
            tier = r[f"risk_{hh}"]
            col.markdown(f"<div class='fc'><div class='h'>{HORIZON_NAME[hh]} ahead</div>"
                         f"<div class='n' style='font-size:34px'>{r[f'cases_{hh}']:.1f}</div>"
                         f"<div class='tier' style='background:{T.RISK_BG[tier]};color:{T.RISK_FG[tier]}'>{tier}</div>"
                         "</div>", unsafe_allow_html=True)
    with b:
        row = c.df[(c.df["ward_id"] == ward) & (c.df["date"] == pd.Timestamp(c.date_str))].iloc[0]
        C.kv_list([
            ("Priority rank (of 60)", f"#{int(p['priority_rank'])} · score {p['priority']:.2f}"),
            ("Population density", f"{row['population_density_sqkm']:,.0f} /km²"),
            ("Water-logging risk index", f"{row['water_logging_risk_index']:.2f}"),
            ("Sanitation score", f"{row['sanitation_score']:.2f}"),
            ("Rain, last 4 weeks", f"{row['rain_sum_4w']:.0f} mm"),
        ] + [(f"{RESOURCE_LABEL[res]} (allocated / needed)",
              f"{int(p[f'{res}_allocated'])} / {int(p[f'{res}_required'])}") for res in RESOURCES]
            + [("Spraying crews", f"{int(p['crews_assigned'])} / {int(p['crews_needed'])}")])
        st.markdown(f"<div class='foot-note' style='margin-top:6px'>Supplies for the {c.hname} horizon at "
                    f"{c.stock}% stock.</div>", unsafe_allow_html=True)

left, right = st.columns([1.1, 1], gap="small")
with left:
    with C.card():
        C.panel_title("Ward Forecast Distribution", right=f"{len(fcv)} wards")
        d = fcv.sort_values(cases_col, ascending=False)
        fig = go.Figure(go.Bar(x=d["ward_id"], y=d[cases_col], marker=dict(color=[T.RISK[t] for t in d[risk_col]]),
                               customdata=d[risk_col], hovertemplate="%{x}<br>%{y:.1f} cases · %{customdata}<extra></extra>"))
        for tier in ("Medium", "High", "Critical"):
            fig.add_hline(y=c.meta["tiers"][tier], line=dict(color=T.RISK[tier], width=1, dash="dot"),
                          annotation_text=tier, annotation_font=dict(size=10.5, color=T.RISK[tier]),
                          annotation_position="top right")
        fig.update_layout(height=330, yaxis_title="Forecast cases / week", xaxis=dict(showticklabels=False),
                          margin=dict(t=14))
        C.chart(fig, key="ri_dist")
        tc = C.tier_counts(fcv, "city", risk_col)
        st.markdown("<div class='foot-note'>" + " · ".join(
            f"{cty}: " + ", ".join(f"{int(n)} {t}" for t, n in tc.loc[cty].items() if n) for cty in tc.index)
            + "</div>", unsafe_allow_html=True)
with right:
    with C.card():
        C.panel_title("Critical and High-Risk Ranking")
        rk = fcv.merge(c.plan[["ward_id", "priority"]], on="ward_id")
        rk = rk[rk[risk_col].isin(["Critical", "High"])].sort_values(cases_col, ascending=False)
        if rk.empty:
            C.empty_state("No Critical or High wards in this scope.")
        else:
            C.risk_table(pd.DataFrame({"Ward": rk["ward_id"], "City": rk["city"], "Risk": rk[risk_col],
                                       "Cases": rk[cases_col], "Priority": rk["priority"]}),
                         height=320, fmt={"Cases": "{:.1f}", "Priority": "{:.2f}"})
        full = fc.rename(columns={"ward_id": "ward"})[["city", "ward", "cases_2w", "risk_2w", "cases_4w", "risk_4w"]]
        st.download_button("Download all-ward ranking (CSV)", full.to_csv(index=False),
                           f"ward_risk_{c.date_str}.csv", "text/csv", icon=":material/download:")
