import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from conftest import ROOT
from config import RESOURCES


def test_dataset_valid(system):
    rep = system["report"]
    assert rep["rows"] == 31320 and rep["wards"] == 60 and rep["cities"] == 5
    assert rep["missing_values"] == 0 and rep["duplicate_rows"] == 0
    assert rep["first_week"] == "2016-01-04" and rep["last_week"] == "2025-12-29"


def test_validation_rejects_bad_data(system):
    from data_processing import DataValidationError, validate
    raw = system["raw"]
    with pytest.raises(DataValidationError):
        validate(raw.drop(columns=["saline_bags_needed"]))
    with pytest.raises(DataValidationError):
        validate(raw[raw["city"] != "Gazipur"])
    with pytest.raises(DataValidationError):
        validate(pd.concat([raw, raw.head(1)]))


def test_models_and_feature_schema(system):
    from features import FEATURES
    meta, models = system["meta"], system["models"]
    assert meta["features"] == FEATURES
    for h in ("2w", "4w"):
        assert list(models[h].feature_names_in_) == FEATURES
        assert not any(r in FEATURES for r in RESOURCES)          # no resource column used as an input
        assert "dengue_cases" not in FEATURES and not any(f.startswith("target") for f in FEATURES)
        m = meta["metrics"][h]
        assert m["mae"] < m["persistence_mae"] and m["mae"] < m["baseline_mae"]


def test_resource_rates_from_training_reproduce_columns(system):
    ev = system["meta"]["resource_rate_eval_2024_2025"]
    for r in RESOURCES:
        assert ev[r]["exact_match"] > 0.99


def test_forecast_covers_all_wards_and_horizons(system):
    from predict import forecast_wards
    fc = forecast_wards(system["models"], system["meta"], system["df"], "2024-08-12")
    assert len(fc) == 60 and {"cases_2w", "cases_4w", "risk_2w", "risk_4w"} <= set(fc.columns)
    cautious = forecast_wards(system["models"], system["meta"], system["df"], "2024-08-12", basis="cautious")
    assert (cautious["cases_2w"].to_numpy() >= fc["cases_2w"].to_numpy() - 1e-6).mean() > 0.9


def test_dispatch_notice_completeness(system):
    from pipeline import run_plan
    from dispatch_generator import html_brief, notices_for, pdf_brief, sms_text, whatsapp_text
    r = run_plan(system, "2024-08-12", "4w", 60, 40)
    plan, tr = r["plan"], r["transfers"]
    notices = notices_for(plan, tr)
    assert len(notices) == 60
    by_ward = plan.set_index("ward_id")
    for n in notices:
        row = by_ward.loc[n["ward_id"]]
        for short, res in (("Saline", "saline_bags_needed"), ("Kits", "diagnostic_kits_needed"),
                           ("Beds", "hospital_beds_required")):
            assert n["supply"][short]["required"] == row[f"{res}_required"]
            assert n["supply"][short]["allocated"] == row[f"{res}_allocated"]
            assert n["supply"][short]["deficit"] == row[f"{res}_deficit"]
        assert n["crews_assigned"] == row["crews_assigned"]
        assert n["deficit_alert"] == bool(row["critical_deficit"])
        sms, wa = sms_text(n), whatsapp_text(n)
        for text in (sms, wa):
            assert n["ward_id"] in text and n["city"] in text and n["risk"].upper() in text.upper()
            assert str(n["supply"]["Saline"]["allocated"]) in text
        assert "Action required" in wa
        if n["transferred_out"]:
            assert n["sent_to"] and "Transfer" in sms
        if n["deficit_alert"]:
            assert "DEFICIT" in sms and "CRITICAL SUPPLY DEFICIT" in wa
    html = html_brief(notices[:3])
    assert html.startswith("<!doctype html>") and notices[0]["ward_id"] in html
    pdf = pdf_brief(notices[:3])
    assert pdf is None or pdf[:4] == b"%PDF"


def test_dispatch_rejects_incomplete_row():
    from dispatch_generator import build_notice
    with pytest.raises(ValueError):
        build_notice({"city": "A", "ward_id": "A1"}, pd.DataFrame())


def test_pipeline_identical_inputs_identical_outputs(system):
    from pipeline import run_plan
    a = run_plan(system, "2025-06-23", "2w", 45, 30)
    b = run_plan(system, "2025-06-23", "2w", 45, 30)
    pd.testing.assert_frame_equal(a["plan"], b["plan"])
    pd.testing.assert_frame_equal(a["transfers"], b["transfers"])


def test_offline_core_execution():
    """Runs the kill-switch script in a fresh process with all sockets disabled."""
    res = subprocess.run([sys.executable, str(ROOT / "offline_check.py")], capture_output=True, text=True,
                         timeout=600)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "PASSED" in res.stdout


def test_no_network_libraries_in_core_modules():
    banned = ("requests", "urllib.request", "httpx", "openai", "anthropic", "aiohttp")
    for f in (ROOT / "src").glob("*.py"):
        text = f.read_text()
        for b in banned:
            assert f"import {b}" not in text and f"from {b}" not in text, (f.name, b)
    assert np.isfinite(1.0)
