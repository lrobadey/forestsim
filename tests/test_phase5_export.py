from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from scipy.io import netcdf_file

from wattforest.engine import WattForestEngine
from wattforest.events import EventLog, EventType, SimEvent
from wattforest.config import LandscapeConfig
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


def _fire_event_payload() -> dict[str, object]:
    return {
        "event_type": "fire_ignition",
        "year": 0,
        "day_of_year": 120,
        "priority": 0,
        "polygon_vertices": [
            [500005.0, 4100005.0],
            [500045.0, 4100005.0],
            [500045.0, 4100045.0],
            [500005.0, 4100045.0],
        ],
        "params": {"historical_footprint": True, "severity": 0.9},
        "notes": "polygon burn",
    }


def _fire_event_mask(shape: tuple[int, int]) -> np.ndarray:
    mask = np.zeros(shape, dtype=bool)
    mask[:2, :2] = True
    return mask


def _apply_expected_fire() -> WattForestEngine:
    engine = _engine_with_vegetation()
    event = SimEvent(
        event_id="expected",
        event_type=EventType.FIRE_IGNITION,
        year=0,
        day_of_year=120,
        priority=0,
        affected_cells=_fire_event_mask(engine.config.shape),
        params={"historical_footprint": True, "severity": 0.9},
        notes="polygon burn",
    )
    engine.event_log = EventLog(events=[event], global_seed=42)
    engine.run(0, 0)
    return engine


def _simple_tiff_read(path: Path) -> dict[int, object]:
    data = path.read_bytes()
    assert data[:2] == b"II"
    endian = "<"
    magic = struct.unpack_from(endian + "H", data, 2)[0]
    assert magic == 42
    ifd_offset = struct.unpack_from(endian + "I", data, 4)[0]
    count = struct.unpack_from(endian + "H", data, ifd_offset)[0]
    offset = ifd_offset + 2
    tags: dict[int, object] = {}
    type_sizes = {1: 1, 2: 1, 3: 2, 4: 4, 12: 8}
    for _ in range(count):
        tag, tag_type, value_count, value_or_offset = struct.unpack_from(endian + "HHII", data, offset)
        offset += 12
        size = type_sizes[tag_type] * value_count
        raw = struct.pack(endian + "I", value_or_offset)[:size] if size <= 4 else data[value_or_offset : value_or_offset + size]
        if tag_type == 2:
            tags[tag] = raw.split(b"\x00", 1)[0].decode("ascii")
        elif tag_type == 3:
            tags[tag] = struct.unpack(endian + "H" * value_count, raw)
        elif tag_type == 4:
            tags[tag] = struct.unpack(endian + "I" * value_count, raw)
        elif tag_type == 12:
            tags[tag] = struct.unpack(endian + "d" * value_count, raw)
        else:
            tags[tag] = raw
    return tags


def test_export_geotiff_writes_georeferenced_raster(tmp_path: Path):
    client = _backend_client(tmp_path)
    branch_id = client.post("/api/branches", json={"source_branch_id": "main", "name": "export-branch"}).json()["branch_id"]
    client.post(f"/api/branches/{branch_id}/events", json=_fire_event_payload())
    client.post(f"/api/branches/{branch_id}/replay", json={"year": 0})

    output = tmp_path / "canopy_height.tif"
    response = client.post(
        "/api/exports/geotiff",
        json={"branch_id": branch_id, "year": 0, "layer": "canopy_height", "output_path": str(output)},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert Path(payload["path"]) == output
    assert output.exists()

    tags = _simple_tiff_read(output)
    expected_engine = _apply_expected_fire()
    expected = np.flipud(expected_engine.dominant_height_grid()).astype("<f4")
    assert tags[256] == (expected.shape[1],)
    assert tags[257] == (expected.shape[0],)
    assert tags[339] == (3,)
    assert json.loads(tags[270])["layer"] == "canopy_height"
    assert tags[33550] == (20.0, 20.0, 0.0)
    assert tags[34735][15] == 32618

    strip_offset = tags[273][0]
    strip_byte_count = tags[279][0]
    pixel_bytes = output.read_bytes()[strip_offset : strip_offset + strip_byte_count]
    exported = np.frombuffer(pixel_bytes, dtype="<f4").reshape(expected.shape)
    np.testing.assert_allclose(exported, expected)


def test_export_netcdf_writes_metadata_and_values(tmp_path: Path):
    client = _backend_client(tmp_path)
    branch_id = client.post("/api/branches", json={"source_branch_id": "main", "name": "export-branch"}).json()["branch_id"]
    client.post(f"/api/branches/{branch_id}/events", json=_fire_event_payload())
    client.post(f"/api/branches/{branch_id}/replay", json={"year": 0})

    output = tmp_path / "mean_age.nc"
    response = client.post(
        "/api/exports/netcdf",
        json={"branch_id": branch_id, "year": 0, "layer": "mean_age", "output_path": str(output)},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert Path(payload["path"]) == output
    assert output.exists()

    expected_engine = _apply_expected_fire()
    expected = np.flipud(expected_engine.mean_age_grid()).astype(np.float32)
    with netcdf_file(output, "r") as dataset:
        assert dataset.dimensions["y"] == expected.shape[0]
        assert dataset.dimensions["x"] == expected.shape[1]
        assert int(dataset.crs_epsg) == 32618
        assert int(dataset.year) == 0
        assert json.loads(dataset.origin_utm) == [500000.0, 4100000.0]
        np.testing.assert_allclose(dataset.variables["mean_age"][:], expected)
