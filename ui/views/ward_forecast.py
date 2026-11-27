import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import HORIZON_NAME, HORIZON_WEEKS
from features import FEATURES
from predict import LABELS, driver_impacts, predict_with_range, risk_tier
from ui import components as C
from ui import theme as T
from ui.state import ALL, ctx

c = ctx()
df, models, meta = c.df, c.models, c.meta
RAIN_COLS = [f for f in FEATURES if f.startswith("rain_")]

C.page_header("Ward forecast", "Expected dengue cases for one ward, 2 and 4 weeks after the selected data week, "
              "with the likely range and what is driving the number.", tags=["real"])

s1, s2, _ = st.columns([1, 1, 1.4])
cities = sorted(df["city"].unique())
city = s1.selectbox("City", cities, index=cities.index(c.city) if c.city != ALL else 0, key="wf_city")
wards = sorted(df.loc[df["city"] == city, "ward_id"].unique())
ward = s2.selectbox("Ward", wards, key="wf_ward")

row = df[(df["ward_id"] == ward) & (df["date"] == pd.Timestamp(c.date_str))].copy()
if row.empty or row[FEATURES].isna().any(axis=None):
    C.empty_state("Not enough weather history before this week to forecast this ward. Pick a later week.")
    st.stop()

# ---------------------------------------------------------------- forecast cards
cols = st.columns([1, 1, 1.05], gap="medium")
for col, h in zip(cols, HORIZON_NAME):
    pred, lo, hi = predict_with_range(models[h], row)
    tier = risk_tier(pred, meta["tiers"])
    wk = pd.Timestamp(c.date_str) + pd.Timedelta(weeks=HORIZON_WEEKS[h])
    act = df[(df["ward_id"] == ward) & (df["date"] == wk)]
    if act.empty:
        actual = "Not in the dataset yet: a genuine forecast."
    else:
        kind = "training year" if wk < pd.Timestamp(meta["split_date"]) else "held-out test week"
        actual = f"Reported that week: <b>{int(act['dengue_cases'].iloc[0])}</b> ({kind})"
    sel = "border:2px solid #1F6FEB;" if h == c.horizon else ""
    col.markdown(
        f"<div class='fc' style='{sel}'><div class='h'>In {HORIZON_NAME[h]}</div>"
        f"<div class='w'>Week of {wk.strftime('%d %b %Y')}</div>"
        f"<div class='n'>{pred:.1f} <small>cases / week</small></div>"
        f"<div class='tier' style='background:{T.RISK_BG[tier]};color:{T.RISK_FG[tier]}'>{tier} risk</div>"
        f"<div class='r'>Likely range <b>{lo:.1f} to {hi:.1f}</b> (10th to 90th percentile of the model's trees)</div>"
        f"<div class='r'>{actual}</div></div>", unsafe_allow_html=True)
with cols[2]:
    r = row.iloc[0]
    with C.card():
        st.markdown(f"**Ward profile** · {ward}")
        C.kv_list([
            ("City", city),
            ("Population density", f"{r['population_density_sqkm']:,.0f} /km²"),
            ("Water-logging risk index", f"{r['water_logging_risk_index']:.2f}"),
            ("Sanitation score", f"{r['sanitation_score']:.2f}"),
            ("Rain, last 4 weeks", f"{r['rain_sum_4w']:.0f} mm"),
            ("Avg temperature, 2 weeks", f"{r['temp_mean_2w']:.1f} °C"),
            ("Avg humidity, 2 weeks", f"{r['humidity_mean_2w']:.0f} %"),
        ])

# ---------------------------------------------------------------- history vs predicted
h = c.horizon
hw = HORIZON_WEEKS[h]
with C.card():
    st.markdown(f"**Reported vs predicted cases** · forecasts made {hw} weeks ahead, last 26 weeks")
    w = df[(df["ward_id"] == ward) & (df["date"] <= pd.Timestamp(c.date_str))].dropna(subset=FEATURES).tail(26)
    hist = pd.DataFrame({"origin": w["date"], "pred": models[h].predict(w[FEATURES])})
    hist["target"] = hist["origin"] + pd.Timedelta(weeks=hw)
    actual = df[df["ward_id"] == ward].set_index("date")["dengue_cases"]
    hist["actual"] = hist["target"].map(actual)
    pred, lo, hi = predict_with_range(models[h], row)
    fig = go.Figure()
    fig.add_scatter(x=hist["target"], y=hist["actual"], name="Reported", mode="lines+markers",
                    line=dict(color=T.SLATE, width=2), marker=dict(size=5))
    fig.add_scatter(x=hist["target"], y=hist["pred"], name="Predicted", mode="lines",
                    line=dict(color=T.BLUE, width=2.5))
    tw = hist["target"].iloc[-1]
    fig.add_scatter(x=[tw], y=[pred], name="Current forecast (range)", mode="markers",
                    marker=dict(size=12, color=T.BLUE, line=dict(color="#FFF", width=2)),
                    error_y=dict(type="data", symmetric=False, array=[hi - pred], arrayminus=[pred - lo],
                                 color=T.BLUE, thickness=1.5, width=6))
    for tier in ("High", "Critical"):
        fig.add_hline(y=meta["tiers"][tier], line=dict(color=T.RISK[tier], width=1, dash="dot"),
                      annotation_text=f"{tier} threshold", annotation_position="top left",
                      annotation_font=dict(size=11, color=T.RISK[tier]))
    fig.update_layout(height=330, yaxis_title="Cases per week", hovermode="x unified")
    C.chart(fig, key="wf_hist")

# ---------------------------------------------------------------- drivers + scenario
left, right = st.columns([1.25, 1], gap="medium")
with left:
    with C.card():
        st.markdown(f"**What is driving the {c.hname} forecast**")
        imp = driver_impacts(models[h], row, meta["baseline"]).rename(LABELS).sort_values()
        fig = go.Figure(go.Bar(y=imp.index, x=imp.values, orientation="h",
                               marker_color=[T.RED if v > 0 else T.CYAN for v in imp.values],
                               hovertemplate="%{y}: %{x:+.2f} cases<extra></extra>"))
        fig.update_layout(height=430, xaxis_title="Effect on predicted cases (vs a typical week)",
                          margin=dict(t=10))
        C.chart(fig, key="wf_drivers")
        st.caption("Red raises the forecast, cyan lowers it. Each bar swaps one input for its typical value: "
                   "an approximation, not a causal effect.")
with right:
    with C.card():
        st.markdown(f"**Rainfall scenario** {C.tag('scenario', 'Scenario · not a forecast')}", unsafe_allow_html=True)
        mult = st.slider("Recent rainfall multiplier", 0.0, 2.0, 1.0, 0.1, key="wf_rain",
                         help="Scales rain this week and the previous 4 weeks, then re-runs the same model.")
        scen = row.copy()
        scen[RAIN_COLS] = scen[RAIN_COLS] * mult
        base, _, _ = predict_with_range(models[h], row)
        sp, slo, shi = predict_with_range(models[h], scen)
        stier = risk_tier(sp, meta["tiers"])
        a, b = st.columns(2)
        a.metric("Forecast, actual weather", f"{base:.1f}")
        b.metric(f"Scenario ×{mult:.1f} rain", f"{sp:.1f}",
                 delta=f"{sp - base:+.1f} cases" if abs(sp - base) >= 0.05 else None, delta_color="inverse")
        st.markdown(f"Scenario risk: {C.risk_badge(stier)} · range {slo:.1f} to {shi:.1f}", unsafe_allow_html=True)
        st.caption("The model responds in steps, not smoothly. Use this to explore sensitivity, not as a forecast.")
        st.markdown("**Recent weather** (12 weeks)")
        wx = df[(df["ward_id"] == ward) & (df["date"] <= pd.Timestamp(c.date_str))].tail(12)
        fig = go.Figure()
        fig.add_bar(x=wx["date"], y=wx["rainfall_mm"], name="Rain (mm)", marker_color="#93C5FD", yaxis="y")
        fig.add_scatter(x=wx["date"], y=wx["avg_temp_c"], name="Temp (°C)", mode="lines+markers",
                        line=dict(color=T.ORANGE), yaxis="y2")
        fig.add_scatter(x=wx["date"], y=wx["relative_humidity_pct"], name="Humidity (%)", mode="lines",
                        line=dict(color="#8B5CF6", dash="dot"), yaxis="y2")
        fig.update_layout(height=240, margin=dict(t=30), yaxis=dict(title="mm"),
                          yaxis2=dict(title="°C / %", overlaying="y", side="right", showgrid=False))
        C.chart(fig, key="wf_wx")
