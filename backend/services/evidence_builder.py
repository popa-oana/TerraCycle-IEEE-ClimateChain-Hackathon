"""
backend/services/evidence_builder.py — Canonical evidence document builder

Transforms the scientific verifier output into the canonical evidence document
schema required for EIP-712 signing and on-chain settlement.

This module does NOT:
- Modify the scientific verifier logic
- Change satellite observations or ML classifications
- Implement FastAPI endpoints or blockchain interactions
- Reimplement canonical serialization or hashing

It ONLY transforms the verifier result + backend commitment metadata
into the canonical evidence document format.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.hashing import canonical_bytes, hash_snapshot
from backend.ml.rules import verify_parcel


# ---------------------------------------------------------------------------
# Constants and configuration
# ---------------------------------------------------------------------------

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "demo.json"
EVIDENCE_SCHEMA_VERSION = "evidence-v1"

# Vegetation threshold used for vegetation_class derivation (from policy)
DEFAULT_NDVI_THRESHOLD = 0.35


# ---------------------------------------------------------------------------
# Policy loading
# ---------------------------------------------------------------------------

def _load_policy(policy_id: str) -> dict[str, Any]:
    """Load verification policy from shared fixture."""
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    policies = data.get("verification_policies", {})
    policy = policies.get(policy_id)
    if not policy:
        raise ValueError(f"Unknown policy '{policy_id}'")
    return policy


def _policy_to_canonical(policy: dict[str, Any]) -> dict[str, Any]:
    """
    Convert backend policy format to canonical evidence policy format.

    Backend policy uses float fractions; canonical uses integer percentages.
    """
    return {
        "policy_version": policy["policy_version"],
        "type": policy["type"],
        "window_start": policy["window_start"] + "T00:00:00Z" if "T" not in policy["window_start"] else policy["window_start"],
        "window_end": policy["window_end"] + "T00:00:00Z" if "T" not in policy["window_end"] else policy["window_end"],
        "minimum_observations": policy["min_observations"],
        "minimum_valid_pixel_percent": int(round(policy["min_valid_pixel_fraction"] * 100)),
        "minimum_temporal_coverage_percent": int(round(policy["min_temporal_coverage"] * 100)),
        "minimum_positive_percent": int(round(policy["required_fraction"] * 100)),
    }


# ---------------------------------------------------------------------------
# Observation transformation
# ---------------------------------------------------------------------------

def _transform_observations(
    observations: list[dict[str, Any]],
    ndvi_threshold: float,
) -> list[dict[str, Any]]:
    """
    Transform verifier observations to canonical evidence format.

    Canonical format requires:
    - acquired_at: ISO 8601 UTC string (unchanged)
    - scene_id: string or null (not available from openEO, set to null)
    - ndvi_milli: integer (ndvi_mean * 1000, rounded)
    - valid_pixel_percent: integer (valid_pixel_fraction * 100, rounded)
    - is_valid: boolean (from is_valid_observation)
    - vegetation_class: 0 or 1 (1 if ndvi_mean > ndvi_threshold, else 0)

    Raises:
        ValueError: If observation contains invalid numeric values.
    """
    canonical_obs = []

    for obs in observations:
        ndvi_mean = obs["ndvi_mean"]
        vpf = obs.get("valid_pixel_fraction")
        is_valid = obs["is_valid_observation"]

        # Validate ndvi_mean
        if not isinstance(ndvi_mean, (int, float)):
            raise ValueError(f"Invalid ndvi_mean type: {type(ndvi_mean)}")
        if not -1 <= ndvi_mean <= 1:
            raise ValueError(f"ndvi_mean out of range [-1, 1]: {ndvi_mean}")

        # Convert ndvi_mean to milli (integer thousandths)
        ndvi_milli = int(round(ndvi_mean * 1000))

        # Convert valid_pixel_fraction to percent (integer)
        if vpf is not None:
            if not isinstance(vpf, (int, float)):
                raise ValueError(f"Invalid valid_pixel_fraction type: {type(vpf)}")
            if not 0 <= vpf <= 1:
                raise ValueError(f"valid_pixel_fraction out of range [0, 1]: {vpf}")
            valid_pixel_percent = int(round(vpf * 100))
        else:
            valid_pixel_percent = None

        # Determine vegetation class
        # Only classify as vegetated if observation is valid AND ndvi > threshold
        vegetation_class = 1 if (is_valid and ndvi_mean > ndvi_threshold) else 0

        canonical_obs.append({
            "acquired_at": obs["acquired_at"],
            "scene_id": obs.get("scene_id"),  # null if not present
            "ndvi_milli": ndvi_milli,
            "valid_pixel_percent": valid_pixel_percent,
            "is_valid": is_valid,
            "vegetation_class": vegetation_class,
        })

    return canonical_obs


# ---------------------------------------------------------------------------
# Quality block transformation
# ---------------------------------------------------------------------------

def _transform_quality(
    quality: dict[str, Any],
    verifier_threshold: float,
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Transform verifier quality block to canonical evidence format.

    Canonical quality fields:
    - total_rows: int
    - valid_count: int
    - excluded_count: int
    - temporal_coverage_percent: int (0-100) or null
    - covered_intervals: int or null
    - total_intervals: int or null
    - inconclusive_reason: string or null
    """
    tc = quality.get("temporal_coverage")
    if tc is not None:
        temporal_coverage_percent = int(round(tc * 100))
    else:
        temporal_coverage_percent = None

    return {
        "total_rows": quality.get("total_rows", 0),
        "valid_count": quality.get("valid_count", 0),
        "excluded_count": quality.get("excluded_count", 0),
        "temporal_coverage_percent": temporal_coverage_percent,
        "covered_intervals": quality.get("covered_intervals"),
        "total_intervals": quality.get("total_intervals"),
        "inconclusive_reason": quality.get("inconclusive_reason"),
    }


# ---------------------------------------------------------------------------
# Dataset/provenance transformation
# ---------------------------------------------------------------------------

def _transform_dataset(source: dict[str, Any]) -> dict[str, Any]:
    """
    Transform verifier source block to canonical dataset block.
    """
    csv_file = source.get("csv_file")
    if csv_file:
        # Use only the filename, not the full path
        csv_file = Path(csv_file).name

    return {
        "provider": source.get("provider", "unknown"),
        "dataset": source.get("dataset", "unknown"),
        "source_file": csv_file,
        "method": source.get("method", "unknown"),
    }


# ---------------------------------------------------------------------------
# Main evidence document builder
# ---------------------------------------------------------------------------

def build_evidence_document(
    verifier_result: dict[str, Any],
    commitment: Any,  # SQLAlchemy Commitment model instance
    policy: dict[str, Any],
) -> tuple[dict[str, Any], bytes, str]:
    """
    Build the canonical evidence document from verifier result and commitment.

    Args:
        verifier_result: Output from verify_parcel()
        commitment: SQLAlchemy Commitment model instance (must have commitment_id,
                    plan_hash, parcel_id, season_id, verification_policy_id,
                    settle_deadline, plan_snapshot)
        policy: Verification policy dict from fixture

    Returns:
        Tuple of (evidence_document, canonical_bytes, evidence_hash)

    Raises:
        ValueError: If required fields are missing or contain invalid values.
    """
    # --- Validate inputs ---
    required_verifier_keys = {"verdict", "verdict_code", "reason_code", "observations", "quality", "model", "source"}
    missing = required_verifier_keys - set(verifier_result.keys())
    if missing:
        raise ValueError(f"Verifier result missing keys: {missing}")

    if not commitment.commitment_id or not commitment.plan_hash:
        raise ValueError("Commitment missing commitment_id or plan_hash")

    if not commitment.parcel_id or not commitment.season_id:
        raise ValueError("Commitment missing parcel_id or season_id")

    # --- Extract verifier data ---
    verdict = verifier_result["verdict"]
    verdict_code = verifier_result["verdict_code"]
    reason_code = verifier_result["reason_code"]
    observations = verifier_result["observations"]
    quality = verifier_result["quality"]
    model = verifier_result["model"]
    source = verifier_result["source"]

    # Validate verdict
    if verdict not in ("conform", "nonconform", "inconclusive"):
        raise ValueError(f"Invalid verdict: {verdict}")

    if verdict_code not in (0, 1, 2):
        raise ValueError(f"Invalid verdict_code: {verdict_code}")

    # --- Get policy threshold for vegetation_class ---
    ndvi_threshold = policy.get("ndvi_threshold", DEFAULT_NDVI_THRESHOLD)

    # --- Transform observations ---
    canonical_observations = _transform_observations(observations, ndvi_threshold)

    # --- Transform quality ---
    canonical_quality = _transform_quality(quality, ndvi_threshold, observations)

    # --- Transform dataset ---
    canonical_dataset = _transform_dataset(source)

    # --- Model block ---
    canonical_model = {
        "model_version": model.get("model_version", "rule-based-v1"),
        "source": model.get("source", "RULE_BASED"),
    }

    # --- Policy block ---
    canonical_policy = _policy_to_canonical(policy)

    # --- Build evidence document ---
    evidence_id = f"evidence-{commitment.parcel_id}-{commitment.season_id}"
    reason_codes = [verifier_result["reason_code"]] if verifier_result.get("reason_code") else []

    evidence_doc = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "commitment_id": commitment.commitment_id,
        "plan_hash": commitment.plan_hash,
        "parcel_id": commitment.parcel_id,
        "season_id": commitment.season_id,
        "policy": canonical_policy,
        "observations": canonical_observations,
        "quality": canonical_quality,
        "dataset": canonical_dataset,
        "model": canonical_model,
        "verdict": verdict,
        "verdict_code": verdict_code,
    }

    # --- Canonicalize and hash ---
    evidence_bytes, evidence_hash = hash_snapshot(evidence_doc)

    return evidence_doc, evidence_bytes, evidence_hash


def build_attestation(
    commitment: Any,
    evidence_hash: str,
    verdict_code: int,
) -> dict[str, Any]:
    """
    Build the EIP-712 attestation payload.

    This matches the VerificationResult struct in the Solidity contract.
    """
    return {
        "commitmentId": commitment.commitment_id,
        "planHash": commitment.plan_hash,
        "evidenceHash": evidence_hash,
        "verdict": verdict_code,
        "validUntil": commitment.settle_deadline,
    }


def verify_evidence_document(evidence_doc: dict[str, Any]) -> bool:
    """
    Validate that an evidence document conforms to the canonical schema
    and can be canonicalized without errors.

    Returns True if valid, raises ValueError if invalid.
    """
    # Check required top-level keys
    required = {
        "schema_version", "commitment_id", "plan_hash", "parcel_id",
        "season_id", "policy", "observations", "quality",
        "dataset", "model", "verdict", "verdict_code"
    }
    missing = required - set(evidence_doc.keys())
    if missing:
        raise ValueError(f"Evidence document missing required keys: {missing}")

    # Verify it can be canonicalized (no floats, valid types)
    try:
        canonical_bytes(evidence_doc)
    except TypeError as e:
        raise ValueError(f"Evidence document not canonically serializable: {e}")

    # Verify policy structure
    policy = evidence_doc.get("policy", {})
    required_policy = {
        "policy_version", "type", "window_start", "window_end",
        "minimum_observations", "minimum_valid_pixel_percent",
        "minimum_temporal_coverage_percent", "minimum_positive_percent"
    }
    missing_policy = required_policy - set(policy.keys())
    if missing_policy:
        raise ValueError(f"Policy missing required keys: {missing_policy}")

    # Verify observations structure
    for i, obs in enumerate(evidence_doc.get("observations", [])):
        required_obs = {"acquired_at", "scene_id", "ndvi_milli", "valid_pixel_percent", "is_valid", "vegetation_class"}
        missing_obs = required_obs - set(obs.keys())
        if missing_obs:
            raise ValueError(f"Observation {i} missing keys: {missing_obs}")

        # Check types
        if not isinstance(obs["ndvi_milli"], int):
            raise ValueError(f"Observation {i} ndvi_milli must be int")
        if obs["valid_pixel_percent"] is not None and not isinstance(obs["valid_pixel_percent"], int):
            raise ValueError(f"Observation {i} valid_pixel_percent must be int or null")
        if not isinstance(obs["is_valid"], bool):
            raise ValueError(f"Observation {i} is_valid must be bool")
        if obs["vegetation_class"] not in (0, 1):
            raise ValueError(f"Observation {i} vegetation_class must be 0 or 1")

    # Verify quality structure
    quality = evidence_doc.get("quality", {})
    required_quality = {"total_rows", "valid_count", "excluded_count",
                        "temporal_coverage_percent", "covered_intervals",
                        "total_intervals", "inconclusive_reason"}
    missing_quality = required_quality - set(quality.keys())
    if missing_quality:
        raise ValueError(f"Quality missing keys: {missing_quality}")

    # Verify verdict
    if evidence_doc["verdict"] not in ("conform", "nonconform", "inconclusive"):
        raise ValueError(f"Invalid verdict: {evidence_doc['verdict']}")
    if evidence_doc["verdict_code"] not in (0, 1, 2):
        raise ValueError(f"Invalid verdict_code: {evidence_doc['verdict_code']}")

    return True