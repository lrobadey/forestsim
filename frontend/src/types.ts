export const supportedEventTypes = [
  "fire_ignition",
  "prescribed_burn",
  "windstorm",
  "harvest",
  "grazing_start",
  "grazing_end",
  "river_shift",
  "flood",
  "climate_shift",
  "planting",
  "insect_outbreak",
  "custom",
] as const;

export type SupportedEventType = (typeof supportedEventTypes)[number];

export type ViewKey = "map" | "timeline" | "compare";
export type TileLayerKey =
  | "canopy_height"
  | "dominant_pft"
  | "mean_age"
  | "gap_mask"
  | "disturbance_type_last"
  | "recent_fire_severity";

export interface TileSource {
  url: string;
  width?: number;
  height?: number;
  bounds?: [number, number, number, number];
}

export interface MetricSeriesPoint {
  year: number;
  mean_gap_fraction: number;
  mean_gap_size_ha: number;
  morans_i_canopy_height: number;
  species_richness: number;
  biomass_trajectory_shape: number;
}

export interface BranchMetrics {
  latest_year: number;
  series: MetricSeriesPoint[];
  endpoint_snapshots: {
    canopy_height_mean: number;
    recent_fire_severity_max: number;
    event_count: number;
  };
}

export interface BranchSummary {
  branch_id: string;
  name: string;
  source_branch_id: string | null;
  workspace_path?: string;
  start_year: number;
  current_year: number;
  event_count: number;
  updated_at: string;
  metrics: BranchMetrics;
  extent_m?: [number, number];
  origin_xy?: [number, number];
  cell_size_m?: number;
}

export interface BranchDetail extends BranchSummary {
  description?: string;
  layers?: TileLayerKey[];
}

export interface ExportArtifact {
  path: string;
  branch_id: string;
  layer: string;
  year: number;
}

export interface BranchEvent {
  event_id: string;
  event_type: SupportedEventType | string;
  year: number;
  day_of_year: number;
  priority: number;
  affected_cells?: Array<[number, number]>;
  center_xy?: [number, number];
  radius_m?: number;
  polygon_vertices?: Array<[number, number]>;
  params: Record<string, unknown>;
  branch_id: string;
  created_at: string;
  notes?: string;
}

export type EventGeometry =
  | {
      kind: "circle";
      center_xy: [number, number];
      radius_m: number;
    }
  | {
      kind: "polygon";
      polygon_vertices: Array<[number, number]>;
    }
  | {
      kind: "mask";
      affected_cells: Array<[number, number]>;
    };

export interface EventDraft {
  event_type: SupportedEventType;
  year: number;
  day_of_year: number;
  priority: number;
  geometry: EventGeometry;
  params: Record<string, unknown>;
  notes: string;
}

export interface BranchCreateInput {
  branch_id?: string;
  name: string;
  source_branch_id?: string | null;
}

export interface ReplayInput {
  from_year: number;
}

export interface ScenarioApi {
  listBranches(): Promise<BranchSummary[]>;
  createBranch(input: BranchCreateInput): Promise<BranchDetail>;
  getBranch(branchId: string): Promise<BranchDetail>;
  listEvents(branchId: string): Promise<BranchEvent[]>;
  createEvent(branchId: string, event: BranchEvent): Promise<BranchEvent>;
  updateEvent(branchId: string, eventId: string, event: BranchEvent): Promise<BranchEvent>;
  deleteEvent(branchId: string, eventId: string): Promise<void>;
  replayBranch(branchId: string, input: ReplayInput): Promise<BranchDetail>;
  getMetrics(branchId: string): Promise<BranchMetrics>;
  getTileUrl(branchId: string, layer: TileLayerKey, year: number, z: number, x: number, y: number): string;
  exportGeoTiff(branchId: string, year: number, layer: TileLayerKey): Promise<ExportArtifact>;
  exportNetcdf(branchId: string, year: number, layer: TileLayerKey): Promise<ExportArtifact>;
}
