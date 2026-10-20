"""
tests/test_ml_insights.py — Day 6C.3 corrected ML visualization/export tests

Focused tests for the corrected ML charts and frontend-ready JSON:

- Corrected evaluation files are used (not the original buggy predictions).
- Correct parcel IDs.
- Correct, genuine UTC timestamps.
- No training/test contamination.
- Displayed metrics agree with the corrected evaluation.
- Valid JSON.
- Reproducible output generation.
- Existing real files remain unchanged.

Uses the real project data files (read-only).
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_SCRIPT = REPO_ROOT / "scripts" / "generate_ml_insights.py"
_spec = importlib.util.spec_from_file_location("generate_ml_insights", _SCRIPT)
ml_insights = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ml_insights)

AI_INSIGHTS = REPO_ROOT / "data/ml/ai_insights.json"
CORRECTED_JSON = REPO_ROOT / "data/ml/evaluation_corrected/trajectory_evaluation_corrected.json"
CORRECTED_CSV = REPO_ROOT / "data/ml/evaluation_corrected/trajectory_test_predictions_corrected.csv"
ORIGINAL_JSON = REPO_ROOT / "data/ml/trajectory_evaluation.json"
ORIGINAL_CSV = REPO_ROOT / "data/ml/trajectory_test_predictions.csv"
OBS_CSV = REPO_ROOT / "data/features/observations_clean_4parcels.csv"
PLOT_DIR = REPO_ROOT / "data/ml/plots"

EXPECTED_PARCELS = ["parcel_01", "parcel_02", "parcel_03", "parcel_04"]


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ============================================================
# Canonical outputs exist and are valid JSON
# ============================================================
class TestCanonicalOutputs:
    def test_ai_insights_json_exists(self):
        assert AI_INSIGHTS.exists()

    def test_all_four_plots_exist(self):
        for pid in EXPECTED_PARCELS:
            path = PLOT_DIR / f"{pid}_trajectory.png"
            assert path.exists(), f"missing chart: {path}"
            assert path.stat().st_size > 0

    def test_valid_json_with_required_keys(self):
        data = _load_json(AI_INSIGHTS)
        for key in ("generated_at", "title", "data_source", "method", "disclaimer", "parcels"):
            assert key in data
        assert isinstance(data["parcels"], list)
        for p in data["parcels"]:
            for key in (
                "parcel_id", "observations", "n_train", "n_test", "split_date",
                "test_period_start", "test_period_end", "gpr_predictions",
                "persistence_predictions", "metrics", "explanation", "limitations",
            ):
                assert key in p

    def test_correct_parcel_ids(self):
        data = _load_json(AI_INSIGHTS)
        assert [p["parcel_id"] for p in data["parcels"]] == EXPECTED_PARCELS


# ============================================================
# Corrected evaluation files are used
# ============================================================
class TestCorrectedSources:
    def test_references_corrected_evaluation(self):
        data = _load_json(AI_INSIGHTS)
        assert data["data_source"]["corrected_evaluation_file"].startswith(
            "data/ml/evaluation_corrected/"
        )

    def test_metrics_agree_with_corrected_evaluation(self):
        data = _load_json(AI_INSIGHTS)
        corrected = _load_json(CORRECTED_JSON)
        for p, cp in zip(data["parcels"], corrected["parcels"]):
            assert p["metrics"]["gpr_mae"] == cp["gpr_mae"]
            assert p["metrics"]["gpr_rmse"] == cp["gpr_rmse"]
            assert p["metrics"]["baseline_mae"] == cp["baseline_mae"]
            assert p["metrics"]["baseline_rmse"] == cp["baseline_rmse"]
            assert (
                p["metrics"]["observed_interval_coverage"]
                == cp["predictive_interval_coverage_95"]
            )
            assert p["n_train"] == cp["n_train"]
            assert p["n_test"] == cp["n_test"]

    def test_predictions_match_corrected_csv(self):
        corrected = pd.read_csv(CORRECTED_CSV)
        data = _load_json(AI_INSIGHTS)
        for p in data["parcels"]:
            pid = p["parcel_id"]
            c = corrected[corrected["parcel_id"] == pid].reset_index(drop=True)
            assert len(p["gpr_predictions"]) == len(c)
            for i, pr in enumerate(p["gpr_predictions"]):
                assert pr["timestamp"] == c.loc[i, "acquired_at"]
                assert pr["predicted_ndvi"] == pytest.approx(c.loc[i, "predicted_ndvi"], abs=1e-9)
                assert pr["predicted_std"] == pytest.approx(c.loc[i, "predicted_std"], abs=1e-9)
            for i, pr in enumerate(p["persistence_predictions"]):
                assert pr["predicted_ndvi"] == pytest.approx(c.loc[i, "baseline_prediction"], abs=1e-9)

    def test_not_original_buggy_predictions(self):
        original = pd.read_csv(ORIGINAL_CSV)
        data = _load_json(AI_INSIGHTS)
        for p in data["parcels"]:
            orig = original[original["parcel_id"] == p["parcel_id"]].reset_index(drop=True)
            assert len(orig) > 0
            # Corrected and original held-out predictions differ for every parcel.
            assert p["gpr_predictions"][0]["predicted_ndvi"] != pytest.approx(
                orig.loc[0, "predicted_ndvi"], abs=1e-6
            )


# ============================================================
# Genuine observations and timestamps
# ============================================================
class TestGenuineObservations:
    def test_observations_match_real_csv(self):
        obs_df = pd.read_csv(OBS_CSV)
        data = _load_json(AI_INSIGHTS)
        for p in data["parcels"]:
            pid = p["parcel_id"]
            real = obs_df[obs_df["parcel_id"] == pid].sort_values("acquired_at")
            assert len(p["observations"]) == len(real)
            for rec, (_, row) in zip(p["observations"], real.iterrows()):
                assert rec["timestamp"] == row["acquired_at"]
                assert rec["ndvi"] == pytest.approx(float(row["ndvi_mean"]), abs=1e-9)

    def test_timestamps_are_valid_utc(self):
        data = _load_json(AI_INSIGHTS)
        for p in data["parcels"]:
            for rec in p["observations"]:
                assert str(rec["timestamp"]).endswith("Z")
                assert pd.notna(pd.to_datetime(rec["timestamp"], utc=True))
            assert pd.notna(pd.to_datetime(p["split_date"], utc=True))
            for rec in p["gpr_predictions"]:
                assert pd.notna(pd.to_datetime(rec["timestamp"], utc=True))


# ============================================================
# No training/test contamination
# ============================================================
class TestNoContamination:
    def test_predictions_are_at_held_out_timestamps_only(self):
        data = _load_json(AI_INSIGHTS)
        for p in data["parcels"]:
            split = pd.Timestamp(p["split_date"])
            obs = p["observations"]
            train_ts = [pd.Timestamp(o["timestamp"]) for o in obs[: p["n_train"]]]
            test_ts = [pd.Timestamp(o["timestamp"]) for o in obs[p["n_train"] :]]
            assert all(t <= split for t in train_ts)
            assert all(t > split for t in test_ts)

            pred_ts = [pd.Timestamp(g["timestamp"]) for g in p["gpr_predictions"]]
            assert pred_ts == test_ts
            assert set(pred_ts).isdisjoint(train_ts)

    def test_prediction_counts_match_n_test(self):
        data = _load_json(AI_INSIGHTS)
        for p in data["parcels"]:
            assert len(p["gpr_predictions"]) == p["n_test"]
            assert len(p["persistence_predictions"]) == p["n_test"]


# ============================================================
# Reproducible output generation
# ============================================================
class TestReproducibility:
    def test_canonical_json_matches_fresh_build(self):
        obs = ml_insights.load_observations(OBS_CSV)
        corrected = ml_insights.load_corrected_evaluation()
        fresh = ml_insights.build_ai_insights(corrected, obs, generated_at="IGNORED")
        canonical = _load_json(AI_INSIGHTS)
        fresh.pop("generated_at")
        canonical.pop("generated_at")
        assert fresh == canonical

    def test_build_ai_insights_is_deterministic(self):
        obs = ml_insights.load_observations(OBS_CSV)
        corrected = ml_insights.load_corrected_evaluation()
        a = ml_insights.build_ai_insights(corrected, obs, generated_at="FIXED")
        b = ml_insights.build_ai_insights(corrected, obs, generated_at="FIXED")
        assert a == b

    def test_plot_generation_is_reproducible(self, tmp_path):
        obs = ml_insights.load_observations(OBS_CSV)
        corrected = ml_insights.load_corrected_evaluation()
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        paths_a = ml_insights.generate_all_plots(corrected, obs, dir_a)
        paths_b = ml_insights.generate_all_plots(corrected, obs, dir_b)
        assert [p.name for p in paths_a] == [p.name for p in paths_b]
        for pa, pb in zip(paths_a, paths_b):
            assert pa.read_bytes() == pb.read_bytes()


# ============================================================
# Existing real files remain unchanged
# ============================================================
class TestRealFilesUnchanged:
    def test_generation_does_not_modify_inputs(self):
        watched = [ORIGINAL_JSON, ORIGINAL_CSV, OBS_CSV]
        before = {p: _hash(p) for p in watched}

        obs = ml_insights.load_observations(OBS_CSV)
        corrected = ml_insights.load_corrected_evaluation()
        ml_insights.build_ai_insights(corrected, obs, generated_at="FIXED")

        after = {p: _hash(p) for p in watched}
        assert before == after
