"""Train the 2-week and 4-week dengue models and save them to models/.

Run:  python src/train.py        (takes about 20-40 seconds)

Phase 2 changes: reads the onsite dataset, reports R2 and a persistence baseline alongside MAE/RMSE, fits the
per-case resource-demand rates on training years only, and writes the demo bed-capacity table.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from config import DATA, MODEL_DIR, SPLIT_DATE, HORIZONS, CAPACITY_FILE
from data_processing import load_dataset
from features import build_features, FEATURES
from resource_demand import fit_rates, evaluate_rates, mapping_table

RF_PARAMS = dict(n_estimators=100, max_depth=12, min_samples_leaf=5, random_state=42, n_jobs=-1)


def _scores(y, p):
    return {
        "mae": round(float(mean_absolute_error(y, p)), 3),
        "rmse": round(float(mean_squared_error(y, p) ** 0.5), 3),
        "r2": round(float(r2_score(y, p)), 3),
    }


def train_all(verbose=True):
    MODEL_DIR.mkdir(exist_ok=True)
    raw, report = load_dataset(DATA)
    df = build_features(raw)
    metrics = {}

    for h in HORIZONS:
        target = f"target_{h}"
        data = df.dropna(subset=FEATURES + [target])
        train = data[data["date"] < SPLIT_DATE]
        test = data[data["date"] >= SPLIT_DATE]

        model = RandomForestRegressor(**RF_PARAMS)
        model.fit(train[FEATURES], train[target])
        pred = model.predict(test[FEATURES])

        m = _scores(test[target], pred)
        # Baselines: the training-period mean, and persistence (cases this week = cases in h weeks).
        m["baseline_mae"] = round(float(mean_absolute_error(test[target], np.full(len(test), train[target].mean()))), 3)
        persist = _scores(test[target], test["dengue_cases"])
        m["persistence_mae"], m["persistence_rmse"], m["persistence_r2"] = persist["mae"], persist["rmse"], persist["r2"]
        m.update({
            "train_rows": int(len(train)), "test_rows": int(len(test)),
            "train_origin_weeks": [train["date"].min().strftime("%Y-%m-%d"), train["date"].max().strftime("%Y-%m-%d")],
            "test_origin_weeks": [test["date"].min().strftime("%Y-%m-%d"), test["date"].max().strftime("%Y-%m-%d")],
        })
        metrics[h] = m
        if verbose:
            print(f"[{h}] train={len(train)} test={len(test)}  MAE={m['mae']}  RMSE={m['rmse']}  R2={m['r2']}  "
                  f"(persistence MAE={m['persistence_mae']}, guess-the-average MAE={m['baseline_mae']})")
        joblib.dump(model, MODEL_DIR / f"model_{h}.pkl", compress=3)

    # Risk-tier cut-offs, 'typical' feature values and resource rates come from the TRAINING years only.
    train_rows = df[df["date"] < SPLIT_DATE]
    test_rows = df[df["date"] >= SPLIT_DATE]
    cases = train_rows["dengue_cases"]
    tiers = {
        "Medium": float(cases.quantile(0.75)),
        "High": float(cases.quantile(0.90)),
        "Critical": float(cases.quantile(0.95)),
    }
    baseline = train_rows[FEATURES].median().to_dict()
    rates = fit_rates(train_rows)
    rate_eval = evaluate_rates(test_rows, rates)
    _, deterministic = mapping_table(raw)

    meta = {
        "tiers": tiers, "metrics": metrics, "split_date": SPLIT_DATE, "baseline": baseline,
        "features": FEATURES,
        "resource_rates": {k: round(v, 5) for k, v in rates.items()},
        "resource_rate_eval_2024_2025": rate_eval,
        "resource_mapping_deterministic": deterministic,
        "dataset": {"file": DATA.name, **{k: v for k, v in report.items() if k != "wards_per_city"}},
        "sklearn_version": sklearn.__version__,
    }
    (MODEL_DIR / "meta.json").write_text(json.dumps(meta, indent=2))

    from hospital_routing import build_demo_capacity     # local import avoids a cycle at module load
    build_demo_capacity(raw).to_csv(CAPACITY_FILE, index=False)

    if verbose:
        print("tier cut-offs (cases per week):", tiers)
        print("resource rates per case:", meta["resource_rates"])
        print("rate reproduction on 2024-2025 (same-week cases):", rate_eval)
    return meta


if __name__ == "__main__":
    train_all()
