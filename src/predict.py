"""Model loading, risk tiers, prediction ranges and driver explanations."""
import json

import joblib
import numpy as np
import pandas as pd

from features import FEATURES
from train import MODEL_DIR, HORIZONS, train_all

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


def load_models():
    """Load saved models. If they are missing or were saved by a different
    scikit-learn version, retrain once (about 20 seconds) and load again."""
    try:
        models = {h: joblib.load(MODEL_DIR / f"model_{h}.pkl") for h in HORIZONS}
        meta = json.loads((MODEL_DIR / "meta.json").read_text())
        probe = pd.DataFrame([meta["baseline"]])[FEATURES]
        for m in models.values():
            m.predict(probe)
    except Exception:
        train_all(verbose=False)
        models = {h: joblib.load(MODEL_DIR / f"model_{h}.pkl") for h in HORIZONS}
        meta = json.loads((MODEL_DIR / "meta.json").read_text())
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
