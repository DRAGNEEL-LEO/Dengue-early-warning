"""UI smoke tests: every page renders without an exception under several scenarios (Streamlit AppTest)."""
import json

import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT

PAGES = ["dashboard", "ward_forecast", "risk_intelligence", "model_performance", "resource_allocation",
         "hospital_routing", "intervention_simulator", "dispatch_center", "system_status"]


def _app():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _visit_all(at):
    for p in PAGES:
        at.switch_page(f"ui/views/{p}.py").run()
        assert not at.exception, (p, [e.value for e in at.exception])


def test_all_pages_default_scenario():
    _visit_all(_app())


@pytest.mark.parametrize("settings", [
    {"scn_h": "4w", "scn_stock": 30, "scn_crews": 0},
    {"scn_city": "Gazipur", "scn_stock": 100, "scn_crews": 200},
    {"scn_week": "2025-12-29"},
    {"scn_week": "2025-06-23", "scn_basis": "cautious", "scn_policy": "triage"},
])
def test_all_pages_other_scenarios(settings):
    at = _app()
    for k, v in settings.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception
    _visit_all(at)


def test_dashboard_shows_real_metrics_and_never_claims_delivery():
    at = _app()
    md = " ".join(m.value for m in at.markdown)
    assert "Dengue Surveillance" in md and "Predicted cases" in md and "Critical wards" in md
    at.switch_page("ui/views/dispatch_center.py").run()
    md = " ".join(m.value for m in at.markdown).lower()
    assert "delivered" not in md.replace("not delivered", "")


def test_map_assets_are_local_and_attributed():
    d = json.loads((ROOT / "data/geo/bd_districts.json").read_text(encoding="utf-8"))
    names = {x["name"] for x in d["districts"] if x["focus"]}
    assert names == {"Dhaka", "Gazipur", "Narayanganj", "Chittagong"}
    assert "CC BY 3.0 IGO" in d["license"]
    for w in (300, 400, 500, 600):
        assert (ROOT / f"static/fonts/inter-latin-{w}-normal.woff2").stat().st_size > 10_000
