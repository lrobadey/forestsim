"""Command-line entrypoint for Phase 3 manifest runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .initializer import LandscapeInitializer, Phase3BaselineRun
from .validation import write_site_pattern_summary


def _result_payload(result: Phase3BaselineRun) -> dict[str, object]:
    payload: dict[str, object] = {
        "site_id": result.site_id,
        "manifest_path": str(result.manifest_path),
        "start_year": result.start_year,
        "end_year": result.end_year,
        "simulated": result.simulated.to_dict(),
    }
    if result.observed is not None:
        payload["observed"] = result.observed.to_dict()
    if result.comparison is not None:
        payload["comparison"] = result.comparison
    return payload


def write_phase3_outputs(output_dir: str | Path, result: Phase3BaselineRun) -> Path:
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)

    write_site_pattern_summary(directory / "simulated_summary.json", result.simulated)
    if result.observed is not None:
        write_site_pattern_summary(directory / "observed_summary.json", result.observed)
    if result.comparison is not None:
        (directory / "comparison.json").write_text(json.dumps(result.comparison, indent=2, sort_keys=True) + "\n")

    metadata = {
        "site_id": result.site_id,
        "manifest_path": str(result.manifest_path),
        "start_year": result.start_year,
        "end_year": result.end_year,
    }
    (directory / "run_metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Phase 3 manifest workflow and emit summaries.")
    parser.add_argument("manifest_path", help="Path to the Phase 3 site manifest JSON.")
    parser.add_argument("--end-year", type=int, default=None, help="Optional simulation end year.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional directory for simulated_summary.json, observed_summary.json, comparison.json, and run_metadata.json.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = LandscapeInitializer.run_phase3_baseline(args.manifest_path, end_year=args.end_year)
    payload = _result_payload(result)
    if args.output_dir is not None:
        payload["output_dir"] = str(write_phase3_outputs(args.output_dir, result))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
