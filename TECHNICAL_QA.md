# Technical Q&A preparation

Answers describe what is implemented and tested in this repository. File references point to the code that does it.

### 1. How does the dengue forecasting model work?

Two Random Forest regressors (`src/train.py`), one predicting a ward's weekly cases 2 weeks after the origin week and
one 4 weeks after. Inputs per ward-week: rainfall this week and 1-4 weeks ago, 4-week rain total, 2- and 4-week
mean temperature and humidity, population density, water-logging risk, sanitation score and month. Each forest has
100 trees (depth 12, at least 5 samples per leaf); the forecast is the mean of the trees and the 10th-90th
percentile across trees gives a likely range. The forecast is mapped to Low / Medium / High / Critical using
cut-offs from the training years (4, 10, 13 cases a week). On 2024-2025 held-out weeks: MAE 1.12 / 1.32 cases,
R² 0.67 / 0.58 for 2 / 4 weeks.

### 2. Why are rainfall lags important?

Rain creates standing water; mosquito eggs need roughly one to two weeks to become biting adults, and infected
people then take several days to show symptoms. So the rain that matters for cases in two weeks fell several weeks
earlier. Giving the model rain 0-4 weeks back plus a 4-week total lets it learn that delay instead of reacting to
today's rain. The Ward Forecast page shows, for a given forecast, how much each lag pushes it up or down versus a
typical week (an approximation, not a causal effect).

### 3. How is data leakage prevented?

- Features at origin week *t* use only weeks ≤ *t* (backward shifts and trailing windows, computed within each ward).
- Chronological split: origin weeks before 2024-01-01 train, 2024-2025 test; no shuffling. One honest caveat: the
  last training rows (December 2023) have 2- and 4-week targets in early January 2024, a standard overlap in
  direct multi-step forecasting that affects at most 4 weeks.
- Tier cut-offs, driver baselines and resource rates come from training years only.
- `saline_bags_needed`, `diagnostic_kits_needed`, `hospital_beds_required` are never inputs; a test
  (`tests/test_pipeline_dispatch_offline.py`) asserts the feature list contains no resource column, no current
  case count and no target.

### 4. Why was the forecasting algorithm chosen?

In Phase 1 we compared six algorithms on the same features and chronological split. Tree ensembles clearly beat
Ridge regression (2-week MAE 1.53) and a single tree (1.27); the ensembles were within about 0.08 of each other
(random forest 1.12, extra trees 1.08, gradient boosting 1.08, Poisson boosting 1.04), so on one split none is a
clear winner. We kept the Random Forest because it models non-linear interactions (rain matters more in a crowded,
poorly drained ward) without scaling, handles many zero weeks, gives a spread across trees for free (used for the
range and the Cautious planning basis) and is easy to explain. It also beats persistence (2-week MAE 1.69,
4-week 2.14). Adding past case counts improved MAE by only about 0.01, so we kept weather-only inputs, which keep
working when case reports are late.

### 5. How does resource allocation work under scarcity?

`src/resource_allocation.py`. Demand per ward = forecast cases × a per-case rate fitted on training years (the
dataset's resource columns are an exact function of cases: about 2.38 saline bags, 1.16 kits, 0.30 beds per case).
Available stock per resource = floor(slider % × total demand over all 60 wards). With the default priority-weighted
policy each ward gets min(1, λ × priority) of its demand, λ found by bisection so the total equals stock exactly;
top-priority wards are filled first and completely, lower ones are reduced in proportion. Strict triage is the
alternative: fill in priority order until stock runs out. Whole units are assigned by largest remainder. Tests
prove allocations never exceed stock or demand, are never negative, and are identical for identical inputs. Any
ward below 100% of any supply is flagged CRITICAL SUPPLY DEFICIT. Crews are needed by tier (0/1/2/3) and dealt
round-robin by priority, never exceeding the total.

### 6. How is ward priority calculated?

priority = 0.7 × risk score + 0.3 × normalised population density (weights adjustable in the sidebar). Risk score:
Low 0, Medium ⅓, High ⅔, Critical 1. Density is min-max scaled over all 60 wards so it does not change when a city
filter is applied. Ties go to the higher forecast, then ward ID, so the ranking is deterministic. Risk reflects
expected burden; density reflects how quickly transmission and facility crowding escalate. These are configurable
system assumptions, not official policy, and a test checks that higher risk and higher density each raise priority.

### 7. How does bed routing guarantee intra-city transfers?

`src/hospital_routing.py` groups wards by city and runs the routing loop separately inside each group, so the only
candidate receivers a sender can ever see are wards of its own city. Within a city, the ward with the largest
deficit sends first, always to the ward with the most free beds, moving min(deficit, headroom) until it is cleared
or the city is full; leftovers are reported as unplaced and escalated. `check_routing_invariants()` asserts that
sender, receiver and transfer city are identical, that no receiver exceeds capacity and that demand = occupied beds
+ unplaced patients per city. A test gives a full city A and an empty city B and confirms nothing moves to B.
Capacities are a labelled demo assumption, because the dataset has none.

### 8. How does the intervention simulator estimate prevented cases?

`src/intervention_simulator.py`. It starts from the ML forecast for each ward at 2 and 4 weeks and applies an
explicit effect curve: E(n) = 0.40 × (1 − e^(−n/2)) for n crews (diminishing returns, zero for zero crews), times a
timing factor (0.5 of the effect by 2 weeks, all of it by 4 weeks). Prevented cases × the per-case rates give bed
and saline reductions; prevented cases ÷ crews is the ROI used for ranking. Officers set crews per ward or press
Optimise, which assigns each next crew to the ward with the largest marginal gain (optimal for this concave curve).
Deploying more crews than available is rejected.

### 9. Why is intervention effectiveness not a proven causal estimate?

The dataset has no record of where or when spraying or larviciding happened and no measured outcomes, so there is
nothing to learn an effect from; the 40% ceiling, 2-crew saturation and timing are assumptions shown on screen and
editable. We also tested using the forest itself as a causal engine (lowering rain and water-logging inputs): for
origin week 2025-09-01 at 4 weeks this *raised* forecasts in all 60 wards, because the forest learned seasonal
correlation, not mosquito biology. Proper estimation would need intervention logs and a design such as staggered
roll-out or matched control wards.

### 10. How does the system work offline?

Dataset, models, metadata and capacity table are local files; notices come from Python templates, not an LLM; no
module imports an HTTP client (a test checks this); Streamlit usage statistics are off. If the saved models are
incompatible they retrain locally. `python offline_check.py` disables socket connect and DNS for the process and
runs forecasting, allocation at 100/60/30% stock, routing, the simulator and all four dispatch formats for three
weeks and both horizons, verifying invariants (passes in about 3 seconds). The same test is a pytest case and a
button on the System Status page; physically, the app keeps working with Wi-Fi off and the sidebar badge switches
to "Offline · all core functions available".

### 11. How are dispatch notices generated?

`src/dispatch_generator.py` builds one structured notice per ward straight from the allocation and routing tables
(required / allocated / deficit for each supply, crews, capacity, transfers, unplaced patients) and derives the
actions with fixed rules. The same notice renders as SMS (compact), WhatsApp (bold markup, emoji risk marker),
printable HTML and PDF. A test checks for all 60 wards that every number in the notice equals the plan and that the
texts contain ward, city, risk, allocations, deficit flags and transfer instructions. Samples are in `exports/`.
Optionally, the SMS notices can be sent through TextBee (`integrations/textbee.py`): only after an officer
confirms, reported as "accepted by TextBee" rather than delivered, and isolated from the core so offline
operation is unaffected. WhatsApp sending is not implemented.

### 12. What are the dataset and model limitations?

- The data look generated rather than observed: resource columns are exact multiples of cases, and peaks are
  synchronised across wards; real data would be noisier.
- No hospital capacity, geography, intervention history or reporting delays in the data; capacity and effectiveness
  are labelled assumptions.
- The model under-predicts the largest peaks (exact tier 84.7% / 82.9%; at 4 weeks 90.4% of High/Critical weeks
  were flagged Medium or above), hence the Cautious (P90) demand basis.
- One chronological split on one dataset; no external validation on real outbreaks.
- Priority weights and crew needs are design choices that public-health officials should set.
