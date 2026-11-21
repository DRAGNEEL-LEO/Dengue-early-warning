"""Train the 2-week and 4-week dengue models and save them to models/.

Run:  python src/train.py        (takes about 20 seconds)
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from features import build_features, FEATURES

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "dengue_raw.csv"
MODEL_DIR = ROOT / "models"
SPLIT_DATE = "2024-01-01"      # chronological split: train before, test on/after
HORIZONS = ("2w", "4w")


def train_all(verbose=True):
    MODEL_DIR.mkdir(exist_ok=True)
    df = build_features(pd.read_csv(DATA))
    metrics = {}

    for h in HORIZONS:
        target = f"target_{h}"
        data = df.dropna(subset=FEATURES + [target])
        train = data[data["date"] < SPLIT_DATE]
        test = data[data["date"] >= SPLIT_DATE]

        model = RandomForestRegressor(
            n_estimators=100, max_depth=12, min_samples_leaf=5,
            random_state=42, n_jobs=-1,
        )
        model.fit(train[FEATURES], train[target])

        pred = model.predict(test[FEATURES])
        mae = mean_absolute_error(test[target], pred)
        rmse = mean_squared_error(test[target], pred) ** 0.5
        base_mae = mean_absolute_error(test[target], np.full(len(test), train[target].mean()))
        metrics[h] = {"mae": round(mae, 3), "rmse": round(rmse, 3), "baseline_mae": round(base_mae, 3)}
        if verbose:
            print(f"[{h}] train={len(train)} test={len(test)}  MAE={mae:.3f}  RMSE={rmse:.3f}  "
                  f"(guess-the-average MAE={base_mae:.3f})")

        joblib.dump(model, MODEL_DIR / f"model_{h}.pkl", compress=3)

    # Risk-tier cut-offs and 'typical' feature values come from the TRAINING years only.
    train_rows = df[df["date"] < SPLIT_DATE]
    cases = train_rows["dengue_cases"]
    tiers = {
        "Medium": float(cases.quantile(0.75)),
        "High": float(cases.quantile(0.90)),
        "Critical": float(cases.quantile(0.95)),
    }
    baseline = train_rows[FEATURES].median().to_dict()
    meta = {"tiers": tiers, "metrics": metrics, "split_date": SPLIT_DATE, "baseline": baseline}
    (MODEL_DIR / "meta.json").write_text(json.dumps(meta, indent=2))
    if verbose:
        print("tier cut-offs (cases per week):", tiers)
    return meta


if __name__ == "__main__":
    train_all()
