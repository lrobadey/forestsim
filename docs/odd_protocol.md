# ODD Protocol

## Overview

The Watt Forest Engine is a deterministic, event-sourced forest landscape simulator organized around interacting plant cohorts, abiotic site layers, and disturbance events. The model emphasizes explicit process interactions over hard-coded target states. The same manifest-driven initialization path supports both baseline validation (Phase 3) and calibration/validation workflows (Phase 4).

## Entities, State Variables, and Scales

- Spatial unit: a rectangular raster landscape defined by `extent_m`, `cell_size_m`, `origin_utm`, and `epsg`.
- Temporal unit: annual time steps with event replay and optional checkpointing.
- Vegetation unit: within each cell, vegetation is represented as a list of cohorts with species identity, age, biomass, density, canopy height, crown cover, and vigor.
- Abiotic layers: terrain (elevation, slope, aspect, TWI, flow accumulation, curvature), soils (AWC, rooting restriction depth, texture class, rock fraction), and climate (GDD, precipitation, drought, frost-free days).
- Disturbance state: recent fire severity, recent aggregate disturbance severity, regeneration delay, time since disturbance, litter, coarse woody debris, mineral soil exposure, and optional grazing or river-shift modifiers.

## Process Overview and Scheduling

For each simulated year the engine executes the following sequence:

1. Reset annual disturbance counters.
2. Apply all events scheduled for the year from the event log.
3. Update climate placeholders.
4. Compute canopy and ground light.
5. Grow cohorts based on species traits, light, climate, and soil.
6. Apply stress/background mortality and local gap turnover.
7. Establish recruits from local seed rain plus immigration.
8. Update fuels and disturbance memory.
9. Record annual summary metrics.
10. Save checkpoints at the configured interval.

The event log is deterministic. Replay from any prior year restores the nearest checkpoint, then reruns forward with the same random stream partitioning.

## Design Concepts

- Emergence: stand structure, patchiness, species composition, and gap dynamics arise from repeated cohort growth, mortality, recruitment, and disturbance interactions.
- Adaptation: species differ by growth, allometry, shade tolerance, climate limits, mortality rates, fecundity, dispersal, and flammability traits.
- Objectives: there is no utility-maximizing agent. Disturbance modules respond to physical forcing or prescribed event parameters.
- Sensing: cohorts respond indirectly through light availability, climate, soil moisture proxies, and disturbance memory.
- Interaction: cohorts interact through light competition, substrate opening, seed rain, and disturbance-mediated mortality.
- Stochasticity: deterministic pseudo-random draws govern mortality, recruitment, and windthrow/fire spread outcomes. Identical inputs and seeds reproduce identical trajectories.
- Observation: the engine emits yearly records plus terminal summaries for validation and calibration.

## Initialization

Phase 3 and Phase 4 both initialize from a local site manifest:

- DEM raster for terrain derivation.
- SSURGO-style vector polygons for soil attributes.
- Climate rasters aligned to the landscape grid.
- FIA-style plot/tree/condition tables plus a species-to-PFT crosswalk.
- MTBS-derived fire history converted into seeded historical events.

The same initializer can also build synthetic landscapes for tests and notebooks.

## Submodels

### Growth

Growth uses species-specific maximum growth rates and allometric normalization under light, climate, and soil constraints. Cohort vigor is updated from realized growth.

### Mortality

Mortality combines age-scaled background loss with vigor-based stress mortality. Additional stress multipliers create gap turnover and site-level dieback under poor drought/rock conditions.

### Recruitment

Recruitment uses 2Dt seed dispersal kernels, light thresholds, climate filters, disturbance opening effects, and grazing/river modifiers. Establishment probability and disturbance response can be scaled globally during calibration.

### Fire

Fire spread is resolved on the raster with wind and slope effects. Burn severity feeds mortality, fuel consumption, mineral soil exposure, and regeneration delay.

### Windthrow

Windthrow uses exposure, ridge position, rooting depth, and canopy height to estimate damage probability. Damage severity propagates to cohort mortality and disturbance memory.

### Harvest, Grazing, and River Shift

Harvest removes biomass according to event parameters. Grazing suppresses recruitment in active cells. River shift scours vegetation and leaves persistent moisture and recruitment modifiers.

## Outputs

- Yearly `YearRecord` summaries for biomass, canopy height, gap fraction, Moran's I, disturbance areas, and species presence.
- Phase 3 site summaries for biomass, gap fraction, canopy height, Moran's I, and PFT composition.
- Phase 4 pattern snapshots for biomass, canopy height, gap quantiles, dominant-PFT patch quantiles, Moran's I, PFT biomass fractions, and biomass-weighted age distributions.

## Calibration and Validation

Phase 3 validation compares one initialized site against optional observed summary targets.

Phase 4 extends that workflow with:

- A calibration spec defining parameter ranges and metric targets.
- Dotted override paths for species traits and a small set of global disturbance/recruitment scalars.
- Deterministic rejection-ABC sampling with weighted distance ranking.
- Family-based acceptance: each family passes only if all of its metrics pass; a parameter set is accepted when at least `min_pattern_families` families pass.
- One-at-a-time sensitivity around the anchor solution.
- Sobol-style first-order and total-order sensitivity indices on the weighted total distance.
- A neutral baseline created by replacing all tunable species traits with across-species means while keeping the calibrated global scalars.

## Known Limits

- Calibration is currently single-site and serial.
- Real-site Phase 4 runs still depend on local geospatial data assets.
- Expensive spatial metrics are summarized at the terminal snapshot rather than every year.
- The disturbance parameter surface remains intentionally thin in v1; most disturbance internals are still encoded as module constants.
