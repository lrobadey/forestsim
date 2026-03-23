# Phase 3 Site Targets

Phase 3 stops short of full ABC calibration, but it does need a reproducible way to compare one initialized site package and one baseline simulation against observed patterns. The checked-in synthetic demo package under `data/sites/synthetic_demo/` is the canonical runnable example.

## Supported summary metrics

- `total_biomass_kg`
- `total_biomass_kg_ha`
- `gap_fraction`
- `mean_canopy_height_m`
- `morans_i_height`
- `pft_biomass_kg`
- `pft_biomass_fraction`

These metrics are produced by `wattforest.validation.summarize_engine(...)` and can be compared with `compare_site_patterns(...)`.

## Target file format

Store one JSON file per site package and reference it from the manifest with:

```json
"validation": {
  "targets_path": "site_targets.json"
}
```

The JSON payload should match the `SitePatternSummary` schema. Example:

```json
{
  "total_biomass_kg": 941500.0,
  "total_biomass_kg_ha": 18740.0,
  "gap_fraction": 0.18,
  "mean_canopy_height_m": 17.4,
  "morans_i_height": 0.29,
  "pft_biomass_kg": {
    "pioneer_conifer": 338940.0,
    "shade_tolerant_hardwood": 263620.0
  },
  "pft_biomass_fraction": {
    "pioneer_conifer": 0.36,
    "shade_tolerant_hardwood": 0.28
  }
}
```

## Intended workflow

1. Build the initialized engine from the local manifest.
2. Load optional observed targets from the same manifest.
3. Run a short baseline simulation.
4. Summarize the resulting landscape.
5. Compare observed vs simulated metrics and inspect the aggregate `phase3_validation_score`.

This keeps Phase 3 focused on real-data ingest plus first-pass validation, while leaving broad parameter search and ABC workflows to Phase 4.
