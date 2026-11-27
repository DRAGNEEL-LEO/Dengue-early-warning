"""Model loading, risk tiers, prediction ranges and driver explanations."""
import json
import warnings

import joblib
import numpy as np
import pandas as pd
import sklearn

from config import HORIZONS, MODEL_DIR
from features import FEATURES
from train import train_all

LABELS = {
    "population_density_sqkm": "Population density",
    "water_logging_risk_index": "Water-logging risk",
    "sanitation_score": "Sanitation score",
    "rain_lag_0w": "Rain this week",
    "rain_lag_1w": "Rain 1 week ago",
    "rain_lag_2w": "Rain 2 weeks ago",
    "rain_lag_3w": "Rain 3 weeks ago",
    "rain_lag_4w": "Rain 4 weeks ago",
    "rain_sum_4w": "Total rain, last 4 weeks",
    "temp_mean_2w": "Avg temperature, last 2 weeks",
    "temp_mean_4w": "Avg temperature, last 4 weeks",
    "humidity_mean_2w": "Avg humidity, last 2 weeks",
    "humidity_mean_4w": "Avg humidity, last 4 weeks",
    "month": "Month of year",
}
TIERS = ("Low", "Medium", "High", "Critical")


def _read():
    meta = json.loads((MODEL_DIR / "meta.json").read_text())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        models = {h: joblib.load(MODEL_DIR / f"model_{h}.pkl") for h in HORIZONS}
    return models, meta


def load_models():
    """Load saved models from local disk (no network). If they are missing, were saved by a different
    scikit-learn version, or predate the Phase 2 metadata, retrain once (about 30 seconds) and load again."""
    try:
        models, meta = _read()
        if meta.get("sklearn_version") != sklearn.__version__ or "resource_rates" not in meta:
            raise RuntimeError("stale model artifacts")
        probe = pd.DataFrame([meta["baseline"]])[FEATURES]
        for m in models.values():
            m.predict(probe)
    except Exception:
        train_all(verbose=False)
        models, meta = _read()
    return models, meta


def risk_tier(cases, tiers):
    if cases >= tiers["Critical"]:
        return "Critical"
    if cases >= tiers["High"]:
        return "High"
    if cases >= tiers["Medium"]:
        return "Medium"
    return "Low"


def predict_with_range(model, row):
    """Prediction for one row plus a 10th-90th percentile range across the trees."""
    X = row[FEATURES].to_numpy(dtype=float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # trees were fitted with column names; plain arrays are fine
        per_tree = np.array([t.predict(X)[0] for t in model.estimators_])
    return float(per_tree.mean()), float(np.percentile(per_tree, 10)), float(np.percentile(per_tree, 90))


def driver_impacts(model, row, baseline):
    """How much each input pushes this prediction up or down compared with a
    typical value (the training-period median). Positive = raises predicted cases."""
    X = row[FEATURES].astype(float).reset_index(drop=True)
    variants = [X]
    for f in FEATURES:
        v = X.copy()
        v[f] = baseline[f]
        variants.append(v)
    P = model.predict(pd.concat(variants, ignore_index=True))
    return pd.Series(P[0] - P[1:], index=FEATURES)


def forecast_wards(models, meta, df, date, basis="expected"):
    """2-week and 4-week forecasts for every ward at one origin week (one model call per horizon).

    basis: "expected" = mean of the trees; "cautious" = 90th percentile across trees, a planning buffer
    because the model under-predicts the largest peaks.
    """
    rows = df[df["date"] == pd.Timestamp(date)].dropna(subset=FEATURES)
    out = rows[["city", "ward_id", "population_density_sqkm"]].copy().reset_index(drop=True)
    X = rows[FEATURES].to_numpy(dtype=float)
    for h in HORIZONS:
        m = models[h]
        if basis == "cautious":
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                per_tree = np.stack([t.predict(X) for t in m.estimators_])
            pred = np.percentile(per_tree, 90, axis=0)
        elif basis == "expected":
            pred = m.predict(rows[FEATURES])
        else:
            raise ValueError("basis must be 'expected' or 'cautious'")
        out[f"cases_{h}"] = np.round(np.clip(pred, 0, None), 2)
        out[f"risk_{h}"] = [risk_tier(p, meta["tiers"]) for p in out[f"cases_{h}"]]
    return out
