import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from config import HORIZON_NAME, HORIZON_WEEKS, RESOURCE_LABEL, RESOURCES, PRIORITY_WEIGHTS, CREWS_NEEDED_BY_TIER
from dispatch_generator import html_brief, notices_for, pdf_brief, sms_text, whatsapp_text
from features import FEATURES
from hospital_routing import CAPACITY_NOTE
from intervention_simulator import default_params, optimal_deployment, simulate
from pipeline import load_system, run_plan
from predict import LABELS, TIERS, driver_impacts, predict_with_range, risk_tier
from system_status import internet_reachable, local_checks

st.set_page_config(page_title="Dengue early-warning and response system", page_icon="🦟", layout="wide")

COLORS = {"Low": "#2e7d32", "Medium": "#f9a825", "High": "#ef6c00", "Critical": "#c62828"}
TEXT = {"Low": "#ffffff", "Medium": "#1a1a1a", "High": "#ffffff", "Critical": "#ffffff"}
PASTEL = {"Low": "#c8e6c9", "Medium": "#fff59d", "High": "#ffcc80", "Critical": "#ef9a9a"}
RAIN_COLS = [c for c in FEATURES if c.startswith("rain_")]
DEFAULT_WEEK = "2024-08-12"     # held-out test week with mixed risk and bed overflow (good for demos)
PAGES = ["Executive Overview", "Ward Forecast", "Resource Allocation", "Hospital Overflow Routing",
         "Vector Control Simulator", "Dispatch Center", "Model Accuracy", "System / Offline Status"]

st.markdown("""
<style>
.block-container {padding-top: 1.5rem;}
.banner {background:#0f3d3a;border:1px solid #1f6f69;color:#ffffff;padding:18px 24px;border-radius:10px;margin-bottom:14px;}
.banner h1 {color:#ffffff;margin:0;font-size:1.75rem;}
.banner p {color:#cfe7e4;margin:6px 0 0 0;font-size:0.98rem;}
.kpi {border-left:6px solid #999;background:#1b2330;padding:10px 14px;border-radius:6px;margin-bottom:8px;}
.kpi .l {font-size:0.82rem;color:#9fb0bf;}
.kpi .n {font-size:1.6rem;font-weight:700;color:#f1f5f9;line-height:1.2;}
.tier {padding:14px;border-radius:10px;text-align:center;font-size:2rem;font-weight:700;margin:6px 0 10px 0;}
.badge {display:inline-block;padding:4px 10px;border-radius:12px;font-weight:600;font-size:0.85rem;}
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------ cached loading (all local files)
@st.cache_resource(show_spinner="Loading data and models from local disk (first run may train them, ~30 s)...")
def get_system():
    return load_system()


@st.cache_data(show_spinner=False)
def cached_plan(date, horizon, stock, crews, policy, basis, capacity, w_risk):
    weights = {"risk": w_risk, "density": 1 - w_risk}
    return run_plan(SYSTEM, date, horizon, stock, crews, policy, basis, capacity=capacity, weights=weights)


@st.cache_data(ttl=30, show_spinner=False)
def net_status():
    return internet_reachable()


@st.cache_data
def validation_summary(horizon):
    models, meta, df = SYSTEM["models"], SYSTEM["meta"], SYSTEM["df"]
    target = f"target_{horizon}"
    test = df[df["date"] >= meta["split_date"]].dropna(subset=FEATURES + [target])
    pred = models[horizon].predict(test[FEATURES])
    actual_t = test[target].map(lambda x: risk_tier(x, meta["tiers"]))
    pred_t = pd.Series(pred, index=test.index).map(lambda x: risk_tier(x, meta["tiers"]))
    outbreak = actual_t.isin(["High", "Critical"])
    flagged = pred_t.isin(["Medium", "High", "Critical"])
    return {"exact": float((actual_t == pred_t).mean()), "outbreak_caught": float(flagged[outbreak].mean()),
            "n_outbreak": int(outbreak.sum())}


def kpi(col, label, value, color="#2dd4bf"):
    col.markdown(f"<div class='kpi' style='border-left-color:{color}'><div class='l'>{label}</div>"
                 f"<div class='n'>{value}</div></div>", unsafe_allow_html=True)


def tier_style(df, cols=("risk",)):
    return df.style.map(lambda v: f"background-color:{PASTEL[v]};color:#000" if v in PASTEL else "",
                        subset=[c for c in cols if c in df.columns])


SYSTEM = get_system()
models, meta, df = SYSTEM["models"], SYSTEM["meta"], SYSTEM["df"]
tiers = meta["tiers"]
if "capacity" not in st.session_state:
    st.session_state.capacity = SYSTEM["capacity"][["city", "ward_id", "bed_capacity"]].copy()

# ------------------------------------------------------------------ sidebar: navigation + global controls
online = net_status()
st.sidebar.markdown(
    "<span class='badge' style='background:#14532d;color:#dcfce7'>● Core system: running locally</span><br>"
    + ("<span class='badge' style='background:#1e3a5f;color:#dbeafe;margin-top:4px'>Internet: available (not required)</span>"
       if online else
       "<span class='badge' style='background:#7c2d12;color:#ffedd5;margin-top:4px'>Internet: OFFLINE, all features still work</span>"),
    unsafe_allow_html=True)
page = st.sidebar.radio("Navigate", PAGES, label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.header("Planning controls")
dates = sorted(df.dropna(subset=FEATURES)["date"].dt.strftime("%Y-%m-%d").unique(), reverse=True)
date_str = st.sidebar.selectbox("Latest week of data (forecast origin)", dates, index=dates.index(DEFAULT_WEEK),
                                help="Forecasts look 2 and 4 weeks beyond this week. Weeks inside the dataset are a "
                                     "replay; the newest week (2025-12-29) is a genuine forecast.")
horizon = st.sidebar.radio("Planning horizon", list(HORIZON_NAME), format_func=HORIZON_NAME.get, horizontal=True)
basis = st.sidebar.radio("Demand basis", ["expected", "cautious"], horizontal=True,
                         format_func={"expected": "Expected", "cautious": "Cautious (P90)"}.get,
                         help="Cautious plans for the 90th percentile across the forest's trees, a buffer because "
                              "the model under-predicts the largest peaks.")
stock_pct = st.sidebar.slider("Available Regional Stock (% of forecast demand)", 30, 100, 60, 5)
total_crews = st.sidebar.number_input("Total spraying crews", min_value=0, max_value=500, value=40, step=1)
policy = st.sidebar.radio("Scarcity policy", ["weighted", "triage"], horizontal=True,
                          format_func={"weighted": "Priority-weighted", "triage": "Strict triage"}.get,
                          help="Priority-weighted: higher-priority wards get a larger share of their demand, top "
                               "wards first. Strict triage: fill wards completely in priority order.")
with st.sidebar.expander("Priority weights (assumption)"):
    w_risk = st.slider("Weight on risk tier (rest = population density)", 0.0, 1.0,
                       float(PRIORITY_WEIGHTS["risk"]), 0.05)
all_cities = sorted(df["city"].unique())
city_filter = st.sidebar.multiselect("City filter (views)", all_cities, default=all_cities)
if not city_filter:
    city_filter = all_cities

R = cached_plan(date_str, horizon, stock_pct, int(total_crews), policy, basis, st.session_state.capacity, w_risk)
plan = R["plan"]
view = plan[plan["city"].isin(city_filter)]
target_week = R["target_week"].strftime("%Y-%m-%d")

st.markdown(
    "<div class='banner'><h1>Dengue early-warning and response system</h1>"
    "<p>Forecast, allocate, route and dispatch for 60 wards in Dhaka North, Dhaka South, Chattogram, Gazipur and "
    "Narayanganj. Everything runs locally, with no internet or LLM API needed.</p></div>", unsafe_allow_html=True)
st.caption(f"Scenario: data up to **{date_str}**, planning for the week of **{target_week}** "
           f"({HORIZON_NAME[horizon]} ahead), {basis} demand, regional stock **{stock_pct}%**, "
           f"**{int(total_crews)}** crews, {'priority-weighted' if policy == 'weighted' else 'strict triage'} policy.")

# ====================================================================== 1. Executive overview
if page == "Executive Overview":
    short = view[view["critical_deficit"]]
    if len(short):
        st.error(f"🚨 CRITICAL SUPPLY DEFICIT in {len(short)} of {len(view)} wards: demand cannot be fully met at "
                 f"{stock_pct}% regional stock.")
    else:
        st.success("All forecast supply demand is met at the current stock level.")
    c = st.columns(6)
    kpi(c[0], "Projected cases (target week)", f"{view['predicted_cases'].sum():.0f}")
    kpi(c[1], "High / Critical wards", f"{int(view['risk'].isin(['High', 'Critical']).sum())}", COLORS["High"])
    kpi(c[2], "Wards with supply deficit", f"{len(short)}", COLORS["Critical"])
    kpi(c[3], "Crews assigned / available", f"{int(view['crews_assigned'].sum())} / {int(total_crews)}")
    kpi(c[4], "Bed transfers (patients)", f"{int(R['transfers']['patients'].sum()) if len(R['transfers']) else 0}")
    kpi(c[5], "Patients without a bed", f"{int(view['unresolved_deficit'].sum())}", COLORS["Critical"])

    left, right = st.columns([1.1, 1])
    with left:
        st.markdown("#### Available versus required supplies (all 60 wards)")
        s = R["supply_summary"].copy()
        s["resource"] = s["resource"].map(RESOURCE_LABEL)
        s["fill %"] = (100 * s["allocated"] / s["required"].where(s["required"] > 0)).round(1).fillna(100)
        st.dataframe(s, hide_index=True, width="stretch")
        st.bar_chart(s.set_index("resource")[["allocated", "deficit"]], horizontal=True, height=200,
                     color=["#2dd4bf", "#ef5350"])
    with right:
        st.markdown("#### City comparison")
        city = view.groupby("city").agg(
            cases=("predicted_cases", "sum"), high_critical=("risk", lambda r: int(r.isin(["High", "Critical"]).sum())),
            saline_deficit=("saline_bags_needed_deficit", "sum"), kits_deficit=("diagnostic_kits_needed_deficit", "sum"),
            crews=("crews_assigned", "sum"), unplaced_patients=("unresolved_deficit", "sum")).round(1)
        st.dataframe(city, width="stretch")
        st.bar_chart(city["cases"], height=200, color="#ffb74d")
    st.markdown("#### Top 10 priority wards")
    top = view.sort_values("priority_rank").head(10)[
        ["priority_rank", "city", "ward_id", "risk", "predicted_cases", "priority", "saline_bags_needed_deficit",
         "diagnostic_kits_needed_deficit", "crews_assigned", "alert"]]
    st.dataframe(tier_style(top), hide_index=True, width="stretch")

# ====================================================================== 2. Ward forecast (Phase 1)
elif page == "Ward Forecast":
    c1, c2, c3 = st.columns([1, 1, 1.2])
    city = c1.selectbox("City", city_filter)
    ward = c2.selectbox("Ward", sorted(df.loc[df["city"] == city, "ward_id"].unique()))
    rain_mult = c3.slider("Rainfall scenario (× recent rain)", 0.0, 2.0, 1.0, 0.1,
                          help="1.0 = actual weather. The forest responds in steps; treat this as a scenario.")
    row = df[(df["ward_id"] == ward) & (df["date"] == pd.Timestamp(date_str))].copy()
    row[RAIN_COLS] = row[RAIN_COLS] * rain_mult
    if rain_mult != 1.0:
        st.info(f"Scenario: recent rainfall multiplied by {rain_mult}.")
    cols = st.columns(2)
    for col, h in zip(cols, HORIZON_NAME):
        pred, lo, hi = predict_with_range(models[h], row)
        tier = risk_tier(pred, tiers)
        wk = pd.Timestamp(date_str) + pd.Timedelta(weeks=HORIZON_WEEKS[h])
        act = df[(df["ward_id"] == ward) & (df["date"] == wk)]
        with col, st.container(border=True):
            st.markdown(f"**In {HORIZON_NAME[h]}** (week of {wk.strftime('%d %b %Y')})")
            st.markdown(f"<div class='tier' style='background:{COLORS[tier]};color:{TEXT[tier]}'>{tier}</div>",
                        unsafe_allow_html=True)
            st.metric("Predicted cases per week", f"{pred:.1f}")
            st.caption(f"Likely range: {lo:.1f} to {hi:.1f} cases (10th to 90th percentile of the trees)")
            if act.empty:
                st.caption("Actual cases: not in the dataset yet, so this is a genuine forecast.")
            else:
                tag = "training years, not a fair test" if wk < pd.Timestamp(meta["split_date"]) else "held-out test week"
                st.caption(f"Actual cases that week: **{int(act['dengue_cases'].iloc[0])}** ({tag}).")
    with st.container(border=True):
        st.markdown(f"#### What is driving the {HORIZON_NAME[horizon]} forecast")
        imp = driver_impacts(models[horizon], row, meta["baseline"]).rename(LABELS)
        order = imp.abs().sort_values(ascending=False).index[:3]
        st.markdown("Top drivers: " + ", ".join(f"**{n}** ({imp[n]:+.1f})" for n in order))
        st.bar_chart(imp.sort_values(), horizontal=True, height=380, color="#2dd4bf")
        st.caption("How much each input raises (+) or lowers (−) predicted cases versus a typical week and ward. "
                   "Approximate, not causal.")
    with st.container(border=True):
        st.markdown("#### Recent weather in this ward")
        hist = df[(df["ward_id"] == ward) & (df["date"] <= pd.Timestamp(date_str))].tail(12).set_index("date")
        a, b, c = st.columns(3)
        a.caption("Rainfall (mm per week)")
        a.bar_chart(hist["rainfall_mm"], height=200, color="#64b5f6")
        b.caption("Average temperature (°C)")
        b.line_chart(hist["avg_temp_c"], height=200, color="#ffb74d")
        c.caption("Relative humidity (%)")
        c.line_chart(hist["relative_humidity_pct"], height=200, color="#ce93d8")
    st.markdown(f"#### All-ward risk ranking ({HORIZON_NAME[horizon]})")
    other = "4w" if horizon == "2w" else "2w"
    rank = R["forecast"][R["forecast"]["city"].isin(city_filter)][
        ["city", "ward_id", f"cases_{horizon}", f"risk_{horizon}", f"cases_{other}"]
    ].rename(columns={f"cases_{horizon}": "predicted_cases", f"risk_{horizon}": "risk",
                      f"cases_{other}": f"cases_{HORIZON_NAME[other]}"}).sort_values("predicted_cases", ascending=False)
    counts = pd.crosstab(rank["city"], rank["risk"]).reindex(columns=list(TIERS), fill_value=0)
    a, b = st.columns([1, 2])
    a.dataframe(counts, width="stretch")
    b.dataframe(tier_style(rank.head(20)), hide_index=True, width="stretch")
    st.download_button("Download ranking as CSV", rank.to_csv(index=False), f"dengue_risk_{date_str}_{horizon}.csv",
                       "text/csv")

# ====================================================================== 3. Resource allocation
elif page == "Resource Allocation":
    st.markdown(f"#### Constrained allocation at **{stock_pct}%** regional stock and **{int(total_crews)}** crews")
    s = R["supply_summary"]
    cols = st.columns(4)
    for col, rr in zip(cols, s.itertuples()):
        col.metric(RESOURCE_LABEL[rr.resource], f"{rr.allocated} / {rr.required}",
                   delta=f"-{rr.deficit} deficit" if rr.deficit else "fully met",
                   delta_color="normal" if rr.deficit else "off")
    cr = R["crews"]
    cols[3].metric("Spraying crews assigned / needed", f"{cr['assigned']} / {cr['needed']}",
                   delta=f"{cr['idle']} idle" if cr["idle"] else (f"-{cr['shortfall']} short" if cr["shortfall"] else "exact"),
                   delta_color="off")
    n_short = int(view["critical_deficit"].sum())
    if n_short:
        st.error(f"🚨 CRITICAL SUPPLY DEFICIT: {n_short} ward(s) in the current view cannot be 100% supplied. "
                 "Highlighted rows below.")
    res = st.radio("Resource", list(RESOURCES), format_func=RESOURCE_LABEL.get, horizontal=True)
    chart = view.sort_values("priority_rank").set_index("ward_id")[[f"{res}_allocated", f"{res}_deficit"]]
    chart.columns = ["Allocated", "Deficit"]
    st.bar_chart(chart, height=320, color=["#2dd4bf", "#ef5350"])
    st.caption("Wards ordered by priority rank (left = highest).")
    show = view.sort_values("priority_rank")[
        ["priority_rank", "city", "ward_id", "risk", "predicted_cases", "population_density_sqkm", "priority"]
        + [f"{r}_{k}" for r in RESOURCES for k in ("required", "allocated", "deficit")]
        + ["crews_needed", "crews_assigned", "alert"]]
    st.dataframe(show.style.map(lambda v: "background-color:#7f1d1d;color:#fff" if v == "CRITICAL SUPPLY DEFICIT" else "",
                                subset=["alert"]).map(
        lambda v: f"background-color:{PASTEL[v]};color:#000" if v in PASTEL else "", subset=["risk"]),
        hide_index=True, width="stretch", height=420)
    st.download_button("Download allocation (CSV)", show.to_csv(index=False),
                       f"allocation_{date_str}_{horizon}_{stock_pct}pct.csv", "text/csv")
    with st.expander("How the allocation works (assumptions)"):
        st.markdown(f"""
- **Demand** per ward = forecast cases × per-case rate fitted on 2016-2023 (saline {meta['resource_rates']['saline_bags_needed']:.3f},
  kits {meta['resource_rates']['diagnostic_kits_needed']:.3f}, beds {meta['resource_rates']['hospital_beds_required']:.3f}),
  rounded. These rates reproduce the dataset's resource columns exactly on held-out 2024-2025 weeks.
- **Available stock** = floor(stock % × total demand across all 60 wards), for each supply.
- **Priority** = {w_risk:.2f} × risk score (Low 0, Medium ⅓, High ⅔, Critical 1) + {1 - w_risk:.2f} × normalised
  population density. Ties: higher forecast, then ward ID.
- **Priority-weighted**: each ward gets min(1, λ·priority) of its demand, λ chosen so total = stock; whole units by
  largest remainder. **Strict triage**: fill wards completely in priority order.
- **Crews needed** by tier: {CREWS_NEEDED_BY_TIER}. Crews are dealt round-robin in priority order.
- Weights, tiers and crew needs are configurable system assumptions, not official public-health policy.
""")

# ====================================================================== 4. Hospital overflow routing
elif page == "Hospital Overflow Routing":
    st.warning("⚠️ " + CAPACITY_NOTE + " Edit the table below to use real figures.")
    city_beds = R["city_beds"][R["city_beds"]["city"].isin(city_filter)]
    st.markdown("#### City-wide bed utilization (transfers only within each city)")
    cols = st.columns(len(city_beds))
    rt = R["routing"][R["routing"]["city"].isin(city_filter)]
    over_before = rt[rt["deficit_before"] > 0].groupby("city").size()
    over_after = rt[rt["unresolved_deficit"] > 0].groupby("city").size()
    for col, c in zip(cols, city_beds.itertuples()):
        nb, na = int(over_before.get(c.city, 0)), int(over_after.get(c.city, 0))
        col.metric(c.city, f"{c.utilization_after_pct:.0f}% utilised",
                   delta=f"wards over capacity: {nb} → {na}", delta_color="off")
        col.caption(f"Demand {c.bed_demand} · capacity {c.bed_capacity} · routed {c.transferred} · "
                    f"headroom left {c.headroom_after} · **unplaced {c.unresolved_deficit}**")
    util = city_beds.set_index("city")[["beds_used_after", "headroom_after", "unresolved_deficit"]]
    util.columns = ["Beds occupied after routing", "Remaining headroom", "Unplaced patients"]
    st.bar_chart(util, height=260, color=["#2dd4bf", "#475569", "#ef5350"])
    if (rt["unresolved_deficit"] > 0).any():
        st.error(f"🚨 {int(rt['unresolved_deficit'].sum())} patient(s) cannot be placed within their own city. "
                 "Escalate for surge beds.")
    a, b = st.columns([1, 1.3])
    with a:
        st.markdown("#### Transfers")
        tr = R["transfers"]
        tr = tr[tr["city"].isin(city_filter)] if len(tr) else tr
        if len(tr):
            st.dataframe(tr, hide_index=True, width="stretch")
        else:
            st.info("No overflow this week: every ward is within local capacity.")
    with b:
        st.markdown("#### Ward deficits and headroom")
        st.dataframe(rt[["city", "ward_id", "beds_demand", "bed_capacity", "deficit_before", "headroom_before",
                         "transferred_out", "transferred_in", "unresolved_deficit", "headroom_after", "status"]]
                     .sort_values(["city", "deficit_before"], ascending=[True, False]),
                     hide_index=True, width="stretch", height=360)
    with st.expander("Edit ward bed capacity (demo assumption)"):
        edited = st.data_editor(st.session_state.capacity, hide_index=True, width="stretch",
                                disabled=["city", "ward_id"], key="cap_editor",
                                column_config={"bed_capacity": st.column_config.NumberColumn(min_value=0, step=1)})
        c1, c2 = st.columns(2)
        if c1.button("Apply capacity changes"):
            st.session_state.capacity = edited.fillna(0).astype({"bed_capacity": int})
            st.rerun()
        if c2.button("Reset to demo defaults"):
            st.session_state.capacity = SYSTEM["capacity"][["city", "ward_id", "bed_capacity"]].copy()
            st.rerun()
    st.caption("Rule: each overflowing ward (largest deficit first) sends patients to the ward in the same city with "
               "the most free beds, repeatedly, until its deficit is cleared or the city is full. Receivers never "
               "exceed capacity; cross-city transfers are impossible by construction.")

# ====================================================================== 5. Vector control simulator
elif page == "Vector Control Simulator":
    st.info("Simulated estimates, not proven causal effects. The dataset has no spraying or larviciding records, so "
            "effectiveness is an explicit, adjustable assumption applied to the ML forecast.")
    c1, c2, c3 = st.columns([1.3, 1, 1])
    sim_cities = c1.multiselect("Cities", all_cities, default=city_filter, key="sim_cities")
    sim_h = c2.radio("Outcome horizon", list(HORIZON_NAME), index=list(HORIZON_NAME).index(horizon),
                     format_func=HORIZON_NAME.get, horizontal=True, key="sim_h")
    teams = c3.number_input("Available spraying teams", 0, 500, int(total_crews), key="sim_teams")
    with st.expander("Effectiveness assumptions (editable)", expanded=False):
        p = default_params()
        e1, e2, e3, e4 = st.columns(4)
        p["max_reduction"] = e1.slider("Max reduction (any number of crews)", 0.0, 0.9, p["max_reduction"], 0.05)
        p["saturation_crews"] = e2.slider("Saturation (crews)", 0.5, 6.0, p["saturation_crews"], 0.5)
        p["timing"]["2w"] = e3.slider("Share of effect by 2 weeks", 0.0, 1.0, p["timing"]["2w"], 0.05)
        p["timing"]["4w"] = e4.slider("Share of effect by 4 weeks", 0.0, 1.0, p["timing"]["4w"], 0.05)
        st.latex(r"\text{prevented}_h = \text{forecast}_h \times m\,(1-e^{-n/s}) \times \tau_h")
    if not sim_cities:
        st.warning("Select at least one city.")
        st.stop()
    fc = R["forecast"][R["forecast"]["city"].isin(sim_cities)].rename(columns={f"risk_{sim_h}": "risk"})
    preset = st.radio("Starting deployment", ["engine", "optimal", "none"], horizontal=True,
                      format_func={"engine": "From allocation engine", "optimal": "Optimise (max cases prevented)",
                                   "none": "Start empty"}.get)
    if preset == "engine":
        eng = plan.set_index("ward_id")["crews_assigned"]
        start, left = {}, int(teams)
        for w in plan.sort_values("priority_rank")["ward_id"]:
            if w in set(fc["ward_id"]) and eng[w] and left:
                start[w] = min(int(eng[w]), left)
                left -= start[w]
    elif preset == "optimal":
        start = optimal_deployment(fc, int(teams), sim_h, p)
    else:
        start = {}
    editor_df = fc[["city", "ward_id", "risk", f"cases_{sim_h}"]].copy()
    editor_df["crews"] = editor_df["ward_id"].map(start).fillna(0).astype(int)
    editor_df = editor_df.sort_values(f"cases_{sim_h}", ascending=False)
    st.caption("Edit the **crews** column to deploy teams to selected wards.")
    edited = st.data_editor(editor_df, hide_index=True, width="stretch", height=260,
                            disabled=["city", "ward_id", "risk", f"cases_{sim_h}"],
                            key=f"dep_{preset}_{date_str}_{sim_h}_{teams}_{'-'.join(sim_cities)}_{p['max_reduction']}_{p['saturation_crews']}",
                            column_config={"crews": st.column_config.NumberColumn(min_value=0, max_value=50, step=1)})
    deployment = dict(zip(edited["ward_id"], edited["crews"].fillna(0).astype(int)))
    used = sum(deployment.values())
    if used > teams:
        st.error(f"{used} crews deployed but only {int(teams)} available. Remove {used - int(teams)} crew(s).")
        st.stop()
    sim, tot = simulate(fc, deployment, int(teams), R["rates"], sim_h, p)
    k = st.columns(6)
    kpi(k[0], f"Baseline cases ({HORIZON_NAME[sim_h]})", f"{tot['baseline_cases']:.1f}", "#94a3b8")
    kpi(k[1], "Simulated cases", f"{tot['simulated_cases']:.1f}", "#2dd4bf")
    kpi(k[2], "Cases prevented", f"{tot['cases_prevented']:.1f}", "#22c55e")
    kpi(k[3], "Bed-demand reduction", f"{tot['beds_reduction']:.1f}", "#64b5f6")
    kpi(k[4], "Saline reduction (bags)", f"{tot['saline_reduction']:.1f}", "#ce93d8")
    kpi(k[5], f"Prevented per crew ({used}/{int(teams)} crews)", f"{tot['cases_prevented_per_crew']:.2f}", "#ffb74d")
    st.caption(f"Across both horizons: {tot['prevented_2w']:.1f} cases prevented by 2 weeks, "
               f"{tot['prevented_4w']:.1f} by 4 weeks.")
    dep = sim[sim["crews"] > 0]
    a, b = st.columns([1.2, 1])
    with a:
        st.markdown("#### Baseline vs simulated, deployed wards")
        if len(dep):
            ch = dep.set_index("ward_id")[[f"cases_{sim_h}", f"simulated_{sim_h}"]]
            ch.columns = ["Baseline forecast", "With intervention"]
            st.bar_chart(ch, stack=False, height=300, color=["#94a3b8", "#2dd4bf"])
        else:
            st.info("No crews deployed: zero intervention, so zero cases prevented.")
    with b:
        st.markdown("#### Intervention ROI ranking")
        st.dataframe(sim[["roi_rank", "ward_id", "city", "crews", "cases_prevented_per_crew", "first_crew_roi",
                          f"prevented_{sim_h}", "beds_reduction", "saline_reduction"]],
                     hide_index=True, width="stretch", height=300)
        st.caption("ROI = cases prevented per crew. first_crew_roi = what one crew would prevent in that ward; "
                   "use it to decide where the next crew goes.")
    st.download_button("Download simulation (CSV)", sim.to_csv(index=False), f"simulation_{date_str}_{sim_h}.csv")

# ====================================================================== 6. Dispatch center
elif page == "Dispatch Center":
    c1, c2 = st.columns([1, 2])
    d_city = c1.selectbox("City", city_filter, key="d_city")
    city_plan = plan[plan["city"] == d_city].sort_values("priority_rank")
    default = city_plan[city_plan["critical_deficit"] | (city_plan["transferred_out"] > 0)]["ward_id"].tolist()[:5] \
        or city_plan["ward_id"].tolist()[:3]
    wards_sel = c2.multiselect("Wards", city_plan["ward_id"].tolist(), default=default)
    if not wards_sel:
        st.info("Select one or more wards to generate notices.")
        st.stop()
    notices = notices_for(city_plan[city_plan["ward_id"].isin(wards_sel)], R["transfers"])
    t1, t2, t3 = st.tabs(["SMS", "WhatsApp", "Commissioner brief (HTML / PDF)"])
    with t1:
        for n in notices:
            txt = sms_text(n)
            st.code(txt, language=None)
            st.caption(f"{len(txt)} characters ({-(-len(txt) // 153)} SMS segment(s))")
        st.download_button("Download SMS notices (.txt)", "\n\n".join(sms_text(n) for n in notices),
                           f"sms_{d_city}_{target_week}.txt")
    with t2:
        for n in notices:
            st.code(whatsapp_text(n), language=None)
        st.download_button("Download WhatsApp notices (.txt)", "\n\n----------\n\n".join(whatsapp_text(n) for n in notices),
                           f"whatsapp_{d_city}_{target_week}.txt")
    with t3:
        title = f"Commissioner dispatch brief: {d_city}, week of {target_week}"
        html = html_brief(notices, title)
        try:
            components.html(html, height=600, scrolling=True)
        except Exception:                          # renderer unavailable: the downloads below still work
            st.info("Preview unavailable in this Streamlit version; download the brief below.")
        c1, c2 = st.columns(2)
        c1.download_button("Download printable HTML brief", html, f"brief_{d_city}_{target_week}.html", "text/html")
        pdf = pdf_brief(notices, title)
        if pdf:
            c2.download_button("Download PDF brief", pdf, f"brief_{d_city}_{target_week}.pdf", "application/pdf")
        else:
            c2.info("PDF library not installed; use the HTML brief and print to PDF from the browser.")
    st.download_button("Download full 60-ward dispatch plan (CSV)", plan.to_csv(index=False),
                       f"dispatch_plan_{date_str}_{horizon}.csv", "text/csv")
    st.caption("Notices are built from local templates with the exact numbers on the allocation and routing pages. "
               "Delivery through SMS or WhatsApp gateways is not connected; notices are exported for officers to send.")

# ====================================================================== 7. Model accuracy (Phase 1 + Phase 2)
elif page == "Model Accuracy":
    st.markdown(f"Tested on weeks the model never saw: **{meta['split_date']} onward** (trained on 2016-2023 only).")
    m_cols = st.columns(2)
    for col, h in zip(m_cols, HORIZON_NAME):
        met = meta["metrics"][h]
        s = validation_summary(h)
        with col, st.container(border=True):
            st.markdown(f"**{HORIZON_NAME[h]} ahead**")
            a, b, c = st.columns(3)
            a.metric("MAE", f"{met['mae']}", help="cases per ward-week")
            b.metric("RMSE", f"{met['rmse']}")
            c.metric("R²", f"{met['r2']}")
            st.write(f"Persistence baseline (next = this week): MAE **{met['persistence_mae']}**, "
                     f"R² {met['persistence_r2']}. Guess-the-average MAE {met['baseline_mae']}.")
            st.write(f"Exact risk tier right: **{s['exact']:.0%}**. High or Critical weeks flagged Medium or "
                     f"above: **{s['outbreak_caught']:.0%}** ({s['n_outbreak']} weeks).")
    st.markdown("#### Resource demand: per-case rates fitted on training years")
    ev = meta["resource_rate_eval_2024_2025"]
    st.dataframe(pd.DataFrame([{"resource": RESOURCE_LABEL[r], "rate per case": meta["resource_rates"][r],
                                "exact match 2024-25": f"{ev[r]['exact_match']:.2%}", "MAE": ev[r]["mae"]}
                               for r in RESOURCES]), hide_index=True)
    st.caption("Each resource column in the onsite data is a deterministic function of same-week cases, so the "
               "rate reproduces it almost exactly. Planning error therefore comes from the case forecast.")
    ward = st.selectbox("Ward for actual vs predicted", sorted(view["ward_id"]))
    target = f"target_{horizon}"
    w = df[(df["ward_id"] == ward) & (df["date"] >= meta["split_date"])].dropna(subset=FEATURES + [target]).copy()
    w["Predicted"] = models[horizon].predict(w[FEATURES])
    w["Actual"] = w[target]
    w = w.set_index(w["date"] + pd.Timedelta(weeks=HORIZON_WEEKS[horizon]))
    st.line_chart(w[["Actual", "Predicted"]], height=300, color=["#e2e8f0", "#ffb74d"])
    st.caption("The model follows the seasonal pattern well but under-predicts the highest peaks; the Cautious "
               "demand basis is the planning buffer for this.")

# ====================================================================== 8. System / offline status
elif page == "System / Offline Status":
    st.markdown("#### Offline resilience")
    a, b = st.columns(2)
    a.metric("Internet", "Available" if online else "Offline", help="Probe only; never required")
    b.metric("Core functions requiring internet", "0 of 5")
    st.dataframe(pd.DataFrame(local_checks()), hide_index=True, width="stretch")
    rep = SYSTEM["report"]
    st.markdown(f"Dataset: **{rep['rows']:,} rows**, {rep['wards']} wards, {rep['cities']} cities, weeks "
                f"{rep['first_week']} to {rep['last_week']}, {rep['missing_values']} missing values, "
                f"{rep['duplicate_rows']} duplicate rows. Models trained with scikit-learn {meta['sklearn_version']}.")
    st.markdown("#### Offline kill-switch self-test")
    st.caption("Runs `offline_check.py` in a separate process with every socket and DNS call disabled, then exercises "
               "forecasting, allocation, routing, the simulator and all dispatch formats.")
    if st.button("Run offline self-test now"):
        with st.spinner("Running with the network disabled..."):
            res = subprocess.run([sys.executable, str(ROOT / "offline_check.py")], capture_output=True, text=True,
                                 timeout=600)
        (st.success if res.returncode == 0 else st.error)("PASSED" if res.returncode == 0 else "FAILED")
        st.code(res.stdout[-4000:] + res.stderr[-2000:], language=None)
