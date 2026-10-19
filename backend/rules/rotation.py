import hashlib
import json
from typing import Any

CROP_FAMILY = {
    "wheat": "cereal",
    "maize": "cereal",
    "barley": "cereal",
    "sunflower": "asteraceae",
    "rapeseed": "brassicaceae",
    "peas": "legume",
    "soybean": "legume",
    "alfalfa": "legume",
}

ALL_CROPS = list(CROP_FAMILY.keys())


def score_sequence(previous_crop: str, sequence: list[str]) -> dict[str, Any]:
    score = 100
    warnings: list[str] = []
    reasons: list[str] = []
    crops = [previous_crop] + sequence

    for before, after in zip(crops, crops[1:]):
        if before == after:
            score -= 35
            warnings.append(f"Avoid repeating {after} immediately in this demo rule.")
        elif CROP_FAMILY.get(before) == CROP_FAMILY.get(after):
            score -= 10
            warnings.append("Two consecutive crops share a broad family grouping.")
        else:
            reasons.append("Alternation across the demo crop groups.")

    return {"score": max(0, score), "reasons": reasons, "warnings": warnings}


def generate_rotations(requested_crop: str, previous_crop: str) -> list[dict[str, Any]]:
    if requested_crop not in CROP_FAMILY:
        raise ValueError(f"Unknown crop: {requested_crop}")

    candidates = []
    for c2 in ALL_CROPS:
        for c3 in ALL_CROPS:
            if c2 == requested_crop:
                continue
            if c3 == c2:
                continue
            seq = [requested_crop, c2, c3]
            result = score_sequence(previous_crop, seq)
            candidates.append({"sequence": seq, **result})

    candidates.sort(key=lambda x: -x["score"])
    top = candidates[:2]
    max_score = top[0]["score"] if top else 1

    rotations = []
    for i, opt in enumerate(top):
        rotations.append(
            {
                "rotation_id": f"rotation-{i + 1:02d}",
                "crops": [
                    {"year": 2025, "crop_id": opt["sequence"][0]},
                    {"year": 2026, "crop_id": opt["sequence"][1]},
                    {"year": 2027, "crop_id": opt["sequence"][2]},
                ],
                "score": round(opt["score"] / max_score, 2),
                "explanations": opt["reasons"] or ["No specific agronomic reason."],
                "risks": opt["warnings"] or ["No significant risk identified."],
            }
        )
    return rotations


def compute_plan_id(request: dict[str, Any]) -> str:
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "plan-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
