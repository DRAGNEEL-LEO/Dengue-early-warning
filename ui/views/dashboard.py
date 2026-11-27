import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import HORIZON_NAME, HORIZON_WEEKS, RESOURCE_LABEL, RESOURCES
from ui import components as C
from ui import geo
from ui import theme as T
from ui.state import ctx, forecast_history

c = ctx()
h, hw = c.horizon, HORIZON_WEEKS[c.horizon]
df, meta = c.df, c.meta
view, fc = c.view, c.forecast
cases_col, risk_col = f"cases_{h}", f"risk_{h}"

# ---------------------------------------------------------------- derived numbers (all from the pipeline)
hist = forecast_history(c.date_str, 13, c.basis)
hist = hist[hist["city"].isin(c.cities)]
origins = sorted(hist["origin"].unique())
prev = hist[hist["origin"] == origins[-2]] if len(origins) > 1 else None

total = float(fc[cases_col].sum())
prev_total = float(prev[cases_col].sum()) if prev is not None else None
n_crit = int((fc[risk_col] == "Critical").sum())
n_high = int((fc[risk_col] == "High").sum())
prev_crit = int((prev[risk_col] == "Critical").sum()) if prev is not None else None
prev_high = int((prev[risk_col] == "High").sum()) if prev is not None else None
train = df[(df["date"] < pd.Timestamp(meta["split_date"])) & df["city"].isin(c.cities)]
record = train.groupby("date")["dengue_cases"].sum()
rec_val = float(record.max())
n_wards = len(fc)

city = fc.groupby("city").agg(cases=(cases_col, "sum"), wards=("ward_id", "count"),
                              n_high_crit=(risk_col, lambda r: int(r.isin(["High", "Critical"]).sum()))).reset_index()
order = {t: i for i, t in enumerate(T.TIERS)}
city["risk"] = fc.groupby("city")[risk_col].agg(lambda r: max(r, key=order.get)).values
prev_city = prev.groupby("city")[cases_col].sum() if prev is not None else pd.Series(dtype=float)

# ---------------------------------------------------------------- header
C.surv_header(
    "Dengue Surveillance",
    "Ward-level dengue forecasting for Dhaka North, Dhaka South, Chattogram, Gazipur and Narayanganj, "
    "turned into supply allocation, hospital overflow routing, vector-control planning and dispatch notices. "
    "All models and calculations run locally.",
    chips=[(f"Data to <b>{c.date_str}</b>", "", False), (f"Planning week <b>{c.target_week}</b>", "", False),
           (f"<b>{HORIZON_NAME[h]}</b> ahead", "", True), (f"<b>{c.city}</b>", "", False),
           ("System operational · local", "ok", True)])

left, right = st.columns([1.22, 1], gap="small")

# ================================================================ LEFT: map + trends
with left:
    with C.card():
        n_hc = n_crit + n_high
        C.panel_title("Ward Risk Map", right=f"<b>{n_hc}</b>&nbsp;High / Critical", dot=True)
        sel = st.session_state.get("dash_city")
        ev = C.chart(geo.city_map(city, selected=sel, height=430), key="dash_map", select=True)
        pts = (ev or {}).get("selection", {}).get("points", []) if ev else []
        if pts and pts[0].get("customdata") and pts[0]["customdata"] != sel:
            st.session_state["dash_city"] = pts[0]["customdata"]
            st.rerun()
        if sel in set(city["city"]):
            r = city.set_index("city").loc[sel]
            top = fc[fc["city"] == sel].sort_values(cases_col, ascending=False).head(3)
            st.markdown(
                f"<div class='foot-note' style='color:{T.TEXT_2}'><b style='color:{T.TEXT}'>{sel}</b> · "
                f"{r['cases']:,.0f} forecast cases · {int(r['n_high_crit'])} of {int(r['wards'])} wards High/Critical · "
                "top wards: " + ", ".join(f"{w} ({v:.1f})" for w, v in zip(top['ward_id'], top[cases_col]))
                + "</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='foot-note' style='display:flex;gap:18px;flex-wrap:wrap;margin-top:8px;"
            f"padding-top:8px;border-top:1px solid {T.BORDER}'>"
            f"<span style='color:{T.AMBER};letter-spacing:.8px'>DATA SOURCES:</span>"
            "<span>Ward dataset 2016-2025</span><span>Random Forest 2w / 4w</span>"
            "<span>Bed capacity (demo)</span><span>Local only</span></div>"
            f"<div class='foot-note' style='margin-top:4px'>{geo.ATTRIBUTION} Click a city to see its top wards.</div>",
            unsafe_allow_html=True)

    with C.card():
        C.panel_title("Dengue Trends", right=f"{HORIZON_NAME[h]} ahead")
        a, b = st.columns([1.45, 1], gap="medium")
        with a:
            pred = hist.groupby("origin")[cases_col].sum().reset_index()
            pred["target"] = pred["origin"] + pd.Timedelta(weeks=hw)
            act = df[df["city"].isin(c.cities)].groupby("date")["dengue_cases"].sum()
            pred["reported"] = pred["target"].map(act)
            fig = go.Figure()
            C.glow_line(fig, pred["target"], pred["reported"], "#C9B79C", "Reported", width=1.6)
            C.glow_line(fig, pred["target"], pred[cases_col], T.AMBER, "Forecast")
            fig.update_layout(height=232, margin=dict(l=4, r=4, t=26, b=4), hovermode="x unified",
                              yaxis=dict(tickformat=",.0f"), xaxis=dict(tickformat="%b %d"))
            C.chart(fig, key="dash_trend")
        with b:
            last_rep = float(act.get(pd.Timestamp(c.date_str), float("nan")))
            prev_rep = float(act.get(pd.Timestamp(c.date_str) - pd.Timedelta(weeks=1), float("nan")))
            d1, k1 = C.pct_change(total, prev_total)
            d2, k2 = C.pct_change(last_rep, prev_rep)
            x, y = st.columns(2)
            C.big_number(x, f"{total:,.0f}", "Forecast cases", d1, k1, amber=True)
            C.big_number(y, "–" if pd.isna(last_rep) else f"{last_rep:,.0f}", "Reported this week", d2, k2)
            st.write("")
            prev_tiers = prev[risk_col].value_counts() if prev is not None else pd.Series(dtype=int)
            tiers = fc[risk_col].value_counts()
            C.bar_rows([dict(name=t, value=int(tiers.get(t, 0)), unit=" wards", color=T.RISK[t],
                             **dict(zip(("delta", "delta_cls"), C.pct_change(int(tiers.get(t, 0)),
                                                                              int(prev_tiers.get(t, 0)) if prev is not None else None))))
                        for t in ("Critical", "High", "Medium", "Low")], max_value=n_wards, compact=True)
        st.markdown(f"<div class='foot-note'>Each point is the forecast made {hw} weeks earlier for that week. "
                    "Changes compare with the forecast made one week earlier.</div>", unsafe_allow_html=True)

# ================================================================ RIGHT: gauges, trends, spread, resources
with right:
    with C.card():
        x, y = st.columns([3, 1])
        with x:
            C.panel_title("Key Metrics")
        with y:
            st.page_link("ui/views/risk_intelligence.py", label="Full report", icon=":material/subject:")
        d0, k0 = C.pct_change(total, prev_total)
        d1, k1 = C.pct_change(n_crit, prev_crit)
        d2, k2 = C.pct_change(n_high, prev_high)
        C.gauges([
            dict(value=f"{total:,.0f}", frac=total / rec_val if rec_val else 0, label="Predicted cases",
                 delta=d0, delta_cls=k0, palette="amber", sub=f"scale: record week {rec_val:,.0f}"),
            dict(value=f"{n_crit}", frac=n_crit / n_wards if n_wards else 0, label="Critical wards",
                 delta=d1, delta_cls=k1, palette="gold", sub=f"of {n_wards} wards"),
            dict(value=f"{n_high}", frac=n_high / n_wards if n_wards else 0, label="High-risk wards",
                 delta=d2, delta_cls=k2, palette="red", sub=f"of {n_wards} wards"),
        ])

    with C.card():
        C.panel_title("Dengue Trends by City", right=f"week of {c.target_week}")
        rows = []
        for r in city.sort_values("cases", ascending=False).itertuples():
            d, k = C.pct_change(r.cases, prev_city.get(r.city))
            rows.append(dict(name=r.city, value=r.cases, delta=d, delta_cls=k, color=T.RISK[r.risk], unit=" cases"))
        C.bar_rows(rows)

    g1, g2 = st.columns([1.05, 1], gap="small")
    with g1:
        with C.card():
            C.panel_title("Geographic Spread")
            per_district = {}
            for r in city.itertuples():
                dname = geo.DISTRICT_OF[r.city]
                per_district[dname] = per_district.get(dname, 0) + r.cases
            C.chart(geo.spread_map(per_district, height=258), key="dash_spread")
            st.markdown("<div class='foot-note'>Forecast cases by district (Dhaka = North + South)</div>",
                        unsafe_allow_html=True)
    with g2:
        with C.card():
            C.panel_title("Resource Status")
            s = c.R["supply_summary"].set_index("resource")
            cr = c.R["crews"]
            items = []
            for res in RESOURCES:
                req, alloc = int(s.loc[res, "required"]), int(s.loc[res, "allocated"])
                pct = 100 * alloc / req if req else 100
                items.append((RESOURCE_LABEL[res], f"{pct:.0f}%", pct < 100))
            cpct = 100 * cr["assigned"] / cr["needed"] if cr["needed"] else 100
            items.append(("Spraying crews", f"{cpct:.0f}%", cpct < 100))
            C.source_list(items)
            st.markdown(f"<div class='foot-note' style='margin:6px 0 10px 0'>Share of forecast demand met at "
                        f"{c.stock}% regional stock</div>", unsafe_allow_html=True)
            short = int(view["critical_deficit"].sum())
            unplaced = int(view["unresolved_deficit"].sum())
            st.markdown(
                f"<div class='stat-box' style='display:flex;justify-content:space-between;align-items:center'>"
                f"<div><div style='color:{T.TEXT};font-size:13.5px'>Critical alerts</div>"
                f"<div class='foot-note'>wards short of supply · {unplaced} without a bed</div></div>"
                f"<div class='bign' style='font-size:30px;color:{T.RED if short else T.TEXT}'>{short}</div></div>",
                unsafe_allow_html=True)

# ---------------------------------------------------------------- alerts strip
a1, a2, a3 = st.columns(3)
crit = view[view["risk"] == "Critical"].sort_values("predicted_cases", ascending=False)
if len(crit):
    C.alert("critical", f"{len(crit)} critical-risk ward(s)",
            ", ".join(crit["ward_id"].head(4)) + (f" +{len(crit) - 4} more" if len(crit) > 4 else ""), target=a1)
else:
    C.alert("ok", "No critical-risk wards", f"Highest ward forecast {view['predicted_cases'].max():.1f} cases/week.",
            target=a1)
rt = c.R["routing"][c.R["routing"]["city"].isin(c.cities)]
over = int((rt["deficit_before"] > 0).sum())
if int(rt["unresolved_deficit"].sum()):
    C.alert("critical", f"{int(rt['unresolved_deficit'].sum())} patient(s) without a bed",
            f"{over} ward(s) over capacity; same-city headroom exhausted.", target=a2)
elif over:
    C.alert("warning", f"{over} ward(s) over bed capacity",
            f"{int(rt['transferred_out'].sum())} patient(s) routed within their own city.", target=a2)
else:
    C.alert("ok", "Hospital capacity sufficient", "Every ward is within local bed capacity.", target=a2)
short = int(view["critical_deficit"].sum())
if short:
    s = c.R["supply_summary"].set_index("resource")
    C.alert("warning", f"Supply deficit in {short} ward(s)",
            f"Saline short {int(s.loc['saline_bags_needed', 'deficit']):,} · kits short "
            f"{int(s.loc['diagnostic_kits_needed', 'deficit']):,} across all wards.", target=a3)
else:
    C.alert("ok", "All supply demand met", f"At {c.stock}% regional stock.", target=a3)
