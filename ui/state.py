"""Shared, cached data and the global scenario controls. Every page reads the same context, so all pages show
numbers from one run of the existing pipeline (src/pipeline.run_plan)."""
from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st

from config import HORIZON_NAME, PRIORITY_WEIGHTS
from features import FEATURES
from pipeline import load_system, run_plan
from predict import forecast_wards, risk_tier
from system_status import internet_reachable

DEFAULT_WEEK = "2024-08-12"     # held-out test week with mixed risk and some bed overflow (good for demos)
ALL = "All cities"


@st.cache_resource(show_spinner="Loading data and models from local disk (first run may train them, ~30 s)...")
def get_system():
    return load_system()


@st.cache_data(show_spinner=False)
def cached_plan(date_str, horizon, stock, crews, policy, basis, capacity, w_risk):
    return run_plan(get_system(), date_str, horizon, stock, crews, policy, basis, capacity=capacity,
                    weights={"risk": w_risk, "density": 1 - w_risk})


@st.cache_data(show_spinner=False)
def forecast_history(date_str, n_weeks, basis):
    """Model forecasts made at each of the last n origin weeks (existing forecast_wards, reused)."""
    s = get_system()
    weeks = sorted(s["df"].loc[s["df"]["date"] <= pd.Timestamp(date_str), "date"].dropna().unique())[-n_weeks:]
    frames = []
    for w in weeks:
        f = forecast_wards(s["models"], s["meta"], s["df"], w, basis=basis)
        f["origin"] = pd.Timestamp(w)
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


@st.cache_data(show_spinner=False)
def validation_summary(horizon):
    s = get_system()
    models, meta, df = s["models"], s["meta"], s["df"]
    target = f"target_{horizon}"
    test = df[df["date"] >= meta["split_date"]].dropna(subset=FEATURES + [target])
    pred = models[horizon].predict(test[FEATURES])
    actual_t = test[target].map(lambda x: risk_tier(x, meta["tiers"]))
    pred_t = pd.Series(pred, index=test.index).map(lambda x: risk_tier(x, meta["tiers"]))
    outbreak = actual_t.isin(["High", "Critical"])
    flagged = pred_t.isin(["Medium", "High", "Critical"])
    confusion = pd.crosstab(actual_t, pred_t).reindex(index=["Low", "Medium", "High", "Critical"],
                                                       columns=["Low", "Medium", "High", "Critical"], fill_value=0)
    return {"exact": float((actual_t == pred_t).mean()), "outbreak_caught": float(flagged[outbreak].mean()),
            "n_outbreak": int(outbreak.sum()), "n": int(len(test)), "confusion": confusion}


@st.cache_data(ttl=30, show_spinner=False)
def net_status():
    return internet_reachable()


@dataclass
class Context:
    system: dict
    date_str: str
    horizon: str
    city: str
    cities: list
    stock: int
    crews: int
    basis: str
    policy: str
    w_risk: float
    R: dict
    online: bool

    @property
    def models(self): return self.system["models"]

    @property
    def meta(self): return self.system["meta"]

    @property
    def df(self): return self.system["df"]

    @property
    def plan(self): return self.R["plan"]

    @property
    def view(self): return self.plan[self.plan["city"].isin(self.cities)]

    @property
    def forecast(self): return self.R["forecast"][self.R["forecast"]["city"].isin(self.cities)]

    @property
    def target_week(self): return self.R["target_week"].strftime("%Y-%m-%d")

    @property
    def hname(self): return HORIZON_NAME[self.horizon]


CTX = None


def ctx():
    return CTX


def _defaults(df):
    dates = sorted(df.dropna(subset=FEATURES)["date"].dt.strftime("%Y-%m-%d").unique(), reverse=True)
    st.session_state.setdefault("scn_week", DEFAULT_WEEK if DEFAULT_WEEK in dates else dates[0])
    st.session_state.setdefault("scn_h", "2w")
    st.session_state.setdefault("scn_city", ALL)
    st.session_state.setdefault("scn_stock", 60)
    st.session_state.setdefault("scn_crews", 40)
    st.session_state.setdefault("scn_basis", "expected")
    st.session_state.setdefault("scn_policy", "weighted")
    st.session_state.setdefault("scn_wrisk", float(PRIORITY_WEIGHTS["risk"]))
    return dates


def build_context():
    """Render the sidebar scenario controls, run the pipeline once, and publish the context."""
    global CTX
    s = get_system()
    df = s["df"]
    if "capacity" not in st.session_state:
        st.session_state.capacity = s["capacity"][["city", "ward_id", "bed_capacity"]].copy()
    dates = _defaults(df)
    cities_all = sorted(df["city"].unique())
    online = net_status()

    # ---- scenario controls (sidebar, below the page links)
    from ui.components import reset_cards
    reset_cards()
    sb = st.sidebar
    sb.markdown("<div class='side-brand' style='margin-top:6px'>Scenario</div>", unsafe_allow_html=True)
    sb.selectbox("Forecast from week", dates, key="scn_week",
                 help="Latest week of data. Forecasts look 2 and 4 weeks beyond it. Weeks inside the dataset are a "
                      "replay; the newest week (2025-12-29) is a genuine forecast.")
    if _has_required():
        sb.segmented_control("Horizon", ["2w", "4w"], key="scn_h", format_func=HORIZON_NAME.get, required=True)
    else:
        sb.radio("Horizon", ["2w", "4w"], key="scn_h", format_func=HORIZON_NAME.get, horizontal=True)
    sb.selectbox("City", [ALL] + cities_all, key="scn_city")
    sb.slider("Available regional stock", 30, 100, key="scn_stock", step=5, format="%d%%",
              help="Share of total forecast demand that is in stock, for each supply.")
    sb.number_input("Spraying crews", 0, 500, key="scn_crews", step=1)
    with sb.expander("Advanced"):
        st.radio("Demand basis", ["expected", "cautious"], key="scn_basis", horizontal=True,
                 format_func={"expected": "Expected", "cautious": "Cautious (P90)"}.get,
                 help="Cautious plans for the 90th percentile across the forest's trees: a buffer because the model "
                      "under-predicts the largest peaks.")
        st.radio("Scarcity policy", ["weighted", "triage"], key="scn_policy", horizontal=True,
                 format_func={"weighted": "Priority-weighted", "triage": "Strict triage"}.get,
                 help="Priority-weighted: higher-priority wards get a larger share, top wards first. "
                      "Strict triage: fill wards completely in priority order.")
        st.slider("Priority weight on risk (rest = density)", 0.0, 1.0, key="scn_wrisk", step=0.05)
    sb.markdown(
        "<div class='side-foot' style='margin-top:14px'>"
        + ("<span class='chip ok'><span class='dot'></span>Internet available · not required</span>" if online else
           "<span class='chip off'><span class='dot'></span>Offline · all core functions available</span>")
        + f"<br><br>Today {date.today().strftime('%d %b %Y')}<br>Local data · local models · no LLM</div>",
        unsafe_allow_html=True)

    ss = st.session_state
    horizon = ss["scn_h"] or "2w"
    city = ss["scn_city"]
    R = cached_plan(ss["scn_week"], horizon, int(ss["scn_stock"]), int(ss["scn_crews"]), ss["scn_policy"],
                    ss["scn_basis"], ss.capacity, float(ss["scn_wrisk"]))
    CTX = Context(system=s, date_str=ss["scn_week"], horizon=horizon, city=city,
                  cities=cities_all if city == ALL else [city], stock=int(ss["scn_stock"]),
                  crews=int(ss["scn_crews"]), basis=ss["scn_basis"], policy=ss["scn_policy"],
                  w_risk=float(ss["scn_wrisk"]), R=R, online=online)
    return CTX


def _has_required():
    import inspect
    return "required" in inspect.signature(st.segmented_control).parameters
