import plotly.graph_objects as go
import streamlit as st

from hospital_routing import CAPACITY_NOTE
from ui import components as C
from ui import theme as T
from ui.state import ctx

c = ctx()
rt = c.R["routing"][c.R["routing"]["city"].isin(c.cities)]
cb = c.R["city_beds"][c.R["city_beds"]["city"].isin(c.cities)].copy()
tr = c.R["transfers"]
tr = tr[tr["city"].isin(c.cities)] if len(tr) else tr

C.page_header("Hospital routing",
              f"Bed demand for the week of {c.target_week} against ward bed capacity, with overflow moved only "
              "within the same city.", tags=["demo"])
C.alert("info", "Recommendations come from the system's routing rule",
        "The ward with the largest deficit sends first, always to the same-city ward with the most free beds, until "
        "the deficit is cleared or the city is full. No road distances or travel times are modelled. "
        "Bed capacities are a demo assumption: " + CAPACITY_NOTE.split(":", 1)[-1].strip())

moved = int(tr["patients"].sum()) if len(tr) else 0
over_b = int((rt["deficit_before"] > 0).sum())
unplaced = int(rt["unresolved_deficit"].sum())
C.kpi_row([
    dict(label="Bed demand", value=f"{int(rt['beds_demand'].sum()):,}", foot=f"forecast, {c.hname} ahead",
         accent=T.CYAN),
    dict(label="Bed capacity", value=f"{int(rt['bed_capacity'].sum()):,}",
         foot=f"{int(cb['headroom_after'].sum()):,} free after routing", accent=T.BLUE),
    dict(label="Overflow wards", value=over_b, unit=f"/ {len(rt)}", foot="demand above local capacity",
         accent=T.ORANGE if over_b else T.GREEN),
    dict(label="Patients transferred", value=moved, foot=f"{len(tr)} transfer(s), same city only", accent=T.BLUE),
    dict(label="Patients without a bed", value=unplaced, foot="after routing",
         accent=T.RED if unplaced else T.GREEN),
])
if unplaced:
    C.alert("critical", f"{unplaced} patient(s) cannot be placed within their own city",
            "Escalate to the city health office for surge beds.")

# ---------------------------------------------------------------- capacity visual + flows
left, right = st.columns([1.1, 1], gap="medium")
with left:
    with C.card():
        st.markdown("**City bed capacity after routing**")
        fig = go.Figure()
        fig.add_bar(y=cb["city"], x=cb["beds_used_after"], name="Occupied", orientation="h", marker_color=T.BLUE,
                    hovertemplate="%{y}: %{x} beds occupied<extra></extra>")
        fig.add_bar(y=cb["city"], x=cb["headroom_after"], name="Free", orientation="h", marker_color="#3A3833",
                    hovertemplate="%{y}: %{x} beds free<extra></extra>")
        fig.add_bar(y=cb["city"], x=cb["unresolved_deficit"], name="No bed", orientation="h", marker_color=T.RED,
                    hovertemplate="%{y}: %{x} patients without a bed<extra></extra>")
        fig.update_layout(barmode="stack", height=300, xaxis_title="Beds", yaxis=dict(autorange="reversed"))
        C.chart(fig, key="hr_city")
        st.dataframe(cb[["city", "bed_demand", "bed_capacity", "utilization_after_pct", "transferred",
                         "unresolved_deficit"]], hide_index=True, width="stretch", column_config={
            "city": "City", "bed_demand": C.num("Demand"), "bed_capacity": C.num("Capacity"),
            "utilization_after_pct": C.bar("Utilisation"), "transferred": C.num("Moved"),
            "unresolved_deficit": C.num("No bed")})
with right:
    with C.card():
        st.markdown("**Suggested transfers**")
        if tr.empty:
            C.empty_state("No overflow this week: every ward is within local capacity.")
        else:
            nodes = sorted(set(tr["from_ward"]) | set(tr["to_ward"]))
            idx = {n: i for i, n in enumerate(nodes)}
            senders = set(tr["from_ward"])
            fig = go.Figure(go.Sankey(
                arrangement="snap",
                node=dict(label=nodes, pad=14, thickness=14,
                          color=[T.ORANGE if n in senders else T.GREEN for n in nodes]),
                link=dict(source=[idx[x] for x in tr["from_ward"]], target=[idx[x] for x in tr["to_ward"]],
                          value=tr["patients"].tolist(), color="rgba(242,163,58,0.22)",
                          hovertemplate="%{source.label} → %{target.label}: %{value} patient(s)<extra></extra>")))
            fig.update_layout(height=max(240, 34 * len(nodes)), margin=dict(t=10, b=10))
            C.chart(fig, key="hr_sankey")
            st.caption("Orange: overflow ward sending patients. Green: receiving ward with free beds.")
            st.dataframe(tr, hide_index=True, width="stretch", column_config={
                "city": "City", "from_ward": "From (overflow)", "to_ward": "To (free beds)",
                "patients": C.num("Patients")})

# ---------------------------------------------------------------- ward detail
with C.card():
    a, b, cc = st.columns([2, 1, 1])
    a.markdown("**Ward bed availability**")
    city_opts = sorted(rt["city"].unique())
    ward_city = b.selectbox("City", city_opts, key="hr_city_sel", label_visibility="collapsed")
    only = cc.toggle("Only wards with activity", value=False, key="hr_only")
    w = rt[rt["city"] == ward_city].sort_values("ward_id")
    fig = go.Figure()
    fig.add_bar(x=w["ward_id"], y=w["bed_capacity"], name="Capacity", marker_color="#2E2D32",
                hovertemplate="%{x}: capacity %{y}<extra></extra>")
    fig.add_bar(x=w["ward_id"], y=w["beds_demand"], name="Demand",
                marker_color=[T.ORANGE if d > cap else T.BLUE for d, cap in zip(w["beds_demand"], w["bed_capacity"])],
                hovertemplate="%{x}: demand %{y}<extra></extra>")
    fig.update_layout(barmode="overlay", height=300, yaxis_title="Beds", margin=dict(t=30))
    fig.update_traces(selector=dict(name="Demand"), width=0.45)
    C.chart(fig, key="hr_wards")
    st.caption("Grey: local capacity. Amber: demand within capacity. Orange: demand above capacity (overflow).")
    t = w if not only else w[w["status"] != "Within capacity"]
    if t.empty:
        C.empty_state("All wards in this city are within capacity.")
    else:
        st.dataframe(t[["ward_id", "beds_demand", "bed_capacity", "deficit_before", "transferred_out",
                        "transferred_in", "unresolved_deficit", "headroom_after", "status"]],
                     hide_index=True, width="stretch", column_config={
                         "ward_id": "Ward", "beds_demand": C.num("Demand"), "bed_capacity": C.num("Capacity"),
                         "deficit_before": C.num("Over by"), "transferred_out": C.num("Sent"),
                         "transferred_in": C.num("Received"), "unresolved_deficit": C.num("No bed"),
                         "headroom_after": C.num("Free after"), "status": "Status"})

with st.expander("Edit ward bed capacity (demo assumption: replace with verified figures)"):
    edited = st.data_editor(st.session_state.capacity, hide_index=True, width="stretch", height=320,
                            disabled=["city", "ward_id"], key="cap_editor",
                            column_config={"city": "City", "ward_id": "Ward",
                                           "bed_capacity": st.column_config.NumberColumn("Beds", min_value=0, step=1)})
    x, y, _ = st.columns([1, 1, 4])
    if x.button("Apply changes", type="primary", icon=":material/check:"):
        st.session_state.capacity = edited.fillna(0).astype({"bed_capacity": int})
        st.rerun()
    if y.button("Reset to demo", icon=":material/restart_alt:"):
        st.session_state.capacity = c.system["capacity"][["city", "ward_id", "bed_capacity"]].copy()
        st.rerun()
