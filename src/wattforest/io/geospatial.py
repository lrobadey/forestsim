"""Shared geospatial utilities for Phase 3 local-file initialization."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from ..config import LandscapeConfig


def target_bounds(config: LandscapeConfig) -> tuple[float, float, float, float]:
    """Return target bounds as (west, south, east, north)."""

    west = float(config.origin_utm[0])
    south = float(config.origin_utm[1])
    east = west + float(config.extent_m[0])
    north = south + float(config.extent_m[1])
    return west, south, east, north


def target_transform(config: LandscapeConfig):
    """Return a north-up affine transform for the target grid."""

    from rasterio.transform import from_origin

    west, _, _, north = target_bounds(config)
    return from_origin(west, north, config.cell_size_m, config.cell_size_m)


def cell_center_xy(config: LandscapeConfig) -> tuple[np.ndarray, np.ndarray]:
    """Return south-up cell-center coordinates aligned to engine indexing."""

    rows, cols = config.shape
    x = config.origin_utm[0] + (np.arange(cols, dtype=np.float64) + 0.5) * config.cell_size_m
    y = config.origin_utm[1] + (np.arange(rows, dtype=np.float64) + 0.5) * config.cell_size_m
    xx, yy = np.meshgrid(x, y)
    return xx, yy


def _engine_to_raster_orientation(array: np.ndarray) -> np.ndarray:
    return np.flipud(np.asarray(array))


def _raster_to_engine_orientation(array: np.ndarray) -> np.ndarray:
    return np.flipud(np.asarray(array))


def read_raster_to_grid(
    raster_path: str | Path,
    config: LandscapeConfig,
    *,
    categorical: bool = False,
    dtype: np.dtype | type | None = None,
    fail_on_nodata: bool = False,
) -> np.ndarray:
    """Reproject and resample a raster onto the landscape grid."""

    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    raster_path = Path(raster_path)
    if not raster_path.exists():
        raise FileNotFoundError(f"Raster not found: {raster_path}")

    resampling = Resampling.nearest if categorical else Resampling.bilinear
    out_dtype = np.dtype(dtype or np.float32)
    dst_nodata = np.nan if np.issubdtype(out_dtype, np.floating) else 0

    with rasterio.open(raster_path) as src:
        if src.count != 1:
            raise ValueError(f"Expected single-band raster at {raster_path}, found {src.count} bands")

        destination = np.full(config.shape, dst_nodata, dtype=out_dtype)
        coverage = np.zeros(config.shape, dtype=np.uint8)
        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=target_transform(config),
            dst_crs=f"EPSG:{config.epsg}",
            dst_nodata=dst_nodata,
            resampling=resampling,
        )

        reproject(
            source=src.dataset_mask(),
            destination=coverage,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=0,
            dst_transform=target_transform(config),
            dst_crs=f"EPSG:{config.epsg}",
            dst_nodata=0,
            resampling=Resampling.nearest,
        )

    if fail_on_nodata and np.any(coverage == 0):
        raise ValueError(f"Raster {raster_path} has nodata gaps inside the target extent")

    if categorical:
        destination = np.rint(destination).astype(out_dtype, copy=False)

    return _raster_to_engine_orientation(destination)


def read_vector_layer(vector_path: str | Path, epsg: int):
    """Load a vector layer and reproject it to the target EPSG."""

    import geopandas as gpd

    vector_path = Path(vector_path)
    if not vector_path.exists():
        raise FileNotFoundError(f"Vector layer not found: {vector_path}")

    frame = gpd.read_file(vector_path)
    if frame.empty:
        raise ValueError(f"Vector layer is empty: {vector_path}")
    if frame.crs is None:
        raise ValueError(f"Vector layer is missing CRS metadata: {vector_path}")
    if int(frame.crs.to_epsg() or -1) != int(epsg):
        frame = frame.to_crs(epsg=epsg)
    return frame


def rasterize_shapes(
    shapes: Iterable[tuple[object, int | float]],
    config: LandscapeConfig,
    *,
    fill: int | float,
    dtype: np.dtype | type,
    all_touched: bool = False,
) -> np.ndarray:
    """Rasterize values onto the target grid and return engine-oriented arrays."""

    from rasterio.features import rasterize

    array = rasterize(
        list(shapes),
        out_shape=config.shape,
        transform=target_transform(config),
        fill=fill,
        dtype=np.dtype(dtype).name,
        all_touched=all_touched,
    )
    return _raster_to_engine_orientation(array.astype(dtype, copy=False))


def rasterize_mask(
    geometries: Sequence[object],
    config: LandscapeConfig,
    *,
    all_touched: bool = True,
) -> np.ndarray:
    """Rasterize a geometry sequence into a boolean engine mask."""

    if not geometries:
        return np.zeros(config.shape, dtype=bool)
    values = ((geometry, 1) for geometry in geometries)
    return rasterize_shapes(values, config, fill=0, dtype=np.uint8, all_touched=all_touched).astype(bool)


def clip_to_extent(frame, config: LandscapeConfig):
    """Clip a GeoDataFrame-like object to the landscape bounds."""

    west, south, east, north = target_bounds(config)
    bounds = (west, south, east, north)
    return frame.cx[bounds[0] : bounds[2], bounds[1] : bounds[3]]
