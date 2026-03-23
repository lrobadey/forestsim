"""Command-line entrypoint for Phase 4 calibration runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .calibration import Phase4CalibrationRun, write_phase4_outputs
from .initializer import LandscapeInitializer


def _result_payload(result: Phase4CalibrationRun) -> dict[str, object]:
    return {
        "site_id": result.site_id,
        "manifest_path": str(result.manifest_path),
        "calibration_spec_path": str(result.calibration_spec_path),
        "start_year": result.start_year,
        "end_year": result.end_year,
        "n_sampled_runs": len(result.sampled_runs),
        "n_accepted_runs": len(result.accepted_runs),
        "best_run": {
            "sample_index": result.best_run.sample_index,
            "total_distance": result.best_run.total_distance,
            "accepted": result.best_run.accepted,
            "passing_family_count": int(sum(result.best_run.family_passes.values())),
        },
        "neutral_baseline": {
            "total_distance": result.neutral_baseline.total_distance,
            "accepted": result.neutral_baseline.accepted,
            "passing_family_count": int(sum(result.neutral_baseline.family_passes.values())),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Phase 4 calibration workflow and emit artifacts.")
    parser.add_argument("manifest_path", help="Path to the Phase 3/4 site manifest JSON.")
    parser.add_argument("--calibration-spec", default=None, help="Optional override path to calibration spec JSON.")
    parser.add_argument("--end-year", type=int, default=None, help="Optional calibration end year override.")
    parser.add_argument("--n-samples", type=int, default=250, help="Number of rejection-ABC samples to evaluate.")
    parser.add_argument("--seed", type=int, default=0, help="Deterministic RNG seed for sampling and sensitivity.")
    parser.add_argument("--sobol-base-n", type=int, default=128, help="Base sample count for Sobol sensitivity.")
    parser.add_argument("--output-dir", default=None, help="Optional directory for CSV and JSON output artifacts.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = LandscapeInitializer.run_phase4_calibration(
        args.manifest_path,
        calibration_spec_path=args.calibration_spec,
        end_year=args.end_year,
        n_samples=args.n_samples,
        seed=args.seed,
        sobol_base_n=args.sobol_base_n,
    )
    payload = _result_payload(result)
    if args.output_dir is not None:
        payload["output_dir"] = str(write_phase4_outputs(args.output_dir, result))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
