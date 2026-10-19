import pytest
from pydantic import ValidationError

from backend.schemas import Attestation, EvidenceDocument, VerifyResponse


def _valid_evidence_dict():
    return {
        "commitment_id": "0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871",
        "evidence_id": "evidence-parcel_01-season-2024",
        "verdict": "nonconform",
        "verdict_code": 1,
        "reason_codes": ["VEGETATION_FRACTION_BELOW_THRESHOLD"],
        "model_version": "rule-based-v1",
        "policy_version": "cover-v1",
        "parcel_id": "parcel_01",
        "season_id": "season-2024",
        "observations": {
            "total_observations": 35,
            "valid_observations": 35,
            "vegetated_count": 13,
            "vegetated_fraction": 0.3714,
        },
        "data_provenance": {
            "provider": "Copernicus Data Space",
            "dataset": "Sentinel-2 L2A",
            "bands": ["B04", "B08", "SCL"],
            "method": "Cloud-masked NDVI mean",
        },
        "valid_until": 1799999999,
    }


def test_evidence_document_valid():
    doc = EvidenceDocument(**_valid_evidence_dict())
    assert doc.verdict == "nonconform"
    assert doc.verdict_code == 1
    assert doc.observations.vegetated_fraction == 0.3714


def test_evidence_document_invalid_verdict_code_mismatch():
    data = _valid_evidence_dict()
    data["verdict"] = "conform"
    data["verdict_code"] = 1
    with pytest.raises(ValidationError):
        EvidenceDocument(**data)


def test_evidence_document_invalid_commitment_id():
    data = _valid_evidence_dict()
    data["commitment_id"] = "not-a-hash"
    with pytest.raises(ValidationError):
        EvidenceDocument(**data)


def test_attestation_valid():
    att = Attestation(
        commitmentId="0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871",
        planHash="0x705b7a9dd94979bbc79a1af1a17b5aed531a3a3e7b27cb5a5f15635e1a1ee127",
        evidenceHash="0x89a43f3a2b84f44f4f8d12809d29a76c52769e62f05c759bc90c003ee3e9a16f",
        verdict=0,
        validUntil=1799999999,
    )
    assert att.verdict == 0


def test_attestation_invalid_verdict_range():
    with pytest.raises(ValidationError):
        Attestation(
            commitmentId="0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871",
            planHash="0x705b7a9dd94979bbc79a1af1a17b5aed531a3a3e7b27cb5a5f15635e1a1ee127",
            evidenceHash="0x89a43f3a2b84f44f4f8d12809d29a76c52769e62f05c759bc90c003ee3e9a16f",
            verdict=5,
            validUntil=1799999999,
        )
