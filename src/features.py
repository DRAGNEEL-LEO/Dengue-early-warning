import pandas as pd

STATIC_COLS = ["population_density_sqkm", "water_logging_risk_index", "sanitation_score"]

FEATURES = (
    STATIC_COLS
    + [f"rain_lag_{k}w" for k in range(0, 5)]
    + ["rain_sum_4w", "temp_mean_2w", "temp_mean_4w",
       "humidity_mean_2w", "humidity_mean_4w", "month"]
)


def build_features(df):
    """Take the raw weekly data and add lag / rolling features per ward."""
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]          # avg_temp_C -> avg_temp_c
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["ward_id", "date"]).reset_index(drop=True)

    g = df.groupby("ward_id")

    # rainfall exactly k weeks ago (0 = this week)
    for k in range(0, 5):
        df[f"rain_lag_{k}w"] = g["rainfall_mm"].shift(k)

    # total rain over this week + previous 3 weeks
    df["rain_sum_4w"] = g["rainfall_mm"].transform(lambda s: s.rolling(4).sum())

    # average temperature / humidity over the last 2 and 4 weeks
    df["temp_mean_2w"] = g["avg_temp_c"].transform(lambda s: s.rolling(2).mean())
    df["temp_mean_4w"] = g["avg_temp_c"].transform(lambda s: s.rolling(4).mean())
    df["humidity_mean_2w"] = g["relative_humidity_pct"].transform(lambda s: s.rolling(2).mean())
    df["humidity_mean_4w"] = g["relative_humidity_pct"].transform(lambda s: s.rolling(4).mean())

    df["month"] = df["date"].dt.month

    # what we want to predict: cases 2 and 4 weeks into the future
    if "dengue_cases" in df.columns:
        df["target_2w"] = g["dengue_cases"].shift(-2)
        df["target_4w"] = g["dengue_cases"].shift(-4)
    return df
