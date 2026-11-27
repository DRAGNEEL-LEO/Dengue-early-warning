"""Dengue Early-Warning & Response System: Streamlit entry point.

The interface lives in ui/ (design system, components, offline map, shared state, one file per page). All
calculations come from the existing modules in src/; pages never re-implement business logic.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Dengue Surveillance", page_icon=str(ROOT / "ui/assets/icon.svg"),
                   layout="wide", initial_sidebar_state="expanded")

from ui import theme  # noqa: E402
from ui.state import build_context  # noqa: E402

theme.inject_css()
st.logo(str(ROOT / "ui/assets/logo.svg"), icon_image=str(ROOT / "ui/assets/icon.svg"), size="large")

V = ROOT / "ui" / "views"
nav = st.navigation({
    "Surveillance": [
        st.Page(V / "dashboard.py", title="Disease Surveillance", icon=":material/radar:", default=True),
    ],
    "Prediction": [
        st.Page(V / "ward_forecast.py", title="Dengue Forecast", icon=":material/show_chart:", url_path="forecast"),
        st.Page(V / "risk_intelligence.py", title="Geographic Risk", icon=":material/map:", url_path="risk"),
        st.Page(V / "model_performance.py", title="Model Performance", icon=":material/query_stats:",
                url_path="performance"),
    ],
    "Response": [
        st.Page(V / "resource_allocation.py", title="Resource Allocation", icon=":material/inventory_2:",
                url_path="allocation"),
        st.Page(V / "hospital_routing.py", title="Hospital Routing", icon=":material/local_hospital:",
                url_path="routing"),
        st.Page(V / "intervention_simulator.py", title="Intervention Simulator", icon=":material/science:",
                url_path="simulator"),
    ],
    "Communication": [
        st.Page(V / "dispatch_center.py", title="Dispatch Center", icon=":material/campaign:", url_path="dispatch"),
    ],
    "System": [
        st.Page(V / "system_status.py", title="System Status", icon=":material/monitor_heart:", url_path="status"),
    ],
}, position="sidebar")

build_context()
nav.run()
