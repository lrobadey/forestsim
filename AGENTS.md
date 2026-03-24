# AGENTS.md

## Project Identity

This repository is a prototype-first forest systems product with an engine-backed future.

The current primary user experience lives in `frontend/`. It is an abstract forest systems dashboard focused on making succession legible.

The Python code under `src/wattforest/` is real and important. It provides the deterministic simulation, validation, calibration, event-sourced branching/backend pieces, and future grounding for the product. Do not present the app as fully backend-driven, fully calibrated, or as a real GIS landscape product unless that integration is implemented and verified in the current code.

When prototype polish and scientific grounding are in tension, preserve honest product messaging and avoid fake coupling.

## Repo Map

- `frontend/`: current product surface, built with React, TypeScript, and Vite
- `src/wattforest/`: core Python engine, backend, API schemas/services, calibration, validation, IO, and simulation modules
- `tests/`: Python test suite for engine, workflows, backend, metrics, determinism, and calibration behavior
- `frontend/tests/`: frontend test suite for the prototype dashboard and related UI behavior
- `data/`, `docs/`, `notebooks/`: supporting assets, specifications, and research workflow material; do not treat these as the main implementation target unless the task explicitly requires them

## Default Agent Behavior

- Inspect the existing code before editing. Follow the current implementation shape before introducing new patterns.
- Finish tasks end to end when practical, but do not guess through meaningful ambiguity. Avoidable guessing is not good autonomy.
- Ask the user when ambiguity affects product wording, UX meaning, workflow behavior, schema/API shape, integration boundaries, destructive changes, or other medium- to high-impact decisions.
- Decide locally when the ambiguity is reversible, local to the implementation, and does not affect product claims, public interfaces, or architectural boundaries.
- Fix problems in the layer that owns the behavior, correctness, or data flow. Do not force frontend-only fixes for backend/model problems, and do not push backend complexity into the UI without a real need.
- Preserve determinism, reproducibility, and testability in engine/backend work.
- Avoid speculative refactors. Change the minimum necessary surface unless the current structure is actively blocking the task.
- Never imply integrations, data flows, scientific fidelity, calibration maturity, or GIS capability that the repository does not currently implement.
- Hard-block changes that would misstate implemented capabilities, scientific grounding, or integration maturity.

## Architecture Guidance

### Frontend

- Treat the frontend as the current product face of the repo.
- Preserve the existing scientific/product language unless the task justifies a different direction.
- Prioritize clarity of:
  - what exists in the forest now
  - what forces are acting on it now
  - why composition is changing
- Keep layouts intentional, hierarchy clear, and copy specific.
- Reject generic "AI dashboard" patterns, weak placeholder states, and visually inconsistent surfaces.
- Handle loading, empty, and error states where the feature actually needs them.
- Do not claim the frontend is driven by the Python engine unless the integration is wired and tested.

### Engine / Backend / Model

- Preserve deterministic behavior, explicit state transitions, and event ordering.
- Extend existing manifest-driven, calibration, validation, replay, and event-sourcing patterns before inventing parallel workflows.
- Keep backend/API changes honest about current scope. A Phase 5 backend endpoint is not the same thing as a fully integrated product workflow.
- Protect existing scientific invariants and characterization behavior unless the task explicitly changes them.

## Implementation Rules

- Prefer existing patterns, types, and module boundaries before adding abstractions.
- Prefer working, connected behavior by default.
- Intentional staged work is allowed when it is safer, clearer, or less misleading than thin temporary wiring.
- Staged work must not leave dead controls, fake coupling, or ambiguous user-facing claims.
- When code is intentionally provisional, stubbed, deferred, or placeholder behavior, add a short comment that states it is temporary, why it is temporary, and what later step or integration is expected.
- Keep business logic out of presentation components when practical.
- Use comments sparingly outside of intentional placeholder/provisional notes.
- Do not add dependencies unless they materially improve the implementation.
- Do not rewrite broad areas of the repo to satisfy local preferences.
- If docs or copy describe system capabilities, ensure they match the actual implementation.

## Docs And Placeholder Comments

- When a change affects user-visible behavior, commands, workflows, config, APIs, or product claims, review and update all relevant docs before the task is done.
- `README.md` is a required check whenever a change affects repo-level capabilities, workflows, setup, status, or product messaging.
- Update docs that would otherwise become stale or misleading. Do not turn this into an unrelated full-repo documentation sweep.
- Placeholder and provisional code paths must be labeled in code with a short reason and next step, not left implicit.

## Verification Rules

Use real commands that exist in the environment and documented repo workflows. Do not invent scripts or reference nonexistent commands.

### Python / Engine Work

- Run targeted `pytest` coverage for the touched area when relevant.
- Use the root Python test suite in `tests/`.
- Supported workflow entry points include:
  - `wattforest-phase3`
  - `wattforest-phase4`

### Frontend Work

- Run the narrowest relevant `npm test` coverage for the touched behavior when UI or frontend logic changes.
- Run `npm run build` in `frontend/` when shipped behavior, bundling, assets, or build output may be affected.

### General

- Do not instruct agents to run nonexistent repo-wide lint or typecheck commands.
- Prefer targeted verification over broad, slow checks when the touched surface is narrow.
- If the touched area already has test coverage, add or update tests to match the change.
- If verification is skipped or blocked, say so explicitly in the final response.

## Definition Of Done

A task is not done until the relevant parts of this list are true:

- the requested behavior works end to end, or is intentionally staged and clearly labeled
- touched code follows existing repo patterns unless a new pattern is justified
- tests are added or updated whenever the touched area already has coverage
- relevant docs were updated when behavior, capabilities, workflows, config, APIs, or claims changed
- no misleading copy, fake coupling, or overstated product claims were introduced
- provisional or placeholder paths are commented when intentionally non-final
- relevant verification was run, or the reason it was not run is stated clearly
- the final response is concise and includes what changed, how it was verified, and any residual risk

## Response Style

- Be concise, direct, and outcome-first.
- Summarize what changed and how it was verified.
- Call out residual risks or unverified assumptions explicitly.
- Avoid long theory dumps unless the user asks for them.
