import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import HORIZON_NAME
from intervention_simulator import default_params, optimal_deployment, simulate
from ui import components as C
from ui import theme as T
from ui.state import ctx

c = ctx()
C.page_header("Intervention simulator",
              "Deploy a limited number of vector-control crews and compare the forecast with and without them.",
              tags=["sim"])
C.alert("warning", "Simulated estimates, not guaranteed real-world outcomes",
        "The dataset has no record of spraying or larviciding, so effectiveness cannot be learned from data. "
        "The reduction is an explicit, editable assumption applied to the ML forecast.")

fc_all = c.forecast
left, right = st.columns([1, 1.3], gap="large")
with left:
    with C.card():
        st.markdown("**1 · Scope and resources**")
        wards_sel = st.multiselect("Wards to consider (empty = all wards in scope)",
                                   sorted(fc_all["ward_id"]), key="sim_wards")
        a, b = st.columns(2)
        sim_h = a.radio("Outcome at", ["2w", "4w"], index=["2w", "4w"].index(c.horizon), horizontal=True,
                        format_func=HORIZON_NAME.get, key="sim_h")
        teams = b.number_input("Vector-control crews available", 0, 500, c.crews, key="sim_teams",
                               help="Larvicide / fogging crews. The simulator models one crew type.")
        p = default_params()
        with st.expander("Effectiveness assumptions (editable)"):
            p["max_reduction"] = st.slider("Maximum reduction any number of crews can achieve", 0.0, 0.9,
                                           p["max_reduction"], 0.05, format="%.2f", key="sim_m")
            p["saturation_crews"] = st.slider("Saturation (crews for ~63% of the maximum)", 0.5, 6.0,
                                              p["saturation_crews"], 0.5, key="sim_s")
            p["timing"]["2w"] = st.slider("Share of the effect visible by 2 weeks", 0.0, 1.0, p["timing"]["2w"], 0.05,
                                          key="sim_t2")
            p["timing"]["4w"] = st.slider("Share of the effect visible by 4 weeks", 0.0, 1.0, p["timing"]["4w"], 0.05,
                                          key="sim_t4")
            st.latex(r"\text{prevented}_h = \text{forecast}_h \times m\,(1-e^{-n/s}) \times \tau_h")
            st.caption("Defaults are conservative, readable assumptions, not estimates from data or literature.")

    fc = fc_all[fc_all["ward_id"].isin(wards_sel)] if wards_sel else fc_all
    fc = fc.rename(columns={f"risk_{sim_h}": "risk"})
    with C.card():
        st.markdown("**2 · Deploy crews** (larvicide / fogging)")
        preset = st.segmented_control("Start from", ["optimal", "engine", "none"], default="optimal", key="sim_preset",
                                      format_func={"optimal": "Optimise", "engine": "Allocation engine",
                                                   "none": "Empty"}.get) or "optimal"
        if preset == "optimal":
            start = optimal_deployment(fc, int(teams), sim_h, p)
        elif preset == "engine":
            eng = c.plan.set_index("ward_id")["crews_assigned"]
            start, left_ = {}, int(teams)
            for w in c.plan.sort_values("priority_rank")["ward_id"]:
                if w in set(fc["ward_id"]) and eng[w] and left_:
                    start[w] = min(int(eng[w]), left_)
                    left_ -= start[w]
        else:
            start = {}
        ed = pd.DataFrame({"ward_id": fc["ward_id"].values})
        ed["crews"] = ed["ward_id"].map(start).fillna(0).astype(int)
        ed["risk"] = fc["risk"].values
        ed["cases"] = fc[f"cases_{sim_h}"].values
        ed = ed.sort_values(["crews", "cases"], ascending=False)
        key = f"sim_ed_{preset}_{c.date_str}_{sim_h}_{teams}_{len(fc)}_{hash(tuple(sorted(fc['ward_id'])))}_" \
              f"{p['max_reduction']}_{p['saturation_crews']}_{p['timing']['2w']}_{p['timing']['4w']}"
        edited = st.data_editor(ed, hide_index=True, width="stretch", height=320, key=key,
                                disabled=["ward_id", "risk", "cases"], column_config={
                                    "ward_id": "Ward",
                                    "crews": st.column_config.NumberColumn("Crews (edit)", min_value=0, max_value=50,
                                                                           step=1),
                                    "risk": "Risk", "cases": C.num(f"Forecast ({HORIZON_NAME[sim_h]})", "%.1f")})
        st.caption("Edit the Crews column to change where crews go.")

deployment = dict(zip(edited["ward_id"], edited["crews"].fillna(0).astype(int)))
used = sum(deployment.values())
with right:
    if used > teams:
        C.alert("critical", f"{used} crews deployed but only {int(teams)} available",
                f"Remove {used - int(teams)} crew(s) to run the simulation.")
        st.stop()
    sim, tot = simulate(fc, deployment, int(teams), c.R["rates"], sim_h, p)
    st.markdown(f"**3 · Results** · {C.tag('sim')}", unsafe_allow_html=True)
    C.kpi_row([
        dict(label="Baseline forecast", value=f"{tot['baseline_cases']:.0f}", foot="no intervention", accent=T.SLATE),
        dict(label="With intervention", value=f"{tot['simulated_cases']:.0f}", foot="simulated", accent=T.BLUE),
        dict(label="Cases prevented", value=f"{tot['cases_prevented']:.1f}", foot=f"by {HORIZON_NAME[sim_h]}",
             accent=T.GREEN),
    ])
    C.kpi_row([
        dict(label="Fewer beds needed", value=f"{tot['beds_reduction']:.1f}", foot="bed demand", accent=T.CYAN),
        dict(label="Saline saved", value=f"{tot['saline_reduction']:.0f}", foot="bags", accent=T.YELLOW),
        dict(label="Prevented per crew", value=f"{tot['cases_prevented_per_crew']:.2f}",
             foot=f"{used} of {int(teams)} crews used", accent=T.ORANGE),
    ])
    with C.card():
        dep = sim[sim["crews"] > 0].sort_values(f"cases_{sim_h}", ascending=False).head(15)
        st.markdown("**Before and after, deployed wards**")
        if dep.empty:
            C.empty_state("No crews deployed: zero intervention, so nothing is prevented.")
        else:
            fig = go.Figure()
            fig.add_bar(y=dep["ward_id"], x=dep[f"cases_{sim_h}"], name="Before (forecast)", orientation="h",
                        marker_color=T.LIGHT_SLATE, hovertemplate="%{y}: %{x:.1f} forecast<extra></extra>")
            fig.add_bar(y=dep["ward_id"], x=dep[f"simulated_{sim_h}"], name="After (simulated)", orientation="h",
                        marker_color=T.BLUE, hovertemplate="%{y}: %{x:.1f} simulated<extra></extra>")
            fig.update_layout(barmode="group", height=max(260, 34 * len(dep) + 70), xaxis_title="Cases per week",
                              yaxis=dict(autorange="reversed"), bargap=0.2)
            C.chart(fig, key="sim_ba")
        st.caption(f"Across both horizons: {tot['prevented_2w']:.1f} cases prevented by 2 weeks and "
                   f"{tot['prevented_4w']:.1f} by 4 weeks (the effect builds as the next mosquito generation is hit).")

with C.card():
    st.markdown("**Intervention ROI ranking** · cases prevented per crew")
    st.dataframe(sim[["roi_rank", "ward_id", "city", "risk", "crews", "cases_prevented_per_crew", "first_crew_roi",
                      f"prevented_{sim_h}", "beds_reduction", "saline_reduction"]],
                 hide_index=True, width="stretch", height=320, column_config={
                     "roi_rank": C.num("Rank"), "ward_id": "Ward", "city": "City", "risk": "Risk",
                     "crews": C.num("Crews"),
                     "cases_prevented_per_crew": C.num("Prevented per crew", "%.2f"),
                     "first_crew_roi": C.num("If 1 crew sent", "%.2f",
                                             help="What a single crew would prevent in this ward"),
                     f"prevented_{sim_h}": C.num("Prevented", "%.1f"),
                     "beds_reduction": C.num("Beds saved", "%.1f"), "saline_reduction": C.num("Saline saved", "%.1f")})
    st.download_button("Download simulation (CSV)", sim.to_csv(index=False), f"simulation_{c.date_str}_{sim_h}.csv",
                       "text/csv", icon=":material/download:")
