import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from config import CREWS_NEEDED_BY_TIER, HORIZON_NAME, HORIZON_WEEKS, PRIORITY_WEIGHTS, RESOURCE_LABEL, RESOURCES
from dispatch_generator import html_brief, notices_for, pdf_brief, sms_text, whatsapp_text
from features import FEATURES
from hospital_routing import CAPACITY_NOTE
from intervention_simulator import default_params, optimal_deployment, simulate
from pipeline import load_system, run_plan
from predict import LABELS, TIERS, driver_impacts, predict_with_range, risk_tier
from system_status import internet_reachable, local_checks
from integrations import textbee

st.set_page_config(page_title="Dengue early-warning and response", page_icon="🦟", layout="wide")

COLORS = {"Low": "#2e7d32", "Medium": "#f9a825", "High": "#ef6c00", "Critical": "#c62828"}
TEXT = {"Low": "#ffffff", "Medium": "#1a1a1a", "High": "#ffffff", "Critical": "#ffffff"}
PASTEL = {"Low": "#c8e6c9", "Medium": "#fff59d", "High": "#ffcc80", "Critical": "#ef9a9a"}
TEAL, RED, GREY, AMBER = "#2dd4bf", "#ef5350", "#64748b", "#ffb74d"
RAIN_COLS = [c for c in FEATURES if c.startswith("rain_")]
DEFAULT_WEEK = "2024-08-12"     # held-out test week with mixed risk and bed overflow (good for demos)
SHORT = {"saline_bags_needed": "Saline", "diagnostic_kits_needed": "Kits", "hospital_beds_required": "Beds"}

st.markdown("""
<style>
.block-container {padding-top: 3.2rem; padding-bottom: 2rem; max-width: 1400px;}
h1.page {font-size:1.6rem; margin:0 0 0.1rem 0;}
.scenario {display:flex; flex-wrap:wrap; gap:6px; margin:0.2rem 0 1rem 0;}
.chip {background:#1b2330; border:1px solid #2b3748; color:#cbd5e1; border-radius:999px; padding:3px 11px;
       font-size:0.82rem;}
.chip b {color:#f1f5f9;}
.kpi {background:#151c27; border:1px solid #263142; border-top:4px solid #2dd4bf; border-radius:10px;
      padding:12px 16px; min-height:112px; margin-bottom:0.6rem;}
.kpi .l {font-size:0.85rem; color:#94a3b8; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.kpi .n {font-size:1.9rem; font-weight:700; color:#f8fafc; line-height:1.25;}
.kpi .s {font-size:0.78rem; color:#94a3b8;}
.tier {padding:12px; border-radius:10px; text-align:center; font-size:1.8rem; font-weight:700; margin:6px 0 10px 0;}
.badge {display:inline-block; padding:4px 10px; border-radius:12px; font-weight:600; font-size:0.8rem; margin:2px 0;}
div[data-testid="stMetricValue"] {font-size:1.7rem;}
section[data-testid="stSidebar"] .block-container {padding-top: 1rem;}
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


# ------------------------------------------------------------------ small display helpers
def kpi(col, label, value, sub="", color=TEAL):
    col.markdown(f"<div class='kpi' style='border-top-color:{color}'><div class='l' title='{label}'>{label}</div>"
                 f"<div class='n'>{value}</div><div class='s'>{sub}&nbsp;</div></div>", unsafe_allow_html=True)


def header(title, note=None):
    st.markdown(f"<h1 class='page'>{title}</h1>", unsafe_allow_html=True)
    chips = [f"Data to <b>{date_str}</b>", f"Planning week <b>{target_week}</b>",
             f"<b>{HORIZON_NAME[horizon]}</b> ahead", f"Stock <b>{stock_pct}%</b>", f"<b>{int(total_crews)}</b> crews",
             f"{'Cautious' if basis == 'cautious' else 'Expected'} demand",
             'Priority-weighted' if policy == 'weighted' else 'Strict triage']
    if len(city_filter) < len(all_cities):
        chips.append("Cities: <b>" + ", ".join(city_filter) + "</b>")
    st.markdown("<div class='scenario'>" + "".join(f"<span class='chip'>{c}</span>" for c in chips) + "</div>",
                unsafe_allow_html=True)
    if note:
        st.caption(note)


def risk_colors(df, col="Risk"):
    return df.style.map(lambda v: f"background-color:{PASTEL[v]};color:#000" if v in PASTEL else "",
                        subset=[col]).format(precision=1)


def hbar(data, y, x_fields, colors, height=None, sort_field=None, title_x=""):
    """Horizontal stacked bar chart with readable ward labels and tooltips."""
    long = data.melt(id_vars=[y], value_vars=list(x_fields), var_name="Series", value_name="Value")
    order = data[y].tolist() if sort_field is None else data.sort_values(sort_field, ascending=False)[y].tolist()
    chart = alt.Chart(long).mark_bar().encode(
        y=alt.Y(f"{y}:N", sort=order, title=None, axis=alt.Axis(labelLimit=200, labelOverlap=False)),
        x=alt.X("Value:Q", title=title_x, stack=True),
        color=alt.Color("Series:N", scale=alt.Scale(domain=list(x_fields), range=colors),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=[y, "Series", "Value"],
    ).properties(height=height or max(160, 30 * len(data)))
    st.altair_chart(chart, width="stretch")


def num(label, fmt="%d"):
    return st.column_config.NumberColumn(label, format=fmt)


SYSTEM = get_system()
models, meta, df = SYSTEM["models"], SYSTEM["meta"], SYSTEM["df"]
tiers = meta["tiers"]
all_cities = sorted(df["city"].unique())
if "capacity" not in st.session_state:
    st.session_state.capacity = SYSTEM["capacity"][["city", "ward_id", "bed_capacity"]].copy()

# ------------------------------------------------------------------ sidebar: status + scenario controls
online = net_status()
st.sidebar.markdown(
    "<span class='badge' style='background:#14532d;color:#dcfce7'>● Running locally</span> "
    + ("<span class='badge' style='background:#1e3a5f;color:#dbeafe'>Internet: on (not needed)</span>"
       if online else "<span class='badge' style='background:#7c2d12;color:#ffedd5'>Internet: OFFLINE · all features work</span>"),
    unsafe_allow_html=True)
st.sidebar.subheader("Scenario")
dates = sorted(df.dropna(subset=FEATURES)["date"].dt.strftime("%Y-%m-%d").unique(), reverse=True)
date_str = st.sidebar.selectbox("Forecast from week", dates, index=dates.index(DEFAULT_WEEK),
                                help="Latest week of data. Forecasts look 2 and 4 weeks beyond it. Weeks inside the "
                                     "dataset are a replay; the newest week (2025-12-29) is a genuine forecast.")
horizon = st.sidebar.radio("Horizon", list(HORIZON_NAME), format_func=HORIZON_NAME.get, horizontal=True)
stock_pct = st.sidebar.slider("Available regional stock (%)", 30, 100, 60, 5,
                              help="Share of total forecast demand that is in stock, for each supply.")
total_crews = st.sidebar.number_input("Total spraying crews", min_value=0, max_value=500, value=40, step=1)
with st.sidebar.expander("Advanced settings"):
    basis = st.radio("Demand basis", ["expected", "cautious"], horizontal=True,
                     format_func={"expected": "Expected", "cautious": "Cautious (P90)"}.get,
                     help="Cautious plans for the 90th percentile across the forest's trees, a buffer because the "
                          "model under-predicts the largest peaks.")
    policy = st.radio("Scarcity policy", ["weighted", "triage"], horizontal=True,
                      format_func={"weighted": "Priority-weighted", "triage": "Strict triage"}.get,
                      help="Priority-weighted: higher-priority wards get a larger share, top wards first. "
                           "Strict triage: fill wards completely in priority order.")
    w_risk = st.slider("Priority weight on risk (rest = density)", 0.0, 1.0, float(PRIORITY_WEIGHTS["risk"]), 0.05)
    city_filter = st.multiselect("Show cities", all_cities, default=all_cities) or all_cities

R = cached_plan(date_str, horizon, stock_pct, int(total_crews), policy, basis, st.session_state.capacity, w_risk)
plan = R["plan"]
view = plan[plan["city"].isin(city_filter)]
target_week = R["target_week"].strftime("%Y-%m-%d")


# ====================================================================== pages
def page_overview():
    header("Executive overview")
    short = view[view["critical_deficit"]]
    if len(short):
        st.error(f"**Critical supply deficit in {len(short)} of {len(view)} wards.** Demand cannot be fully met "
                 f"at {stock_pct}% regional stock. See *Resource allocation*.", icon="🚨")
    else:
        st.success("All forecast supply demand is met at the current stock level.", icon="✅")
    transfers = int(R["transfers"]["patients"].sum()) if len(R["transfers"]) else 0
    c = st.columns(4)
    kpi(c[0], "Projected cases", f"{view['predicted_cases'].sum():.0f}", f"week of {target_week}", AMBER)
    kpi(c[1], "High / Critical wards", f"{int(view['risk'].isin(['High', 'Critical']).sum())}",
        f"of {len(view)} wards", COLORS["High"])
    kpi(c[2], "Wards short of supplies", f"{len(short)}", "at least one supply < 100%", RED)
    kpi(c[3], "Patients without a bed", f"{int(view['unresolved_deficit'].sum())}",
        f"{transfers} moved within city", RED if view["unresolved_deficit"].sum() else TEAL)
    st.write("")

    t1, t2, t3 = st.tabs(["📦 Supplies", "🏙️ Cities", "⭐ Priority wards"])
    with t1:
        s = R["supply_summary"].copy()
        s["Supply"] = s["resource"].map(RESOURCE_LABEL)
        s["Met %"] = (100 * s["allocated"] / s["required"].where(s["required"] > 0)).fillna(100)
        cr = R["crews"]
        crew_row = pd.DataFrame([{"Supply": "Spraying crews", "required": cr["needed"], "available_stock": cr["total"],
                                  "allocated": cr["assigned"], "deficit": cr["shortfall"],
                                  "wards_short": int((plan["crews_deficit"] > 0).sum()),
                                  "Met %": 100 * cr["assigned"] / cr["needed"] if cr["needed"] else 100}])
        s = pd.concat([s, crew_row], ignore_index=True)
        a, b = st.columns([1.6, 1])
        a.dataframe(s[["Supply", "required", "available_stock", "allocated", "deficit", "Met %"]],
                    hide_index=True, width="stretch", column_config={
                        "required": num("Required"), "available_stock": num("In stock"),
                        "allocated": num("Allocated"), "deficit": num("Short by"), "wards_short": num("Wards short"),
                        "Met %": st.column_config.ProgressColumn("Met", format="%.0f%%", min_value=0, max_value=100)})
        with b:
            hbar(s.rename(columns={"allocated": "Allocated", "deficit": "Short by"}), "Supply",
                 ["Allocated", "Short by"], [TEAL, RED], height=210)
        st.caption("All 60 wards share one regional pool. Crews: needed by risk tier, assigned in priority order.")
    with t2:
        city = view.groupby("city").agg(
            cases=("predicted_cases", "sum"), hc=("risk", lambda r: int(r.isin(["High", "Critical"]).sum())),
            short=("critical_deficit", "sum"), saline=("saline_bags_needed_deficit", "sum"),
            kits=("diagnostic_kits_needed_deficit", "sum"), crews=("crews_assigned", "sum"),
            unplaced=("unresolved_deficit", "sum")).reset_index()
        a, b = st.columns([1.3, 1])
        a.dataframe(city, hide_index=True, width="stretch", column_config={
            "city": "City", "cases": num("Projected cases", "%.0f"), "hc": num("High/Critical"),
            "short": num("Wards short"), "saline": num("Saline short"), "kits": num("Kits short"),
            "crews": num("Crews"), "unplaced": num("No bed")})
        with b:
            hbar(city.rename(columns={"cases": "Projected cases"}), "city", ["Projected cases"], [AMBER],
                 sort_field="Projected cases", height=200)
    with t3:
        top = view.sort_values("priority_rank").head(10)
        tbl = pd.DataFrame({
            "Rank": top["priority_rank"], "Ward": top["ward_id"], "City": top["city"], "Risk": top["risk"],
            "Cases": top["predicted_cases"],
            "Saline": top["saline_bags_needed_allocated"].astype(str) + " / " + top["saline_bags_needed_required"].astype(str),
            "Kits": top["diagnostic_kits_needed_allocated"].astype(str) + " / " + top["diagnostic_kits_needed_required"].astype(str),
            "Crews": top["crews_assigned"], "Status": top["critical_deficit"].map({True: "⚠ Deficit", False: "✓ Supplied"})})
        st.dataframe(risk_colors(tbl), hide_index=True, width="stretch")
        st.caption("Saline and kits shown as allocated / required.")


def page_forecast():
    header("Ward forecast")
    c1, c2 = st.columns(2)
    city = c1.selectbox("City", city_filter)
    ward = c2.selectbox("Ward", sorted(df.loc[df["city"] == city, "ward_id"].unique()))
    row = df[(df["ward_id"] == ward) & (df["date"] == pd.Timestamp(date_str))].copy()
    t1, t2, t3 = st.tabs(["Forecast", "Drivers and weather", "All-ward ranking"])
    with t1:
        rain_mult = st.slider("Rainfall scenario (× recent rain)", 0.0, 2.0, 1.0, 0.1,
                              help="1.0 = actual weather. The forest responds in steps; treat this as a scenario.")
        row[RAIN_COLS] = row[RAIN_COLS] * rain_mult
        cols = st.columns(2)
        for col, h in zip(cols, HORIZON_NAME):
            pred, lo, hi = predict_with_range(models[h], row)
            tier = risk_tier(pred, tiers)
            wk = pd.Timestamp(date_str) + pd.Timedelta(weeks=HORIZON_WEEKS[h])
            act = df[(df["ward_id"] == ward) & (df["date"] == wk)]
            with col, st.container(border=True):
                st.markdown(f"**In {HORIZON_NAME[h]}** · week of {wk.strftime('%d %b %Y')}")
                st.markdown(f"<div class='tier' style='background:{COLORS[tier]};color:{TEXT[tier]}'>{tier}</div>",
                            unsafe_allow_html=True)
                st.metric("Predicted cases per week", f"{pred:.1f}")
                st.caption(f"Likely range {lo:.1f} to {hi:.1f} (10th to 90th percentile of the trees)")
                if act.empty:
                    st.caption("Actual: not in the dataset yet (genuine forecast).")
                else:
                    tag = "training year" if wk < pd.Timestamp(meta["split_date"]) else "held-out test week"
                    st.caption(f"Actual that week: **{int(act['dengue_cases'].iloc[0])}** ({tag})")
    with t2:
        a, b = st.columns([1.2, 1])
        with a:
            st.markdown(f"**What drives the {HORIZON_NAME[horizon]} forecast**")
            imp = driver_impacts(models[horizon], row, meta["baseline"]).rename(LABELS)
            d = imp.reset_index()
            d.columns = ["Input", "Effect"]
            d["Direction"] = d["Effect"].map(lambda v: "Raises cases" if v >= 0 else "Lowers cases")
            ch = alt.Chart(d).mark_bar().encode(
                y=alt.Y("Input:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
                x=alt.X("Effect:Q", title="Change in predicted cases vs a typical week"),
                color=alt.Color("Direction:N", scale=alt.Scale(domain=["Raises cases", "Lowers cases"],
                                                               range=[RED, TEAL]), legend=alt.Legend(orient="top", title=None)),
                tooltip=["Input", alt.Tooltip("Effect:Q", format="+.2f")]).properties(height=380)
            st.altair_chart(ch, width="stretch")
            st.caption("Approximate, not causal.")
        with b:
            st.markdown("**Recent weather (12 weeks)**")
            hist = df[(df["ward_id"] == ward) & (df["date"] <= pd.Timestamp(date_str))].tail(12).set_index("date")
            st.caption("Rainfall (mm/week)")
            st.bar_chart(hist["rainfall_mm"], height=130, color="#64b5f6")
            st.caption("Average temperature (°C)")
            st.line_chart(hist["avg_temp_c"], height=110, color=AMBER)
            st.caption("Relative humidity (%)")
            st.line_chart(hist["relative_humidity_pct"], height=110, color="#ce93d8")
    with t3:
        other = "4w" if horizon == "2w" else "2w"
        fc = R["forecast"][R["forecast"]["city"].isin(city_filter)]
        rank = pd.DataFrame({"Ward": fc["ward_id"], "City": fc["city"], "Risk": fc[f"risk_{horizon}"],
                             f"Cases in {HORIZON_NAME[horizon]}": fc[f"cases_{horizon}"],
                             f"Cases in {HORIZON_NAME[other]}": fc[f"cases_{other}"]}
                            ).sort_values(f"Cases in {HORIZON_NAME[horizon]}", ascending=False)
        counts = pd.crosstab(rank["City"], rank["Risk"]).reindex(columns=list(TIERS), fill_value=0)
        a, b = st.columns([1, 2])
        a.markdown("**Wards per risk tier**")
        a.dataframe(counts, width="stretch")
        b.dataframe(risk_colors(rank), hide_index=True, width="stretch", height=360)
        st.download_button("Download ranking (CSV)", rank.to_csv(index=False), f"dengue_risk_{date_str}_{horizon}.csv",
                           "text/csv")


def page_allocation():
    header("Resource allocation")
    s = R["supply_summary"].set_index("resource")
    cr = R["crews"]
    cols = st.columns(4)
    for col, r in zip(cols, RESOURCES):
        d = int(s.loc[r, "deficit"])
        kpi(col, RESOURCE_LABEL[r], f"{int(s.loc[r, 'allocated']):,} / {int(s.loc[r, 'required']):,}",
            f"short by {d:,}" if d else "fully met", RED if d else TEAL)
    kpi(cols[3], "Spraying crews", f"{cr['assigned']} / {cr['needed']}",
        f"short by {cr['shortfall']}" if cr["shortfall"] else f"{cr['idle']} idle", RED if cr["shortfall"] else TEAL)
    n_short = int(view["critical_deficit"].sum())
    if n_short:
        st.error(f"**Critical supply deficit:** {n_short} ward(s) cannot be 100% supplied.", icon="🚨")

    c1, c2, c3 = st.columns([1.4, 1, 1])
    res = c1.segmented_control("Supply", list(RESOURCES), format_func=RESOURCE_LABEL.get, default=RESOURCES[0]) \
        or RESOURCES[0]
    only_short = c2.toggle("Only wards with a shortfall", value=False)
    top_n = c3.selectbox("Chart", [15, 30, 60], format_func=lambda n: f"Top {n} by priority" if n < 60 else "All wards")

    t = view.sort_values("priority_rank")
    if only_short:
        t = t[t[f"{res}_deficit"] > 0]
    tbl = pd.DataFrame({
        "Rank": t["priority_rank"], "Ward": t["ward_id"], "City": t["city"], "Risk": t["risk"],
        "Cases": t["predicted_cases"], "Priority": t["priority"], "Required": t[f"{res}_required"],
        "Allocated": t[f"{res}_allocated"], "Short by": t[f"{res}_deficit"], "Met": t[f"{res}_fill_pct"],
        "Crews": t["crews_assigned"].astype(str) + " / " + t["crews_needed"].astype(str),
        "Status": t["critical_deficit"].map({True: "⚠ Deficit", False: "✓ Supplied"})})
    st.markdown(f"**{RESOURCE_LABEL[res]}: allocated vs shortfall, highest priority at the top**")
    if len(tbl):
        hbar(tbl.head(top_n), "Ward", ["Allocated", "Short by"], [TEAL, RED])
    else:
        st.info("No ward is short of this supply.")
    with st.container():
        st.markdown("**Ward detail**")
        st.dataframe(
            tbl.style.map(lambda v: f"background-color:{PASTEL[v]};color:#000" if v in PASTEL else "", subset=["Risk"])
            .map(lambda v: "color:#fca5a5;font-weight:600" if v == "⚠ Deficit" else "color:#86efac",
                 subset=["Status"]).format({"Cases": "{:.1f}", "Priority": "{:.2f}"}),
            hide_index=True, width="stretch", height=min(620, 38 + 35 * max(len(tbl), 1)),
            column_config={"Met": st.column_config.ProgressColumn("Met", format="%.0f%%", min_value=0, max_value=100)})
    full = view.sort_values("priority_rank")[
        ["priority_rank", "city", "ward_id", "risk", "predicted_cases", "population_density_sqkm", "priority"]
        + [f"{r}_{k}" for r in RESOURCES for k in ("required", "allocated", "deficit")]
        + ["crews_needed", "crews_assigned", "alert"]]
    st.download_button("Download full allocation, all supplies (CSV)", full.to_csv(index=False),
                       f"allocation_{date_str}_{horizon}_{stock_pct}pct.csv", "text/csv")
    with st.expander("How the allocation works"):
        rates = meta["resource_rates"]
        st.markdown(f"""
- **Demand** = forecast cases × per-case rate fitted on 2016-2023 (saline {rates['saline_bags_needed']:.2f},
  kits {rates['diagnostic_kits_needed']:.2f}, beds {rates['hospital_beds_required']:.2f}), rounded.
- **Stock** = {stock_pct}% of total demand over all 60 wards, per supply.
- **Priority** = {w_risk:.2f} × risk (Low 0, Medium ⅓, High ⅔, Critical 1) + {1 - w_risk:.2f} × population density
  (scaled 0-1). Ties: higher forecast, then ward ID.
- **Priority-weighted:** each ward gets min(1, λ × priority) of its demand, λ chosen so the total equals stock.
  **Strict triage:** fill wards completely in priority order.
- **Crews needed** by tier {CREWS_NEEDED_BY_TIER}, dealt one at a time in priority order.
- Weights and crew needs are configurable assumptions, not official policy.
""")


def page_routing():
    header("Hospital overflow routing")
    st.warning("Bed capacities are a **demo assumption**, not verified hospital data. "
               "Edit them at the bottom of this page.", icon="⚠️")
    rt = R["routing"][R["routing"]["city"].isin(city_filter)]
    cb = R["city_beds"][R["city_beds"]["city"].isin(city_filter)].copy()
    over_b = rt[rt["deficit_before"] > 0].groupby("city").size()
    over_a = rt[rt["unresolved_deficit"] > 0].groupby("city").size()
    moved = int(R["transfers"]["patients"].sum()) if len(R["transfers"]) else 0
    c = st.columns(4)
    kpi(c[0], "Bed demand", f"{int(cb['bed_demand'].sum())}", f"capacity {int(cb['bed_capacity'].sum())}", AMBER)
    kpi(c[1], "Wards over capacity", f"{int(over_b.sum())}", "before routing", COLORS["High"])
    kpi(c[2], "Patients moved", f"{moved}", "within their own city", TEAL)
    kpi(c[3], "Patients without a bed", f"{int(cb['unresolved_deficit'].sum())}", "after routing",
        RED if cb["unresolved_deficit"].sum() else TEAL)
    if (rt["unresolved_deficit"] > 0).any():
        st.error(f"{int(rt['unresolved_deficit'].sum())} patient(s) cannot be placed in their own city. "
                 "Escalate for surge beds.", icon="🚨")
    st.write("")

    st.markdown("**City bed pools** (transfers never cross city lines)")
    cb["over_before"] = cb["city"].map(over_b).fillna(0).astype(int)
    cb["over_after"] = cb["city"].map(over_a).fillna(0).astype(int)
    st.dataframe(cb[["city", "bed_demand", "bed_capacity", "utilization_after_pct", "transferred", "headroom_after",
                     "over_before", "over_after", "unresolved_deficit"]],
                 hide_index=True, width="stretch", column_config={
                     "city": "City", "bed_demand": num("Bed demand"), "bed_capacity": num("Capacity"),
                     "utilization_after_pct": st.column_config.ProgressColumn("Utilisation", format="%.0f%%",
                                                                              min_value=0, max_value=100),
                     "transferred": num("Moved"), "headroom_after": num("Free beds left"),
                     "over_before": num("Wards over (before)"), "over_after": num("Wards over (after)"),
                     "unresolved_deficit": num("No bed")})

    t1, t2, t3 = st.tabs(["🔁 Transfers", "🏥 Ward deficits and headroom", "✏️ Edit bed capacity"])
    with t1:
        tr = R["transfers"]
        tr = tr[tr["city"].isin(city_filter)] if len(tr) else tr
        if len(tr):
            st.dataframe(tr, hide_index=True, width="stretch", column_config={
                "city": "City", "from_ward": "From ward", "to_ward": "To ward", "patients": num("Patients")})
        else:
            st.info("No overflow this week: every ward is within local capacity.")
        st.caption("Rule: the ward with the largest deficit sends first, always to the same-city ward with the most "
                   "free beds, until its deficit is cleared or the city is full.")
    with t2:
        show_all = st.toggle("Show all wards", value=False, help="Off: only wards that send, receive or are short.")
        w = rt if show_all else rt[rt["status"] != "Within capacity"]
        if w.empty:
            st.info("All wards are within capacity.")
        else:
            st.dataframe(w[["city", "ward_id", "beds_demand", "bed_capacity", "deficit_before", "transferred_out",
                            "transferred_in", "unresolved_deficit", "headroom_after", "status"]]
                         .sort_values(["city", "deficit_before"], ascending=[True, False]),
                         hide_index=True, width="stretch", height=380, column_config={
                             "city": "City", "ward_id": "Ward", "beds_demand": num("Demand"),
                             "bed_capacity": num("Capacity"), "deficit_before": num("Over by"),
                             "transferred_out": num("Sent"), "transferred_in": num("Received"),
                             "unresolved_deficit": num("No bed"), "headroom_after": num("Free after"),
                             "status": "Status"})
    with t3:
        st.caption(CAPACITY_NOTE)
        edited = st.data_editor(st.session_state.capacity, hide_index=True, width="stretch", height=320,
                                disabled=["city", "ward_id"], key="cap_editor",
                                column_config={"city": "City", "ward_id": "Ward",
                                               "bed_capacity": st.column_config.NumberColumn("Beds", min_value=0, step=1)})
        a, b, _ = st.columns([1, 1, 3])
        if a.button("Apply changes", type="primary"):
            st.session_state.capacity = edited.fillna(0).astype({"bed_capacity": int})
            st.rerun()
        if b.button("Reset to demo"):
            st.session_state.capacity = SYSTEM["capacity"][["city", "ward_id", "bed_capacity"]].copy()
            st.rerun()


def page_simulator():
    header("Vector control simulator")
    st.info("Simulated scenarios, not proven effects: the data has no spraying records, so effectiveness is an "
            "editable assumption applied to the ML forecast.", icon="ℹ️")
    left, right = st.columns([1, 1.25], gap="large")
    with left:
        st.markdown("**1 · Set up**")
        sim_cities = st.multiselect("Cities", all_cities, default=city_filter, key="sim_cities")
        c1, c2 = st.columns(2)
        sim_h = c1.radio("Outcome at", list(HORIZON_NAME), index=list(HORIZON_NAME).index(horizon),
                         format_func=HORIZON_NAME.get, horizontal=True, key="sim_h")
        teams = c2.number_input("Teams available", 0, 500, int(total_crews), key="sim_teams")
        p = default_params()
        with st.expander("Effectiveness assumptions"):
            p["max_reduction"] = st.slider("Max reduction (any number of crews)", 0.0, 0.9, p["max_reduction"], 0.05)
            p["saturation_crews"] = st.slider("Saturation (crews)", 0.5, 6.0, p["saturation_crews"], 0.5)
            p["timing"]["2w"] = st.slider("Share of effect by 2 weeks", 0.0, 1.0, p["timing"]["2w"], 0.05)
            p["timing"]["4w"] = st.slider("Share of effect by 4 weeks", 0.0, 1.0, p["timing"]["4w"], 0.05)
            st.latex(r"\text{prevented} = \text{forecast} \times m\,(1-e^{-n/s}) \times \tau_h")
        if not sim_cities:
            st.warning("Select at least one city.")
            return
        fc = R["forecast"][R["forecast"]["city"].isin(sim_cities)].rename(columns={f"risk_{sim_h}": "risk"})
        st.markdown("**2 · Deploy teams**")
        preset = st.segmented_control("Start from", ["engine", "optimal", "none"], default="optimal",
                                      format_func={"engine": "Allocation engine", "optimal": "Optimise",
                                                   "none": "Empty"}.get) or "optimal"
        if preset == "engine":
            eng = plan.set_index("ward_id")["crews_assigned"]
            start, left_ = {}, int(teams)
            for w in plan.sort_values("priority_rank")["ward_id"]:
                if w in set(fc["ward_id"]) and eng[w] and left_:
                    start[w] = min(int(eng[w]), left_)
                    left_ -= start[w]
        elif preset == "optimal":
            start = optimal_deployment(fc, int(teams), sim_h, p)
        else:
            start = {}
        ed = pd.DataFrame({"ward_id": fc["ward_id"]})
        ed["crews"] = ed["ward_id"].map(start).fillna(0).astype(int)
        ed["risk"] = fc["risk"].values
        ed["cases"] = fc[f"cases_{sim_h}"].values
        ed = ed.sort_values(["crews", "cases"], ascending=False)
        edited = st.data_editor(
            ed, hide_index=True, width="stretch", height=300, disabled=["ward_id", "risk", "cases"],
            key=f"dep_{preset}_{date_str}_{sim_h}_{teams}_{'-'.join(sim_cities)}_{p['max_reduction']}_{p['saturation_crews']}",
            column_config={"ward_id": "Ward", "risk": "Risk",
                           "cases": num(f"Forecast ({HORIZON_NAME[sim_h]})", "%.1f"),
                           "crews": st.column_config.NumberColumn("Crews ✏️", min_value=0, max_value=50, step=1)})
        st.caption("Edit the **Crews** column to change the deployment.")
    deployment = dict(zip(edited["ward_id"], edited["crews"].fillna(0).astype(int)))
    used = sum(deployment.values())
    with right:
        st.markdown("**3 · Results**")
        if used > teams:
            st.error(f"{used} crews deployed but only {int(teams)} available. Remove {used - int(teams)}.")
            return
        sim, tot = simulate(fc, deployment, int(teams), R["rates"], sim_h, p)
        r1 = st.columns(3)
        kpi(r1[0], "Baseline cases", f"{tot['baseline_cases']:.0f}", "no intervention", GREY)
        kpi(r1[1], "With intervention", f"{tot['simulated_cases']:.0f}", "simulated", TEAL)
        kpi(r1[2], "Cases prevented", f"{tot['cases_prevented']:.1f}", f"by {HORIZON_NAME[sim_h]}", "#22c55e")
        st.write("")
        r2 = st.columns(3)
        kpi(r2[0], "Fewer beds needed", f"{tot['beds_reduction']:.1f}", "bed-weeks", "#64b5f6")
        kpi(r2[1], "Fewer saline bags", f"{tot['saline_reduction']:.0f}", "bags", "#ce93d8")
        kpi(r2[2], "Prevented per crew", f"{tot['cases_prevented_per_crew']:.2f}", f"{used}/{int(teams)} crews used",
            AMBER)
        st.caption(f"Across horizons: {tot['prevented_2w']:.1f} cases prevented by 2 weeks, "
                   f"{tot['prevented_4w']:.1f} by 4 weeks.")
        dep = sim[sim["crews"] > 0].head(15)
        if len(dep):
            ch = dep[["ward_id", f"simulated_{sim_h}", f"prevented_{sim_h}"]].rename(
                columns={f"simulated_{sim_h}": "Remaining cases", f"prevented_{sim_h}": "Prevented"})
            st.markdown("**Deployed wards: forecast split into remaining vs prevented**")
            hbar(ch, "ward_id", ["Remaining cases", "Prevented"], [GREY, "#22c55e"], sort_field="Prevented")
        else:
            st.info("No crews deployed: zero intervention, so nothing is prevented.")
    st.markdown("**Intervention ROI ranking** (cases prevented per crew)")
    st.dataframe(sim[["roi_rank", "ward_id", "city", "crews", "cases_prevented_per_crew", "first_crew_roi",
                      f"prevented_{sim_h}", "beds_reduction", "saline_reduction"]],
                 hide_index=True, width="stretch", height=300, column_config={
                     "roi_rank": num("Rank"), "ward_id": "Ward", "city": "City", "crews": num("Crews"),
                     "cases_prevented_per_crew": num("Prevented per crew", "%.2f"),
                     "first_crew_roi": num("If 1 crew sent", "%.2f"), f"prevented_{sim_h}": num("Prevented", "%.1f"),
                     "beds_reduction": num("Beds saved", "%.1f"), "saline_reduction": num("Saline saved", "%.1f")})
    st.caption("“If 1 crew sent” shows what a single crew would prevent in that ward: use it to decide where the next "
               "crew goes.")
    st.download_button("Download simulation (CSV)", sim.to_csv(index=False), f"simulation_{date_str}_{sim_h}.csv")


CONTACTS_FILE = ROOT / "data" / "ward_contacts.csv"            # local only, git-ignored (personal data)
CONTACTS_EXAMPLE = ROOT / "data" / "ward_contacts.example.csv"


def _secrets():
    try:
        st.secrets.to_dict()          # raises if no secrets file exists
        return st.secrets
    except Exception:
        return None


def textbee_config():
    return textbee.load_config(_secrets())


def load_contacts():
    if "contacts" not in st.session_state:
        src = CONTACTS_FILE if CONTACTS_FILE.exists() else CONTACTS_EXAMPLE
        try:
            c = pd.read_csv(src, dtype=str).fillna("")
        except Exception:
            c = pd.DataFrame(columns=["city", "ward_id", "contact_name", "phone"])
        st.session_state.contacts = c
    return st.session_state.contacts


def sms_send_panel(notices, d_city):
    """Optional real SMS delivery through TextBee. Nothing is sent without an explicit confirmation."""
    st.markdown("#### Send by SMS (TextBee)")
    cfg = textbee_config()
    if cfg is None:
        st.info("Sending is off: no TextBee API key is configured, so notices are generated and exported only. "
                "To enable it, add `TEXTBEE_API_KEY` (and optionally `TEXTBEE_DEVICE_ID`) to "
                "`.streamlit/secrets.toml` or Streamlit Cloud secrets. See README, *SMS delivery with TextBee*.")
        return
    st.caption(f"TextBee configured · device: {cfg['device_id'] or 'default device'} · gateway: {cfg['base_url']}. "
               "Messages go out from the phone running the TextBee app; normal SMS charges and plan limits apply.")
    contacts = load_contacts()
    wards = [n["ward_id"] for n in notices]
    cur = contacts.set_index("ward_id") if len(contacts) else pd.DataFrame()
    ed = pd.DataFrame({"ward_id": wards,
                       "contact_name": [cur["contact_name"].get(w, "") if len(cur) else "" for w in wards],
                       "phone": [cur["phone"].get(w, "") if len(cur) else "" for w in wards]})
    edited = st.data_editor(ed, hide_index=True, width="stretch", key=f"sms_contacts_{d_city}_{'-'.join(wards)}",
                            disabled=["ward_id"], column_config={
                                "ward_id": "Ward", "contact_name": "Ward commissioner / officer",
                                "phone": st.column_config.TextColumn("Mobile number",
                                                                     help="e.g. 01712345678 or +8801712345678")})
    edited["number"] = edited["phone"].map(textbee.normalize_phone)
    valid = edited[edited["number"].notna()]
    invalid = edited[edited["phone"].str.strip().ne("") & edited["number"].isna()]
    if len(invalid):
        st.warning("Not a valid mobile number: " + ", ".join(invalid["ward_id"]))
    if st.button("Save contacts for this session", help="Kept in memory. To keep them, copy data/ward_contacts.example.csv "
                                                     "to data/ward_contacts.csv and fill it in (it is git-ignored)."):
        upd = contacts.set_index("ward_id")
        for r in edited.itertuples():
            upd.loc[r.ward_id, ["contact_name", "phone"]] = [r.contact_name, r.phone]
        st.session_state.contacts = upd.reset_index()
        st.success("Contacts saved for this session.")
    if valid.empty:
        st.caption("Enter at least one valid mobile number to enable sending.")
        return
    batch = st.session_state.get("sms_batches", 0)          # new checkbox after every send: confirm again each time
    confirm = st.checkbox(f"I confirm sending {len(valid)} real SMS to the numbers above.", key=f"sms_confirm_{batch}")
    if st.button(f"Send {len(valid)} SMS now", type="primary", disabled=not confirm):
        by_ward = {n["ward_id"]: n for n in notices}
        results = []
        with st.spinner("Sending through TextBee..."):
            for r in valid.itertuples():
                res = textbee.send_sms([r.number], sms_text(by_ward[r.ward_id]), cfg)
                results.append({"time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"), "ward_id": r.ward_id,
                                "number": r.number, "result": "Accepted by TextBee" if res["ok"] else "Failed",
                                "http_status": res["status"], "detail": res["detail"]})
        log = pd.DataFrame(results)
        st.session_state.sms_log = pd.concat([st.session_state.get("sms_log", pd.DataFrame()), log],
                                             ignore_index=True)
        n_ok = int((log["result"] != "Failed").sum())
        (st.success if n_ok == len(log) else st.warning)(
            f"{n_ok} of {len(log)} message(s) accepted by TextBee. 'Accepted' means queued on the phone; "
            "confirm delivery in the TextBee dashboard.")
        st.session_state.sms_batches = batch + 1
    if "sms_log" in st.session_state and len(st.session_state.sms_log):
        st.dataframe(st.session_state.sms_log, hide_index=True, width="stretch")
        st.download_button("Download send log (CSV)", st.session_state.sms_log.to_csv(index=False),
                           "sms_send_log.csv", "text/csv")


def page_dispatch():
    header("Dispatch center")
    c1, c2 = st.columns([1, 2.2])
    d_city = c1.selectbox("City", city_filter, key="d_city")
    city_plan = plan[plan["city"] == d_city].sort_values("priority_rank")
    default = city_plan[city_plan["critical_deficit"] | (city_plan["transferred_out"] > 0)]["ward_id"].tolist()[:3] \
        or city_plan["ward_id"].tolist()[:3]
    wards_sel = c2.multiselect("Wards (highest priority first)", city_plan["ward_id"].tolist(), default=default)
    if not wards_sel:
        st.info("Select one or more wards to generate notices.")
        return
    notices = notices_for(city_plan[city_plan["ward_id"].isin(wards_sel)], R["transfers"])
    t1, t2, t3 = st.tabs(["💬 SMS", "🟢 WhatsApp", "🖨️ Commissioner brief"])
    with t1:
        cols = st.columns(2)
        for i, n in enumerate(notices):
            txt = sms_text(n)
            with cols[i % 2], st.container(border=True):
                st.markdown(f"**{n['ward_id']}** · {n['risk']} · {-(-len(txt) // 153)} SMS segment(s)")
                st.text(txt)
        st.download_button("Download SMS (.txt)", "\n\n".join(sms_text(n) for n in notices),
                           f"sms_{d_city}_{target_week}.txt")
        st.divider()
        sms_send_panel(notices, d_city)
    with t2:
        cols = st.columns(2)
        for i, n in enumerate(notices):
            with cols[i % 2], st.container(border=True):
                st.text(whatsapp_text(n))
        st.download_button("Download WhatsApp (.txt)", "\n\n----------\n\n".join(whatsapp_text(n) for n in notices),
                           f"whatsapp_{d_city}_{target_week}.txt")
    with t3:
        title = f"Commissioner dispatch brief: {d_city}, week of {target_week}"
        html = html_brief(notices, title)
        a, b, _ = st.columns([1, 1, 2])
        a.download_button("Download HTML (printable)", html, f"brief_{d_city}_{target_week}.html", "text/html")
        pdf = pdf_brief(notices, title)
        if pdf:
            b.download_button("Download PDF", pdf, f"brief_{d_city}_{target_week}.pdf", "application/pdf")
        try:
            components.html(html, height=620, scrolling=True)
        except Exception:
            st.info("Preview unavailable in this Streamlit version; use the downloads above.")
    st.divider()
    st.download_button("Download full 60-ward dispatch plan (CSV)", plan.to_csv(index=False),
                       f"dispatch_plan_{date_str}_{horizon}.csv", "text/csv")
    st.caption("Built from local templates with the same numbers as the allocation and routing pages. SMS can be "
               "sent through TextBee when configured (SMS tab); WhatsApp and briefs are exported for officers to send.")


def page_accuracy():
    header("Model accuracy", f"Tested on weeks the model never saw ({meta['split_date']} onward); trained on 2016-2023.")
    cols = st.columns(2)
    for col, h in zip(cols, HORIZON_NAME):
        met = meta["metrics"][h]
        s = validation_summary(h)
        with col, st.container(border=True):
            st.markdown(f"#### {HORIZON_NAME[h]} ahead")
            a, b, c = st.columns(3)
            a.metric("MAE (cases)", f"{met['mae']}", delta=f"{met['mae'] - met['persistence_mae']:+.2f} vs persistence",
                     delta_color="inverse")
            b.metric("RMSE", f"{met['rmse']}")
            c.metric("R²", f"{met['r2']}")
            st.caption(f"Persistence baseline MAE {met['persistence_mae']}, R² {met['persistence_r2']} · "
                       f"guess-the-average MAE {met['baseline_mae']}")
            st.progress(s["exact"], text=f"Exact risk tier right: {s['exact']:.0%}")
            st.progress(s["outbreak_caught"], text=f"High/Critical weeks flagged Medium or above: "
                                                   f"{s['outbreak_caught']:.0%} ({s['n_outbreak']} weeks)")
    a, b = st.columns([1.4, 1])
    with a:
        st.markdown(f"**Actual vs predicted, {HORIZON_NAME[horizon]} ahead**")
        ward = st.selectbox("Ward", sorted(view["ward_id"]), label_visibility="collapsed")
        target = f"target_{horizon}"
        w = df[(df["ward_id"] == ward) & (df["date"] >= meta["split_date"])].dropna(subset=FEATURES + [target]).copy()
        w["Predicted"] = models[horizon].predict(w[FEATURES])
        w["Actual"] = w[target]
        w = w.set_index(w["date"] + pd.Timedelta(weeks=HORIZON_WEEKS[horizon]))
        st.line_chart(w[["Actual", "Predicted"]], height=280, color=["#e2e8f0", AMBER])
        st.caption("Follows the season well but under-predicts the highest peaks; the Cautious demand basis is the "
                   "planning buffer for this.")
    with b:
        st.markdown("**Resource demand rates** (fitted on 2016-2023)")
        ev = meta["resource_rate_eval_2024_2025"]
        st.dataframe(pd.DataFrame([{"Supply": RESOURCE_LABEL[r], "Per case": meta["resource_rates"][r],
                                    "Exact match 2024-25": 100 * ev[r]["exact_match"]} for r in RESOURCES]),
                     hide_index=True, width="stretch", column_config={
                         "Per case": num("Per case", "%.3f"),
                         "Exact match 2024-25": st.column_config.ProgressColumn(format="%.2f%%", min_value=0,
                                                                                max_value=100)})
        st.caption("The dataset's supply columns are a fixed rate × cases, so planning error comes from the case "
                   "forecast.")


def page_status():
    header("System and offline status")
    c = st.columns(3)
    kpi(c[0], "Internet", "Available" if online else "Offline", "probe only, never required",
        TEAL if online else COLORS["High"])
    kpi(c[1], "Core functions needing internet", "0 of 5", "forecast · allocate · route · simulate · dispatch")
    rep = SYSTEM["report"]
    kpi(c[2], "Dataset", f"{rep['rows']:,} rows", f"{rep['wards']} wards · {rep['first_week']} to {rep['last_week']}")
    st.write("")
    a, b = st.columns([1.2, 1], gap="large")
    with a:
        st.markdown("**Local components**")
        cfg = textbee_config()
        checks = local_checks() + [{
            "component": "SMS delivery (TextBee, optional)", "status": "CONFIGURED" if cfg else "OFF",
            "detail": ("sends only when an officer confirms; needs internet" if cfg
                       else "no API key set: notices are generated and exported only")}]
        st.dataframe(pd.DataFrame(checks), hide_index=True, width="stretch",
                     column_config={"component": "Component", "status": "Status", "detail": "Detail"})
        st.caption(f"{rep['missing_values']} missing values, {rep['duplicate_rows']} duplicate rows. "
                   f"Models trained with scikit-learn {meta['sklearn_version']}.")
    with b:
        st.markdown("**Offline kill-switch self-test**")
        st.caption("Runs `offline_check.py` in a separate process with every network call disabled, then exercises "
                   "forecasting, allocation, routing, the simulator and all dispatch formats.")
        if st.button("Run offline self-test", type="primary"):
            with st.spinner("Running with the network disabled..."):
                res = subprocess.run([sys.executable, str(ROOT / "offline_check.py")], capture_output=True, text=True,
                                     timeout=600)
            (st.success if res.returncode == 0 else st.error)("PASSED" if res.returncode == 0 else "FAILED")
            st.code(res.stdout[-4000:] + res.stderr[-2000:], language=None)


nav = st.navigation({
    "Plan": [st.Page(page_overview, title="Overview", icon="📊", default=True),
             st.Page(page_forecast, title="Ward forecast", icon="📈", url_path="forecast")],
    "Respond": [st.Page(page_allocation, title="Allocation", icon="📦", url_path="allocation"),
                st.Page(page_routing, title="Bed routing", icon="🏥", url_path="routing"),
                st.Page(page_simulator, title="Simulator", icon="🦟", url_path="simulator"),
                st.Page(page_dispatch, title="Dispatch", icon="📨", url_path="dispatch")],
    "System": [st.Page(page_accuracy, title="Accuracy", icon="🎯", url_path="accuracy"),
               st.Page(page_status, title="Offline status", icon="🛰️", url_path="status")],
}, position="top")
nav.run()
