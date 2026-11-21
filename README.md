# Dengue early-warning dashboard

Predicts weekly dengue cases and a risk tier (Low / Medium / High / Critical) for 60 wards in Dhaka North,
Dhaka South, Chattogram, Gazipur and Narayanganj, **2 and 4 weeks ahead**, using lagged rainfall,
temperature and humidity plus ward vulnerability (density, water-logging risk, sanitation).

EDU AI Engineering Hackathon 2026, preliminary round: "AI for Urban Dengue Outbreak".

**Live demo:** _paste your Streamlit URL here_
**Demo video:** _paste your video link here_

## Run it locally (about 2 minutes)

```bash
git clone <YOUR-REPO-URL>
cd dengue-early-warning
pip install -r requirements.txt
python src/train.py          # optional: trains both models in ~20 s and prints MAE/RMSE
streamlit run app.py
```

Open http://localhost:8501. If `models/` is empty or was saved by a different scikit-learn version, the app
retrains automatically on first launch (about 20 seconds), so `python src/train.py` is optional.

Run in Google Colab: upload the project, `pip install -r requirements.txt`, `python src/train.py`, then use a
tunnel such as `npx localtunnel --port 8501` after `streamlit run app.py &`.

## What is in the repo

| Path | Purpose |
|---|---|
| `data/dengue_raw.csv` | Organizer dataset: 60 wards x 522 weeks (2016-2025), unchanged |
| `src/features.py` | Builds per-ward multi-week lag features and the 2-week / 4-week targets |
| `src/train.py` | Chronological split, trains two Random Forests, saves models, tier cut-offs and metrics |
| `src/predict.py` | Model loading, risk tiers, prediction range, per-forecast driver breakdown |
| `app.py` | Streamlit dashboard (ward forecast, all-ward ranking, accuracy tab) |
| `models/` | Serialized models (`model_2w.pkl`, `model_4w.pkl`) and `meta.json` |
| `ARCHITECTURE.md` | Data flow diagram, validation split, model choice, cost controls |

## Features of the dashboard

- Pick a city, ward, week of weather data and see the 2-week and 4-week forecast, risk tier and likely range.
- Driver chart: which inputs push this forecast up or down versus a typical week and ward.
- Rainfall scenario slider (what if rain doubles?).
- All-ward risk ranking and per-city tier counts, with CSV download.
- Accuracy tab: MAE / RMSE on held-out 2024-2025 weeks, tier accuracy and an actual-vs-predicted chart.

## Results (trained on 2016-2023, tested on 2024-2025)

| Horizon | MAE (cases/week) | RMSE | Guess-the-average MAE |
|---|---|---|---|
| 2 weeks | 1.12 | 2.23 | 3.14 |
| 4 weeks | 1.32 | 2.54 | 3.14 |

Exact risk tier correct: 85% (2 weeks), 83% (4 weeks). Every High or Critical week in the test period was
flagged Medium or above. The model tends to under-predict the largest peaks.

## AI disclosure and external services

- **AI assistants used:** Claude (Anthropic) for code, documentation and review. _Edit this list so it names every AI tool your team used._
- **External APIs at runtime:** none. No LLM or web API is called when the app runs.
- **Other services:** Google Colab (development), GitHub (hosting), Streamlit Community Cloud (deployment, if used).
- **Libraries:** streamlit, pandas, numpy, scikit-learn, joblib.

## Team

Asad Uz Zaman (242002712)
Junaid Siddique (242002212)
Mohammad Fahim (242002112)
