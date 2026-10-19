r"""
run_verification.py — CLI entry point for the provisional parcel verifier.

Calls the existing backend.ml.rules.verify_parcel() function (the single
source of truth) for one or all four parcels and writes JSON reports.

This script is a thin adapter: it contains NO verification logic.

Usage (from the repository root):
    .\.venv\Scripts\python.exe scripts\run_verification.py --parcel parcel_01
    .\.venv\Scripts\python.exe scripts\run_verification.py --all
    .\.venv\Scripts\python.exe scripts\run_verification.py --parcel parcel_02 --output-dir data/verification
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.rules import verify_parcel  # noqa: E402

DEFAULT_OUTPUT_DIR = REPO_ROOT / "data/verification"
DEFAULT_EVIDENCE_DIR = REPO_ROOT / "data/ndvi"
DEFAULT_CONFIG = REPO_ROOT / "backend/ml/processing_config.json"

VALID_PARCELS = ("parcel_01", "parcel_02", "parcel_03", "parcel_04")


def _load_policy() -> dict:
    """Load the verification policy from the processing configuration."""
    with open(DEFAULT_CONFIG, encoding="utf-8") as f:
        config = json.load(f)
    return {
        "ndvi_threshold": 0.35,
        "required_fraction": 0.80,
        "min_observations": config["min_valid_observations"],
        "min_valid_pixel_fraction": config["min_valid_pixel_fraction"],
        "min_temporal_coverage": config["temporal_coverage"]["min_temporal_coverage"],
        "temporal_coverage_interval_days": config["temporal_coverage"]["interval_length_days"],
        "window_start": config["time_interval"]["start"],
        "window_end": config["time_interval"]["end"],
    }


def _run_single(parcel_id: str, policy: dict, evidence_dir: Path, output_dir: Path) -> dict:
    """Run verification for one parcel and write its JSON report."""
    result = verify_parcel(parcel_id, policy, str(evidence_dir))

    # Envelope with metadata (the result itself is unchanged)
    envelope = {
        "parcel_id": parcel_id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "validation_status": "experimental_only",
        "disclaimer": (
            "This is an experimental NDVI-based vegetation assessment. "
            "It is NOT organic certification, NOT a compliance verdict, "
            "and does NOT authorize blockchain settlement."
        ),
        "result": result,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{parcel_id}_verification.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, ensure_ascii=False)

    return envelope


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the provisional verifier on real parcel data."
    )
    parser.add_argument(
        "--parcel",
        choices=VALID_PARCELS,
        help="Parcel ID to verify (one of: " + ", ".join(VALID_PARCELS) + ")",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Verify all four parcels",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--evidence-dir",
        default=str(DEFAULT_EVIDENCE_DIR),
        help=f"Evidence directory (default: {DEFAULT_EVIDENCE_DIR})",
    )
    args = parser.parse_args()

    if not args.parcel and not args.all:
        parser.error("Specify --parcel <id> or --all")

    parcel_ids = list(VALID_PARCELS) if args.all else [args.parcel]
    policy = _load_policy()
    evidence_dir = Path(args.evidence_dir)
    output_dir = Path(args.output_dir)

    print("=" * 70)
    print("TERRACYCLE PROOF — VERIFICATION")
    print("=" * 70)
    print(f"Parcels: {', '.join(parcel_ids)}")
    print(f"Evidence: {evidence_dir}")
    print(f"Output: {output_dir}")
    print(f"Window: {policy['window_start']} .. {policy['window_end']}")
    print()

    for pid in parcel_ids:
        envelope = _run_single(pid, policy, evidence_dir, output_dir)
        r = envelope["result"]
        q = r["quality"]
        print(f"{pid}:")
        print(f"  Verdict: {r['verdict']} (code {r['verdict_code']})")
        print(f"  Reason:  {r['reason_code']} — {r['reason']}")
        print(f"  Valid observations: {q['valid_count']}/{q['total_rows']}")
        print(f"  Vegetated: {q['vegetated_count']} (fraction {q['vegetated_fraction']:.2f})")
        print(f"  Temporal coverage: {q['temporal_coverage']}")
        print(f"  Evidence quality: {q['evidence_quality']}")
        if q["warnings"]:
            for w in q["warnings"]:
                print(f"  WARNING: {w}")
        print(f"  Report: {output_dir / f'{pid}_verification.json'}")
        print()

    print("Done. Reports are experimental and do NOT authorize settlement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
