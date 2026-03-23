import type { BranchDetail, BranchEvent, BranchMetrics, ExportArtifact, TileLayerKey } from "../types";
import { buildEventGeometryLabel } from "../domain";

interface MapViewProps {
  branch: BranchDetail | null;
  events: BranchEvent[];
  metrics: BranchMetrics | null;
  selectedYear: number;
  selectedLayer: TileLayerKey;
  lastExport: ExportArtifact | null;
  loading: boolean;
  saving: boolean;
  onYearChange(year: number): void;
  onLayerChange(layer: TileLayerKey): void;
  buildTileUrl(branchId: string, layer: TileLayerKey, year: number, z: number, x: number, y: number): string;
  onExportGeoTiff(): Promise<void>;
  onExportNetcdf(): Promise<void>;
}

function eventStroke(event: BranchEvent): string {
  switch (event.event_type) {
    case "fire_ignition":
    case "prescribed_burn":
      return "#f8b645";
    case "windstorm":
      return "#3cd0b5";
    case "harvest":
      return "#d9b36c";
    case "flood":
    case "river_shift":
      return "#87b8ff";
    case "insect_outbreak":
      return "#ff8eb4";
    default:
      return "#cbd8d0";
  }
}

export function MapView({
  branch,
  events,
  metrics,
  selectedYear,
  selectedLayer,
  lastExport,
  loading,
  saving,
  onYearChange,
  onLayerChange,
  buildTileUrl,
  onExportGeoTiff,
  onExportNetcdf,
}: MapViewProps) {
  const layerOptions: TileLayerKey[] = [
    "canopy_height",
    "dominant_pft",
    "mean_age",
    "gap_mask",
    "disturbance_type_last",
    "recent_fire_severity",
  ];
  const visibleEvents = events.filter((event) => event.year <= selectedYear);
  const extent = branch?.extent_m ?? [1280, 1280];
  const origin = branch?.origin_xy ?? [0, 0];
  const cellSize = branch?.cell_size_m ?? 20;
  const rasterUrl = branch ? buildTileUrl(branch.branch_id, selectedLayer, selectedYear, 0, 0, 0) : "";

  return (
    <section className="panel map-panel" aria-label="Map view">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Map</p>
          <h2>Replay-backed raster and event geometry</h2>
        </div>
        <div className="inline-status">
          <span>{branch ? branch.name : "No branch loaded"}</span>
          <span>{branch ? `${visibleEvents.length} visible / ${branch.event_count} total events` : "Loading events"}</span>
        </div>
      </div>

      <div className="map-toolbar">
        <label>
          <span>Layer</span>
          <select aria-label="Layer" value={selectedLayer} onChange={(event) => onLayerChange(event.target.value as TileLayerKey)}>
            {layerOptions.map((layer) => (
              <option key={layer} value={layer}>
                {layer.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Year</span>
          <input
            aria-label="Year"
            type="range"
            min={branch?.start_year ?? 2020}
            max={branch?.current_year ?? 2025}
            value={selectedYear}
            onChange={(event) => onYearChange(Number(event.target.value))}
          />
          <strong>{selectedYear}</strong>
        </label>
        <div className="map-actions">
          <button type="button" onClick={() => void onExportGeoTiff()} disabled={!branch || loading || saving}>
            Export GeoTIFF
          </button>
          <button type="button" onClick={() => void onExportNetcdf()} disabled={!branch || loading || saving}>
            Export NetCDF
          </button>
        </div>
      </div>

      <div className="map-stage">
        {branch ? (
          <div className="map-canvas">
            <img className="map-raster" src={rasterUrl} alt={`${selectedLayer.replaceAll("_", " ")} for ${branch.name} in ${selectedYear}`} />
            <svg
              className="map-event-overlay"
              viewBox={`${origin[0]} ${origin[1]} ${extent[0]} ${extent[1]}`}
              preserveAspectRatio="none"
              role="img"
              aria-label={`Event geometry for ${branch.name}`}
            >
              {visibleEvents.map((event) => {
                const stroke = eventStroke(event);
                const label = `${event.event_type} ${event.year} • ${buildEventGeometryLabel(event)}`;

                if (event.polygon_vertices?.length) {
                  return (
                    <polygon
                      key={event.event_id}
                      className="map-event map-event-polygon"
                      points={event.polygon_vertices.map(([x, y]) => `${x},${y}`).join(" ")}
                      stroke={stroke}
                    >
                      <title>{label}</title>
                    </polygon>
                  );
                }

                if (event.center_xy && typeof event.radius_m === "number") {
                  return (
                    <circle
                      key={event.event_id}
                      className="map-event map-event-circle"
                      cx={event.center_xy[0]}
                      cy={event.center_xy[1]}
                      r={event.radius_m}
                      stroke={stroke}
                    >
                      <title>{label}</title>
                    </circle>
                  );
                }

                if (event.affected_cells?.length) {
                  return (
                    <g key={event.event_id} className="map-event map-event-mask">
                      <title>{label}</title>
                      {event.affected_cells.map(([row, col]) => (
                        <rect
                          key={`${event.event_id}-${row}-${col}`}
                          x={origin[0] + col * cellSize}
                          y={origin[1] + row * cellSize}
                          width={cellSize}
                          height={cellSize}
                          stroke={stroke}
                        />
                      ))}
                    </g>
                  );
                }

                return null;
              })}
            </svg>
            <div className="map-grid" />
          </div>
        ) : null}
      </div>

      <div className="map-foot">
        {branch ? (
          <>
            <span>
              Extent {branch.extent_m?.[0] ?? 0} m x {branch.extent_m?.[1] ?? 0} m
            </span>
            <span>{branch.event_count} branch events</span>
            {lastExport ? <span>Last export: {lastExport.path}</span> : null}
          </>
        ) : null}
      </div>
    </section>
  );
}
