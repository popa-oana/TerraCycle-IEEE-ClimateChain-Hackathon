# Day 6C.2A — Diagnostic report: why GPR performs poorly

**Date:** 2026-10-20
**Scope:** `backend/ml/trajectory_model.py`, `backend/ml/trajectory_evaluation.py`,
`scripts/train_trajectory_models.py`, `scripts/evaluate_trajectory_models.py`,
`data/ml/trajectory_evaluation.json`, `data/ml/trajectory_test_predictions.csv`.

**Hard constraints respected**

- The original Day 6C.2 evaluation outputs were **not modified**.
- The held-out test observations were **never used** for fitting, scaling,
  hyperparameter selection, or candidate selection.
- The two alternative GPR configurations were chosen **before** any validation
  result was inspected (see "Candidate selection" below).
- No final test scores were produced; all numbers below come from the original
  outputs or from rolling validation restricted to the original training period.

---

## 1. Actual causes found

The poor GPR performance is **primarily a software/configuration defect**, not
evidence that Gaussian processes cannot model this signal.

### 1.1 Root cause: test features are re-zeroed to the wrong time origin

`observations_to_training_data()` computes elapsed days as
`(timestamps - timestamps.min())`. In `trajectory_evaluation.evaluate_parcel`
it is called **twice, once on the training subset and once on the test subset**:

```python
train_elapsed, _ = observations_to_training_data(train_ndvi, train_ts)
test_elapsed,  _ = observations_to_training_data(test_ndvi,  test_ts)
```

Because the test subset is passed on its own, its minimum becomes the test
origin, so every test point is re-zeroed. The model — fitted on training
elapsed days `[0, ~150]` — is then asked to predict at test elapsed days
`[0, ~60]`, i.e. **early-season coordinates**, even though the test
observations actually occur ~155–240 days after the training start.

Measured mismatch (from `diagnostic_manifest.json` → `split_audit`):

| Parcel  | train elapsed (d) | buggy test elapsed (d) | correct test offset (d) | min coordinate gap to a training point (d) |
|---------|-------------------|------------------------|-------------------------|--------------------------------------------|
| parcel_01 | 0 – 140 | 0 – 60 | 155 – 215 | **0.0000** |
| parcel_02 | 0 – 175 | 0 – 57 | 183 – 240 | **0.0000** |
| parcel_03 | 0 – 165 | 0 – 55 | 167 – 222 | **0.0000** |
| parcel_04 | 0 – 153 | 0 – 65 | 155 – 215 | **0.0000** |

A minimum coordinate gap of exactly **0.0 days** means several test query points
land *on top of* training observations. Consequences, all visible in
`trajectory_test_predictions.csv`:

- parcel_01 first test point (2024-08-25) is predicted as `0.853875` with
  `std = 4e-05`. The training observation on 2024-03-23 has `ndvi_mean =
  0.853875`. The model is literally reproducing a training value.
- Because the query coordinates are inside the training range, the GPR is
  *interpolating*, not extrapolating — yet the reported MAE is 0.10–0.62,
  far worse than interpolation should be.

This is the dominant cause of the observed test errors and of the 0–25%
coverage: the model predicts early-season NDVI at the wrong coordinates.

### 1.2 Secondary cause: WhiteKernel noise collapses to zero

The fitted kernels on the original training period (`diagnostic_manifest.json`
→ `kernel_audit`):

| Parcel  | Matern length scale (d) | WhiteKernel noise level | y mean | y std |
|---------|-------------------------|-------------------------|--------|-------|
| parcel_01 | 26.7 | **8.8e-09** | 0.472 | 0.302 |
| parcel_02 | 43.7 | 3.3e-02 | 0.479 | 0.208 |
| parcel_03 | 30.6 | 1.2e-02 | 0.475 | 0.172 |
| parcel_04 | 31.3 | 4.9e-03 | 0.450 | 0.243 |

For parcel_01 the optimizer drove the noise level to essentially the lower
bound (`1e-10`). With near-zero noise, predictive intervals shrink to almost
nothing — which is exactly why four parcel_01 intervals have width `< 1e-3`.
The WhiteKernel bounds `(1e-10, 1e1)` allow this collapse; the existing
configuration does not prevent it. Note the model also relies on sklearn's
default `alpha=1e-10` jitter and `normalize_y=True` (the latter rescales both
the mean and the std correctly, so it is not itself the problem).

### 1.3 Contributing cause: the test period is a different seasonal phase

Even with correct alignment, the test period (late Aug – late Oct) is the
post-peak / senescence phase, whereas training covers the growth phase
(Mar – Aug). The persistence baseline is strong on the test set
(MAE 0.018–0.038) precisely because the last training value is already low and
close to the late-season values. A smooth GP fitted on the rising phase has no
mechanism to anticipate the downturn, so genuine late-season extrapolation
would still be hard. This is a real difficulty, but it is **not** the main
reason for the current numbers.

### 1.4 What is NOT wrong

- **Time units are correct.** `observations_to_training_data` converts
  nanoseconds → seconds → days correctly.
- **Chronological split is valid.** Train indices precede test indices and the
  index sets are disjoint (existing tests cover this).
- **Test NDVI values are genuinely unseen** in the sense that no test row is in
  the training set. The defect is in the *feature encoding* of the test rows,
  not in target leakage.
- **The predictive-std formula is technically correct** (see §4).

---

## 2. Small controlled comparison (rolling-origin validation)

Method: for each parcel, take **only** the original training period (the first
75% by count, 21/47/46/45 observations). Run an expanding-window,
1-step-ahead rolling validation: fold `k` fits on observations `[0, k)` and
predicts observation `k`. The elapsed-day origin is the fold's first training
observation; targets are never re-zeroed. 127 folds total.

Candidates (fixed before results):

1. `persistence` — last training NDVI.
2. `linear_trend` — least-squares straight line on elapsed days.
3. `gpr_existing` — the exact `trajectory_model.build_model()` configuration.
4. `gpr_smooth` — Matern(ν=2.5, ℓ=60 d) + WhiteKernel(0.05). *(Alternative A,
   chosen to test overfitting/overconfidence: smoother kernel, larger noise
   floor.)*
5. `gpr_periodic` — Matern(ν=1.5, ℓ=30 d) + ExpSineSquared(period 180 d) +
   WhiteKernel(0.01). *(Alternative B, chosen to test whether explicit
   seasonal structure helps.)*

### Pooled validation metrics (original training period)

| Candidate      | Folds | MAE    | RMSE   | mean std | 95% coverage |
|----------------|-------|--------|--------|----------|--------------|
| persistence    | 127   | 0.0390 | 0.0557 | —        | —            |
| linear_trend   | 127   | 0.1520 | 0.1895 | —        | —            |
| gpr_existing   | 127   | 0.0476 | 0.0669 | 0.0486   | 86.6%        |
| gpr_smooth     | 127   | 0.0489 | 0.0691 | 0.0474   | 85.0%        |
| gpr_periodic   | 127   | 0.0490 | 0.0733 | 0.0468   | 83.5%        |

### Per-parcel validation MAE

| Parcel  | persistence | linear_trend | gpr_existing | gpr_smooth | gpr_periodic |
|---------|-------------|--------------|--------------|------------|--------------|
| parcel_01 | **0.0485** | 0.1482 | 0.0782 | 0.0939 | 0.0782 |
| parcel_02 | **0.0481** | 0.1907 | 0.0541 | 0.0513 | 0.0538 |
| parcel_03 | **0.0346** | 0.1562 | 0.0388 | 0.0405 | 0.0393 |
| parcel_04 | **0.0306** | 0.1081 | 0.0392 | 0.0394 | 0.0435 |

**Answer to "does any alternative consistently beat persistence on validation?"
No.** Persistence has the lowest MAE in all four parcels and pooled. The three
GPR configurations are close to each other (MAE 0.0476–0.0490) and all slightly
worse than persistence. Linear trend is far worse, as expected on a curved
seasonal signal.

Note the validation MAE of the GPRs (≈0.048) is an order of magnitude smaller
than their original test MAE (0.10–0.62). That gap is the signature of the
feature-alignment defect, not of a fundamentally unusable model.

---

## 3. Uncertainty investigation

`predict_with_uncertainty` returns `model.predict(X, return_std=True)`. For
`normalize_y=True`, sklearn computes the predictive variance in the normalized
space and rescales it by `_y_train_std²`. That is the standard, correct GPR
predictive standard deviation (it includes the WhiteKernel noise term), so the
**calculation itself is technically correct**.

The nominal 95% intervals are narrow for two concrete reasons:

1. **Wrong coordinates (dominant).** parcel_01 has 4 of 8 intervals narrower
   than `1e-3`, with `std ≈ 4e-05`. Those test points sit exactly on training
   coordinates (`min coordinate gap = 0.0`), so the posterior variance collapses
   to the noise floor. The model is maximally confident and maximally wrong.

2. **Noise collapse (secondary).** parcel_01's fitted WhiteKernel is `8.8e-09`,
   so even off-training points have tiny intervals.

On the original test set, the predicted std (0.024–0.046) is far smaller than
the actual absolute error (0.104–0.618), so coverage is 0–25%. On the
*training-period* rolling validation, by contrast, coverage is 83–87% and mean
std (≈0.047) is close to the actual MAE (≈0.048). **This is the key evidence
that the model is well-behaved in-distribution and that the test failure comes
from the coordinate defect plus the seasonal phase shift.**

**Cause ranking:** software/configuration defect (feature origin) ≫ insufficient
noise modelling > seasonal distribution shift / extrapolation. There is
sufficient evidence to distinguish these.

---

## 4. Is the uncertainty calculation technically correct?

Yes. `GaussianProcessRegressor.predict(..., return_std=True)` implements the
standard GPR predictive variance and correctly de-normalizes it when
`normalize_y=True`. The interval width equals `2·1.96·std` and is symmetric
(both asserted by existing tests). The problem is not the formula; it is the
inputs to the formula:

- the query coordinates are wrong (re-zeroed), and
- the fitted noise is allowed to collapse to ~0.

So the intervals are *arithmetically correct but not calibrated*, and they must
not be interpreted as validated 95% intervals on the original test set. No
artificial inflation was applied.

---

## 5. Recommended final model

**No GPR configuration is supported as a final model by the current evidence.**
On rolling validation over the training period, persistence is the best and
simplest candidate, and it also wins on the original test set. The GPRs are
close but never better, and their test failure is dominated by a fixable
encoding bug. The honest recommendation is:

- Keep the **rule-based verifier** as the decision mechanism; it is unaffected.
- Treat the GPR as an **experimental** module until the origin bug is fixed and
  a corrected evaluation is run.
- If a regression model is later wanted, persistence (or a seasonal
  persistence-with-drift variant) is the defensible baseline on this data.

---

## 6. Is improving GPR worthwhile?

Partly. The GPR is not fundamentally broken: on in-distribution rolling
validation it reaches MAE 0.048 and 83–87% interval coverage — in the same
ballpark as the other candidates, though still slightly behind persistence.
Improving it is worthwhile **only** after:

1. fixing the test-feature origin so targets are measured from the training
   origin, and
2. bounding the WhiteKernel noise away from `1e-10` so intervals cannot collapse.

Even then, with a single historical growing season, seasonal extrapolation
remains genuinely hard, and persistence is likely to remain competitive. Given
the small test sample sizes (8–16 points), no configuration change should be
adopted without a corrected, honest evaluation. The highest-value fix is the
bug, not a new kernel.

---

## 7. Reproduction

From the repository root (Windows / PowerShell):

```powershell
# 1. Run the diagnostic (writes to data/ml/diagnostics/, does NOT touch the
#    original evaluation outputs).
.\.venv\Scripts\python.exe scripts\diagnose_trajectory_models.py

# 2. Run the relevant tests (new diagnostics tests + existing trajectory tests).
.\.venv\Scripts\python.exe -m pytest tests\test_trajectory_diagnostics.py `
    tests\test_trajectory_model.py tests\test_trajectory_evaluation.py -q

# 3. Re-run the original evaluation (unchanged; for reference only).
.\.venv\Scripts\python.exe scripts\evaluate_trajectory_models.py
```

Note: `tests/test_hashing.py` fails to collect because the optional `eth_abi`
dependency is not installed in `.venv`. This is pre-existing and unrelated to
the ML work; the rest of the suite passes:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/test_hashing.py
# 299 passed
```

### Artifacts

| File | Contents |
|------|----------|
| `data/ml/diagnostics/diagnostic_manifest.json` | Split audit, kernel audit, validation summary, uncertainty audit |
| `data/ml/diagnostics/validation_summary.csv` | MAE / RMSE / std / coverage per candidate and per parcel |
| `data/ml/diagnostics/validation_folds.csv` | One row per fold per candidate |
| `data/ml/diagnostics/REPORT.md` | This report |

### New source files

| File | Purpose |
|------|---------|
| `backend/ml/trajectory_diagnostics.py` | Diagnostic utilities (fixed origin, rolling validation, aggregation) |
| `scripts/diagnose_trajectory_models.py` | Runner for Steps 1–3 |
| `tests/test_trajectory_diagnostics.py` | Tests for the diagnostic module |
