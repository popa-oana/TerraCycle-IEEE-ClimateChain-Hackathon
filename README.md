# TerraCycle---IEEE-ClimateChain-Hackathon

Setup: see SETUP.md
Contributing: see CONTRIBUTING.md

## Repository layout

```text
├── backend/     FastAPI backend, DB models + migrations, ML verifier (backend/ml/)
├── data/        Parcel GeoJSON, NDVI exports, features, labels
├── docs/        API contract and project documentation
├── scripts/     Runnable satellite/ML pipeline scripts
├── tests/       Test suites for the ML verifier
└── *.md         Team guides (START_AICI.md, Agent.md, Role_*.md, ...)
```

- Satellite/ML scripts (run from the repo root): `scripts/check_parcel.py`,
  `scripts/export_ndvi.py`, `scripts/inspect_ndvi.py`,
  `scripts/run_real_verification.py`, `scripts/test_copernicus.py`.
- Tests: `tests/test_rules.py` (manual scenarios) and
  `tests/test_rules_pytest.py` (pytest suite).
- See `backend/ml/README.md` for the verification rules and integration contract.
