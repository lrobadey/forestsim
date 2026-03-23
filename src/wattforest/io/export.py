"""Raster export helpers for GeoTIFF and NetCDF outputs."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Mapping

import numpy as np

from ..config import LandscapeConfig

_TIFF_TAGS = {
    "ImageWidth": 256,
    "ImageLength": 257,
    "BitsPerSample": 258,
    "Compression": 259,
    "PhotometricInterpretation": 262,
    "ImageDescription": 270,
    "StripOffsets": 273,
    "SamplesPerPixel": 277,
    "RowsPerStrip": 278,
    "StripByteCounts": 279,
    "PlanarConfiguration": 284,
    "SampleFormat": 339,
    "ModelPixelScaleTag": 33550,
    "ModelTiepointTag": 33922,
    "GeoKeyDirectoryTag": 34735,
}

_TIFF_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 12: 8}


def _as_array(array: np.ndarray | object) -> np.ndarray:
    result = np.asarray(array)
    if result.ndim != 2:
        raise ValueError("Raster exports require a 2D array")
    return np.ascontiguousarray(result)


def _normalize_for_north_up(array: np.ndarray) -> np.ndarray:
    return np.flipud(_as_array(array))


def _dtype_spec(array: np.ndarray) -> tuple[np.dtype, int, int]:
    dtype = np.asarray(array).dtype
    if dtype.kind == "f":
        return np.dtype("<f4"), 3, 32
    if dtype.kind == "b":
        return np.dtype("uint8"), 1, 8
    if dtype.kind == "u":
        if dtype.itemsize <= 1:
            return np.dtype("uint8"), 1, 8
        if dtype.itemsize <= 2:
            return np.dtype("<u2"), 1, 16
        return np.dtype("<u4"), 1, 32
    if dtype.kind == "i":
        if dtype.itemsize <= 1:
            return np.dtype("<i1"), 2, 8
        if dtype.itemsize <= 2:
            return np.dtype("<i2"), 2, 16
        return np.dtype("<i4"), 2, 32
    raise TypeError(f"Unsupported raster dtype for export: {dtype}")


def _pack_ascii(text: str) -> bytes:
    payload = text.encode("ascii", errors="replace")
    if not payload.endswith(b"\x00"):
        payload += b"\x00"
    return payload


def _pack_values(tag_type: int, values: object) -> bytes:
    if tag_type == 2:
        if isinstance(values, (str, bytes)):
            return _pack_ascii(values.decode() if isinstance(values, bytes) else values)
        raise TypeError("ASCII tag requires string input")

    if not isinstance(values, (tuple, list, np.ndarray)):
        values = [values]

    if tag_type == 3:
        return struct.pack("<" + "H" * len(values), *[int(value) for value in values])
    if tag_type == 4:
        return struct.pack("<" + "I" * len(values), *[int(value) for value in values])
    if tag_type == 12:
        return struct.pack("<" + "d" * len(values), *[float(value) for value in values])
    if tag_type == 1:
        return bytes(int(value) & 0xFF for value in values)
    raise TypeError(f"Unsupported TIFF tag type: {tag_type}")


def _geokey_directory(epsg: int) -> bytes:
    entries = [
        1, 1, 0, 4,
        1024, 0, 1, 1,
        1025, 0, 1, 1,
        3072, 0, 1, int(epsg),
        3076, 0, 1, 9001,
    ]
    return struct.pack("<" + "H" * len(entries), *entries)


def _tiff_tag_bytes(tag_type: int, values: object) -> bytes:
    if isinstance(values, bytes):
        return values
    return _pack_values(tag_type, values)


def export_geotiff(
    path: str | Path,
    array: np.ndarray | object,
    config: LandscapeConfig,
    *,
    layer_name: str,
    year: int,
    branch_id: str,
    metadata: Mapping[str, object] | None = None,
) -> Path:
    """Write a single-band GeoTIFF for a north-up raster snapshot."""

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    raster = _normalize_for_north_up(array)
    dtype, sample_format, bits_per_sample = _dtype_spec(raster)
    raster = np.ascontiguousarray(raster.astype(dtype, copy=False))
    height, width = raster.shape
    pixel_bytes = raster.tobytes(order="C")

    description = {
        "branch_id": branch_id,
        "layer": layer_name,
        "year": int(year),
        "shape": [int(height), int(width)],
        "crs_epsg": int(config.epsg),
    }
    if metadata:
        description.update(metadata)

    geokey_bytes = _geokey_directory(config.epsg)
    tag_specs: list[tuple[int, int, object]] = [
        (_TIFF_TAGS["ImageWidth"], 4, width),
        (_TIFF_TAGS["ImageLength"], 4, height),
        (_TIFF_TAGS["BitsPerSample"], 3, bits_per_sample),
        (_TIFF_TAGS["Compression"], 3, 1),
        (_TIFF_TAGS["PhotometricInterpretation"], 3, 1),
        (_TIFF_TAGS["ImageDescription"], 2, json.dumps(description, sort_keys=True)),
        (_TIFF_TAGS["StripOffsets"], 4, 0),
        (_TIFF_TAGS["SamplesPerPixel"], 3, 1),
        (_TIFF_TAGS["RowsPerStrip"], 4, height),
        (_TIFF_TAGS["StripByteCounts"], 4, len(pixel_bytes)),
        (_TIFF_TAGS["PlanarConfiguration"], 3, 1),
        (_TIFF_TAGS["SampleFormat"], 3, sample_format),
        (_TIFF_TAGS["ModelPixelScaleTag"], 12, [config.cell_size_m, config.cell_size_m, 0.0]),
        (
            _TIFF_TAGS["ModelTiepointTag"],
            12,
            [0.0, 0.0, 0.0, float(config.origin_utm[0]), float(config.origin_utm[1] + config.extent_m[1]), 0.0],
        ),
        (_TIFF_TAGS["GeoKeyDirectoryTag"], 3, geokey_bytes),
    ]

    ifd_entries: list[tuple[int, int, int, bytes | None, bytes | None]] = []
    extra_payloads: list[bytes] = []
    for tag, tag_type, values in tag_specs:
        payload = _tiff_tag_bytes(tag_type, values)
        count = len(payload) // _TIFF_TYPE_SIZES[tag_type]
        if len(payload) <= 4:
            ifd_entries.append((tag, tag_type, count, payload.ljust(4, b"\x00"), None))
        else:
            ifd_entries.append((tag, tag_type, count, None, payload))
            extra_payloads.append(payload)

    ifd_size = 2 + len(ifd_entries) * 12 + 4
    extra_size = sum(len(payload) for payload in extra_payloads)
    strip_offset = 8 + ifd_size + extra_size

    patched_entries: list[tuple[int, int, int, bytes | None, bytes | None]] = []
    for tag, tag_type, count, inline_payload, payload in ifd_entries:
        if tag == _TIFF_TAGS["StripOffsets"]:
            patched_entries.append((tag, tag_type, 1, struct.pack("<I", strip_offset), None))
        else:
            patched_entries.append((tag, tag_type, count, inline_payload, payload))

    with out_path.open("wb") as handle:
        handle.write(b"II")
        handle.write(struct.pack("<H", 42))
        handle.write(struct.pack("<I", 8))
        handle.write(struct.pack("<H", len(patched_entries)))
        extra_cursor = 0
        for tag, tag_type, count, inline_payload, payload in patched_entries:
            if payload is None:
                handle.write(struct.pack("<HHI4s", tag, tag_type, count, inline_payload or b"\x00\x00\x00\x00"))
            else:
                offset = 8 + ifd_size + extra_cursor
                handle.write(struct.pack("<HHII", tag, tag_type, count, offset))
                extra_cursor += len(payload)
        handle.write(struct.pack("<I", 0))
        for payload in extra_payloads:
            handle.write(payload)
        handle.write(pixel_bytes)
    return out_path


def export_netcdf(
    path: str | Path,
    array: np.ndarray | object,
    config: LandscapeConfig,
    *,
    layer_name: str,
    year: int,
    branch_id: str,
    metadata: Mapping[str, object] | None = None,
) -> Path:
    """Write a classic NetCDF file for a north-up raster snapshot."""

    from scipy.io import netcdf_file

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    raster = _normalize_for_north_up(array)
    dtype, _, _ = _dtype_spec(raster)
    if dtype.kind == "u":
        dtype = np.dtype("<i4")
        raster = raster.astype(dtype, copy=False)
    elif dtype.kind == "b":
        dtype = np.dtype("<i1")
        raster = raster.astype(dtype, copy=False)
    else:
        raster = raster.astype(dtype, copy=False)

    rows, cols = raster.shape
    x_coords = config.origin_utm[0] + (np.arange(cols, dtype=np.float64) + 0.5) * config.cell_size_m
    y_coords = config.origin_utm[1] + config.extent_m[1] - (np.arange(rows, dtype=np.float64) + 0.5) * config.cell_size_m

    with netcdf_file(out_path, "w") as dataset:
        dataset.createDimension("y", rows)
        dataset.createDimension("x", cols)
        x_var = dataset.createVariable("x", "f8", ("x",))
        y_var = dataset.createVariable("y", "f8", ("y",))
        data_var = dataset.createVariable(layer_name, raster.dtype.char, ("y", "x"))

        x_var[:] = x_coords
        y_var[:] = y_coords
        data_var[:] = raster

        dataset.layer_name = layer_name
        dataset.branch_id = branch_id
        dataset.year = int(year)
        dataset.crs_epsg = int(config.epsg)
        dataset.cell_size_m = float(config.cell_size_m)
        dataset.origin_utm = json.dumps([float(config.origin_utm[0]), float(config.origin_utm[1])])
        dataset.extent_m = json.dumps([float(config.extent_m[0]), float(config.extent_m[1])])
        dataset.variable_metadata = json.dumps(dict(metadata or {}), sort_keys=True)
    return out_path
