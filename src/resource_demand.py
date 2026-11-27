"""Convert dengue case counts into supply demand.

What the data shows (see ARCHITECTURE.md): in the onsite dataset each resource column is an exact,
deterministic function of the same week's dengue_cases (every case count maps to exactly one value), close to
a fixed rate per case with rounding. A separate ML model per resource is therefore not justified: it could only
re-learn this mapping. We estimate one rate per resource from the TRAINING years only (least squares through
the origin) and apply it to forecast cases. Future resource columns are never used as model inputs.
"""
import numpy as np

from config import RESOURCES


def fit_rates(train_df):
    """Per-case rate for each resource, fitted on training rows only."""
    x = train_df["dengue_cases"].to_numpy(dtype=float)
    denom = float((x * x).sum())
    if denom == 0:
        raise ValueError("Training data has no dengue cases; cannot fit resource rates")
    return {r: float((x * train_df[r].to_numpy(dtype=float)).sum() / denom) for r in RESOURCES}


def round_half_up(values):
    return np.floor(np.asarray(values, dtype=float) + 0.5).astype(int)


def demand_from_cases(cases, rates):
    """Integer demand per resource for an array of (possibly fractional) forecast cases."""
    cases = np.clip(np.asarray(cases, dtype=float), 0, None)
    return {r: round_half_up(cases * rates[r]) for r in RESOURCES}


def evaluate_rates(test_df, rates):
    """How well rate x cases reproduces each resource column on held-out weeks (same-week actual cases)."""
    out = {}
    est = demand_from_cases(test_df["dengue_cases"], rates)
    for r in RESOURCES:
        actual = test_df[r].to_numpy()
        out[r] = {
            "exact_match": round(float((est[r] == actual).mean()), 4),
            "mae": round(float(np.abs(est[r] - actual).mean()), 4),
        }
    return out


def mapping_table(df):
    """Observed mapping case-count -> resource values, with a determinism check."""
    g = df.groupby("dengue_cases")[list(RESOURCES)]
    deterministic = bool((g.nunique() == 1).all().all())
    return g.first().reset_index(), deterministic


def add_demand_columns(frame, rates, cases_col="predicted_cases"):
    frame = frame.copy()
    for r, v in demand_from_cases(frame[cases_col], rates).items():
        frame[r] = v
    return frame
