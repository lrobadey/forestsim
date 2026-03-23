from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from wattforest.config import LandscapeConfig
from wattforest.engine import WattForestEngine
from wattforest.species import default_species_table
from wattforest.web_backend import create_backend_app
from wattforest.modules.structure import recompute_cohort_structure
from wattforest.state import CellVegetation, Cohort


def _cohort(species, age: int, biomass_kg_ha: float, density_stems_ha: float) -> Cohort:
    cohort = Cohort(
        species_id=species.species_id,
        age=age,
        biomass_kg_ha=biomass_kg_ha,
        density_stems_ha=density_stems_ha,
        canopy_height_m=0.0,
        crown_cover_frac=0.0,
        vigor=0.9,
    )
    recompute_cohort_structure(cohort, species)
    return cohort


def _engine_with_vegetation() -> WattForestEngine:
    config = LandscapeConfig((80.0, 80.0), 20.0, (500000.0, 4100000.0), 32618)
    shape = config.shape
    species_table = list(default_species_table()[:3])
    vegetation = np.empty(shape, dtype=object)
    for row in range(shape[0]):
        for col in range(shape[1]):
            vegetation[row, col] = CellVegetation(
                cohorts=[
                    _cohort(species_table[0], age=18 + row + col, biomass_kg_ha=2600.0 + 120.0 * row, density_stems_ha=220.0),
                    _cohort(species_table[1], age=32 + row, biomass_kg_ha=1600.0 + 80.0 * col, density_stems_ha=120.0),
                ],
                litter_kg_ha=250.0,
                coarse_woody_debris_kg_ha=120.0,
                mineral_soil_exposed_frac=0.08,
            )
    return WattForestEngine.from_synthetic(
        config,
        species_table=species_table,
        initial_vegetation=vegetation,
    )


def _backend_client(tmp_path: Path) -> TestClient:
    app = create_backend_app(workspace_dir=tmp_path / "workspace", base_engine=_engine_with_vegetation(), start_year=0)
    return TestClient(app)


def _polygon_vertices() -> list[list[float]]:
    return [
        [500005.0, 4100005.0],
        [500045.0, 4100005.0],
        [500045.0, 4100045.0],
        [500005.0, 4100045.0],
    ]


def test_branch_crud_replay_and_tiles(tmp_path: Path):
    client = _backend_client(tmp_path)

    branches = client.get("/api/branches").json()
    assert branches and branches[0]["branch_id"] == "main"
    assert "metrics" in branches[0]
    assert branches[0]["current_year"] == 0

    created = client.post("/api/branches", json={"source_branch_id": "main", "name": "scenario-a"}).json()
    branch_id = created["branch_id"]
    assert created["source_branch_id"] == "main"
    assert created["layers"]

    event_payload = {
        "event_type": "fire_ignition",
        "year": 0,
        "day_of_year": 120,
        "priority": 0,
        "polygon_vertices": _polygon_vertices(),
        "params": {"historical_footprint": True, "severity": 0.9},
        "notes": "polygon burn",
    }
    response = client.post(f"/api/branches/{branch_id}/events", json=event_payload)
    assert response.status_code == 200, response.text
    added = response.json()
    event_id = added["event_id"]
    assert added["polygon_vertices"] == _polygon_vertices()
    events = client.get(f"/api/branches/{branch_id}/events").json()
    assert len(events) == 1
    assert events[0]["event_type"] == "fire_ignition"
    assert events[0]["polygon_vertices"] == _polygon_vertices()

    replay = client.post(f"/api/branches/{branch_id}/replay", json={"year": 0}).json()
    burned_biomass = replay["metrics"]["latest_snapshot"]["total_biomass_kg"]
    metrics = client.get(f"/api/branches/{branch_id}/metrics").json()
    assert metrics["latest_year"] == 0
    assert [point["year"] for point in metrics["series"]] == [0]

    tile = client.get(f"/api/branches/{branch_id}/tiles/canopy_height/0/0/0/0.png")
    assert tile.status_code == 200, tile.text
    assert tile.headers["content-type"] == "image/png"
    assert tile.content.startswith(b"\x89PNG\r\n\x1a\n")

    updated = {
        **event_payload,
        "params": {"historical_footprint": True, "severity": 0.25},
    }
    client.put(f"/api/branches/{branch_id}/events/{event_id}", json=updated)
    replay_after_update = client.post(f"/api/branches/{branch_id}/replay", json={"year": 0}).json()
    assert replay_after_update["metrics"]["latest_snapshot"]["total_biomass_kg"] > burned_biomass

    client.delete(f"/api/branches/{branch_id}/events/{event_id}")
    events_after_delete = client.get(f"/api/branches/{branch_id}/events").json()
    assert events_after_delete == []

    main_replay = client.post("/api/branches/main/replay", json={"year": 0}).json()
    assert replay_after_update["metrics"]["latest_snapshot"]["total_biomass_kg"] < main_replay["metrics"]["latest_snapshot"]["total_biomass_kg"]


def test_climate_shift_and_invalid_custom_event_round_trip_correctly(tmp_path: Path):
    client = _backend_client(tmp_path)
    branch_id = client.get("/api/branches").json()[0]["branch_id"]

    climate_response = client.post(
        f"/api/branches/{branch_id}/events",
        json={
            "event_type": "climate_shift",
            "year": 0,
            "center_xy": [20.0, 20.0],
            "radius_m": 20.0,
            "params": {"gdd_delta": 200.0},
        },
    )
    assert climate_response.status_code == 200, climate_response.text
    assert climate_response.json()["event_type"] == "climate_shift"

    invalid_custom = client.post(
        f"/api/branches/{branch_id}/events",
        json={
            "event_type": "custom",
            "year": 0,
            "center_xy": [20.0, 20.0],
            "radius_m": 20.0,
            "params": {"delegate_event_type": "custom"},
        },
    )
    assert invalid_custom.status_code == 200, invalid_custom.text
    replay_invalid_custom = client.post(f"/api/branches/{branch_id}/replay", json={"year": 0})
    assert replay_invalid_custom.status_code == 400, replay_invalid_custom.text
