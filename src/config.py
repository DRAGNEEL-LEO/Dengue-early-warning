"""Central configuration: file paths, operational assumptions and policy weights.

Everything that is an *assumption* rather than something learned from the data lives here, so it can be
reviewed in one place and replaced with verified operational values. Nothing in this file is official
public-health policy.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MODEL_DIR = ROOT / "models"
EXPORT_DIR = ROOT / "exports"

# Phase 2 onsite dataset (supplied file, copied unchanged). The Phase 1 file data/dengue_raw.csv is kept for
# reference; its 12 columns are identical to the first 12 columns of the onsite file.
DATA = DATA_DIR / "bangladesh_dengue_onsite.csv"
PHASE1_DATA = DATA_DIR / "dengue_raw.csv"
CAPACITY_FILE = DATA_DIR / "ward_bed_capacity.csv"

SPLIT_DATE = "2024-01-01"          # chronological split: train before, test on/after
HORIZONS = ("2w", "4w")
HORIZON_WEEKS = {"2w": 2, "4w": 4}
HORIZON_NAME = {"2w": "2 weeks", "4w": "4 weeks"}

EXPECTED_CITIES = {"Dhaka North": 20, "Dhaka South": 20, "Chattogram": 10, "Gazipur": 5, "Narayanganj": 5}
RESOURCES = ("saline_bags_needed", "diagnostic_kits_needed", "hospital_beds_required")
RESOURCE_LABEL = {
    "saline_bags_needed": "Saline bags",
    "diagnostic_kits_needed": "Diagnostic kits",
    "hospital_beds_required": "Hospital beds",
}

# ---------------------------------------------------------------------------------------------------------
# Resource allocation policy (configurable system assumptions, NOT official policy)
# ---------------------------------------------------------------------------------------------------------
RISK_SCORE = {"Low": 0.0, "Medium": 1 / 3, "High": 2 / 3, "Critical": 1.0}
PRIORITY_WEIGHTS = {"risk": 0.7, "density": 0.3}   # must be >= 0; they are normalised to sum to 1
PRIORITY_FLOOR = 0.05      # every ward keeps a small positive weight so 'weighted' never zeroes it outright

# Spraying crews a ward would ideally receive, by forecast risk tier (assumption).
CREWS_NEEDED_BY_TIER = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}

# ---------------------------------------------------------------------------------------------------------
# Vector-control simulator (configurable assumptions; NOT learned from intervention data, which the
# dataset does not contain)
# ---------------------------------------------------------------------------------------------------------
# Reduction in forecast cases from n crews in a ward:  E(n) = max_reduction * (1 - exp(-n / saturation_crews))
SIM_MAX_REDUCTION = 0.40        # ceiling on the share of forecast cases any number of crews can prevent
SIM_SATURATION_CREWS = 2.0      # larger = slower saturation (more crews needed for the same effect)
# Larvicide / fogging acts on the next mosquito generation, so less of the effect is assumed to have arrived
# by the 2-week horizon than by the 4-week horizon.
SIM_TIMING = {"2w": 0.5, "4w": 1.0}

# Hospital capacity: data/ward_bed_capacity.csv is a DEMO ASSUMPTION (see hospital_routing.build_demo_capacity):
# city pool = this quantile of weekly city bed demand in training years, split by ward density share.
CAPACITY_QUANTILE = 0.95
CAPACITY_MIN_BEDS = 1
