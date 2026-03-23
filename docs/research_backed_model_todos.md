# Research-Backed Simulation TODOs

This document captures the highest-priority gaps between the current codebase and a simulation that can produce convincing, literature-aligned forest results.

It is intentionally organized around implementation surfaces in this repository so each item can be turned into concrete work.

## 1. Product Scope And Runtime Path

- TODO: Decide whether the primary product is the abstract stand-scale prototype or the Python landscape engine, then make the shipped UI reflect that choice.
- TODO: If the prototype remains the default UI, keep describing it as a systems toy and avoid implying that it is already calibrated to real forests.
- TODO: If the landscape engine becomes the primary path, replace the prototype-first landing flow with backend-driven metrics, state, and playback.

## 2. Validation Metrics

- TODO: Fix landscape biomass density reporting so `total_biomass_kg_ha` is computed as an area-weighted landscape mean instead of the raw sum of per-cell `kg/ha`.
- TODO: Audit every downstream consumer of `total_biomass_kg_ha`, especially Phase 3 comparisons and Phase 4 calibration scoring, after correcting the metric.
- TODO: Add regression tests that compare reported `kg/ha` against `total_biomass_kg / total_area_ha` to prevent the bug from returning.
- TODO: Add a test case with nontrivial extent and cell size so unit mistakes are caught by CI.

Why this matters:
- A broken density metric can make calibration outputs look numerically plausible while being off by orders of magnitude.

## 3. Demo Targets And Calibration Specs

- TODO: Replace the current `synthetic_demo` target files with clearly labeled placeholder targets or with externally justified targets derived from observed data.
- TODO: Stop using fixed `min == max` calibration ranges in demo specs when the goal is to show real calibration behavior.
- TODO: Replace near-zero tolerances in demo calibration specs with realistic uncertainty bands that reflect measurement and model error.
- TODO: Record provenance for every target metric in the site package, including the data source, processing method, units, and date.
- TODO: Add a manifest field or sidecar metadata file that distinguishes "simulator-generated fixture targets" from "observed targets."

Why this matters:
- The current demo artifacts are useful as regression fixtures, but they do not establish ecological realism by themselves.

## 4. Prototype Neutral Baseline

- TODO: Recenter the prototype default controls so a neutral run produces a stable forested stand rather than a chronically high-gap, high-fire-risk state.
- TODO: Define explicit acceptance criteria for a neutral baseline, such as target ranges for live-tree count, gap fraction, and disturbance frequency over 20 to 100 simulated years.
- TODO: Add multi-seed regression tests for the neutral baseline so the prototype stays within those bounds after future tuning.
- TODO: Separate "stress-test defaults" from "neutral defaults" if both are useful during design.

Why this matters:
- A simulation can be directionally responsive and still fail as a convincing reference state if its baseline looks permanently stressed.

## 5. Prototype Control Semantics

- TODO: Map the four prototype controls to explicit ecological interpretations and approximate quantitative ranges.
- TODO: Document which controls are exogenous forcings versus which are compressed proxies for multiple mechanisms.
- TODO: Replace purely unitless control labels with helper text or calibrated ranges so users understand what a mid-value means.
- TODO: Add parameter notes explaining which formulas are intentionally abstract and which are meant to approximate real processes.

Research alignment to preserve:
- Disturbance-opportunistic species should benefit more from openings.
- Shade-tolerant species should persist better under suppression.
- Heat and drought should increase mortality and fire risk monotonically.

## 6. Prototype Dynamics And Stability

- TODO: Add long-horizon ensemble tests across many seeds for 20, 60, and 100 year runs.
- TODO: Track whether the prototype converges toward a narrow band of gap fraction, fire risk, and density regardless of scenario, then loosen or rebalance feedbacks if it does.
- TODO: Add tests for scenario separation so "hot", "windy", and "growth-advantaged" runs remain distinguishable in outcome space.
- TODO: Add tests for dominant-temperament turnover and recovery after major disturbance, not just static end-state counts.

## 7. Species / PFT Tables

- TODO: Replace the default `eastern_us_pfts.json` fallback with a regionally appropriate default or require an explicit species asset for site runs.
- TODO: Align the default trait table with the app's stated Pacific Northwest inspiration if that remains the product framing.
- TODO: Add provenance notes for each trait class: shade tolerance, drought tolerance, maturity age, fecundity, dispersal, and flammability.
- TODO: Separate "prototype temperament roles" from "backend PFTs" in documentation so users do not assume they are calibrated equivalents.

Research alignment to preserve:
- Douglas-fir is disturbance-opportunistic, relatively shade-intolerant, and commonly disperses mostly within roughly 100 m of parent trees.
- Western hemlock is highly shade tolerant, commonly establishes under canopy or on moist microsites, and is highly susceptible to fire and windthrow.

## 8. Fire Model

- TODO: Replace the current heuristic rate-of-spread formula with a better-justified spread model or a documented approximation derived from a standard fire model.
- TODO: Distinguish surface fuel load, fuel model, live fuels, dead fuels, and fuel moisture inputs instead of collapsing them into one simple spread term.
- TODO: Incorporate vegetation structure into fire behavior rather than ignoring the passed vegetation grid.
- TODO: Add calibration targets for burned area, severity distribution, and spread anisotropy under known wind and slope settings.
- TODO: State clearly whether the fire module is meant to emulate Rothermel-style spread, a simplified educational surrogate, or something else.

## 9. Windthrow Model

- TODO: Rework the critical wind speed equation so it is justified by mechanical-failure reasoning or published windthrow relationships.
- TODO: Remove or justify the use of `flammability` inside windthrow susceptibility.
- TODO: Add species- and structure-specific factors that better match known windthrow risk drivers, especially height, rooting depth, exposure, and recent edge creation.
- TODO: Add calibration cases for chronic background windthrow versus episodic blowdown.

## 10. Real-Data Initialization And Reproducibility

- TODO: Make the geospatial runtime dependencies easier to install and verify in one step.
- TODO: Add a smoke script or CI target that can run the full manifest-driven workflow when geospatial dependencies are present.
- TODO: Export a compact diagnostic report for each manifest run: site area, occupied-cell fraction, initial biomass, canopy cover, target provenance, and derived metric units.
- TODO: Add a validation warning when observed targets imply a near-empty landscape or otherwise conflict with the manifest extent.

## 11. Research And Documentation Backlog

- TODO: Add a short bibliography file in `docs/` that records which formulas and parameter assumptions are tied to which sources.
- TODO: Separate "used for qualitative direction" from "used for quantitative calibration" in that bibliography.
- TODO: Document where the current model is still a scaffold so downstream users do not mistake passing tests for ecological validation.

## Reference Anchors

- Spies, Franklin, and Klopsch (1990), canopy gaps in Douglas-fir / western hemlock forests: https://andrewsforest.oregonstate.edu/pubs/pdf/pub1074.pdf
- Rothermel (1972), mathematical model for fire spread: https://research.fs.usda.gov/treesearch/32533
- Douglas-fir silvics page: https://research.fs.usda.gov/silvics/douglas-fir
- Western hemlock silvics page: https://research.fs.usda.gov/silvics/western-hemlock
- Larson et al., old-growth mortality rates: https://scholarworks.umt.edu/forest_pubs/55/
- Late-seral Douglas-fir biomass study: https://www.sciencedirect.com/science/article/pii/S0378112725001021
