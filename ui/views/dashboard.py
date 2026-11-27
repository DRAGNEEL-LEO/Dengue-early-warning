import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import HORIZON_WEEKS
from ui import components as C
from ui import theme as T
from ui.state import ctx, forecast_history

c = ctx()
view, fc = c.view, c.forecast
C.page_header("Executive dashboard",
              f"Planning for the week of <b>{c.target_week}</b> ({c.hname} ahead) using data up to "
              f"<b>{c.date_str}</b>. Scope: <b>{c.city}</b>, {len(view)} wards.", tags=["real"])

# ---------------------------------------------------------------- KPIs
rt = c.R["routing"][c.R["routing"]["city"].isin(c.cities)]
beds_need = int(view["hospital_beds_required_required"].sum())
beds_cap = int(rt["bed_capacity"].sum())
tiers = c.meta["tiers"]
n_crit = int((view["risk"] == "Critical").sum())
n_high = int((view["risk"] == "High").sum())
n_short = int(view["critical_deficit"].sum())
unplaced = int(rt["unresolved_deficit"].sum())
over_before = int((rt["deficit_before"] > 0).sum())
C.kpi_row([
    dict(label="Total predicted cases", value=f"{view['predicted_cases'].sum():,.0f}",
         foot=f"week of {c.target_week}", accent=T.BLUE),
    dict(label="Critical-risk wards", value=n_crit, unit=f"/ {len(view)}", foot=f"forecast ≥ {tiers['Critical']:g} cases/week",
         accent=T.RED),
    dict(label="High-risk wards", value=n_high, unit=f"/ {len(view)}", foot=f"{tiers['High']:g} to {tiers['Critical']:g} cases/week",
         accent=T.ORANGE),
    dict(label="Hospital beds required", value=f"{beds_need:,}", foot=f"local capacity {beds_cap:,} (demo)",
         accent=T.CYAN),
    dict(label="Wards short of supply", value=n_short, unit=f"/ {len(view)}",
         foot=f"at {c.stock}% regional stock", accent=T.RED if n_short else T.GREEN),
])

# ---------------------------------------------------------------- alerts
C.section("Alerts", "generated from the current forecast and allocation")
a1, a2, a3 = st.columns(3)
crit = view[view["risk"] == "Critical"].sort_values("predicted_cases", ascending=False)
if len(crit):
    names = ", ".join(crit["ward_id"].head(4)) + (f" +{len(crit) - 4} more" if len(crit) > 4 else "")
    C.alert("critical", f"{len(crit)} critical-risk ward(s)", names, target=a1)
else:
    C.alert("ok", "No critical-risk wards", f"Highest forecast: {view['predicted_cases'].max():.1f} cases/week.",
            target=a1)
if unplaced:
    C.alert("critical", f"{unplaced} patient(s) without a bed",
            f"{over_before} ward(s) over capacity; same-city headroom exhausted.", target=a2)
elif over_before:
    moved = int(rt["transferred_out"].sum())
    C.alert("warning", f"{over_before} ward(s) over bed capacity",
            f"{moved} patient(s) routed to wards in the same city. No one left without a bed.", target=a2)
else:
    C.alert("ok", "Hospital capacity sufficient", "Every ward is within local bed capacity.", target=a2)
if n_short:
    s = c.R["supply_summary"].set_index("resource")
    C.alert("warning" if c.stock >= 80 else "critical", f"Supply deficit in {n_short} ward(s)",
            f"Saline short by {int(s.loc['saline_bags_needed', 'deficit']):,} · kits short by "
            f"{int(s.loc['diagnostic_kits_needed', 'deficit']):,} (all 60 wards).", target=a3)
else:
    C.alert("ok", "All supply demand met", f"At {c.stock}% regional stock.", target=a3)

# ---------------------------------------------------------------- grid + distribution
with C.card():
    st.markdown(f"**Ward risk grid** · {c.hname} ahead · {C.tag('demo', 'Schematic · not geographic')}",
                unsafe_allow_html=True)
    C.chart(C.ward_grid(fc, f"cases_{c.horizon}", f"risk_{c.horizon}", width_px=1250), key="dash_grid")
    st.caption("One tile per ward, grouped by city in ward-ID order. The dataset has no ward coordinates or "
               "boundaries, so this is not a map. Top line = ward number; bottom line = forecast cases. "
               "Open Risk Intelligence to click into a ward.")

left, right = st.columns([1.65, 1], gap="medium")
with right:
    with C.card():
        st.markdown("**Risk distribution by city**")
        tc = C.tier_counts(fc, "city", f"risk_{c.horizon}")
        fig = go.Figure()
        for tier in T.TIERS:
            fig.add_bar(y=tc.index, x=tc[tier], name=tier, orientation="h", marker_color=T.RISK[tier],
                        hovertemplate=f"%{{y}}: %{{x}} {tier} wards<extra></extra>")
        fig.update_layout(barmode="stack", height=360, xaxis_title="Wards", yaxis=dict(autorange="reversed"))
        C.chart(fig, key="dash_dist")

# ---------------------------------------------------------------- trend + top wards
with left:
    with C.card():
        h = HORIZON_WEEKS[c.horizon]
        hist = forecast_history(c.date_str, 12, c.basis)
        hist = hist[hist["city"].isin(c.cities)]
        pred = hist.groupby("origin")[f"cases_{c.horizon}"].sum().reset_index()
        pred["target"] = pred["origin"] + pd.Timedelta(weeks=h)
        act = c.df[c.df["city"].isin(c.cities)].groupby("date")["dengue_cases"].sum()
        pred["actual"] = pred["target"].map(act)
        st.markdown(f"**Weekly forecast trend** · {c.hname} ahead", unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_scatter(x=pred["target"], y=pred["actual"], name="Reported cases", mode="lines+markers",
                        line=dict(color=T.SLATE, width=2), marker=dict(size=5))
        fig.add_scatter(x=pred["target"], y=pred[f"cases_{c.horizon}"], name="Model forecast",
                        mode="lines+markers", line=dict(color=T.BLUE, width=2.5), marker=dict(size=5))
        last = pred.iloc[-1]
        fig.add_scatter(x=[last["target"]], y=[last[f"cases_{c.horizon}"]], name="Current forecast",
                        mode="markers", marker=dict(size=13, color=T.BLUE, line=dict(color="#FFFFFF", width=2)))
        fig.update_layout(height=360, yaxis_title="Cases per week", hovermode="x unified")
        C.chart(fig, key="dash_trend")
        st.caption(f"Each point is the forecast made {h} weeks earlier for that week, against reported cases. "
                   "The last point is the current planning forecast.")
with C.card():
    st.markdown("**Highest-risk wards**")
    top = view.sort_values("predicted_cases", ascending=False).head(10)
    tbl = pd.DataFrame({
        "Ward": top["ward_id"], "City": top["city"], "Risk": top["risk"], "Cases": top["predicted_cases"],
        "Priority rank": top["priority_rank"],
        "Saline (alloc / need)": top["saline_bags_needed_allocated"].astype(str) + " / "
        + top["saline_bags_needed_required"].astype(str),
        "Kits (alloc / need)": top["diagnostic_kits_needed_allocated"].astype(str) + " / "
        + top["diagnostic_kits_needed_required"].astype(str),
        "Beds needed": top["hospital_beds_required_required"], "Bed status": top["status"],
        "Crews": top["crews_assigned"].astype(str) + " / " + top["crews_needed"].astype(str),
        "Status": top["critical_deficit"].map({True: "⚠ Shortage", False: "✓ Supplied"})})
    C.risk_table(tbl, fmt={"Cases": "{:.1f}"})
