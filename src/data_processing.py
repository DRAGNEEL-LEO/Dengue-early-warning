"""Load and validate the onsite dataset. The source CSV is never modified."""
import pandas as pd

from config import DATA, EXPECTED_CITIES, RESOURCES

BASE_COLUMNS = [
    "date", "city", "ward_id", "population_density_sqkm", "water_logging_risk_index", "sanitation_score",
    "avg_temp_c", "max_temp_c", "min_temp_c", "rainfall_mm", "relative_humidity_pct", "dengue_cases",
]
REQUIRED_COLUMNS = BASE_COLUMNS + list(RESOURCES)


class DataValidationError(ValueError):
    pass


def load_raw(path=DATA):
    df = pd.read_csv(path)
    # Phase 1 data used 'avg_temp_C'; the onsite file is already lowercase. Lowercasing is a no-op here.
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def validate(df, require_resources=True):
    """Return a report dict; raise DataValidationError on problems that would break the pipeline."""
    needed = REQUIRED_COLUMNS if require_resources else BASE_COLUMNS
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise DataValidationError(f"Missing columns: {missing}")

    dates = pd.to_datetime(df["date"], errors="coerce")
    if dates.isna().any():
        raise DataValidationError(f"{int(dates.isna().sum())} unparseable dates")

    numeric = [c for c in needed if c not in ("date", "city", "ward_id")]
    bad_numeric = [c for c in numeric if not pd.api.types.is_numeric_dtype(df[c])]
    if bad_numeric:
        raise DataValidationError(f"Non-numeric columns: {bad_numeric}")
    negative = [c for c in numeric if c not in ("avg_temp_c", "max_temp_c", "min_temp_c") and (df[c] < 0).any()]
    if negative:
        raise DataValidationError(f"Negative values in: {negative}")

    wards_per_city = df.groupby("city")["ward_id"].nunique().to_dict()
    if wards_per_city != EXPECTED_CITIES:
        raise DataValidationError(f"Unexpected city/ward structure: {wards_per_city}")
    if df.groupby("ward_id")["city"].nunique().max() > 1:
        raise DataValidationError("A ward_id appears in more than one city")

    dup_keys = int(df.duplicated(subset=["date", "ward_id"]).sum())
    if dup_keys:
        raise DataValidationError(f"{dup_keys} duplicate (date, ward_id) rows")

    return {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "cities": len(wards_per_city),
        "wards": int(df["ward_id"].nunique()),
        "wards_per_city": wards_per_city,
        "first_week": dates.min().strftime("%Y-%m-%d"),
        "last_week": dates.max().strftime("%Y-%m-%d"),
        "weeks": int(dates.nunique()),
        "missing_values": int(df[needed].isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
    }


def load_dataset(path=DATA):
    df = load_raw(path)
    report = validate(df)
    return df, report
