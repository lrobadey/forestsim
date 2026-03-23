# Watt Forest Engine

Deterministic, event-sourced forest landscape simulation grounded in Watt's pattern-and-process framework.

## Status

This repository now contains working phase-0 through phase-4 infrastructure. Phase 3 remains the manifest-driven local initialization and baseline validation workflow. Phase 4 layers a deterministic single-site calibration suite on top of that path: richer terminal-year pattern metrics, a rejection-ABC sampler, thresholded family acceptance, one-at-a-time sensitivity, Sobol-style sensitivity indices, and a neutral-baseline comparison. A checked-in synthetic demo site package lives under `data/sites/synthetic_demo/` so the full ingest and calibration path can run without external assets.

## Layout

- `src/wattforest/`: core package
- `tests/`: test scaffolding
- `notebooks/`: Jupyter workflow entry points
- `docs/`: model documentation and calibration notes
- `data/`: synthetic demo and parameter assets

## Milestone Status

- Phase 0: implemented, with characterization tests for canopy closure, gap formation, and spatial structure. Exact old-growth behavior should be reviewed from observed metrics, not fit to a canned target.
- Phase 1: implemented, with hard tests for wind/slope spread, deterministic replay, durable checkpoints, and structural consistency after mortality/fire edits, plus characterization checks for post-fire compositional change.
- Phase 2: implemented. Replay-at-checkpoint-year and fire arrival ordering are hardened, and windthrow, harvest, grazing, river-shift, and multi-disturbance interaction coverage now run in the test suite.
- Phase 3: implemented for local manifest workflows. `LandscapeInitializer.run_phase3_baseline(...)` and `wattforest-phase3` execute the documented workflow end to end: build an engine from a site manifest, run a baseline window, summarize the simulated landscape, resolve optional observed target files, compute observed-vs-simulated comparisons using biomass, gap fraction, Moran's I, canopy height, and PFT composition, and optionally write JSON outputs for downstream review. The checked-in synthetic demo site exercises this path without external data.
- Phase 4: implemented for single-site calibration workflows. `LandscapeInitializer.run_phase4_calibration(...)` and `wattforest-phase4` resolve a calibration spec from the same manifest package, sample species/global parameter overrides deterministically, score each run against multiple independent pattern families, rank accepted parameter sets by weighted distance, and emit sensitivity plus neutral-baseline artifacts for review.

## Phase 3 Workflow

Use `LandscapeInitializer.run_phase3_baseline(...)` to execute the Phase 3 workflow from one local site package:

```python
from wattforest import LandscapeInitializer

result = LandscapeInitializer.run_phase3_baseline("data/sites/synthetic_demo/site_manifest.json", end_year=2025)

engine = result.engine
simulated = result.simulated
observed = result.observed
comparison = result.comparison
```

You can also run the same workflow from the terminal:

```bash
wattforest-phase3 data/sites/synthetic_demo/site_manifest.json --end-year 2025 --output-dir outputs/synthetic_demo
```

If you want the manifest to fully define the baseline window, add `validation.baseline_end_year` and omit the method argument:

```json
"validation": {
  "baseline_end_year": 2025,
  "targets_path": "site_targets.json"
}
```

The manifest contract lives under `data/sites/<site_id>/site_manifest.json` and requires:

- `site_id`, `epsg`, `origin_utm`, `extent_m`, `cell_size_m`, `start_year`
- `dem_path`
- `ssurgo_path`
- `climate.baseline.gdd_path`, `climate.baseline.precip_path`, `climate.baseline.drought_path`, `climate.baseline.frost_free_path`
- `fia.plots_path`, `fia.trees_path`, `fia.conditions_path`, `fia.crosswalk_path`
- `mtbs_path`
- Optional: `climate.yearly_overrides.<year>.gdd_path`, `climate.yearly_overrides.<year>.precip_path`, `climate.yearly_overrides.<year>.drought_path`, `climate.yearly_overrides.<year>.frost_free_path`
- Optional: `landfire.evt`, `landfire.bps`, `landfire.fuel_model`
- Optional: `validation.targets_path`
- Optional: `validation.baseline_end_year`
- Optional: `calibration.spec_path`
- Optional: `calibration.end_year`

Paths may be absolute or relative to the manifest directory. When present, `validation.targets_path` should point to a JSON file matching the `SitePatternSummary` schema exposed by `wattforest.validation`. The checked-in `data/sites/synthetic_demo/` package is a runnable demo rather than a placeholder schema example.

## Phase 4 Workflow

Use `LandscapeInitializer.run_phase4_calibration(...)` to execute the Phase 4 workflow from the same local site package:

```python
from wattforest import LandscapeInitializer

result = LandscapeInitializer.run_phase4_calibration(
    "data/sites/synthetic_demo/site_manifest.json",
    n_samples=250,
    seed=0,
    sobol_base_n=128,
)

best_run = result.best_run
accepted_runs = result.accepted_runs
neutral_baseline = result.neutral_baseline
```

You can also run the calibration pipeline from the terminal:

```bash
wattforest-phase4 data/sites/synthetic_demo/site_manifest.json \
  --n-samples 250 \
  --seed 0 \
  --sobol-base-n 128 \
  --output-dir outputs/<site_id>/phase4
```

The calibration spec is a JSON file referenced by `calibration.spec_path` in the manifest, or passed directly with `--calibration-spec`. The checked-in `data/sites/synthetic_demo/calibration_spec.json` demonstrates the schema:

- `parameter_space`: dotted parameter paths with `{min, max, scale}`
- `metric_targets`: metric/family/observed/tolerance/weight definitions
- `gap_threshold`
- `age_bins`
- `min_pattern_families`

Phase 4 emits these artifacts when `--output-dir` is set:

- `calibration_spec_resolved.json`
- `runs.csv`
- `accepted_runs.csv`
- `best_run.json`
- `neutral_baseline.json`
- `oat_sensitivity.csv`
- `sobol_indices.csv`
- `run_metadata.json`

## Dependencies

Phase 3 adds the geospatial stack to the base environment:

- `rasterio`
- `geopandas`
- `shapely`
- `pyproj`
- `fiona`
- `pandas`
- `pysheds`
- `SALib`

The test suite will skip the Phase 3 geospatial tests if those libraries are not installed, but real-data initialization requires them.

## Known Gaps

Research-backed follow-up work is tracked in `docs/research_backed_model_todos.md`.
