import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd
import streamlit as st

from features import build_features, FEATURES
from predict import load_models, risk_tier, predict_with_range, driver_impacts, LABELS, TIERS
from train import DATA

st.set_page_config(page_title="Dengue early-warning dashboard", page_icon="🦟", layout="wide")

COLORS = {"Low": "#2e7d32", "Medium": "#f9a825", "High": "#ef6c00", "Critical": "#c62828"}
TEXT = {"Low": "#ffffff", "Medium": "#1a1a1a", "High": "#ffffff", "Critical": "#ffffff"}
PASTEL = {"Low": "#c8e6c9", "Medium": "#fff59d", "High": "#ffcc80", "Critical": "#ef9a9a"}
RAIN_COLS = [c for c in FEATURES if c.startswith("rain_")]
HORIZON_NAME = {"2w": "2 weeks", "4w": "4 weeks"}

st.markdown("""
<style>
.block-container {padding-top: 1.5rem;}
.banner {background:#0f3d3a;border:1px solid #1f6f69;color:#ffffff;padding:20px 26px;border-radius:10px;margin-bottom:14px;}
.banner h1 {color:#ffffff;margin:0;font-size:1.9rem;}
.banner p {color:#cfe7e4;margin:6px 0 0 0;font-size:1rem;}
.kpi {border-left:6px solid #999;background:#1b2330;padding:10px 14px;border-radius:6px;}
.kpi .l {font-size:0.85rem;color:#9fb0bf;}
.kpi .n {font-size:1.8rem;font-weight:700;color:#f1f5f9;line-height:1.2;}
.tier {padding:14px;border-radius:10px;text-align:center;font-size:2rem;font-weight:700;margin:6px 0 10px 0;}
</style>
""", unsafe_allow_html=True)


# ---- cached loading: models and features are built once, not on every click ----
@st.cache_resource(show_spinner="Loading models (first run may train them, about 20 s)...")
def get_models():
    return load_models()


@st.cache_data(show_spinner="Preparing weather features...")
def get_data():
    return build_features(pd.read_csv(DATA))


@st.cache_data
def predict_all_wards(date_str, horizon):
    models, meta = get_models()
    df = get_data()
    rows = df[df["date"] == pd.Timestamp(date_str)].dropna(subset=FEATURES)
    out = rows[["city", "ward_id"]].copy()
    out["predicted_cases"] = models[horizon].predict(rows[FEATURES]).round(2)
    out["risk"] = [risk_tier(p, meta["tiers"]) for p in out["predicted_cases"]]
    return out.sort_values("predicted_cases", ascending=False).reset_index(drop=True)


@st.cache_data
def validation_summary(horizon):
    models, meta = get_models()
    df = get_data()
    target = f"target_{horizon}"
    test = df[df["date"] >= meta["split_date"]].dropna(subset=FEATURES + [target])
    pred = models[horizon].predict(test[FEATURES])
    actual_t = test[target].map(lambda x: risk_tier(x, meta["tiers"]))
    pred_t = pd.Series(pred, index=test.index).map(lambda x: risk_tier(x, meta["tiers"]))
    outbreak = actual_t.isin(["High", "Critical"])
    flagged = pred_t.isin(["Medium", "High", "Critical"])
    return {
        "exact": float((actual_t == pred_t).mean()),
        "outbreak_caught": float(flagged[outbreak].mean()),
        "n_outbreak": int(outbreak.sum()),
    }


models, meta = get_models()
df = get_data()
tiers = meta["tiers"]


def actual_cases(ward_id, date_str, weeks):
    d = pd.Timestamp(date_str) + pd.Timedelta(weeks=weeks)
    r = df[(df["ward_id"] == ward_id) & (df["date"] == d)]
    return d, (None if r.empty else int(r["dengue_cases"].iloc[0]))


# ---- sidebar inputs ----
st.sidebar.header("Choose area and time")
city = st.sidebar.selectbox("City", sorted(df["city"].unique()))
ward = st.sidebar.selectbox("Ward", sorted(df.loc[df["city"] == city, "ward_id"].unique()))
dates = sorted(df.dropna(subset=FEATURES)["date"].dt.strftime("%Y-%m-%d").unique(), reverse=True)
date_str = st.sidebar.selectbox("Latest week of weather data", dates,
                                help="The forecast looks 2 and 4 weeks beyond this week.")
horizon = st.sidebar.radio("Explain drivers for", list(HORIZON_NAME), format_func=HORIZON_NAME.get, horizontal=True)
rain_mult = st.sidebar.slider("Rainfall scenario (× recent rain)", 0.0, 2.0, 1.0, 0.1,
                              help="1.0 = actual weather. Try 2.0 to see the effect of much heavier rain.")
st.sidebar.divider()
st.sidebar.caption("Weeks inside the dataset are a replay: the model sees only data up to the chosen week, "
                   "then we compare with what really happened. The newest week gives a genuine forecast.")

# ---- header ----
st.markdown(
    "<div class='banner'><h1>Dengue early-warning dashboard</h1>"
    "<p>Forecasts dengue cases and risk level 2 and 4 weeks ahead for 60 wards in Dhaka North, Dhaka South, "
    "Chattogram, Gazipur and Narayanganj, from rainfall, temperature, humidity and ward conditions.</p></div>",
    unsafe_allow_html=True)

# ---- city-wide summary strip ----
summary = predict_all_wards(date_str, "2w")
st.markdown(f"**All 60 wards, risk 2 weeks after the week of {date_str}**")
kpi_cols = st.columns(4)
for col, t in zip(kpi_cols, TIERS):
    n = int((summary["risk"] == t).sum())
    col.markdown(f"<div class='kpi' style='border-left-color:{COLORS[t]}'>"
                 f"<div class='l'>{t}</div><div class='n'>{n} wards</div></div>", unsafe_allow_html=True)
st.write("")

row = df[(df["ward_id"] == ward) & (df["date"] == pd.Timestamp(date_str))].copy()
row[RAIN_COLS] = row[RAIN_COLS] * rain_mult

tab1, tab2, tab3 = st.tabs(["Ward forecast", "All wards", "Model accuracy"])

# ================= Tab 1: one ward =================
with tab1:
    st.subheader(f"{ward} ({city})")
    if rain_mult != 1.0:
        st.info(f"Scenario: recent rainfall multiplied by {rain_mult}.")
    cols = st.columns(2)
    for col, h in zip(cols, HORIZON_NAME):
        pred, lo, hi = predict_with_range(models[h], row)
        tier = risk_tier(pred, tiers)
        wk, actual = actual_cases(ward, date_str, int(h[0]))
        with col:
            with st.container(border=True):
                st.markdown(f"**In {HORIZON_NAME[h]}** (week of {wk.strftime('%d %b %Y')})")
                st.markdown(f"<div class='tier' style='background:{COLORS[tier]};color:{TEXT[tier]}'>{tier}</div>",
                            unsafe_allow_html=True)
                st.metric("Predicted cases per week", f"{pred:.1f}")
                st.caption(f"Likely range: {lo:.1f} to {hi:.1f} cases (10th to 90th percentile of the model's trees)")
                if actual is None:
                    st.caption("Actual cases: not in the dataset yet, so this is a genuine forecast.")
                elif wk < pd.Timestamp(meta["split_date"]):
                    st.caption(f"Actual cases that week: **{actual}** (training years, not a fair test).")
                else:
                    st.caption(f"Actual cases that week: **{actual}** (held-out test week).")

    with st.container(border=True):
        st.markdown(f"#### What is driving the {HORIZON_NAME[horizon]} forecast")
        imp = driver_impacts(models[horizon], row, meta["baseline"]).rename(LABELS)
        order = imp.abs().sort_values(ascending=False).index[:3]
        st.markdown("Top drivers: " + ", ".join(f"**{n}** ({imp[n]:+.1f})" for n in order))
        st.bar_chart(imp.sort_values(), horizontal=True, height=420, color="#2dd4bf")
        st.caption("Bars show how much each input raises (+) or lowers (−) predicted cases compared with a "
                   "typical week and ward. Impact is approximate.")

    with st.container(border=True):
        st.markdown("#### Recent weather in this ward")
        hist = df[(df["ward_id"] == ward) & (df["date"] <= pd.Timestamp(date_str))].tail(12).set_index("date")
        c1, c2, c3 = st.columns(3)
        c1.caption("Rainfall (mm per week)")
        c1.bar_chart(hist["rainfall_mm"], height=200, color="#64b5f6")
        c2.caption("Average temperature (°C)")
        c2.line_chart(hist["avg_temp_c"], height=200, color="#ffb74d")
        c3.caption("Relative humidity (%)")
        c3.line_chart(hist["relative_humidity_pct"], height=200, color="#ce93d8")

# ================= Tab 2: all wards =================
with tab2:
    h2 = st.radio("Forecast horizon", list(HORIZON_NAME), format_func=HORIZON_NAME.get, horizontal=True, key="h2")
    table = predict_all_wards(date_str, h2)
    st.markdown(f"Risk in **{HORIZON_NAME[h2]}** after the week of {date_str}")
    counts = pd.crosstab(table["city"], table["risk"]).reindex(columns=list(TIERS), fill_value=0)
    st.markdown("Wards per risk tier, by city")
    st.dataframe(counts)
    st.markdown("Highest-risk wards")
    styled = table.head(20).style.map(
        lambda v: f"background-color:{PASTEL[v]};color:#000" if v in PASTEL else "", subset=["risk"])
    st.dataframe(styled, hide_index=True)
    st.download_button("Download all 60 wards as CSV", table.to_csv(index=False),
                       file_name=f"dengue_risk_{date_str}_{h2}.csv", mime="text/csv")

# ================= Tab 3: validation =================
with tab3:
    st.markdown(f"Tested on weeks the model never saw: **{meta['split_date']} onward** "
                f"(trained on earlier years only).")
    m_cols = st.columns(2)
    for col, h in zip(m_cols, HORIZON_NAME):
        met = meta["metrics"][h]
        s = validation_summary(h)
        with col:
            with st.container(border=True):
                st.markdown(f"**{HORIZON_NAME[h]} ahead**")
                st.metric("Average error (MAE)", f"{met['mae']} cases",
                          help=f"Guessing the average would give {met['baseline_mae']}")
                st.metric("RMSE", f"{met['rmse']} cases")
                st.write(f"Exact risk tier right: **{s['exact']:.0%}**")
                st.write(f"High or Critical weeks flagged Medium or above: **{s['outbreak_caught']:.0%}** "
                         f"({s['n_outbreak']} weeks)")
    st.markdown(f"#### Actual vs predicted: {ward}, {HORIZON_NAME[horizon]} ahead")
    target = f"target_{horizon}"
    w = df[(df["ward_id"] == ward) & (df["date"] >= meta["split_date"])].dropna(subset=FEATURES + [target]).copy()
    w["Predicted"] = models[horizon].predict(w[FEATURES])
    w["Actual"] = w[target]
    w = w.set_index(w["date"] + pd.Timedelta(weeks=int(horizon[0])))
    st.line_chart(w[["Actual", "Predicted"]], height=300, color=["#e2e8f0", "#ffb74d"])
    st.caption("The model follows the seasonal pattern well but tends to under-predict the highest peaks.")
