"""Local FIA ingestion for Phase 3 initialization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from ..config import LandscapeConfig
from ..modules.structure import recompute_cohort_structure
from ..rng import DeterministicRNG
from ..species import SpeciesParams
from ..state import CellVegetation, Cohort
from .geospatial import cell_center_xy


@dataclass(frozen=True)
class FiaPaths:
    plots_path: Path
    trees_path: Path
    conditions_path: Path


def _read_table(table_path: str | Path):
    import pandas as pd

    table_path = Path(table_path)
    if not table_path.exists():
        raise FileNotFoundError(f"FIA table not found: {table_path}")

    suffix = table_path.suffix.lower()
    if suffix == ".csv":
        table = pd.read_csv(table_path)
    elif suffix in {".tsv", ".txt"}:
        table = pd.read_csv(table_path, sep="\t")
    elif suffix == ".parquet":
        table = pd.read_parquet(table_path)
    elif suffix == ".json":
        table = pd.read_json(table_path)
    else:
        raise ValueError(f"Unsupported FIA table format: {table_path}")

    table.columns = [str(column).strip().lower() for column in table.columns]
    return table


def _resolve_column(columns: Sequence[str], candidates: Iterable[str], label: str) -> str:
    available = {column.lower(): column for column in columns}
    for candidate in candidates:
        if candidate.lower() in available:
            return available[candidate.lower()]
    raise ValueError(f"Could not resolve FIA {label}; tried {tuple(candidates)}")


def _optional_column(columns: Sequence[str], candidates: Iterable[str]) -> str | None:
    available = {column.lower(): column for column in columns}
    for candidate in candidates:
        if candidate.lower() in available:
            return available[candidate.lower()]
    return None


def _resolve_plot_coordinates(plots, config: LandscapeConfig):
    import pyproj

    x_column = _optional_column(plots.columns, ("x", "utm_x", "easting", "lon", "longitude"))
    y_column = _optional_column(plots.columns, ("y", "utm_y", "northing", "lat", "latitude"))
    if x_column is None or y_column is None:
        raise ValueError("FIA plots table requires easting/northing or lon/lat columns")

    x = plots[x_column].astype(float).to_numpy()
    y = plots[y_column].astype(float).to_numpy()
    if "lon" in x_column or "longitude" in x_column or "lat" in y_column or "latitude" in y_column:
        transformer = pyproj.Transformer.from_crs(4326, config.epsg, always_xy=True)
        x, y = transformer.transform(x, y)
    return x.astype(float), y.astype(float)


def _load_crosswalk(crosswalk_path: str | Path) -> dict[int, str]:
    import pandas as pd

    crosswalk_path = Path(crosswalk_path)
    if not crosswalk_path.exists():
        raise FileNotFoundError(f"FIA crosswalk not found: {crosswalk_path}")

    suffix = crosswalk_path.suffix.lower()
    if suffix == ".json":
        payload = pd.read_json(crosswalk_path)
    else:
        payload = pd.read_csv(crosswalk_path)
    payload.columns = [str(column).strip().lower() for column in payload.columns]
    spcd_column = _resolve_column(payload.columns, ("spcd", "species_code"), "crosswalk SPCD column")
    pft_column = _resolve_column(payload.columns, ("pft", "target_pft"), "crosswalk PFT column")
    return {int(row[spcd_column]): str(row[pft_column]) for _, row in payload.iterrows()}


def _species_lookup(species_table: Sequence[SpeciesParams]) -> tuple[dict[str, int], dict[int, SpeciesParams]]:
    by_pft = {species.pft: species.species_id for species in species_table}
    by_id = {species.species_id: species for species in species_table}
    return by_pft, by_id


def _tree_age_series(trees, conditions):
    age_column = _optional_column(trees.columns, ("age", "tree_age", "totage"))
    if age_column is not None:
        return trees[age_column].astype(float)
    condition_age_column = _optional_column(conditions.columns, ("stdage", "stand_age", "age"))
    if condition_age_column is None:
        raise ValueError("FIA input requires tree ages or condition stand ages")
    if condition_age_column not in trees.columns:
        raise ValueError("Condition stand age was not propagated onto FIA tree rows")
    return trees[condition_age_column].astype(float)


def _tree_density_series(trees):
    density_column = _optional_column(
        trees.columns,
        ("density_stems_ha", "trees_per_ha", "tph", "tpa_unadj", "trees_per_acre"),
    )
    if density_column is None:
        raise ValueError("FIA trees table requires density_stems_ha, trees_per_ha, tph, or tpa_unadj")
    density = trees[density_column].astype(float)
    if density_column in {"tpa_unadj", "trees_per_acre"}:
        density = density * 2.471053814671653
    return density


def _tree_biomass_series(trees):
    biomass_column = _optional_column(
        trees.columns,
        ("biomass_kg_ha", "ag_biomass_kg_ha", "aboveground_biomass_kg_ha"),
    )
    if biomass_column is not None:
        return trees[biomass_column].astype(float)

    diameter_column = _optional_column(trees.columns, ("dia", "dbh_cm", "diameter_cm"))
    if diameter_column is None:
        raise ValueError("FIA trees table requires biomass_kg_ha or diameter columns")
    density = _tree_density_series(trees).to_numpy(dtype=float)
    diameter_cm = trees[diameter_column].astype(float).to_numpy(dtype=float)
    biomass_per_tree_kg = 0.12 * np.power(np.clip(diameter_cm, 1.0, None), 2.4)
    return density * biomass_per_tree_kg


def _prepare_plot_records(
    plots_path: str | Path,
    trees_path: str | Path,
    conditions_path: str | Path,
    crosswalk_path: str | Path,
    species_table: Sequence[SpeciesParams],
    config: LandscapeConfig,
):
    plots = _read_table(plots_path)
    trees = _read_table(trees_path)
    conditions = _read_table(conditions_path)

    plot_id_column = _resolve_column(plots.columns, ("plot_id", "plt_cn", "cn", "plot"), "plot id")
    tree_plot_id_column = _resolve_column(trees.columns, ("plot_id", "plt_cn", "cn", "plot"), "tree plot id")
    condition_plot_id_column = _resolve_column(conditions.columns, ("plot_id", "plt_cn", "cn", "plot"), "condition plot id")
    tree_condition_column = _optional_column(trees.columns, ("condid", "condition_id"))
    condition_id_column = _optional_column(conditions.columns, ("condid", "condition_id"))

    plots = plots.copy()
    plots["plot_id_join"] = plots[plot_id_column].astype(str)
    trees = trees.copy()
    trees["plot_id_join"] = trees[tree_plot_id_column].astype(str)
    conditions = conditions.copy()
    conditions["plot_id_join"] = conditions[condition_plot_id_column].astype(str)

    if tree_condition_column is not None and condition_id_column is not None:
        trees["condition_id_join"] = trees[tree_condition_column].astype(str)
        conditions["condition_id_join"] = conditions[condition_id_column].astype(str)
        merge_keys = ["plot_id_join", "condition_id_join"]
    else:
        merge_keys = ["plot_id_join"]

    condition_prop_column = _optional_column(conditions.columns, ("condprop_unadj", "condition_proportion"))
    if condition_prop_column is None:
        conditions["condition_weight"] = 1.0
    else:
        conditions["condition_weight"] = conditions[condition_prop_column].astype(float).clip(lower=0.0)

    condition_columns = merge_keys + ["condition_weight"]
    condition_age_column = _optional_column(conditions.columns, ("stdage", "stand_age", "age"))
    if condition_age_column is not None and condition_age_column not in condition_columns:
        condition_columns.append(condition_age_column)
    if condition_id_column and condition_id_column not in merge_keys and condition_id_column not in condition_columns:
        condition_columns.append(condition_id_column)

    trees = trees.merge(conditions[condition_columns], on=merge_keys, how="left")
    trees["condition_weight"] = trees["condition_weight"].fillna(1.0)

    x, y = _resolve_plot_coordinates(plots, config)
    plots["x_utm"] = x
    plots["y_utm"] = y
    plot_coords = plots[["plot_id_join", "x_utm", "y_utm"]].drop_duplicates(subset=["plot_id_join"])

    crosswalk = _load_crosswalk(crosswalk_path)
    species_by_pft, species_by_id = _species_lookup(species_table)

    spcd_column = _resolve_column(trees.columns, ("spcd", "species_code"), "tree SPCD")
    unmapped = sorted({int(value) for value in trees[spcd_column].dropna().unique() if int(value) not in crosswalk})
    if unmapped:
        raise ValueError(f"Missing FIA SPCD to PFT mappings for codes: {unmapped}")

    tree_age = _tree_age_series(trees, conditions).to_numpy(dtype=float)
    tree_density = _tree_density_series(trees).to_numpy(dtype=float) * trees["condition_weight"].to_numpy(dtype=float)
    tree_biomass = _tree_biomass_series(trees).astype(float)
    if hasattr(tree_biomass, "to_numpy"):
        tree_biomass = tree_biomass.to_numpy(dtype=float)
    tree_biomass = tree_biomass * trees["condition_weight"].to_numpy(dtype=float)

    trees["spcd_int"] = trees[spcd_column].astype(int)
    trees["pft"] = trees["spcd_int"].map(crosswalk)
    missing_pfts = sorted({pft for pft in trees["pft"].dropna().unique() if pft not in species_by_pft})
    if missing_pfts:
        raise ValueError(f"Crosswalk PFTs do not exist in the 5-PFT table: {missing_pfts}")

    trees["species_id"] = trees["pft"].map(species_by_pft).astype(int)
    trees["age"] = np.clip(np.rint(tree_age), 1, None).astype(int)
    trees["density_stems_ha"] = np.clip(tree_density, 0.0, None)
    trees["biomass_kg_ha"] = np.clip(tree_biomass, 0.0, None)

    trees = trees.merge(plot_coords, on="plot_id_join", how="left")
    if trees[["x_utm", "y_utm"]].isna().any().any():
        raise ValueError("Some FIA tree rows could not be matched to plot coordinates")

    trees = trees.loc[trees["density_stems_ha"] > 0.0].copy()
    trees = trees.loc[trees["biomass_kg_ha"] > 0.0].copy()
    if trees.empty:
        raise ValueError("FIA ingest produced no live tree records after filtering")

    trees = trees.sort_values(["plot_id_join", "species_id", "age", "biomass_kg_ha"], kind="mergesort").reset_index(drop=True)
    return trees, species_by_id


def _weighted_plot_indices(plot_points: np.ndarray, x: float, y: float, search_radius_m: float) -> tuple[np.ndarray, np.ndarray]:
    distances = np.hypot(plot_points[:, 0] - x, plot_points[:, 1] - y)
    in_radius = np.where(distances <= search_radius_m)[0]
    if in_radius.size > 1:
        chosen = in_radius
    else:
        chosen = np.array([int(np.argmin(distances))], dtype=int)
    chosen_distances = distances[chosen]
    weights = 1.0 / np.maximum(chosen_distances, 1.0)
    weights = weights / weights.sum()
    return chosen, weights


def _build_cell_from_grouped_records(records, species_by_id: dict[int, SpeciesParams], rng: DeterministicRNG, row: int, col: int) -> CellVegetation:
    cell = CellVegetation()
    if records.empty:
        return cell

    for _, grouped in records.iterrows():
        species = species_by_id[int(grouped["species_id"])]
        age = int(grouped["age_bin"]) + 5
        age += int(round(rng.normal(0.0, 1.0, "fia_age_jitter", row, col, species.species_id)))
        age = int(np.clip(age, 1, species.age_max_yr))
        biomass = float(grouped["biomass_kg_ha"]) * (0.92 + 0.16 * rng.uniform("fia_biomass_jitter", row, col, species.species_id))
        density = float(grouped["density_stems_ha"]) * (0.88 + 0.20 * rng.uniform("fia_density_jitter", row, col, species.species_id))
        cohort = Cohort(
            species_id=species.species_id,
            age=age,
            biomass_kg_ha=max(5.0, biomass),
            density_stems_ha=max(1.0, density),
            canopy_height_m=0.0,
            crown_cover_frac=0.0,
            vigor=float(np.clip(0.72 + 0.2 * rng.uniform("fia_vigor", row, col, species.species_id), 0.35, 1.0)),
        )
        recompute_cohort_structure(cohort, species)
        cell.add_or_merge_cohort(cohort, age_window=5, species=species)

    cell.litter_kg_ha = 0.02 * cell.total_biomass_kg_ha
    cell.coarse_woody_debris_kg_ha = 0.01 * cell.total_biomass_kg_ha
    cell.mineral_soil_exposed_frac = float(np.clip(0.08 + 0.25 * (1.0 - cell.total_canopy_cover), 0.05, 0.45))
    return cell


def load_fia_plots(
    fia_paths: FiaPaths | dict[str, str | Path],
    species_table: Sequence[SpeciesParams],
    crosswalk_path: str | Path,
    config: LandscapeConfig,
    *,
    rng_seed: int = 42,
    search_radius_m: float | None = None,
) -> np.ndarray:
    """Build an engine-aligned vegetation grid from local FIA tables."""

    if isinstance(fia_paths, dict):
        paths = FiaPaths(
            plots_path=Path(fia_paths["plots_path"]),
            trees_path=Path(fia_paths["trees_path"]),
            conditions_path=Path(fia_paths["conditions_path"]),
        )
    else:
        paths = fia_paths

    trees, species_by_id = _prepare_plot_records(
        plots_path=paths.plots_path,
        trees_path=paths.trees_path,
        conditions_path=paths.conditions_path,
        crosswalk_path=crosswalk_path,
        species_table=species_table,
        config=config,
    )

    grouped_by_plot = {plot_id: frame.copy() for plot_id, frame in trees.groupby("plot_id_join", sort=True)}
    plot_points = (
        trees[["plot_id_join", "x_utm", "y_utm"]]
        .drop_duplicates(subset=["plot_id_join"])
        .sort_values("plot_id_join", kind="mergesort")
        .reset_index(drop=True)
    )
    if plot_points.empty:
        raise ValueError("No FIA plots intersect the provided site package")

    search_radius_m = float(search_radius_m or max(250.0, config.cell_size_m * 5.0))
    point_coords = plot_points[["x_utm", "y_utm"]].to_numpy(dtype=float)
    west = config.origin_utm[0]
    south = config.origin_utm[1]
    east = west + config.extent_m[0]
    north = south + config.extent_m[1]

    if not np.any(
        (point_coords[:, 0] >= west - search_radius_m)
        & (point_coords[:, 0] <= east + search_radius_m)
        & (point_coords[:, 1] >= south - search_radius_m)
        & (point_coords[:, 1] <= north + search_radius_m)
    ):
        raise ValueError("No FIA plot falls within reach of the site extent; cannot initialize vegetation")

    grid = np.empty(config.shape, dtype=object)
    xx, yy = cell_center_xy(config)
    rng = DeterministicRNG(rng_seed)

    for row in range(config.shape[0]):
        for col in range(config.shape[1]):
            chosen_indices, weights = _weighted_plot_indices(point_coords, float(xx[row, col]), float(yy[row, col]), search_radius_m)
            weighted_frames = []
            for chosen_index, weight in zip(chosen_indices.tolist(), weights.tolist()):
                plot_id = str(plot_points.iloc[chosen_index]["plot_id_join"])
                plot_frame = grouped_by_plot[plot_id].copy()
                plot_frame["density_stems_ha"] *= weight
                plot_frame["biomass_kg_ha"] *= weight
                weighted_frames.append(plot_frame[["species_id", "age", "density_stems_ha", "biomass_kg_ha"]])
            if len(weighted_frames) == 1:
                cell_records = weighted_frames[0]
            else:
                import pandas as pd

                cell_records = pd.concat(weighted_frames, ignore_index=True)
            cell_records["age_bin"] = (cell_records["age"].astype(int) // 10) * 10
            grouped = (
                cell_records.groupby(["species_id", "age_bin"], sort=True, as_index=False)[["density_stems_ha", "biomass_kg_ha"]]
                .sum()
                .sort_values(["species_id", "age_bin"], kind="mergesort")
            )
            grid[row, col] = _build_cell_from_grouped_records(grouped, species_by_id, rng, row, col)
    return grid
