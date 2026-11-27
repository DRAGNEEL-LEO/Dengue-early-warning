import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import HORIZON_NAME, RESOURCE_LABEL, RESOURCES
from ui import components as C
from ui import theme as T
from ui.state import ctx

c = ctx()
h = c.horizon
fc = c.forecast.copy()
plan = c.plan.set_index("ward_id")

C.page_header("Risk intelligence",
              f"Where risk is concentrated {c.hname} ahead (week of {c.target_week}). Click a tile to open the ward.",
              tags=["real"])

f1, f2 = st.columns([2, 1])
tiers_sel = f1.multiselect("Show risk tiers", list(T.TIERS), default=list(T.TIERS), key="ri_tiers")
sort_by = f2.selectbox("Rank wards by", ["Forecast cases", "Priority score"], key="ri_sort")
if not tiers_sel:
    C.empty_state("Select at least one risk tier.")
    st.stop()
fcv = fc[fc[f"risk_{h}"].isin(tiers_sel)]
if fcv.empty:
    C.empty_state("No ward in this scope is in the selected risk tiers.")
    st.stop()

if st.session_state.get("ri_ward") not in set(fcv["ward_id"]):
    st.session_state["ri_ward"] = fcv.sort_values(f"cases_{h}", ascending=False)["ward_id"].iloc[0]

left, right = st.columns([1.7, 1], gap="medium")
with left:
    with C.card():
        st.markdown(f"**Ward risk grid** · {C.tag('demo', 'Schematic · not geographic')}", unsafe_allow_html=True)
        ev = C.chart(C.ward_grid(fcv, f"cases_{h}", f"risk_{h}", selected=st.session_state["ri_ward"],
                                 width_px=780, max_units=17),
                     key="ri_grid", select=True)
        pts = (ev or {}).get("selection", {}).get("points", []) if ev else []
        if pts and pts[0].get("customdata") and pts[0]["customdata"] != st.session_state["ri_ward"]:
            st.session_state["ri_ward"] = pts[0]["customdata"]
            st.rerun()
        st.caption("Tiles are grouped by city in ward-ID order; the dataset has no coordinates, so this is not a map.")

with right:
    with C.card():
        wards = sorted(fcv["ward_id"])
        ward = st.selectbox("Ward detail", wards, key="ri_ward")
        r = fc.set_index("ward_id").loc[ward]
        p = plan.loc[ward]
        st.markdown(f"**{ward}** · {r['city']}", unsafe_allow_html=True)
        a, b = st.columns(2)
        for col, hh in ((a, "2w"), (b, "4w")):
            tier = r[f"risk_{hh}"]
            col.markdown(f"<div class='fc' style='padding:10px 12px'><div class='h'>{HORIZON_NAME[hh]}</div>"
                         f"<div class='n' style='font-size:26px'>{r[f'cases_{hh}']:.1f}</div>"
                         f"<div class='tier' style='margin-top:6px;font-size:12.5px;background:{T.RISK_BG[tier]};"
                         f"color:{T.RISK_FG[tier]}'>{tier}</div></div>", unsafe_allow_html=True)
        st.write("")
        row = c.df[(c.df["ward_id"] == ward) & (c.df["date"] == pd.Timestamp(c.date_str))].iloc[0]
        C.kv_list([
            ("Priority rank (of 60)", f"#{int(p['priority_rank'])}  ·  score {p['priority']:.2f}"),
            ("Population density", f"{row['population_density_sqkm']:,.0f} /km²"),
            ("Water-logging risk", f"{row['water_logging_risk_index']:.2f}"),
            ("Sanitation score", f"{row['sanitation_score']:.2f}"),
            ("Rain, last 4 weeks", f"{row['rain_sum_4w']:.0f} mm"),
        ] + [(f"{RESOURCE_LABEL[res]} (alloc / need)",
              f"{int(p[f'{res}_allocated'])} / {int(p[f'{res}_required'])}") for res in RESOURCES]
            + [("Spraying crews", f"{int(p['crews_assigned'])} / {int(p['crews_needed'])}")])
        st.caption(f"Supply figures are for the {c.hname} planning horizon at {c.stock}% stock.")

# ---------------------------------------------------------------- distribution + ranking
left, right = st.columns([1.15, 1], gap="medium")
with left:
    with C.card():
        st.markdown("**Ward-level forecast distribution**")
        d = fcv.sort_values(f"cases_{h}", ascending=False)
        fig = go.Figure(go.Bar(x=d["ward_id"], y=d[f"cases_{h}"], marker_color=[T.RISK[t] for t in d[f"risk_{h}"]],
                               customdata=d[f"risk_{h}"],
                               hovertemplate="%{x}<br>%{y:.1f} cases · %{customdata}<extra></extra>"))
        for tier in ("Medium", "High", "Critical"):
            fig.add_hline(y=c.meta["tiers"][tier], line=dict(color=T.RISK[tier], width=1, dash="dot"))
        fig.update_layout(height=360, yaxis_title="Forecast cases / week", xaxis=dict(showticklabels=len(d) <= 25),
                          margin=dict(t=20))
        C.chart(fig, key="ri_dist")
        st.caption("Dotted lines: Medium, High and Critical thresholds (from training years).")
with right:
    with C.card():
        st.markdown("**Critical and high-risk ward ranking**")
        rk = fc.merge(c.plan[["ward_id", "priority", "priority_rank"]], on="ward_id")
        rk = rk[rk[f"risk_{h}"].isin(["Critical", "High"]) & rk[f"risk_{h}"].isin(tiers_sel)]
        rk = rk.sort_values(f"cases_{h}" if sort_by == "Forecast cases" else "priority", ascending=False)
        if rk.empty:
            C.empty_state("No Critical or High wards in this scope.")
        else:
            tbl = pd.DataFrame({"Ward": rk["ward_id"], "City": rk["city"], "Risk": rk[f"risk_{h}"],
                                "Cases": rk[f"cases_{h}"], "Priority": rk["priority"]})
            C.risk_table(tbl, height=330, fmt={"Cases": "{:.1f}", "Priority": "{:.2f}"})
        full = fc.rename(columns={"ward_id": "ward"})[["city", "ward", "cases_2w", "risk_2w", "cases_4w", "risk_4w"]]
        st.download_button("Download all-ward ranking (CSV)", full.to_csv(index=False),
                           f"ward_risk_{c.date_str}.csv", "text/csv", icon=":material/download:")
