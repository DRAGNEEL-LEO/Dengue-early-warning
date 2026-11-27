import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import CREWS_NEEDED_BY_TIER, RESOURCE_LABEL, RESOURCES
from ui import components as C
from ui import theme as T
from ui.state import ctx

c = ctx()
view, meta = c.view, c.meta
summ = c.R["supply_summary"].set_index("resource")
cr = c.R["crews"]
C.page_header("Resource allocation",
              f"Forecast demand for the week of {c.target_week}, shared out from a regional stock of "
              f"<b>{c.stock}%</b> of total demand using the <b>{'priority-weighted' if c.policy == 'weighted' else 'strict triage'}</b> "
              "policy. Change stock, crews and policy in the sidebar.")

# ---------------------------------------------------------------- KPI cards
items = []
for r in RESOURCES:
    s = summ.loc[r]
    short = int(s["deficit"])
    items.append(dict(label=RESOURCE_LABEL[r], value=f"{int(s['allocated']):,}", unit=f"/ {int(s['required']):,}",
                      foot=(f"short by <b style='color:{T.RED}'>{short:,}</b> · {int(s['wards_short'])} wards"
                            if short else "demand fully met"), accent=T.RED if short else T.GREEN))
items.append(dict(label="Spraying crews", value=cr["assigned"], unit=f"/ {cr['needed']}",
                  foot=(f"short by <b style='color:{T.RED}'>{cr['shortfall']}</b>" if cr["shortfall"]
                        else f"{cr['idle']} idle"), accent=T.RED if cr["shortfall"] else T.GREEN))
C.kpi_row(items)
n_short = int(view["critical_deficit"].sum())
if n_short:
    C.alert("critical", f"Critical supply deficit in {n_short} of {len(view)} wards",
            "At least one supply is below 100% of forecast demand. Highest-priority wards are served first.")
else:
    C.alert("ok", "All forecast demand met", f"Regional stock of {c.stock}% covers every ward in scope.")

# ---------------------------------------------------------------- summary table (all 60 wards)
with C.card():
    st.markdown("**Allocation summary** · regional pool, all 60 wards")
    rows = []
    for r in RESOURCES:
        s = summ.loc[r]
        rows.append({"Supply": RESOURCE_LABEL[r], "Estimated demand": int(s["required"]),
                     "Available stock": int(s["available_stock"]), "Allocated": int(s["allocated"]),
                     "Shortage": int(s["deficit"]),
                     "Demand met": 100 * s["allocated"] / s["required"] if s["required"] else 100.0})
    rows.append({"Supply": "Spraying crews", "Estimated demand": cr["needed"], "Available stock": cr["total"],
                 "Allocated": cr["assigned"], "Shortage": cr["shortfall"],
                 "Demand met": 100 * cr["assigned"] / cr["needed"] if cr["needed"] else 100.0})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
        "Estimated demand": C.num("Estimated demand", help="Forecast cases × per-case rate (fitted on 2016-2023)"),
        "Available stock": C.num("Available stock", help=f"{c.stock}% of total demand; crews = crews available"),
        "Allocated": C.num("Allocated"), "Shortage": C.num("Shortage"), "Demand met": C.bar("Demand met")})

# ---------------------------------------------------------------- supply selector + before/after
sel = st.segmented_control("Supply", list(RESOURCES), format_func=RESOURCE_LABEL.get, default=RESOURCES[0],
                           key="ra_res") or RESOURCES[0]
left, right = st.columns([1, 1.25], gap="medium")
with left:
    with C.card():
        st.markdown(f"**Before and after allocation by city** · {RESOURCE_LABEL[sel]}")
        city = view.groupby("city")[[f"{sel}_required", f"{sel}_allocated", f"{sel}_deficit"]].sum().reset_index()
        fig = go.Figure()
        fig.add_bar(x=city["city"], y=city[f"{sel}_required"], name="Demand (before)", marker_color=T.LIGHT_SLATE,
                    hovertemplate="%{x}: demand %{y:,}<extra></extra>")
        fig.add_bar(x=city["city"], y=city[f"{sel}_allocated"], name="Allocated (after)", marker_color=T.BLUE,
                    hovertemplate="%{x}: allocated %{y:,}<extra></extra>")
        fig.add_scatter(x=city["city"], y=city[f"{sel}_required"], mode="text", showlegend=False,
                        text=[f"−{v:,}" if v else "" for v in city[f"{sel}_deficit"]], textposition="top center",
                        textfont=dict(color=T.RED, size=12), hoverinfo="skip")
        fig.update_layout(barmode="group", height=360, yaxis_title="Units", xaxis=dict(tickangle=0))
        C.chart(fig, key="ra_city")
        st.caption("Red labels show each city's remaining shortage.")
with right:
    with C.card():
        n = st.select_slider("Wards shown", [15, 30, 60], value=15, key="ra_n",
                             format_func=lambda v: f"Top {v}" if v < 60 else "All")
        st.markdown(f"**Distribution by ward, highest priority at the top** · {RESOURCE_LABEL[sel]}")
        t = view.sort_values("priority_rank").head(n)
        d = pd.DataFrame({"Ward": t["ward_id"], "Allocated": t[f"{sel}_allocated"], "Shortage": t[f"{sel}_deficit"]})
        C.chart(C.hbar(d, "Ward", ["Allocated", "Shortage"], [T.BLUE, T.RED], height=max(280, 24 * len(d) + 70)),
                key="ra_ward")

# ---------------------------------------------------------------- priority table
with C.card():
    a, b = st.columns([3, 1])
    a.markdown(f"**Allocation priority** · {RESOURCE_LABEL[sel]}")
    only = b.toggle("Only wards with a shortage", key="ra_only")
    t = view.sort_values("priority_rank")
    if only:
        t = t[t[f"{sel}_deficit"] > 0]
    if t.empty:
        C.empty_state("No ward is short of this supply.")
    else:
        tbl = pd.DataFrame({
            "Rank": t["priority_rank"], "Ward": t["ward_id"], "City": t["city"], "Risk": t["risk"],
            "Cases": t["predicted_cases"], "Priority": t["priority"], "Demand": t[f"{sel}_required"],
            "Allocated": t[f"{sel}_allocated"], "Shortage": t[f"{sel}_deficit"], "Met": t[f"{sel}_fill_pct"],
            "Crews": t["crews_assigned"].astype(str) + " / " + t["crews_needed"].astype(str),
            "Status": t["critical_deficit"].map({True: "Shortage", False: "Supplied"})})
        C.risk_table(tbl, height=min(520, 40 + 35 * len(tbl)), fmt={"Cases": "{:.1f}", "Priority": "{:.2f}"},
                     column_config={"Priority": st.column_config.NumberColumn(
                         "Priority", help="risk weight × risk score + density weight × normalised density"),
                         "Met": C.bar("Met")})
    full = view.sort_values("priority_rank")[
        ["priority_rank", "city", "ward_id", "risk", "predicted_cases", "population_density_sqkm", "priority"]
        + [f"{r}_{k}" for r in RESOURCES for k in ("required", "allocated", "deficit")]
        + ["crews_needed", "crews_assigned", "alert"]]
    st.download_button("Download full allocation, all supplies (CSV)", full.to_csv(index=False),
                       f"allocation_{c.date_str}_{c.horizon}_{c.stock}pct.csv", "text/csv", icon=":material/download:")

with st.expander("How the allocation works (configurable assumptions, not official policy)"):
    rates = meta["resource_rates"]
    st.markdown(f"""
- **Estimated demand** = forecast cases × per-case rate fitted on 2016-2023 (saline {rates['saline_bags_needed']:.2f},
  kits {rates['diagnostic_kits_needed']:.2f}, beds {rates['hospital_beds_required']:.2f}), rounded.
- **Available stock** = {c.stock}% of total demand across all 60 wards, for each supply.
- **Priority** = {c.w_risk:.2f} × risk score (Low 0, Medium ⅓, High ⅔, Critical 1) + {1 - c.w_risk:.2f} × population
  density scaled 0-1. Ties: higher forecast, then ward ID.
- **Priority-weighted:** each ward gets min(1, λ × priority) of its demand, with λ set so the total equals stock.
  **Strict triage:** wards are filled completely in priority order.
- **Crews needed** by tier {CREWS_NEEDED_BY_TIER}, assigned one at a time in priority order.
""")
