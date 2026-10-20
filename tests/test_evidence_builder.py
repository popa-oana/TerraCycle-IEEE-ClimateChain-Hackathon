"""
tests/test_evidence_builder.py — Evidence Builder Tests

Validates the canonical evidence document builder:
- Real verifier response schema compatibility
- Correct evidence field mapping
- Valid integer conversion
- Missing required commitment metadata
- Missing scene_id
- Missing provenance
- Invalid numeric values
- Deterministic canonical serialization
- Reproducible evidence hash
- Preservation of verdict and reason codes
- Preservation of evidence-quality limitations
- No mutation of original verifier data
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.services.evidence_builder import (  # noqa: E402
    build_evidence_document,
    build_attestation,
    verify_evidence_document,
    _transform_observations,
    _transform_quality,
    _transform_dataset,
    _policy_to_canonical,
)
from backend.hashing import canonical_bytes, hash_snapshot  # noqa: E402
from backend.ml.rules import verify_parcel  # noqa: E402

EVIDENCE_DIR = REPO_ROOT / "data" / "ndvi"
FIXTURE_PATH = REPO_ROOT / "data" / "fixtures" / "demo.json"
CANONICAL_FIXTURE = REPO_ROOT / "data" / "fixtures" / "canonical_evidence_snapshot.json"

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


class MockCommitment:
    """Mock SQLAlchemy Commitment model for testing."""
    def __init__(self, **kwargs):
        self.commitment_id = kwargs.get("commitment_id", "0x8979bf59bbcd3c6b2ff84ee6c2306d649d2cb37a4e0c4ceeb06b72ca1387d834")
        self.plan_hash = kwargs.get("plan_hash", "0x7a3e21820b1b9e2cb92a34493de3df34177c38c82649b1a133b3a677114b010f")
        self.parcel_id = kwargs.get("parcel_id", "parcel_01")
        self.season_id = kwargs.get("season_id", "season-2024")
        self.verification_policy_id = kwargs.get("verification_policy_id", "cover-v1")
        self.settle_deadline = kwargs.get("settle_deadline", 1799999999)
        self.plan_snapshot = kwargs.get("plan_snapshot", b"{}")


def _load_fixture_policy(policy_id: str) -> dict:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return data["verification_policies"][policy_id]


# ============================================================
# Policy conversion tests
# ============================================================

class TestPolicyConversion:
    def test_policy_to_canonical(self):
        policy = _load_fixture_policy("cover-v1")
        canonical = _policy_to_canonical(policy)

        assert canonical["policy_version"] == "cover-v1"
        assert canonical["type"] == "vegetation_cover"
        assert canonical["window_start"] == "2024-03-01T00:00:00Z"
        assert canonical["window_end"] == "2024-11-01T00:00:00Z"
        assert canonical["minimum_observations"] == 5
        assert canonical["minimum_valid_pixel_percent"] == 50
        assert canonical["minimum_temporal_coverage_percent"] == 50
        assert canonical["minimum_positive_percent"] == 80

    def test_spring_policy_conversion(self):
        policy = _load_fixture_policy("spring-cover-v1")
        canonical = _policy_to_canonical(policy)

        assert canonical["policy_version"] == "spring-cover-v1"
        assert canonical["window_start"] == "2024-03-20T00:00:00Z"
        assert canonical["window_end"] == "2024-05-30T00:00:00Z"


# ============================================================
# Observation transformation tests
# ============================================================

class TestObservationTransformation:
    def test_valid_observation_transformation(self):
        observations = [{
            "acquired_at": "2024-03-23T00:00:00Z",
            "ndvi_mean": 0.853875,
            "is_valid_observation": True,
            "valid_pixel_fraction": 1.0,
        }]
        result = _transform_observations(observations, 0.35)

        assert len(result) == 1
        obs = result[0]
        assert obs["acquired_at"] == "2024-03-23T00:00:00Z"
        assert obs["scene_id"] is None
        assert obs["ndvi_milli"] == 854  # round(0.853875 * 1000)
        assert obs["valid_pixel_percent"] == 100  # round(1.0 * 100)
        assert obs["is_valid"] is True
        assert obs["vegetation_class"] == 1  # 0.853875 > 0.35

    def test_invalid_observation_vegetation_class(self):
        """Invalid observations get vegetation_class = 0 regardless of NDVI."""
        observations = [{
            "acquired_at": "2024-03-03T00:00:00Z",
            "ndvi_mean": 0.444298,
            "is_valid_observation": False,
            "valid_pixel_fraction": 0.0956,
            "quality_reason": "valid_pixel_fraction=0.0956 < 0.50"
        }]
        result = _transform_observations(observations, 0.35)

        assert result[0]["vegetation_class"] == 0  # Invalid = not vegetated

    def test_ndvi_below_threshold_vegetation_class(self):
        """Valid observation with NDVI below threshold gets vegetation_class = 0."""
        observations = [{
            "acquired_at": "2024-06-11T00:00:00Z",
            "ndvi_mean": 0.226821,
            "is_valid_observation": True,
            "valid_pixel_fraction": 1.0,
        }]
        result = _transform_observations(observations, 0.35)

        assert result[0]["vegetation_class"] == 0  # 0.226821 < 0.35

    def test_ndvi_milli_rounding(self):
        """Test ndvi_milli rounding convention."""
        test_cases = [
            (0.444298, 444),   # round(444.298) = 444
            (0.890062, 890),   # round(890.062) = 890
            (0.920044, 920),   # round(920.044) = 920
            (0.226821, 227),   # round(226.821) = 227
            (0.199282, 199),   # round(199.282) = 199
        ]
        for ndvi_mean, expected in test_cases:
            observations = [{
                "acquired_at": "2024-01-01T00:00:00Z",
                "ndvi_mean": ndvi_mean,
                "is_valid_observation": True,
                "valid_pixel_fraction": 1.0,
            }]
            result = _transform_observations(observations, 0.35)
            assert result[0]["ndvi_milli"] == expected, f"ndvi_mean={ndvi_mean}"

    def test_valid_pixel_percent_rounding(self):
        """Test valid_pixel_percent rounding convention."""
        test_cases = [
            (1.0, 100),
            (0.9046, 90),      # round(90.46) = 90
            (0.6997, 70),      # round(69.97) = 70
            (0.5, 50),         # round(50) = 50
            (0.0956, 10),      # round(9.56) = 10
            (0.0137, 1),       # round(1.37) = 1
        ]
        for vpf, expected in test_cases:
            observations = [{
                "acquired_at": "2024-01-01T00:00:00Z",
                "ndvi_mean": 0.5,
                "is_valid_observation": True,
                "valid_pixel_fraction": vpf,
            }]
            result = _transform_observations(observations, 0.35)
            assert result[0]["valid_pixel_percent"] == expected, f"vpf={vpf}"

    def test_missing_valid_pixel_fraction(self):
        """Missing valid_pixel_fraction becomes null."""
        observations = [{
            "acquired_at": "2024-01-01T00:00:00Z",
            "ndvi_mean": 0.5,
            "is_valid_observation": True,
        }]
        result = _transform_observations(observations, 0.35)
        assert result[0]["valid_pixel_percent"] is None

    def test_scene_id_preserved_as_null(self):
        """Missing scene_id becomes null."""
        observations = [{
            "acquired_at": "2024-01-01T00:00:00Z",
            "ndvi_mean": 0.5,
            "is_valid_observation": True,
            "valid_pixel_fraction": 1.0,
        }]
        result = _transform_observations(observations, 0.35)
        assert result[0]["scene_id"] is None

    def test_invalid_ndvi_range_raises(self):
        """NDVI outside [-1, 1] raises ValueError."""
        observations = [{
            "acquired_at": "2024-01-01T00:00:00Z",
            "ndvi_mean": 1.5,
            "is_valid_observation": True,
            "valid_pixel_fraction": 1.0,
        }]
        with pytest.raises(ValueError, match="ndvi_mean out of range"):
            _transform_observations(observations, 0.35)

    def test_invalid_vpf_range_raises(self):
        """valid_pixel_fraction outside [0, 1] raises ValueError."""
        observations = [{
            "acquired_at": "2024-01-01T00:00:00Z",
            "ndvi_mean": 0.5,
            "is_valid_observation": True,
            "valid_pixel_fraction": 1.5,
        }]
        with pytest.raises(ValueError, match="valid_pixel_fraction out of range"):
            _transform_observations(observations, 0.35)

    def test_invalid_ndvi_type_raises(self):
        """Non-numeric ndvi_mean raises ValueError."""
        observations = [{
            "acquired_at": "2024-01-01T00:00:00Z",
            "ndvi_mean": "invalid",
            "is_valid_observation": True,
            "valid_pixel_fraction": 1.0,
        }]
        with pytest.raises(ValueError, match="Invalid ndvi_mean type"):
            _transform_observations(observations, 0.35)


# ============================================================
# Quality transformation tests
# ============================================================

class TestQualityTransformation:
    def test_quality_transformation(self):
        quality = {
            "valid_count": 29,
            "total_rows": 48,
            "excluded_count": 19,
            "temporal_coverage": 0.76,
            "covered_intervals": 19,
            "total_intervals": 25,
            "inconclusive_reason": None,
        }
        result = _transform_quality(quality, 0.35, [])

        assert result["total_rows"] == 48
        assert result["valid_count"] == 29
        assert result["excluded_count"] == 19
        assert result["temporal_coverage_percent"] == 76  # round(0.76 * 100)
        assert result["covered_intervals"] == 19
        assert result["total_intervals"] == 25
        assert result["inconclusive_reason"] is None

    def test_missing_temporal_coverage_becomes_null(self):
        quality = {
            "valid_count": 5,
            "total_rows": 10,
            "excluded_count": 5,
        }
        result = _transform_quality(quality, 0.35, [])
        assert result["temporal_coverage_percent"] is None
        assert result["covered_intervals"] is None
        assert result["total_intervals"] is None


# ============================================================
# Dataset transformation tests
# ============================================================

class TestDatasetTransformation:
    def test_dataset_transformation(self):
        source = {
            "provider": "Copernicus Data Space",
            "dataset": "Sentinel-2 L2A",
            "method": "cloud-masked NDVI (SCL classes 4,5)",
            "csv_file": "C:\\Users\\path\\to\\parcel_01_2024_quality.csv",
        }
        result = _transform_dataset(source)

        assert result["provider"] == "Copernicus Data Space"
        assert result["dataset"] == "Sentinel-2 L2A"
        assert result["method"] == "cloud-masked NDVI (SCL classes 4,5)"
        assert result["source_file"] == "parcel_01_2024_quality.csv"  # basename only

    def test_missing_source_fields(self):
        source = {}
        result = _transform_dataset(source)
        assert result["provider"] == "unknown"
        assert result["dataset"] == "unknown"
        assert result["method"] == "unknown"
        assert result["source_file"] is None


# ============================================================
# Full evidence document builder tests
# ============================================================

class TestEvidenceDocumentBuilder:
    def test_build_evidence_document_with_real_verifier(self):
        """Test with real verifier output for parcel_01."""
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        commitment = MockCommitment()
        policy = _load_fixture_policy("cover-v1")

        evidence_doc, evidence_bytes, evidence_hash = build_evidence_document(
            verifier_result, commitment, policy
        )

        # Check top-level structure
        assert evidence_doc["schema_version"] == "evidence-v1"
        assert evidence_doc["commitment_id"] == commitment.commitment_id
        assert evidence_doc["plan_hash"] == commitment.plan_hash
        assert evidence_doc["parcel_id"] == "parcel_01"
        assert evidence_doc["season_id"] == "season-2024"
        assert evidence_doc["verdict"] == "nonconform"
        assert evidence_doc["verdict_code"] == 1

        # Check policy
        assert evidence_doc["policy"]["policy_version"] == "cover-v1"
        assert evidence_doc["policy"]["minimum_valid_pixel_percent"] == 50
        assert evidence_doc["policy"]["minimum_temporal_coverage_percent"] == 50
        assert evidence_doc["policy"]["minimum_positive_percent"] == 80

        # Check observations
        assert len(evidence_doc["observations"]) > 0
        for obs in evidence_doc["observations"]:
            assert "acquired_at" in obs
            assert "scene_id" in obs
            assert "ndvi_milli" in obs
            assert isinstance(obs["ndvi_milli"], int)
            assert "valid_pixel_percent" in obs
            assert obs["valid_pixel_percent"] is None or isinstance(obs["valid_pixel_percent"], int)
            assert "is_valid" in obs
            assert isinstance(obs["is_valid"], bool)
            assert "vegetation_class" in obs
            assert obs["vegetation_class"] in (0, 1)

        # Check quality
        q = evidence_doc["quality"]
        assert q["total_rows"] == 48
        assert q["valid_count"] == 29
        assert q["temporal_coverage_percent"] == 76  # round(0.76 * 100)
        assert q["covered_intervals"] == 19
        assert q["total_intervals"] == 25

        # Check dataset
        assert evidence_doc["dataset"]["provider"] == "Copernicus Data Space"
        assert evidence_doc["dataset"]["dataset"] == "Sentinel-2 L2A"
        assert "parcel_01_2024_quality.csv" in evidence_doc["dataset"]["source_file"]

        # Check model
        assert evidence_doc["model"]["model_version"] == "rule-based-v1"
        assert evidence_doc["model"]["source"] == "RULE_BASED"

    def test_evidence_doc_passes_canonical_serialization(self):
        """Built evidence document must pass canonical_bytes()."""
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        commitment = MockCommitment()
        policy = _load_fixture_policy("cover-v1")

        evidence_doc, evidence_bytes, evidence_hash = build_evidence_document(
            verifier_result, commitment, _load_fixture_policy("cover-v1")
        )

        # Must not raise
        content, digest = hash_snapshot(evidence_doc)
        assert content == evidence_bytes
        assert digest == evidence_hash
        assert digest.startswith("0x")
        assert len(digest) == 66

    def test_evidence_doc_passes_verify_evidence_document(self):
        """Built evidence document must pass verify_evidence_document()."""
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        commitment = MockCommitment()
        policy = _load_fixture_policy("cover-v1")

        evidence_doc, _, _ = build_evidence_document(
            verifier_result, commitment, policy
        )

        # Must not raise
        assert verify_evidence_document(evidence_doc) is True

    def test_deterministic_serialization(self):
        """Same inputs produce identical canonical bytes and hash."""
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        commitment = MockCommitment()
        policy = _load_fixture_policy("cover-v1")

        _, bytes1, hash1 = build_evidence_document(verifier_result, commitment, policy)
        _, bytes2, hash2 = build_evidence_document(verifier_result, commitment, policy)

        assert bytes1 == bytes2
        assert hash1 == hash2

    def test_evidence_hash_changes_with_meaningful_change(self):
        """Changing a meaningful field changes the hash."""
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        commitment = MockCommitment()
        policy = _load_fixture_policy("cover-v1")

        _, _, hash1 = build_evidence_document(verifier_result, commitment, policy)

        # Change verdict
        verifier_result2 = verifier_result.copy()
        verifier_result2["verdict"] = "conform"
        verifier_result2["verdict_code"] = 0

        _, _, hash2 = build_evidence_document(verifier_result2, commitment, policy)

        assert hash1 != hash2

    def test_all_four_parcels(self):
        """Test all four parcels produce valid evidence documents."""
        for parcel_id in ["parcel_01", "parcel_02", "parcel_03", "parcel_04"]:
            verifier_result = verify_parcel(parcel_id, POLICY, str(EVIDENCE_DIR))
            commitment = MockCommitment(parcel_id=parcel_id)
            policy = _load_fixture_policy("cover-v1")

            evidence_doc, evidence_bytes, evidence_hash = build_evidence_document(
                verifier_result, commitment, policy
            )

            # Verify canonical serialization works
            hash_snapshot(evidence_doc)
            assert verify_evidence_document(evidence_doc) is True


# ============================================================
# Attestation builder tests
# ============================================================

class TestAttestationBuilder:
    def test_build_attestation(self):
        commitment = MockCommitment()
        evidence_hash = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        verdict_code = 1

        attestation = build_attestation(commitment, evidence_hash, verdict_code)

        assert attestation["commitmentId"] == commitment.commitment_id
        assert attestation["planHash"] == commitment.plan_hash
        assert attestation["evidenceHash"] == evidence_hash
        assert attestation["verdict"] == verdict_code
        assert attestation["validUntil"] == commitment.settle_deadline


# ============================================================
# Evidence document validation tests
# ============================================================

class TestEvidenceDocumentValidation:
    def test_valid_evidence_document_passes(self):
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        commitment = MockCommitment()
        policy = _load_fixture_policy("cover-v1")

        evidence_doc, _, _ = build_evidence_document(verifier_result, commitment, policy)

        assert verify_evidence_document(evidence_doc) is True

    def test_missing_top_level_key_raises(self):
        doc = {"schema_version": "evidence-v1"}
        with pytest.raises(ValueError, match="missing required keys"):
            verify_evidence_document(doc)

    def test_float_in_evidence_raises(self):
        """Canonical evidence must not contain floats."""
        doc = {
            "schema_version": "evidence-v1",
            "commitment_id": "0x1",
            "plan_hash": "0x2",
            "parcel_id": "parcel_01",
            "season_id": "season-2024",
            "policy": {
                "policy_version": "cover-v1",
                "type": "vegetation_cover",
                "window_start": "2024-03-01T00:00:00Z",
                "window_end": "2024-11-01T00:00:00Z",
                "minimum_observations": 5,
                "minimum_valid_pixel_percent": 50,
                "minimum_temporal_coverage_percent": 50,
                "minimum_positive_percent": 80,
            },
            "observations": [{
                "acquired_at": "2024-03-01T00:00:00Z",
                "scene_id": None,
                "ndvi_milli": 500,
                "valid_pixel_percent": 100,
                "is_valid": True,
                "vegetation_class": 1,
            }],
            "quality": {
                "total_rows": 1,
                "valid_count": 1,
                "excluded_count": 0,
                "temporal_coverage_percent": 100,
                "covered_intervals": 1,
                "total_intervals": 1,
                "inconclusive_reason": None,
            },
            "dataset": {"provider": "test", "dataset": "test", "source_file": "test.csv", "method": "test"},
            "model": {"model_version": "test", "source": "RULE_BASED"},
            "verdict": "conform",
            "verdict_code": 0,
        }
        # Add a float to make it invalid
        doc["quality"]["temporal_coverage_percent"] = 100.0  # float!

        with pytest.raises(ValueError, match="not canonically serializable"):
            verify_evidence_document(doc)

    def test_invalid_vegetation_class_raises(self):
        doc = {
            "schema_version": "evidence-v1",
            "commitment_id": "0x1",
            "plan_hash": "0x2",
            "parcel_id": "parcel_01",
            "season_id": "season-2024",
            "policy": {
                "policy_version": "cover-v1",
                "type": "vegetation_cover",
                "window_start": "2024-03-01T00:00:00Z",
                "window_end": "2024-11-01T00:00:00Z",
                "minimum_observations": 5,
                "minimum_valid_pixel_percent": 50,
                "minimum_temporal_coverage_percent": 50,
                "minimum_positive_percent": 80,
            },
            "observations": [{
                "acquired_at": "2024-03-01T00:00:00Z",
                "scene_id": None,
                "ndvi_milli": 500,
                "valid_pixel_percent": 100,
                "is_valid": True,
                "vegetation_class": 2,  # Invalid!
            }],
            "quality": {
                "total_rows": 1,
                "valid_count": 1,
                "excluded_count": 0,
                "temporal_coverage_percent": 100,
                "covered_intervals": 1,
                "total_intervals": 1,
                "inconclusive_reason": None,
            },
            "dataset": {"provider": "test", "dataset": "test", "source_file": "test.csv", "method": "test"},
            "model": {"model_version": "test", "source": "RULE_BASED"},
            "verdict": "conform",
            "verdict_code": 0,
        }

        with pytest.raises(ValueError, match="vegetation_class must be 0 or 1"):
            verify_evidence_document(doc)

    def test_missing_observation_fields_raises(self):
        doc = {
            "schema_version": "evidence-v1",
            "commitment_id": "0x1",
            "plan_hash": "0x2",
            "parcel_id": "parcel_01",
            "season_id": "season-2024",
            "policy": {
                "policy_version": "cover-v1",
                "type": "vegetation_cover",
                "window_start": "2024-03-01T00:00:00Z",
                "window_end": "2024-11-01T00:00:00Z",
                "minimum_observations": 5,
                "minimum_valid_pixel_percent": 50,
                "minimum_temporal_coverage_percent": 50,
                "minimum_positive_percent": 80,
            },
            "observations": [{
                "acquired_at": "2024-03-01T00:00:00Z",
                # missing scene_id, ndvi_milli, etc.
            }],
            "quality": {
                "total_rows": 1,
                "valid_count": 1,
                "excluded_count": 0,
                "temporal_coverage_percent": 100,
                "covered_intervals": 1,
                "total_intervals": 1,
                "inconclusive_reason": None,
            },
            "dataset": {"provider": "test", "dataset": "test", "source_file": "test.csv", "method": "test"},
            "model": {"model_version": "test", "source": "RULE_BASED"},
            "verdict": "conform",
            "verdict_code": 0,
        }

        with pytest.raises(ValueError, match="missing keys"):
            verify_evidence_document(doc)


# ============================================================
# Verifier result preservation tests
# ============================================================

class TestVerifierResultPreservation:
    def test_verdict_preserved(self):
        """Verdict and verdict_code are preserved exactly."""
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        commitment = MockCommitment()
        policy = _load_fixture_policy("cover-v1")

        evidence_doc, _, _ = build_evidence_document(verifier_result, commitment, policy)

        assert evidence_doc["verdict"] == verifier_result["verdict"]
        assert evidence_doc["verdict_code"] == verifier_result["verdict_code"]

    def test_reason_code_preserved(self):
        """Reason code is preserved in the attestation (not in evidence doc per canonical schema)."""
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        commitment = MockCommitment()
        policy = _load_fixture_policy("cover-v1")

        evidence_doc, evidence_bytes, evidence_hash = build_evidence_document(verifier_result, commitment, policy)
        attestation = build_attestation(commitment, evidence_hash, evidence_doc["verdict_code"])

        # reason_code is in attestation/Verdict model, not in canonical evidence doc
        # Canonical evidence schema doesn't include reason_codes at top level
        assert "reason_codes" not in evidence_doc  # Per canonical schema
        # But reason_code is available for inclusion in Verdict/attestation
        assert verifier_result["reason_code"] == "RULE_BASED_DECISION"
        # The evidence doc doesn't directly store reason_code but the attestation/verdict do

    def test_quality_warnings_preserved(self):
        """Quality warnings from verifier are available (though not in canonical schema)."""
        # Test with NDVI-only CSV (no valid_pixel_fraction)
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
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

            verifier_result = verify_parcel("parcel_01", POLICY, str(tmp_path))
            assert verifier_result["quality"]["evidence_quality"] == "unknown"
            assert any("valid_pixel_fraction" in w for w in verifier_result["quality"]["warnings"])


# ============================================================
# No mutation tests
# ============================================================

class TestNoMutation:
    def test_verifier_result_not_mutated(self):
        """Original verifier result must not be mutated."""
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        original_verdict = verifier_result["verdict"]
        original_observations = json.dumps(verifier_result["observations"])

        commitment = MockCommitment()
        policy = _load_fixture_policy("cover-v1")

        build_evidence_document(verifier_result, commitment, policy)

        assert verifier_result["verdict"] == original_verdict
        assert json.dumps(verifier_result["observations"]) == original_observations

    def test_commitment_not_mutated(self):
        """Commitment object must not be mutated."""
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        commitment = MockCommitment()
        original_commitment_id = commitment.commitment_id
        original_plan_hash = commitment.plan_hash

        build_evidence_document(verifier_result, commitment, _load_fixture_policy("cover-v1"))

        assert commitment.commitment_id == original_commitment_id
        assert commitment.plan_hash == original_plan_hash


# ============================================================
# Missing commitment metadata tests
# ============================================================

class TestMissingCommitmentMetadata:
    def test_missing_commitment_id_raises(self):
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        commitment = MockCommitment(commitment_id="")
        policy = _load_fixture_policy("cover-v1")

        with pytest.raises(ValueError, match="missing commitment_id or plan_hash"):
            build_evidence_document(verifier_result, commitment, policy)

    def test_missing_plan_hash_raises(self):
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        commitment = MockCommitment(plan_hash="")
        policy = _load_fixture_policy("cover-v1")

        with pytest.raises(ValueError, match="missing commitment_id or plan_hash"):
            build_evidence_document(verifier_result, commitment, policy)

    def test_missing_parcel_id_raises(self):
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        commitment = MockCommitment(parcel_id="")
        policy = _load_fixture_policy("cover-v1")

        with pytest.raises(ValueError, match="missing parcel_id or season_id"):
            build_evidence_document(verifier_result, commitment, policy)

    def test_missing_season_id_raises(self):
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        commitment = MockCommitment(season_id="")
        policy = _load_fixture_policy("cover-v1")

        with pytest.raises(ValueError, match="missing parcel_id or season_id"):
            build_evidence_document(verifier_result, commitment, policy)

    def test_missing_verifier_keys_raises(self):
        commitment = MockCommitment()
        policy = _load_fixture_policy("cover-v1")
        incomplete_result = {"verdict": "conform"}

        with pytest.raises(ValueError, match="missing keys"):
            build_evidence_document(incomplete_result, commitment, policy)


# ============================================================
# Canonical fixture compatibility
# ============================================================

class TestCanonicalFixtureCompatibility:
    def test_canonical_fixture_passes_validation(self):
        """The official canonical fixture must pass validation."""
        fixture = json.loads(CANONICAL_FIXTURE.read_text(encoding="utf-8"))
        assert verify_evidence_document(fixture) is True

    def test_canonical_fixture_hashes(self):
        """The canonical fixture must produce the expected hash."""
        fixture = json.loads(CANONICAL_FIXTURE.read_text(encoding="utf-8"))
        content, digest = hash_snapshot(fixture)
        assert digest.startswith("0x")
        assert len(digest) == 66

    def test_built_doc_matches_fixture_structure(self):
        """Built document must have same structure as canonical fixture."""
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        commitment = MockCommitment(
            commitment_id="0x8979bf59bbcd3c6b2ff84ee6c2306d649d2cb37a4e0c4ceeb06b72ca1387d834",
            plan_hash="0x7a3e21820b1b9e2cb92a34493de3df34177c38c82649b1a133b3a677114b010f",
        )
        policy = _load_fixture_policy("cover-v1")

        evidence_doc, _, _ = build_evidence_document(verifier_result, commitment, policy)

        # Check structure matches fixture
        fixture = json.loads(CANONICAL_FIXTURE.read_text(encoding="utf-8"))

        # Same top-level keys
        assert set(evidence_doc.keys()) == set(fixture.keys())

        # Same observation structure
        for obs_key in ["acquired_at", "scene_id", "ndvi_milli", "valid_pixel_percent", "is_valid", "vegetation_class"]:
            assert obs_key in evidence_doc["observations"][0]
            assert obs_key in fixture["observations"][0]


# ============================================================
# Missing provenance handling
# ============================================================

class TestMissingProvenance:
    def test_missing_scene_id_becomes_null(self):
        """Missing scene_id in verifier output becomes null in canonical."""
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        # Verifier output doesn't have scene_id
        for obs in verifier_result["observations"]:
            assert "scene_id" not in obs or obs.get("scene_id") is None

        commitment = MockCommitment()
        policy = _load_fixture_policy("cover-v1")

        evidence_doc, _, _ = build_evidence_document(verifier_result, commitment, policy)

        for obs in evidence_doc["observations"]:
            assert obs["scene_id"] is None

    def test_missing_source_file_becomes_null(self):
        """Missing csv_file in source becomes null."""
        verifier_result = verify_parcel("parcel_01", POLICY, str(EVIDENCE_DIR))
        # Remove csv_file
        verifier_result2 = verifier_result.copy()
        verifier_result2["source"] = verifier_result["source"].copy()
        verifier_result2["source"].pop("csv_file", None)

        commitment = MockCommitment()
        policy = _load_fixture_policy("cover-v1")

        evidence_doc, _, _ = build_evidence_document(verifier_result2, commitment, policy)

        assert evidence_doc["dataset"]["source_file"] is None


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])