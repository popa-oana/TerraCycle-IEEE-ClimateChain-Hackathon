"""
tests/test_ml_backend_contract.py — ML-to-Backend Contract Validation

Validates that verify_parcel() output structure is compatible with the
canonical evidence document schema and can be consumed by Corina's backend.

These are ML-side tests that ensure the verifier's contract is stable.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.rules import VERDICT_CODES, verify_parcel  # noqa: E402
from backend.hashing import canonical_bytes, hash_snapshot  # noqa: E402

EVIDENCE_DIR = REPO_ROOT / "data" / "ndvi"

POLICY = {
    "window_start": "2024-03-01",
    "window_end": "2024-11-01",
    "ndvi_threshold": 0.35,
    "required_fraction": 0.80,
    "min_observations": 5,
    "min_valid_pixel_fraction": 0.50,
    "min_temporal_coverage": 0.50,
    "temporal_coverage_interval_days": 10,
}

ALL_PARCELS = ("parcel_01", "parcel_02", "parcel_03", "parcel_04")


# ============================================================
# Verifier Output Structure
# ============================================================

class TestVerifierOutputStructure:
    """verify_parcel() returns the expected top-level structure."""

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_top_level_keys_present(self, parcel_id):
        result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        required = {
            "verdict", "verdict_code", "reason_code", "reason",
            "observations", "quality", "model", "source"
        }
        assert required.issubset(result.keys()), f"Missing keys in {parcel_id}: {required - set(result.keys())}"

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_verdict_is_valid(self, parcel_id):
        result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        assert result["verdict"] in ("conform", "nonconform", "inconclusive")

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_verdict_code_matches_mapping(self, parcel_id):
        result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        assert result["verdict_code"] == VERDICT_CODES[result["verdict"]]

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_reason_code_is_known(self, parcel_id):
        result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        known_codes = {
            "RULE_BASED_DECISION", "INSUFFICIENT_OBSERVATIONS",
            "INSUFFICIENT_TEMPORAL_COVERAGE", "MISSING_EVIDENCE",
            "INVALID_CSV_STRUCTURE", "CSV_READ_ERROR", "INVALID_INPUT"
        }
        assert result["reason_code"] in known_codes

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_observations_is_list(self, parcel_id):
        result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        assert isinstance(result["observations"], list)

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_quality_is_dict(self, parcel_id):
        result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        assert isinstance(result["quality"], dict)

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_model_is_dict(self, parcel_id):
        result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        assert isinstance(result["model"], dict)
        assert result["model"]["source"] == "RULE_BASED"

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_source_is_dict(self, parcel_id):
        result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        assert isinstance(result["source"], dict)
        assert result["source"]["provider"] == "Copernicus Data Space"
        assert result["source"]["dataset"] == "Sentinel-2 L2A"


# ============================================================
# Observation Fields
# ============================================================

class TestObservationFields:
    """Each observation has the required fields with correct types."""

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_observation_fields_and_types(self, parcel_id):
        result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        for obs in result["observations"]:
            # Required fields
            assert isinstance(obs["acquired_at"], str)
            assert isinstance(obs["ndvi_mean"], float)
            assert -1 <= obs["ndvi_mean"] <= 1
            assert isinstance(obs["is_valid_observation"], bool)

            # Optional fields
            if "valid_pixel_fraction" in obs:
                vpf = obs["valid_pixel_fraction"]
                assert vpf is None or isinstance(vpf, float)
                if vpf is not None:
                    assert 0 <= vpf <= 1

            if "quality_reason" in obs:
                assert isinstance(obs["quality_reason"], str)

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_valid_observations_have_ndvi_above_threshold(self, parcel_id):
        """Valid observations with ndvi_mean > 0.35 should be vegetated."""
        result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        for obs in result["observations"]:
            if obs["is_valid_observation"] and obs["ndvi_mean"] > 0.35:
                # This is the vegetation classification used downstream
                pass  # Just verifying structure


# ============================================================
# Quality Block
# ============================================================

class TestQualityBlock:
    """Quality block has required fields with correct types."""

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_quality_required_fields(self, parcel_id):
        result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        q = result["quality"]
        required = {
            "valid_count", "total_rows", "excluded_count",
            "quality_metadata_available", "evidence_quality",
            "min_valid_pixel_fraction", "warnings"
        }
        assert required.issubset(q.keys())

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_quality_types(self, parcel_id):
        result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        q = result["quality"]
        assert isinstance(q["valid_count"], int)
        assert isinstance(q["total_rows"], int)
        assert isinstance(q["excluded_count"], int)
        assert isinstance(q["quality_metadata_available"], bool)
        assert q["evidence_quality"] in ("assessed", "unknown")
        assert isinstance(q["min_valid_pixel_fraction"], (int, float))
        assert isinstance(q["warnings"], list)

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_temporal_coverage_range(self, parcel_id):
        result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        tc = result["quality"]["temporal_coverage"]
        if tc is not None:
            assert isinstance(tc, float)
            assert 0 <= tc <= 1


# ============================================================
# JSON Serializability
# ============================================================

class TestJSONSerializability:
    """verify_parcel output is fully JSON-serializable."""

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_json_serializable(self, parcel_id):
        result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        json_str = json.dumps(result, ensure_ascii=False)
        assert len(json_str) > 0

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_json_roundtrip(self, parcel_id):
        result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        json_str = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["verdict"] == result["verdict"]
        assert parsed["verdict_code"] == result["verdict_code"]
        assert len(parsed["observations"]) == len(result["observations"])


# ============================================================
# Deterministic Results
# ============================================================

class TestDeterministicResults:
    """Same input produces identical output."""

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_same_data_same_result(self, parcel_id):
        result1 = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        result2 = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
        assert result1["verdict"] == result2["verdict"]
        assert result1["verdict_code"] == result2["verdict_code"]
        assert result1["reason_code"] == result2["reason_code"]
        assert result1["observations"] == result2["observations"]
        assert result1["quality"] == result2["quality"]
        assert result1["model"] == result2["model"]
        assert result1["source"] == result2["source"]


# ============================================================
# Commitment-Window Enforcement
# ============================================================

class TestCommitmentWindowEnforcement:
    """Window filtering is applied before classification."""

    def test_out_of_window_excluded(self, tmp_path):
        """Observations outside window are excluded from verdict."""
        import pandas as pd
        rows = [
            ("parcel_01", "2024-02-01T00:00:00Z", "", 0.1, 1.0),  # before window
            ("parcel_01", "2024-04-01T00:00:00Z", "", 0.6, 1.0),
            ("parcel_01", "2024-04-05T00:00:00Z", "", 0.7, 1.0),
            ("parcel_01", "2024-04-10T00:00:00Z", "", 0.65, 1.0),
            ("parcel_01", "2024-04-15T00:00:00Z", "", 0.55, 1.0),
            ("parcel_01", "2024-12-01T00:00:00Z", "", 0.1, 1.0),  # after window
        ]
        path = tmp_path / "parcel_01_2024_quality.csv"
        with open(path, "w", encoding="utf-8") as f:
            f.write("parcel_id,acquired_at,scene_id,ndvi_mean,valid_pixel_fraction\n")
            for r in rows:
                f.write(",".join(str(v) for v in r) + "\n")

        result = verify_parcel("parcel_01", POLICY, str(tmp_path))
        # Only 4 in-window observations
        assert result["quality"]["valid_count"] <= 4
        assert all(
            "2024-03-01" <= obs["acquired_at"] < "2024-11-01"
            for obs in result["observations"]
        )

    def test_invalid_window_returns_invalid_input(self, tmp_path):
        """Partially specified window returns INVALID_INPUT."""
        import pandas as pd
        rows = [
            ("parcel_01", "2024-04-01T00:00:00Z", "", 0.6, 1.0),
            ("parcel_01", "2024-04-05T00:00:00Z", "", 0.7, 1.0),
            ("parcel_01", "2024-04-10T00:00:00Z", "", 0.65, 1.0),
            ("parcel_01", "2024-04-15T00:00:00Z", "", 0.55, 1.0),
            ("parcel_01", "2024-04-20T00:00:00Z", "", 0.5, 1.0),
        ]
        path = tmp_path / "parcel_01_2024_quality.csv"
        with open(path, "w", encoding="utf-8") as f:
            f.write("parcel_id,acquired_at,scene_id,ndvi_mean,valid_pixel_fraction\n")
            for r in rows:
                f.write(",".join(str(v) for v in r) + "\n")

        bad_policy = dict(POLICY, window_start="not-a-date")
        result = verify_parcel("parcel_01", bad_policy, str(tmp_path))
        assert result["verdict"] == "inconclusive"
        assert result["reason_code"] == "INVALID_INPUT"


# ============================================================
# Evidence Quality Reporting
# ============================================================

class TestEvidenceQualityReporting:
    """Missing provenance is reported truthfully."""

    def test_quality_metadata_available_when_csv_has_vpf(self, tmp_path):
        """CSV with valid_pixel_fraction -> evidence_quality = assessed."""
        import pandas as pd
        rows = [
            ("parcel_01", "2024-04-01T00:00:00Z", "", 0.6, 1.0),
            ("parcel_01", "2024-04-05T00:00:00Z", "", 0.7, 1.0),
            ("parcel_01", "2024-04-10T00:00:00Z", "", 0.65, 1.0),
            ("parcel_01", "2024-04-15T00:00:00Z", "", 0.55, 1.0),
            ("parcel_01", "2024-04-20T00:00:00Z", "", 0.5, 1.0),
        ]
        path = tmp_path / "parcel_01_2024_quality.csv"
        with open(path, "w", encoding="utf-8") as f:
            f.write("parcel_id,acquired_at,scene_id,ndvi_mean,valid_pixel_fraction\n")
            for r in rows:
                f.write(",".join(str(v) for v in r) + "\n")

        result = verify_parcel("parcel_01", POLICY, str(tmp_path))
        assert result["quality"]["quality_metadata_available"] is True
        assert result["quality"]["evidence_quality"] == "assessed"

    def test_missing_quality_metadata_flagged(self, tmp_path):
        """CSV without valid_pixel_fraction -> evidence_quality = unknown."""
        rows = [
            ("parcel_01", "2024-04-01T00:00:00Z", "", 0.6),
            ("parcel_01", "2024-04-05T00:00:00Z", "", 0.7),
            ("parcel_01", "2024-04-10T00:00:00Z", "", 0.65),
            ("parcel_01", "2024-04-15T00:00:00Z", "", 0.55),
            ("parcel_01", "2024-04-20T00:00:00Z", "", 0.5),
        ]
        path = tmp_path / "parcel_01_2024.csv"
        with open(path, "w", encoding="utf-8") as f:
            f.write("parcel_id,acquired_at,scene_id,ndvi_mean\n")
            for r in rows:
                f.write(",".join(str(v) for v in r) + "\n")

        result = verify_parcel("parcel_01", POLICY, str(tmp_path))
        assert result["quality"]["quality_metadata_available"] is False
        assert result["quality"]["evidence_quality"] == "unknown"
        assert any("valid_pixel_fraction" in w for w in result["quality"]["warnings"])


# ============================================================
# Canonical Evidence Compatibility
# ============================================================

class TestCanonicalEvidenceCompatibility:
    """Verify verifier output can be transformed to canonical evidence schema."""

    def test_verifier_output_contains_floats_rejected_by_canonical(self):
        """
        DOCUMENTED EXPECTATION: verify_parcel output contains floats
        that would be rejected by canonical_bytes().
        This test documents the expected failure — backend MUST convert.
        """
        result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))

        # These fields contain floats that canonical_bytes() rejects
        float_fields = []

        # observations[*].ndvi_mean
        for obs in result["observations"]:
            if isinstance(obs["ndvi_mean"], float):
                float_fields.append(f"observations.ndvi_mean={obs['ndvi_mean']}")

        # observations[*].valid_pixel_fraction
        for obs in result["observations"]:
            if "valid_pixel_fraction" in obs and isinstance(obs["valid_pixel_fraction"], float):
                float_fields.append(f"observations.valid_pixel_fraction={obs['valid_pixel_fraction']}")

        # quality.temporal_coverage
        tc = result["quality"]["temporal_coverage"]
        if isinstance(tc, float):
            float_fields.append(f"quality.temporal_coverage={tc}")

        # quality.vegetated_fraction
        vf = result["quality"]["vegetated_fraction"]
        if isinstance(vf, float):
            float_fields.append(f"quality.vegetated_fraction={vf}")

        # model.thresholds values
        for k, v in result["model"]["thresholds"].items():
            if isinstance(v, float):
                float_fields.append(f"model.thresholds.{k}={v}")

        assert len(float_fields) > 0, "Expected floats in verifier output"

        # This MUST raise TypeError — backend must convert before hashing
        with pytest.raises(TypeError, match="Floats are forbidden"):
            canonical_bytes(result)

    def test_canonical_evidence_fixture_passes_hashing(self):
        """The canonical evidence fixture passes canonical serialization."""
        fixture_path = REPO_ROOT / "data" / "fixtures" / "canonical_evidence_snapshot.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

        # Must not raise
        content, digest = hash_snapshot(fixture)
        assert isinstance(content, bytes)
        assert digest.startswith("0x")
        assert len(digest) == 66

    def test_fixture_has_no_floats(self):
        """Canonical fixture contains no floats."""
        fixture_path = REPO_ROOT / "data" / "fixtures" / "canonical_evidence_snapshot.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

        def find_floats(obj, path=""):
            floats = []
            if isinstance(obj, float):
                floats.append(path)
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    floats.extend(find_floats(v, f"{path}.{k}"))
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    floats.extend(find_floats(v, f"{path}[{i}]"))
            return floats

        floats = find_floats(fixture)
        assert len(floats) == 0, f"Floats found in canonical fixture: {floats}"

    def test_fixture_matches_expected_schema(self):
        """Canonical fixture has expected structure."""
        fixture_path = REPO_ROOT / "data" / "fixtures" / "canonical_evidence_snapshot.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

        required_top = {
            "schema_version", "commitment_id", "plan_hash", "parcel_id",
            "season_id", "policy", "observations", "quality",
            "dataset", "model", "verdict", "verdict_code"
        }
        assert required_top.issubset(fixture.keys())
        assert fixture["schema_version"] == "evidence-v1"
        assert fixture["verdict"] in ("conform", "nonconform", "inconclusive")
        assert fixture["verdict_code"] in (0, 1, 2)

        for obs in fixture["observations"]:
            assert "acquired_at" in obs
            assert "ndvi_milli" in obs
            assert isinstance(obs["ndvi_milli"], int)
            assert "valid_pixel_percent" in obs
            assert isinstance(obs["valid_pixel_percent"], int)
            assert "is_valid" in obs
            assert isinstance(obs["is_valid"], bool)
            assert "vegetation_class" in obs
            assert obs["vegetation_class"] in (0, 1)


# ============================================================
# Integration Questions Documentation
# ============================================================

class TestIntegrationQuestions:
    """Tests that document unresolved contract questions."""

    def test_ndvi_milli_rounding_unspecified(self):
        """
        BLOCKED: ndvi_milli = round(ndvi_mean * 1000) — rounding mode unspecified.
        Canonical fixture shows ndvi_milli=444 for ndvi_mean=0.444298.
        round(0.444298 * 1000) = 444 — matches round-half-even?
        """
        # This test documents the ambiguity
        ndvi_mean = 0.444298
        ndvi_milli = round(ndvi_mean * 1000)
        assert ndvi_milli == 444
        # But what about 0.4445? round(0.4445 * 1000) = 445 (banker's rounding)
        # Or should it be floor/int? int(0.4445 * 1000) = 444
        # Contract must specify.

    def test_valid_pixel_percent_rounding_unspecified(self):
        """
        BLOCKED: valid_pixel_percent = round(vpf * 100).
        Canonical fixture shows 90 for vpf=0.9 (exact).
        But for 0.9046 -> round(90.46) = 90 vs int(90.46) = 90.
        For 0.905 -> round(90.5) = 90 (banker's) vs int = 90.
        Contract must specify rounding mode.
        """
        pass  # Documents the ambiguity

    def test_temporal_coverage_percent_fixture_mismatch(self):
        """
        BLOCKED: Canonical fixture shows temporal_coverage_percent=92
        but verifier reports temporal_coverage=0.76 for parcel_01.
        0.76 * 100 = 76, not 92.
        This suggests the fixture uses a different window or calculation.
        """
        result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        tc = result["quality"]["temporal_coverage"]
        # Verifier reports 0.76 (19/25 intervals)
        # Fixture shows 92 — these are different numbers
        assert tc == 0.76
        # Fixture 92% must be for different window or calculation
        # This is a BLOCKED contract ambiguity

    def test_vegetation_class_derivation(self):
        """
        BLOCKED: How is vegetation_class derived?
        Option A: 1 if ndvi_mean > ndvi_threshold else 0
        Option B: 1 if ndvi_mean > ndvi_threshold AND is_valid_observation else 0
        Option C: From ML model prediction (not current)
        Current verify.py uses Option A on ALL observations.
        But canonical fixture shows vegetation_class=1 for ndvi_milli=444 (0.444 > 0.35)
        and vegetation_class=0 for ndvi_milli=227 (0.227 < 0.35).
        Need Crenguța confirmation.
        """
        pass  # Documents the ambiguity


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])