"""FastAPI app factory for the Phase 5 backend."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from .engine import WattForestEngine
from .api.schemas import BranchCreateRequest, BranchEventPayload, ExportRequest, ReplayRequest
from .api.service import BranchRepository


def _to_http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, NotImplementedError):
        return HTTPException(status_code=501, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def create_backend_app(
    *,
    workspace_dir: str | Path,
    base_engine: WattForestEngine | None = None,
    engine_factory: Callable[[], WattForestEngine] | None = None,
    start_year: int = 0,
) -> FastAPI:
    """Create the FastAPI backend with a branch workspace rooted on disk."""

    if base_engine is None:
        if engine_factory is None:
            raise ValueError("create_backend_app requires base_engine or engine_factory")
        base_engine = engine_factory()

    repo = BranchRepository(workspace_dir, base_engine, start_year=start_year)
    app = FastAPI(title="Watt Forest Phase 5 Backend", version="0.1.0")
    app.state.repository = repo

    @app.get("/api/branches")
    def list_branches():
        return [repo._branch_payload(branch.branch_id) for branch in repo.list_branches()]

    @app.post("/api/branches")
    def create_branch(payload: BranchCreateRequest):
        try:
            branch = repo.create_branch(payload.source_branch_id, payload.name)
            return repo._branch_payload(branch.branch_id, include_layers=True)
        except Exception as exc:  # pragma: no cover - narrowed via _to_http_exception
            raise _to_http_exception(exc) from exc

    @app.get("/api/branches/{branch_id}")
    def get_branch(branch_id: str):
        try:
            return repo._branch_payload(branch_id, include_layers=True)
        except Exception as exc:
            raise _to_http_exception(exc) from exc

    @app.get("/api/branches/{branch_id}/events")
    def get_events(branch_id: str):
        try:
            return repo.list_events(branch_id)
        except Exception as exc:
            raise _to_http_exception(exc) from exc

    @app.post("/api/branches/{branch_id}/events")
    def add_event(branch_id: str, payload: BranchEventPayload):
        try:
            event = repo.add_event(branch_id, payload.model_dump())
            return repo.list_events(branch_id)[-1]
        except Exception as exc:
            raise _to_http_exception(exc) from exc

    @app.put("/api/branches/{branch_id}/events/{event_id}")
    def update_event(branch_id: str, event_id: str, payload: BranchEventPayload):
        try:
            event = repo.update_event(branch_id, event_id, payload.model_dump())
            return next(item for item in repo.list_events(branch_id) if item["event_id"] == event.event_id)
        except Exception as exc:
            raise _to_http_exception(exc) from exc

    @app.delete("/api/branches/{branch_id}/events/{event_id}")
    def delete_event(branch_id: str, event_id: str):
        try:
            repo.delete_event(branch_id, event_id)
            return Response(status_code=204)
        except Exception as exc:
            raise _to_http_exception(exc) from exc

    @app.post("/api/branches/{branch_id}/replay")
    def replay_branch(branch_id: str, payload: ReplayRequest):
        try:
            repo.replay_branch(branch_id, payload.year)
            return repo._branch_payload(branch_id, include_layers=True)
        except Exception as exc:
            raise _to_http_exception(exc) from exc

    @app.get("/api/branches/{branch_id}/metrics")
    def get_metrics(branch_id: str):
        try:
            return repo.branch_metrics(branch_id)
        except Exception as exc:
            raise _to_http_exception(exc) from exc

    @app.get("/api/branches/{branch_id}/tiles/{layer}/{year}/{rest:path}")
    def get_tile(branch_id: str, layer: str, year: int, rest: str):
        try:
            z_text, x_text, y_text = str(rest).split("/", 2)
            z_index = int(z_text)
            x_index = int(x_text)
            y_index = int(y_text.removesuffix(".png"))
            png = repo.tile_bytes(branch_id, layer, year, z_index, x_index, y_index)
            return Response(content=png, media_type="image/png")
        except Exception as exc:
            raise _to_http_exception(exc) from exc

    @app.post("/api/exports/geotiff")
    def export_geotiff_endpoint(payload: ExportRequest):
        try:
            path = repo.export_layer(
                branch_id=payload.branch_id,
                layer=payload.layer,
                year=payload.year,
                output_path=payload.output_path,
                format_name="geotiff",
            )
            return {"path": str(path), "branch_id": payload.branch_id, "layer": payload.layer, "year": payload.year}
        except Exception as exc:
            raise _to_http_exception(exc) from exc

    @app.post("/api/exports/netcdf")
    def export_netcdf_endpoint(payload: ExportRequest):
        try:
            path = repo.export_layer(
                branch_id=payload.branch_id,
                layer=payload.layer,
                year=payload.year,
                output_path=payload.output_path,
                format_name="netcdf",
            )
            return {"path": str(path), "branch_id": payload.branch_id, "layer": payload.layer, "year": payload.year}
        except Exception as exc:
            raise _to_http_exception(exc) from exc

    return app
