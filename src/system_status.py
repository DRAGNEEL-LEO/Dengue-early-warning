"""Local system checks for the System / Offline Status page. Nothing here is needed for the core math."""
import importlib.util
import socket

from config import CAPACITY_FILE, DATA, MODEL_DIR


def internet_reachable(timeout=0.8):
    """Optional probe. The system never needs the internet; this only informs the status badge."""
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=timeout):
            return True
    except OSError:
        return False


def local_checks():
    files = {
        "Dataset (onsite CSV)": DATA,
        "2-week model": MODEL_DIR / "model_2w.pkl",
        "4-week model": MODEL_DIR / "model_4w.pkl",
        "Model metadata (tiers, rates, metrics)": MODEL_DIR / "meta.json",
        "Bed capacity table (demo assumption)": CAPACITY_FILE,
    }
    rows = [{"component": k, "status": "OK" if p.exists() else "MISSING",
             "detail": f"{p.name} ({p.stat().st_size / 1024:.0f} KB)" if p.exists() else str(p)}
            for k, p in files.items()]
    has_pdf = importlib.util.find_spec("fpdf") is not None
    rows.append({"component": "PDF export (fpdf2, optional)", "status": "OK" if has_pdf else "FALLBACK",
                 "detail": "installed" if has_pdf else "not installed: HTML brief is used instead"})
    rows.append({"component": "External APIs / LLM", "status": "NOT USED",
                 "detail": "forecasting, allocation, routing, simulation and dispatch are all local"})
    return rows
