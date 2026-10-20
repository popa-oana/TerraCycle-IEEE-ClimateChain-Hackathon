# AI Insights Demo — Day 6C.3 (corrected GPR NDVI trajectories)

This document explains the **corrected** Gaussian Process Regression (GPR) NDVI
experiment for the TerraCycle Proof demo: what it does, what it does **not** do,
and how to show it to the jury. It is written for Oana (frontend) and for anyone
reviewing the demo, not as a scientific paper.

---

## 1. What the ML experiment does

For each of the four demo parcels, the experiment tries to **predict future
Sentinel-2 NDVI values from past ones**, using a small Gaussian Process
Regression model fitted only on that parcel's earlier observations.

- **Input:** genuine Sentinel-2 L2A NDVI measurements from
  `data/features/observations_clean_4parcels.csv`.
- **Split:** chronological — the first 75% of each parcel's observations train
  the model; the last 25% is held out and never used for fitting.
- **Prediction:** the held-out NDVI, with a predictive standard deviation.
- **Baseline:** persistence — simply repeat the last training value. This is the
  honest "no model" comparison.

This is an **experimental** regression module. It does **not** create compliance
labels, does **not** predict compliance verdicts, and does **not** decide
settlement.

---

## 2. Why genuine Sentinel-2 data

The charts and JSON use the real quality-approved observations from the four
demo parcels (Copernicus Data Space, Sentinel-2 L2A, NDVI =
`(B08 − B04) / (B08 + B04)`). Nothing is fabricated: every plotted observation is
a real measurement from the CSV. Missing dates are **not** interpolated and are
**not** shown as observed values.

---

## 3. How the model was evaluated

1. Parse and sort each parcel's observations by acquisition time (UTC).
2. Take the first 75% as training, the last 25% as a chronologically held-out
   test set.
3. Fit the GPR on the training observations only.
4. Predict the held-out observations and compare against the real values.
5. Compute MAE and RMSE for the GPR and for the persistence baseline.
6. Report how often the real held-out value falls inside the GPR's nominal 95%
   predictive interval.

The same evaluation runs for all four parcels. The code lives in
`backend/ml/trajectory_evaluation.py`; the corrected runner is
`scripts/evaluate_trajectory_models_corrected.py`.

---

## 4. What the time-origin bug was

During Day 6C.2 the evaluation converted timestamps to "days since the first
observation" **twice** — once for the training subset and once for the test
subset. Because the test subset was converted on its own, its first test date
was treated as day 0. The model, which had learned NDVI as a function of days
since the season start, was then asked to predict at **early-season
coordinates** (days 0–60) instead of the true held-out coordinates (days
155–240).

The result was meaningless: for parcel_01 the first test point was predicted as
`0.853875`, exactly the value of the very first training observation, with a
near-zero uncertainty. This was a software defect, not evidence that the model
was useless.

Day 6C.2B fixed it so that **training and prediction share one consistent time
origin** (the first training observation). The corrected evaluation is a
**reanalysis of the same previously inspected test set**, not a fresh
independent benchmark.

---

## 5. What the corrected results show

| Parcel | N train | N test | GPR MAE (orig) | GPR MAE (corr) | GPR RMSE (corr) | Persistence MAE (corr) | Coverage 95% (orig) | Coverage 95% (corr) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| parcel_01 | 21 | 8 | 0.6183 | 0.2169 | 0.2225 | **0.0320** | 0% | 100% |
| parcel_02 | 47 | 16 | 0.1038 | 0.1025 | 0.1169 | **0.0179** | 25% | 100% |
| parcel_03 | 46 | 16 | 0.2332 | 0.0959 | 0.1142 | **0.0310** | 0% | 100% |
| parcel_04 | 45 | 15 | 0.5401 | 0.1097 | 0.1197 | **0.0382** | 0% | 100% |

The corrected predictions are dramatically better than the buggy ones for
parcels 01, 03 and 04. The corrected intervals now cover every held-out point.

**Honest statement:** the GPR **still loses to persistence on all four parcels**
(bold column). The fix removed the catastrophic failure; it did not make the GP
a better forecaster here.

---

## 6. Why persistence still performs better

The training period (roughly March–August) is the **growing season**, when NDVI
rises. The held-out period (late August–October) is the **post-peak / senescence
phase**, when NDVI falls. A smooth GP fitted on the rising phase has no
mechanism to anticipate the downturn and reverts toward the training average
(~0.3–0.4). Persistence simply repeats the last observed value, which is already
low and therefore much closer to the late-season truth. This is genuine seasonal
extrapolation, and it is hard.

---

## 7. Why four parcels and one season limit conclusions

- **Four parcels** is far too few to estimate generalization; the parcels are
  also spatially close and share the same weather.
- **One growing season (2024)** means there is no way to separate "the model is
  weak" from "this season was unusual."
- The **held-out test sets are small** (8–16 points), so MAE/RMSE and the
  observed coverage are noisy.
- The shaded band is a **nominal, uncalibrated** GPR predictive interval. 100%
  observed coverage on 8–16 points is **not** proof of calibration and must not
  be described as a guaranteed 95% interval.

Therefore the ML experiment is presented as an **exploratory demonstration**,
not as a validated predictive product.

---

## 8. How Oana can display the charts or JSON

### Charts

Four PNG files, ready to embed in React or a slide deck:

```
data/ml/plots/parcel_01_trajectory.png
data/ml/plots/parcel_02_trajectory.png
data/ml/plots/parcel_03_trajectory.png
data/ml/plots/parcel_04_trajectory.png
```

Each chart shows:

- grey circles — all real Sentinel-2 NDVI observations;
- blue circles — training observations;
- green circles — chronologically held-out test observations;
- dashed vertical line — the train/test split;
- red line with markers — corrected GPR prediction for the held-out period;
- dashed orange line — persistence baseline;
- pink shaded band — the **nominal, uncalibrated** GPR predictive interval
  (labelled on the chart as *not* guaranteed 95% coverage);
- a text box with GPR and baseline MAE/RMSE.

### JSON

`data/ml/ai_insights.json` is a standalone, frontend-ready document. It is
**independent of the verifier API response schema** and contains, per parcel:
genuine observation timestamps/NDVI, the split date, corrected held-out GPR
predictions and predictive standard deviations, persistence predictions, MAE and
RMSE for both models, observed interval coverage, a plain-English explanation and
a limitations list. All timestamps are UTC ISO-8601 with a `Z` suffix.

Example consumption in React (fetch the file, no backend change required):

```tsx
type ParcelInsight = {
  parcel_id: string;
  observations: { timestamp: string; ndvi: number }[];
  split_date: string;
  gpr_predictions: {
    timestamp: string; predicted_ndvi: number;
    predicted_std: number; lower_95: number; upper_95: number;
  }[];
  persistence_predictions: { timestamp: string; predicted_ndvi: number }[];
  metrics: {
    gpr_mae: number; gpr_rmse: number;
    baseline_mae: number; baseline_rmse: number;
    observed_interval_coverage: number;
    gpr_better_than_persistence: boolean;
  };
  explanation: string;
  limitations: string[];
};
```

Always render the disclaimer that the band is nominal/uncalibrated and that
persistence outperformed the GP.

---

## 9. Why the ML experiment cannot authorize blockchain settlement

The NDVI experiment describes **vegetation signal over time**. It does not
verify the agricultural practice, does not prove the absence of herbicides, and
does not constitute organic certification. Settlement in TerraCycle Proof is
authorized only by an **authorized verifier** who signs an EIP-712 result and by
the escrow contract after backend receipt verification. The ML charts and JSON
are **informational only** and must never be wired into the settlement path.

---

## 10. Regeneration commands

Run from the repository root (Windows / PowerShell):

```powershell
# 1. (Re)generate the corrected evaluation from the fixed implementation
#    (same kernel, same split, same persistence baseline).
.\.venv\Scripts\python.exe scripts\evaluate_trajectory_models_corrected.py

# 2. Generate the four charts and the frontend-ready JSON.
.\.venv\Scripts\python.exe scripts\generate_ml_insights.py

# 3. Run the focused visualization/export tests.
.\.venv\Scripts\python.exe -m pytest tests\test_ml_insights.py -q

# 4. Run the whole suite (tests/test_hashing.py is excluded because the
#    optional eth_abi dependency is not installed in .venv; it is unrelated).
.\.venv\Scripts\python.exe -m pytest tests/ -q --ignore=tests/test_hashing.py
```

Notes:

- `generate_ml_insights.py` reads only the **corrected** evaluation outputs; if
  they are missing or incomplete it regenerates them with the corrected
  implementation (no model or split change).
- The original Day 6C.2 outputs (`data/ml/trajectory_evaluation.json`,
  `data/ml/trajectory_test_predictions.csv`) are **never overwritten**.
- No model is retrained or tuned by the visualization script.

---

## 11. Known scientific limitations (summary)

1. Four parcels and one historical season (2024) only.
2. Small held-out test sets (8–16 observations) → noisy error estimates.
3. Predicting late-season NDVI from an early-season model is genuine, hard
   extrapolation.
4. Persistence outperformed the GP on every parcel.
5. The shaded band is a nominal, uncalibrated predictive interval; observed
   coverage does not prove calibration.
6. NDVI prediction says nothing about compliance, certification, or settlement.
