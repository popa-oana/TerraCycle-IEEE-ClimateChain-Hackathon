# Day 6C.2B — Corrected chronological evaluation (before/after)

> **Reanalysis of the previously inspected test set, not a fresh
> independent benchmark.** Kernel, hyperparameters, chronological split
> and persistence baseline are unchanged; only the time origin used for
> held-out predictions is fixed.

Generated: 2026-10-20T06:55:12Z

| Parcel | N train | N test | GPR MAE (orig) | GPR MAE (corr) | GPR RMSE (orig) | GPR RMSE (corr) | Baseline MAE (corr) | Coverage 95% (orig) | Coverage 95% (corr) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| parcel_01 | 21 | 8 | 0.6183 | 0.2169 | 0.6313 | 0.2225 | 0.0320 | 0.00% | 100.00% |
| parcel_02 | 47 | 16 | 0.1038 | 0.1025 | 0.1108 | 0.1169 | 0.0179 | 25.00% | 100.00% |
| parcel_03 | 46 | 16 | 0.2332 | 0.0959 | 0.2446 | 0.1142 | 0.0310 | 0.00% | 100.00% |
| parcel_04 | 45 | 15 | 0.5401 | 0.1097 | 0.5407 | 0.1197 | 0.0382 | 0.00% | 100.00% |

GPR better than persistence on the corrected run: parcel_01=NO, parcel_02=NO, parcel_03=NO, parcel_04=NO
