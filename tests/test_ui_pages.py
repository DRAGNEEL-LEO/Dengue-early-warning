"""UI smoke tests: every page renders without an exception under several scenarios (Streamlit AppTest)."""
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
    {"scn_h": "4w", "scn_stock": 30, "scn_crews": 0},                 # scarcity, no crews
    {"scn_city": "Gazipur", "scn_stock": 100, "scn_crews": 200},       # single city, full stock
    {"scn_week": "2025-12-29"},                                        # off-season week, near-zero demand
    {"scn_week": "2025-06-23", "scn_basis": "cautious", "scn_policy": "triage"},  # unplaced patients, triage
])
def test_all_pages_other_scenarios(settings):
    at = _app()
    for k, v in settings.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception
    _visit_all(at)


def test_header_and_kpis_reflect_pipeline():
    at = _app()
    md = " ".join(m.value for m in at.markdown)
    assert "Dengue Early-Warning" in md and "Total predicted cases" in md
    at.switch_page("ui/views/dispatch_center.py").run()
    md = " ".join(m.value for m in at.markdown)
    assert "not sent" in md.lower()          # never claims delivery
