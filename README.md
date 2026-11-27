# Dengue early-warning and response system

Forecasts weekly dengue cases and a risk tier (Low / Medium / High / Critical) for 60 urban wards in Dhaka North,
Dhaka South, Chattogram, Gazipur and Narayanganj, **2 and 4 weeks ahead**, then turns the forecast into operational
decisions: how much saline, how many diagnostic kits and hospital beds each ward needs, who gets scarce stock,
where overflow patients go, where spraying crews should be sent, and ready-to-send dispatch notices.

EDU AI Engineering Hackathon 2026. Phase 1 (preliminary round, "AI for Urban Dengue Outbreak") built the
forecaster; Phase 2 (onsite final) extends the same repository into a resource-optimisation, intervention-simulation
and dispatch command system. Build tag: **BLUEPINE**.

**Live demo:** https://dengue-early-warning.streamlit.app/

## Phase 2 modules

| # | Module | What it does | Where |
|---|---|---|---|
| 1 | Constrained resource allocation | Converts forecast cases into saline, kit and bed demand, then allocates them under an **Available Regional Stock (30-100%)** slider and a **Total Spraying Crews** control, prioritising high-risk, high-density wards. Flags a **CRITICAL SUPPLY DEFICIT** for every ward whose demand is not 100% met. | `src/resource_demand.py`, `src/resource_allocation.py` |
| 2 | Hospital overflow routing | Compares each ward's bed demand with its local capacity and routes overflow patients to the lowest-burden wards **in the same city only**, showing net deficits, headroom and city-wide utilisation. | `src/hospital_routing.py` |
| 3 | Vector-control simulator | Deploy a limited number of larvicide / fogging teams to chosen wards and see the simulated 2-week and 4-week reduction in cases, bed load and saline use, ranked by ROI (cases prevented per crew). Includes an optimiser. | `src/intervention_simulator.py` |
| 4 | Multi-channel dispatch | Ward-specific SMS, WhatsApp and printable HTML / PDF commissioner briefs listing forecast cases, allocated vs required supplies, deficit alerts, transfers, crews and the action required. | `src/dispatch_generator.py`, `exports/` |
| 5 | Offline resilience | Every core function runs from local files with no internet and no LLM API. An automated kill-switch test disables all sockets and runs the full chain. | `offline_check.py`, `src/system_status.py` |

All five share one code path, `src/pipeline.py` (forecast → demand → allocation → routing), used by the dashboard,
the export script, the offline test and the unit tests alike.

## Run it locally

```bash
git clone https://github.com/DRAGNEEL-LEO/Dengue-early-warning.git
cd Dengue-early-warning
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501. Saved models load from `models/`. If they are missing or were saved by a different
scikit-learn version, the app retrains once on first launch (about 10-30 seconds, fully offline).

Other commands:

```bash
python src/train.py            # retrain both models, refit resource rates, rebuild the demo capacity table
python -m pytest -q            # 57 automated tests
python offline_check.py        # offline kill-switch test (exit code 0 = passed)
python generate_exports.py     # regenerate the sample notices in exports/
```

## Offline execution

Nothing in the core path calls a network service: the dataset, models, metadata, bed-capacity table and notice
templates are local files, and notices are produced from deterministic templates, not an LLM. Streamlit's usage
statistics are switched off in `.streamlit/config.toml`.

Two ways to demonstrate it:

1. **Automated kill-switch:** `python offline_check.py` replaces Python's socket connect and DNS functions with
   ones that raise, then runs forecasting (both horizons), allocation at 100/60/30% stock, routing, the simulator and
   all four dispatch formats for three different weeks, checking every invariant. The report is written to
   `exports/offline_check_report.txt`. The same test is a button on the **System / Offline Status** page and a pytest case.
2. **Physical test:** start `streamlit run app.py`, switch off Wi-Fi, and use every page. The sidebar badge changes
   to "Internet: OFFLINE, all features still work".

The hosted Streamlit Cloud URL obviously needs the internet to reach; offline operation applies to a local run.

## SMS delivery with TextBee (optional)

The Dispatch page can send each ward's SMS notice for real through [TextBee](https://textbee.dev), an SMS gateway
that sends from an Android phone running the TextBee app. It is optional: without a key the app generates and exports
notices exactly as before, and the offline guarantee is unchanged (the core never imports the gateway).

1. In the TextBee dashboard, add your Android phone and copy the API key (and the device ID if you have several phones).
2. Create `.streamlit/secrets.toml` in the project folder (it is git-ignored, never commit it):

   ```toml
   TEXTBEE_API_KEY = "paste-your-key-here"
   TEXTBEE_DEVICE_ID = "optional-device-id"
   ```

   On Streamlit Cloud, paste the same lines into the app's **Settings → Secrets** instead.
3. Copy `data/ward_contacts.example.csv` to `data/ward_contacts.csv` and fill in each ward's contact and mobile number
   (01XXXXXXXXX or +8801XXXXXXXXX). This file is git-ignored because it holds personal phone numbers. You can also type
   numbers directly in the Dispatch page.
4. Restart the app, open **Dispatch → SMS**, check the numbers, tick the confirmation box and press **Send**.

What the app reports: "Accepted by TextBee" means the gateway queued the message on the phone. Delivery is confirmed
in the TextBee dashboard; the app never claims a message was delivered. If the internet is down or the key is wrong,
the send fails with a clear message and nothing else is affected. Test with your own number first. Normal SMS charges
and TextBee plan limits apply.

## Dashboard pages

Navigation sits in the top bar, in three groups; the sidebar holds only the scenario controls (forecast week,
horizon, stock %, crews) with demand basis, policy, priority weight and city filter under *Advanced settings*. Every
page opens with a row of chips summarising the active scenario.

- **Plan → Overview**: deficit alert, four headline numbers (projected cases, High/Critical wards, wards short of
  supplies, patients without a bed) and tabs for supplies, cities and the top 10 priority wards.
- **Plan → Ward forecast** (Phase 1): 2- and 4-week forecast with risk tier and range, rainfall scenario slider,
  driver chart, recent weather and the all-ward ranking with CSV download.
- **Respond → Allocation**: supply cards, a supply selector, a priority-ordered chart of allocated vs shortfall
  (top 15 / 30 / all), a ward table with fill bars and a "only wards with a shortfall" filter, CSV export.
- **Respond → Bed routing**: city bed pools with utilisation bars, transfers, ward deficits and headroom (wards with
  activity by default), and the editable capacity table.
- **Respond → Simulator**: set-up, crew deployment editor (allocation engine, optimised or empty start) and results
  side by side, then the ROI ranking.
- **Respond → Dispatch**: SMS and WhatsApp cards, printable brief preview, downloads (TXT, HTML, PDF, CSV).
- **System → Accuracy**: MAE, RMSE, R² against persistence, tier accuracy, actual vs predicted, resource rates.
- **System → Offline status**: local component checks, internet probe and the one-click offline self-test.

The default week, 2024-08-12, is a held-out test week chosen because it has a mix of risk tiers and some bed
overflow, which makes every module visible.

## Dataset

`data/bangladesh_dengue_onsite.csv` is the supplied onsite file, copied unchanged: 31,320 rows, 15 columns,
60 wards in 5 cities (Dhaka North 20, Dhaka South 20, Chattogram 10, Gazipur 5, Narayanganj 5), weekly from
2016-01-04 to 2025-12-29, no missing values and no duplicate rows. `src/data_processing.py` validates schema, dates,
city/ward structure, numeric types, negatives and duplicate (date, ward) keys on every load.

Its first 12 columns are identical, value for value, to the Phase 1 file `data/dengue_raw.csv` (kept for reference).
The three new columns, `saline_bags_needed`, `diagnostic_kits_needed` and `hospital_beds_required`, turned out to
be exact deterministic functions of the same week's `dengue_cases`: each case count always maps to the same value,
about 2.38 bags, 1.16 kits and 0.30 beds per case with rounding. We therefore fit one rate per resource on the
training years and apply it to forecast cases (see ARCHITECTURE.md). Resource columns are never model inputs.

## Models and validation

Two Random Forests (100 trees, depth 12, min 5 samples per leaf) predict cases 2 and 4 weeks after the origin week
from rainfall this week and 1-4 weeks ago, 4-week rain total, 2- and 4-week mean temperature and humidity, ward
density, water-logging risk, sanitation and month. Validation is chronological: origin weeks before 2024-01-01 train
the model, 2024-2025 is held out.

| Horizon | MAE | RMSE | R² | Persistence MAE | Guess-the-average MAE |
|---|---|---|---|---|---|
| 2 weeks | 1.119 | 2.225 | 0.672 | 1.691 | 3.135 |
| 4 weeks | 1.324 | 2.538 | 0.579 | 2.136 | 3.143 |

Exact risk tier correct: 84.7% (2 weeks), 82.9% (4 weeks). High or Critical test weeks flagged Medium or above:
100% at 2 weeks and 90.4% at 4 weeks (447 such ward-weeks). The model under-predicts the largest peaks, so the
dashboard offers a **Cautious (P90)** demand basis that plans for the 90th percentile across the forest's trees.

Per-case resource rates fitted on 2016-2023 reproduce the resource columns on 2024-2025 exactly for saline and beds
and in 99.97% of rows for kits, so planning error comes almost entirely from the case forecast.

## Assumptions and limitations

- **Bed capacity is a demo assumption.** The dataset has none. `data/ward_bed_capacity.csv` sets each city's pool
  to the 95th percentile of its weekly bed demand in 2016-2023 and splits it by population-density share. It is
  labelled in the file and the UI, editable in the dashboard, and must be replaced with verified hospital data.
- **Intervention effectiveness is an assumption, not a measured effect.** The dataset contains no spraying or
  larviciding records. The simulator applies an explicit, adjustable effect curve to the ML forecast (default: at
  most 40% reduction, saturating with about 2 crews, half the effect visible by 2 weeks). Results are scenarios.
- **Priority weights, crew needs per tier and the stock definition** (percentage of total forecast demand) are
  configurable system assumptions in `src/config.py`, not official public-health policy.
- Forecasts come from one dataset and one chronological split; they show the method works on this data, not that it
  is validated on real outbreaks. Dates inside the dataset are a replay; the newest week is a genuine forecast.
- SMS can be sent through TextBee when configured (optional, needs internet); WhatsApp messages and briefs are
  generated and exported, not sent.
- Routing has no road-distance data, so "lowest burden" means most free beds in the same city.

## Repository layout

| Path | Purpose |
|---|---|
| `app.py` | Streamlit dashboard (8 pages) |
| `src/config.py` | Paths and every configurable assumption |
| `src/data_processing.py` | Load and validate the dataset |
| `src/features.py` | Per-ward lag and rolling features, 2- and 4-week targets (Phase 1) |
| `src/train.py` | Chronological training, metrics, resource rates, demo capacity table |
| `src/predict.py` | Model loading, risk tiers, ranges, driver impacts, all-ward forecasts |
| `src/resource_demand.py` | Per-case rate fitting and demand from forecast cases |
| `src/resource_allocation.py` | Priority score, scarcity allocation, crew assignment |
| `src/hospital_routing.py` | Intra-city overflow routing and invariant checks |
| `src/intervention_simulator.py` | Counterfactual crew simulator, ROI and optimiser |
| `src/dispatch_generator.py` | SMS, WhatsApp, HTML and PDF notices |
| `src/pipeline.py` | End-to-end chain used everywhere |
| `src/system_status.py` | Local component checks and internet probe |
| `integrations/textbee.py` | Optional SMS sending through TextBee (only used when an officer confirms a send) |
| `data/ward_contacts.example.csv` | Template for ward contact numbers; copy to the git-ignored `data/ward_contacts.csv` |
| `offline_check.py` | Offline kill-switch test |
| `generate_exports.py` | Writes the sample notices in `exports/` |
| `tests/` | 57 pytest tests |
| `exports/` | Sample SMS, WhatsApp, HTML/PDF brief, plan CSVs, offline report |
| `models/` | `model_2w.pkl`, `model_4w.pkl`, `meta.json` |
| `ARCHITECTURE.md`, `TECHNICAL_QA.md` | Design document and prepared answers for judges |

## AI disclosure and external services

- **AI assistants used:** Claude (Anthropic) for code, data analysis, tests and documentation in both phases. The
  team reviewed and directed the work and is responsible for it.
- **External APIs at runtime:** none for the core system. No LLM or weather API is used. The only optional
  external call is TextBee SMS sending, made only when an officer confirms a send on the Dispatch page.
- **Other services:** Google Colab (Phase 1 development), GitHub (hosting), Streamlit Community Cloud (deployment).
- **Libraries:** streamlit, pandas, numpy, scikit-learn, joblib, fpdf2 (PDF briefs, optional), pytest (tests).

## Team

Asad Uz Zaman (242002712)

Junaid Siddique (242002212)

Mohammad Fahim (242002112)
