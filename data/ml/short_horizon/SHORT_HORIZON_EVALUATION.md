# Day 6C.4 — Short-Horizon NDVI Forecasting Evaluation

> **EXPERIMENTAL rolling backtest on previously inspected data.**
> Not a fresh independent benchmark. Results do not establish
> validated forecasting performance, agronomic compliance,
> certification, or blockchain settlement eligibility.

Generated: 2026-10-20T07:58:44Z
Input: C:\Users\Crenguta Ciobanica\Desktop\TerraCycle\TerraCycle-IEEE-ClimateChain-Hackathon\data\features\observations_clean_4parcels.csv
Min history: 8
Linear trend window: 10

## Per-Parcel Overall Metrics (MAE)

| Parcel | N obs | N preds | Persistence | Linear Trend | GPR | Recommended |
|---|---:|---:|---:|---:|---:|---|
| parcel_01 | 29 | 21 | 0.0409 | 0.1050 | 0.0683 | persistence |
| parcel_02 | 63 | 55 | 0.0385 | 0.0534 | 0.0434 | persistence |
| parcel_03 | 62 | 54 | 0.0285 | 0.0404 | 0.0319 | persistence |
| parcel_04 | 60 | 52 | 0.0268 | 0.0404 | 0.0337 | persistence |

## Metrics by Prediction Horizon Band

### parcel_01

| Band | N | Persistence MAE | Linear MAE | GPR MAE | GPR Mean Std | GPR 95% Coverage |
|---|---:|---:|---:|---:|---:|---:|
| 0-7_days | 15 | 0.0486 | 0.1299 | 0.0717 | 0.0706 | 80.00% |
| 8-14_days | 4 | 0.0140 | 0.0405 | 0.0449 | 0.1283 | 100.00% |
| 15+_days | 2 | 0.0366 | 0.0473 | 0.0893 | 0.1858 | 100.00% |

### parcel_02

| Band | N | Persistence MAE | Linear MAE | GPR MAE | GPR Mean Std | GPR 95% Coverage |
|---|---:|---:|---:|---:|---:|---:|
| 0-7_days | 51 | 0.0360 | 0.0508 | 0.0406 | 0.0570 | 96.08% |
| 8-14_days | 4 | 0.0703 | 0.0858 | 0.0784 | 0.0743 | 75.00% |
| 15+_days | 0 | N/A | N/A | N/A | N/A | N/A |

### parcel_03

| Band | N | Persistence MAE | Linear MAE | GPR MAE | GPR Mean Std | GPR 95% Coverage |
|---|---:|---:|---:|---:|---:|---:|
| 0-7_days | 50 | 0.0258 | 0.0407 | 0.0276 | 0.0343 | 90.00% |
| 8-14_days | 4 | 0.0619 | 0.0375 | 0.0855 | 0.0533 | 50.00% |
| 15+_days | 0 | N/A | N/A | N/A | N/A | N/A |

### parcel_04

| Band | N | Persistence MAE | Linear MAE | GPR MAE | GPR Mean Std | GPR 95% Coverage |
|---|---:|---:|---:|---:|---:|---:|
| 0-7_days | 49 | 0.0268 | 0.0414 | 0.0344 | 0.0406 | 87.76% |
| 8-14_days | 3 | 0.0278 | 0.0236 | 0.0214 | 0.0703 | 100.00% |
| 15+_days | 0 | N/A | N/A | N/A | N/A | N/A |

## Presentation Recommendations

| Parcel | Display | Recommended Model | Reason |
|---|---|---|---|
| parcel_01 | True | persistence | 21 predictions evaluated |
| parcel_02 | True | persistence | 55 predictions evaluated |
| parcel_03 | True | persistence | 54 predictions evaluated |
| parcel_04 | True | persistence | 52 predictions evaluated |

## Uncertainty-Horizon Correlation

- parcel_01: (computed in JSON output)
- parcel_02: (computed in JSON output)
- parcel_03: (computed in JSON output)
- parcel_04: (computed in JSON output)

## Conclusion

Average MAE across parcels (overall):
- Persistence: 0.0337
- Linear Trend: 0.0598
- GPR: 0.0443

**Persistence remains the best performer on average.**
GPR MAE is 31.6% higher than persistence.

**Recommendation for demo:** Use persistence baseline for any displayed
short-term NDVI predictions. GPR does not add measurable value for
this seasonal extrapolation task. All model outputs are experimental
and must carry explicit disclaimers.