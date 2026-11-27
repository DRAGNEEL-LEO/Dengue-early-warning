import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import HORIZON_NAME, HORIZON_WEEKS, RESOURCE_LABEL, RESOURCES
from features import FEATURES
from ui import components as C
from ui import theme as T
from ui.state import ctx, validation_summary

c = ctx()
meta, df, models = c.meta, c.df, c.models
m2, m4 = meta["metrics"]["2w"], meta["metrics"]["4w"]
C.page_header("Model performance",
              f"Measured on weeks the model never saw ({meta['split_date']} onward). Trained on 2016-2023 only, "
              "split by date (no shuffling).")

# ---------------------------------------------------------------- headline comparison
cols = st.columns(2, gap="medium")
for col, h in zip(cols, ("2w", "4w")):
    m = meta["metrics"][h]
    v = validation_summary(h)
    with col, C.card():
        st.markdown(f"#### {HORIZON_NAME[h]} ahead")
        a, b, cc = st.columns(3)
        a.metric("MAE", f"{m['mae']:.2f}", delta=f"{m['mae'] - m['persistence_mae']:+.2f} vs persistence",
                 delta_color="inverse", help="Mean absolute error, cases per ward-week. Lower is better.")
        b.metric("RMSE", f"{m['rmse']:.2f}", help="Root mean squared error; penalises large misses more.")
        cc.metric("R²", f"{m['r2']:.3f}", help="Share of variance in weekly cases explained (1 = perfect).")
        st.progress(v["exact"], text=f"Risk-tier agreement: **{v['exact']:.1%}** of {v['n']:,} ward-weeks")
        st.progress(v["outbreak_caught"], text=f"High/Critical weeks flagged Medium or above: "
                                               f"**{v['outbreak_caught']:.1%}** ({v['n_outbreak']} ward-weeks)")
        st.caption("Risk-tier agreement measures whether the predicted tier (Low/Medium/High/Critical) matches the "
                   "actual tier. It is not the accuracy of the case numbers, which MAE/RMSE/R² describe.")

# ---------------------------------------------------------------- baselines chart + confusion
left, right = st.columns([1.1, 1], gap="medium")
with left:
    with C.card():
        st.markdown("**Error vs simple baselines** (MAE, lower is better)")
        names = ["Random Forest", "Persistence<br>(same as this week)", "Training-period<br>average"]
        fig = go.Figure()
        for h, colr in (("2w", T.BLUE), ("4w", T.CYAN)):
            m = meta["metrics"][h]
            fig.add_bar(x=names, y=[m["mae"], m["persistence_mae"], m["baseline_mae"]], name=HORIZON_NAME[h],
                        marker_color=colr, text=[f"{x:.2f}" for x in (m["mae"], m["persistence_mae"], m["baseline_mae"])],
                        textposition="outside", hovertemplate="%{x}: %{y:.3f}<extra></extra>")
        fig.update_layout(barmode="group", height=330, yaxis_title="MAE (cases per ward-week)",
                          xaxis=dict(tickangle=0), yaxis_range=[0, 3.8])
        C.chart(fig, key="mp_base")
with right:
    with C.card():
        h = c.horizon
        st.markdown(f"**Risk-tier confusion matrix** · {HORIZON_NAME[h]} (rows: actual, columns: predicted)")
        cm = validation_summary(h)["confusion"]
        fig = go.Figure(go.Heatmap(z=cm.values, x=[f"Pred {t}" for t in cm.columns], y=[f"Actual {t}" for t in cm.index],
                                   colorscale=[[0, "#17171A"], [0.35, "#5A3A1C"], [1, T.AMBER]], text=cm.values, texttemplate="%{text}",
                                   showscale=False, hovertemplate="%{y} / %{x}: %{z}<extra></extra>"))
        fig.update_layout(height=330, yaxis=dict(autorange="reversed"), margin=dict(t=10))
        C.chart(fig, key="mp_cm")

# ---------------------------------------------------------------- actual vs predicted
with C.card():
    h = c.horizon
    hw = HORIZON_WEEKS[h]
    opts = sorted(c.view["ward_id"])
    a, _ = st.columns([1, 2])
    ward = a.selectbox("Ward", opts, key="mp_ward")
    st.markdown(f"**Actual vs predicted, held-out period** · {ward}, {HORIZON_NAME[h]} ahead")
    t = f"target_{h}"
    w = df[(df["ward_id"] == ward) & (df["date"] >= meta["split_date"])].dropna(subset=FEATURES + [t])
    x = w["date"] + pd.Timedelta(weeks=hw)
    fig = go.Figure()
    fig.add_scatter(x=x, y=w[t], name="Actual", mode="lines", line=dict(color=T.SLATE, width=2))
    fig.add_scatter(x=x, y=models[h].predict(w[FEATURES]), name="Predicted", mode="lines",
                    line=dict(color=T.BLUE, width=2.2))
    fig.update_layout(height=320, yaxis_title="Cases per week", hovermode="x unified")
    C.chart(fig, key="mp_avp")

# ---------------------------------------------------------------- rates + limitations
left, right = st.columns([1, 1.2], gap="medium")
with left:
    with C.card():
        st.markdown("**Resource-demand rates** (fitted on 2016-2023)")
        ev = meta["resource_rate_eval_2024_2025"]
        st.dataframe(pd.DataFrame([{"Supply": RESOURCE_LABEL[r], "Per case": meta["resource_rates"][r],
                                    "Exact match 2024-25": 100 * ev[r]["exact_match"]} for r in RESOURCES]),
                     hide_index=True, width="stretch",
                     column_config={"Per case": C.num("Per case", "%.3f"),
                                    "Exact match 2024-25": C.bar("Exact match 2024-25", "%.2f%%")})
        st.caption("The dataset's supply columns are a fixed rate × cases, so planning error comes from the case "
                   "forecast, not from the conversion.")
with right:
    with C.card():
        st.markdown("**Limitations**")
        st.markdown(f"""
- Under-predicts the largest peaks: at {HORIZON_NAME['4w']}, {validation_summary('4w')['outbreak_caught']:.0%} of
  High/Critical ward-weeks were flagged Medium or above (2 weeks: {validation_summary('2w')['outbreak_caught']:.0%}).
  The *Cautious (P90)* demand basis is the planning buffer.
- One dataset and one chronological split; no validation on real outbreak data from outside this dataset.
- Inputs are weather and ward attributes; past case counts were tested and improved MAE by only about 0.01.
- Driver bars and the rainfall scenario are approximations, not causal effects.
""")
