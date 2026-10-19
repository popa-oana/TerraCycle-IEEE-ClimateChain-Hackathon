"""Run the rule-based verifier on all 4 parcels and produce a summary."""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.ml.rules import verify_parcel  # noqa: E402

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


def main():
    evidence_dir = REPO_ROOT / "data/ndvi"
    results = {}
    for i in range(1, 5):
        pid = f"parcel_{i:02d}"
        result = verify_parcel(pid, POLICY, str(evidence_dir))
        results[pid] = result
        q = result["quality"]
        print(f"{pid}: verdict={result['verdict']} "
              f"reason_code={result['reason_code']} "
              f"valid={q['valid_count']}/{q['total_rows']} "
              f"coverage={q['temporal_coverage']} "
              f"vegetated={q['vegetated_count']}")

    # Write summary
    summary = {
        "policy": POLICY,
        "evidence_directory": "data/ndvi",
        "parcels": {
            pid: {
                "verdict": r["verdict"],
                "verdict_code": r["verdict_code"],
                "reason_code": r["reason_code"],
                "reason": r["reason"],
                "valid_observations": r["quality"]["valid_count"],
                "total_rows": r["quality"]["total_rows"],
                "temporal_coverage": r["quality"]["temporal_coverage"],
                "covered_intervals": r["quality"]["covered_intervals"],
                "total_intervals": r["quality"]["total_intervals"],
                "vegetated_count": r["quality"]["vegetated_count"],
                "vegetated_fraction": r["quality"]["vegetated_fraction"],
                "quality_metadata_available": r["quality"]["quality_metadata_available"],
            }
            for pid, r in results.items()
        },
    }
    out_path = REPO_ROOT / "data/features/verification_summary.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nSummary written: {out_path}")


if __name__ == "__main__":
    main()
