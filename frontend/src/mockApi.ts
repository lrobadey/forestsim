import type {
  BranchCreateInput,
  BranchDetail,
  BranchEvent,
  ExportArtifact,
  BranchMetrics,
  BranchSummary,
  MetricSeriesPoint,
  ReplayInput,
  ScenarioApi,
  TileLayerKey,
} from "./types";

interface MockBranchState {
  detail: BranchDetail;
  events: BranchEvent[];
  profileOffset: number;
  terrainSeed: number;
}

const GRID_CELLS = 48;
const SVG_SIZE = 480;

function clone<T>(value: T): T {
  return structuredClone(value);
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function smoothstep(value: number): number {
  return value * value * (3 - 2 * value);
}

function fract(value: number): number {
  return value - Math.floor(value);
}

function hashString(input: string): number {
  let hash = 2166136261;
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function seededValue(x: number, y: number, seed: number): number {
  return fract(Math.sin(x * 127.1 + y * 311.7 + seed * 74.7) * 43758.5453123);
}

function smoothNoise(x: number, y: number, seed: number): number {
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const tx = smoothstep(x - x0);
  const ty = smoothstep(y - y0);

  const top = lerp(seededValue(x0, y0, seed), seededValue(x0 + 1, y0, seed), tx);
  const bottom = lerp(seededValue(x0, y0 + 1, seed), seededValue(x0 + 1, y0 + 1, seed), tx);
  return lerp(top, bottom, ty);
}

function octaveNoise(x: number, y: number, seed: number): number {
  let amplitude = 0.6;
  let frequency = 1;
  let total = 0;
  let weight = 0;

  for (let octave = 0; octave < 4; octave += 1) {
    total += smoothNoise(x * frequency, y * frequency, seed + octave * 19) * amplitude;
    weight += amplitude;
    amplitude *= 0.5;
    frequency *= 2;
  }

  return total / Math.max(weight, 1e-6);
}

function mixColor(a: [number, number, number], b: [number, number, number], t: number): [number, number, number] {
  return [
    Math.round(lerp(a[0], b[0], t)),
    Math.round(lerp(a[1], b[1], t)),
    Math.round(lerp(a[2], b[2], t)),
  ];
}

function colorString(color: [number, number, number]): string {
  return `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
}

function colorForScalar(stops: Array<{ stop: number; color: [number, number, number] }>, value: number): [number, number, number] {
  const normalized = clamp(value, 0, 1);
  for (let index = 1; index < stops.length; index += 1) {
    const previous = stops[index - 1];
    const next = stops[index];
    if (normalized <= next.stop) {
      const local = (normalized - previous.stop) / Math.max(next.stop - previous.stop, 1e-6);
      return mixColor(previous.color, next.color, local);
    }
  }
  return stops[stops.length - 1].color;
}

function pointInPolygon(point: [number, number], polygon: Array<[number, number]>): boolean {
  let inside = false;

  for (let current = 0, previous = polygon.length - 1; current < polygon.length; previous = current, current += 1) {
    const [x1, y1] = polygon[current];
    const [x2, y2] = polygon[previous];
    const intersects =
      y1 > point[1] !== y2 > point[1] &&
      point[0] < ((x2 - x1) * (point[1] - y1)) / Math.max(y2 - y1, 1e-6) + x1;
    if (intersects) {
      inside = !inside;
    }
  }

  return inside;
}

function normalizeEventIds(events: BranchEvent[], branchId: string): BranchEvent[] {
  return events.map((event, index) => ({
    ...clone(event),
    event_id: `${branchId}-event-${index + 1}`,
    branch_id: branchId,
  }));
}

function makeSeries(baseYear: number, offsets: number): MetricSeriesPoint[] {
  return Array.from({ length: 5 }, (_, index) => {
    const year = baseYear + index;
    return {
      year,
      mean_gap_fraction: 0.15 + offsets * 0.01 + index * 0.015,
      mean_gap_size_ha: 0.4 + offsets * 0.03 + index * 0.025,
      morans_i_canopy_height: 0.22 + offsets * 0.02 + index * 0.01,
      species_richness: 6 + offsets + index,
      biomass_trajectory_shape: 0.5 + offsets * 0.04 + index * 0.02,
    };
  });
}

function makeMetrics(branchId: string, currentYear: number, eventCount: number, offsets: number): BranchMetrics {
  return {
    latest_year: currentYear,
    series: makeSeries(currentYear - 4, offsets),
    endpoint_snapshots: {
      canopy_height_mean: 18 + offsets * 1.4,
      recent_fire_severity_max: branchId.includes("burn") ? 0.72 : 0.24 + offsets * 0.03,
      event_count: eventCount,
    },
  };
}

function makeDetail(branchId: string, name: string, currentYear: number, eventCount: number, offsets: number): BranchDetail {
  return {
    branch_id: branchId,
    name,
    source_branch_id: branchId === "main" ? null : "main",
    workspace_path: `/tmp/wattforest/${branchId}`,
    start_year: currentYear - 4,
    current_year: currentYear,
    event_count: eventCount,
    updated_at: new Date().toISOString(),
    extent_m: [1280, 1280],
    origin_xy: [0, 0],
    cell_size_m: 20,
    description: "Synthetic demo branch for app wiring.",
    layers: [
      "canopy_height",
      "dominant_pft",
      "mean_age",
      "gap_mask",
      "disturbance_type_last",
      "recent_fire_severity",
    ],
    metrics: makeMetrics(branchId, currentYear, eventCount, offsets),
  };
}

function seededBranchEvents(branchId: string): BranchEvent[] {
  return [
    {
      event_id: `${branchId}-fire-1`,
      event_type: "prescribed_burn",
      year: 2022,
      day_of_year: 181,
      priority: 0,
      affected_cells: [
        [6, 6],
        [6, 7],
        [7, 6],
        [7, 7],
      ],
      params: {
        severity: 0.64,
      },
      branch_id: branchId,
      created_at: "2026-03-20T12:00:00.000Z",
      notes: "Synthetic burn block",
    },
    {
      event_id: `${branchId}-wind-1`,
      event_type: "windstorm",
      year: 2023,
      day_of_year: 99,
      priority: 0,
      center_xy: [720, 660],
      radius_m: 380,
      params: {
        wind_speed_ms: 26,
        wind_dir_deg: 245,
      },
      branch_id: branchId,
      created_at: "2026-03-20T12:00:00.000Z",
      notes: "Gap expansion pulse",
    },
  ];
}

function createBranchState(branchId: string, name: string, offsets: number, terrainSeed = hashString(branchId)): MockBranchState {
  const currentYear = 2025;
  const events = seededBranchEvents(branchId);
  return {
    detail: makeDetail(branchId, name, currentYear, events.length, offsets),
    events,
    profileOffset: offsets,
    terrainSeed,
  };
}

function eventInfluence(
  event: BranchEvent,
  point: [number, number],
  row: number,
  col: number,
  origin: [number, number],
  cellSize: number,
): number {
  if (event.center_xy && typeof event.radius_m === "number") {
    const dx = point[0] - event.center_xy[0];
    const dy = point[1] - event.center_xy[1];
    const distance = Math.sqrt(dx * dx + dy * dy);
    if (distance > event.radius_m) {
      return 0;
    }
    return 1 - distance / Math.max(event.radius_m, 1);
  }

  if (event.polygon_vertices?.length) {
    return pointInPolygon(point, event.polygon_vertices) ? 1 : 0;
  }

  if (event.affected_cells?.length) {
    const actualRow = Math.floor((point[1] - origin[1]) / cellSize);
    const actualCol = Math.floor((point[0] - origin[0]) / cellSize);
    return event.affected_cells.some(([eventRow, eventCol]) => eventRow === actualRow && eventCol === actualCol) ? 1 : 0;
  }

  return row === col ? 0.18 : 0;
}

function applyEventToCell(
  event: BranchEvent,
  influence: number,
  yearsSince: number,
  cell: {
    canopy: number;
    age: number;
    moisture: number;
    pftIndex: number;
    disturbance: string;
    fireSeverity: number;
    gapSignal: number;
  },
) {
  const recency = clamp(1 - yearsSince / 6, 0.1, 1);

  switch (event.event_type) {
    case "fire_ignition":
    case "prescribed_burn": {
      const severity = clamp(Number(event.params.severity ?? 0.55), 0.2, 1);
      cell.canopy *= 1 - influence * (0.45 + severity * 0.35);
      cell.age *= 1 - influence * 0.68;
      cell.fireSeverity = Math.max(cell.fireSeverity, severity * recency * influence);
      cell.gapSignal += influence * (0.32 + severity * 0.38);
      cell.disturbance = "fire";
      break;
    }
    case "windstorm": {
      const windSpeed = clamp(Number(event.params.wind_speed_ms ?? 24) / 35, 0.2, 1.2);
      cell.canopy *= 1 - influence * 0.34 * windSpeed;
      cell.gapSignal += influence * 0.45 * windSpeed;
      cell.disturbance = "wind";
      break;
    }
    case "harvest": {
      const retention = clamp(Number(event.params.retention_frac ?? 0.2), 0, 0.95);
      cell.canopy *= 1 - influence * (0.72 - retention * 0.5);
      cell.age *= 1 - influence * 0.48;
      cell.gapSignal += influence * 0.26;
      cell.disturbance = "harvest";
      break;
    }
    case "flood":
    case "river_shift": {
      cell.moisture = clamp(cell.moisture + influence * 0.28, 0, 1);
      cell.canopy *= 1 - influence * 0.18;
      cell.pftIndex = 2;
      cell.gapSignal += influence * 0.12;
      cell.disturbance = "flood";
      break;
    }
    case "planting": {
      cell.age = lerp(cell.age, 0.12, influence);
      cell.canopy = lerp(cell.canopy, 0.28, influence * 0.8);
      cell.pftIndex = Number(event.params.species_id ?? 0) % 4;
      break;
    }
    case "insect_outbreak": {
      const severity = clamp(Number(event.params.severity ?? 0.5), 0.1, 1);
      cell.canopy *= 1 - influence * severity * 0.4 * cell.age;
      cell.gapSignal += influence * severity * 0.25;
      cell.disturbance = "insect";
      break;
    }
    case "grazing_start": {
      cell.canopy *= 1 - influence * 0.08;
      cell.gapSignal += influence * 0.06;
      break;
    }
    case "climate_shift": {
      const drought = clamp(Number(event.params.drought_delta ?? 0.08), -0.2, 0.4);
      cell.moisture = clamp(cell.moisture - drought * influence, 0, 1);
      cell.canopy = clamp(cell.canopy - drought * influence * 0.22, 0, 1);
      break;
    }
    default: {
      cell.gapSignal += influence * 0.08;
    }
  }
}

function renderMockTile(state: MockBranchState, layer: TileLayerKey, year: number): string {
  const extent = state.detail.extent_m ?? [1280, 1280];
  const origin = state.detail.origin_xy ?? [0, 0];
  const cellSize = state.detail.cell_size_m ?? 20;
  const cellPixelSize = SVG_SIZE / GRID_CELLS;
  const events = [...state.events]
    .filter((event) => event.year <= year)
    .sort((a, b) => a.year - b.year || a.day_of_year - b.day_of_year || a.priority - b.priority);
  const terrainSeed = state.terrainSeed;

  const rects: string[] = [];
  for (let row = 0; row < GRID_CELLS; row += 1) {
    for (let col = 0; col < GRID_CELLS; col += 1) {
      const nx = col / Math.max(GRID_CELLS - 1, 1);
      const ny = row / Math.max(GRID_CELLS - 1, 1);
      const point: [number, number] = [
        origin[0] + extent[0] * nx,
        origin[1] + extent[1] * ny,
      ];

      const terrain = octaveNoise(nx * 5.8 + 1.2, ny * 5.8 + 3.4, terrainSeed);
      const moistureField = octaveNoise(nx * 4.2 + 8.1, ny * 4.2 + 2.6, terrainSeed + 11);
      const structureField = octaveNoise(nx * 8.4 + 0.7, ny * 8.4 + 6.9, terrainSeed + 29);
      const ridgeShade = 0.5 + 0.5 * Math.sin(nx * 7.4 + terrainSeed * 0.001 + ny * 1.8);
      const riverCenter =
        0.18 +
        nx * 0.28 +
        Math.sin(nx * 5.2 + terrainSeed * 0.002) * 0.08 +
        Math.sin(nx * 12.4 + terrainSeed * 0.0013) * 0.025;
      const riverDistance = Math.abs(ny - riverCenter);
      const waterBand = clamp(1 - riverDistance / 0.05, 0, 1);
      const riparianBand = clamp(1 - riverDistance / 0.18, 0, 1);

      const cell = {
        canopy: clamp(0.3 + terrain * 0.34 + moistureField * 0.18 + ridgeShade * 0.08 + riparianBand * 0.1 - waterBand * 0.42, 0.02, 1),
        age: clamp(0.22 + terrain * 0.42 + structureField * 0.22 + (1 - riparianBand) * 0.12, 0.04, 1),
        moisture: clamp(moistureField * 0.72 + riparianBand * 0.28, 0, 1),
        pftIndex: riparianBand > 0.8 ? 2 : terrain > 0.62 ? 0 : moistureField > 0.58 ? 1 : 3,
        disturbance: "none",
        fireSeverity: 0,
        gapSignal: waterBand > 0.78 ? 0.28 : 0,
      };

      for (const event of events) {
        const influence = eventInfluence(event, point, row, col, origin, cellSize);
        if (influence <= 0) {
          continue;
        }
        applyEventToCell(event, influence, year - event.year, cell);
      }

      cell.canopy = clamp(cell.canopy, 0, 1);
      cell.age = clamp(cell.age, 0, 1);
      cell.moisture = clamp(cell.moisture, 0, 1);

      const gapMask = cell.canopy < 0.28 || cell.gapSignal > 0.42;
      const canopyHeight = cell.canopy * (22 + cell.age * 12);
      const ageYears = 8 + cell.age * 120;

      let fill: [number, number, number];
      switch (layer) {
        case "canopy_height": {
          fill = colorForScalar(
            [
              { stop: 0, color: [14, 26, 19] },
              { stop: 0.28, color: [43, 76, 48] },
              { stop: 0.6, color: [73, 119, 74] },
              { stop: 1, color: [172, 211, 126] },
            ],
            canopyHeight / 36,
          );
          if (waterBand > 0.72) {
            fill = mixColor(fill, [40, 88, 106], waterBand * 0.75);
          }
          break;
        }
        case "dominant_pft": {
          const palette: Array<[number, number, number]> = [
            [54, 96, 62],
            [98, 132, 74],
            [48, 112, 118],
            [148, 136, 88],
          ];
          fill = palette[cell.pftIndex] ?? palette[0];
          if (gapMask) {
            fill = mixColor(fill, [190, 176, 132], 0.34);
          }
          break;
        }
        case "mean_age": {
          fill = colorForScalar(
            [
              { stop: 0, color: [39, 60, 44] },
              { stop: 0.4, color: [99, 112, 63] },
              { stop: 0.75, color: [161, 124, 74] },
              { stop: 1, color: [210, 182, 124] },
            ],
            ageYears / 128,
          );
          break;
        }
        case "gap_mask": {
          fill = gapMask ? [216, 189, 136] : [24, 48, 33];
          if (waterBand > 0.7) {
            fill = [46, 86, 104];
          }
          break;
        }
        case "disturbance_type_last": {
          const palette: Record<string, [number, number, number]> = {
            none: [44, 82, 53],
            fire: [210, 104, 54],
            wind: [76, 170, 162],
            harvest: [186, 144, 70],
            flood: [73, 115, 166],
            insect: [147, 92, 116],
          };
          fill = palette[cell.disturbance] ?? palette.none;
          break;
        }
        case "recent_fire_severity": {
          fill = colorForScalar(
            [
              { stop: 0, color: [24, 34, 28] },
              { stop: 0.25, color: [78, 60, 39] },
              { stop: 0.55, color: [149, 89, 42] },
              { stop: 1, color: [238, 156, 83] },
            ],
            cell.fireSeverity,
          );
          if (waterBand > 0.72 && cell.fireSeverity < 0.2) {
            fill = [54, 90, 114];
          }
          break;
        }
      }

      const x = Math.round(col * cellPixelSize);
      const y = Math.round(row * cellPixelSize);
      const width = Math.ceil(cellPixelSize + 0.75);
      const height = Math.ceil(cellPixelSize + 0.75);
      rects.push(`<rect x="${x}" y="${y}" width="${width}" height="${height}" fill="${colorString(fill)}" />`);
    }
  }

  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${SVG_SIZE} ${SVG_SIZE}" shape-rendering="crispEdges">
      <rect width="${SVG_SIZE}" height="${SVG_SIZE}" fill="#07110d" />
      ${rects.join("")}
      <path
        d="M ${SVG_SIZE * 0.06} ${SVG_SIZE * 0.18}
           C ${SVG_SIZE * 0.21} ${SVG_SIZE * 0.25}, ${SVG_SIZE * 0.37} ${SVG_SIZE * 0.2}, ${SVG_SIZE * 0.47} ${SVG_SIZE * 0.32}
           S ${SVG_SIZE * 0.69} ${SVG_SIZE * 0.56}, ${SVG_SIZE * 0.9} ${SVG_SIZE * 0.82}"
        fill="none"
        stroke="rgba(212, 236, 255, 0.18)"
        stroke-width="${SVG_SIZE * 0.02}"
        stroke-linecap="round"
      />
      <rect width="${SVG_SIZE}" height="${SVG_SIZE}" fill="url(#shade)" opacity="0.24" />
      <defs>
        <linearGradient id="shade" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="rgba(255,255,255,0.18)" />
          <stop offset="45%" stop-color="rgba(255,255,255,0)" />
          <stop offset="100%" stop-color="rgba(0,0,0,0.22)" />
        </linearGradient>
      </defs>
    </svg>
  `;

  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

export function createMockScenarioApi(): ScenarioApi {
  const branches = new Map<string, MockBranchState>();
  branches.set("main", createBranchState("main", "Main branch", 0, 11));
  branches.set("research-burn", createBranchState("research-burn", "Research burn", 3, 37));

  const syncDetail = (branchId: string) => {
    const state = branches.get(branchId);
    if (!state) {
      throw new Error(`Unknown branch ${branchId}`);
    }
    state.detail = {
      ...state.detail,
      event_count: state.events.length,
      updated_at: new Date().toISOString(),
      metrics: makeMetrics(branchId, state.detail.current_year, state.events.length, state.profileOffset),
    };
  };

  const replay = (branchId: string) => {
    const state = branches.get(branchId);
    if (!state) {
      throw new Error(`Unknown branch ${branchId}`);
    }
    const nextYear = Math.max(state.detail.current_year, ...state.events.map((event) => event.year));
    const offset = (state.profileOffset + state.events.reduce((sum, event) => sum + event.year + event.day_of_year, 0)) % 5;
    state.detail = {
      ...state.detail,
      current_year: nextYear,
      event_count: state.events.length,
      updated_at: new Date().toISOString(),
      metrics: makeMetrics(branchId, nextYear, state.events.length, offset),
    };
    return clone(state.detail);
  };

  return {
    async listBranches() {
      return clone(Array.from(branches.values()).map((state) => state.detail));
    },
    async createBranch(input: BranchCreateInput) {
      const branchId = input.branch_id ?? `branch-${branches.size + 1}`;
      const sourceState = input.source_branch_id ? branches.get(input.source_branch_id) : null;
      const state = sourceState
        ? {
            detail: {
              ...clone(sourceState.detail),
              branch_id: branchId,
              name: input.name,
              source_branch_id: input.source_branch_id ?? null,
              workspace_path: `/tmp/wattforest/${branchId}`,
              updated_at: new Date().toISOString(),
            },
            events: normalizeEventIds(sourceState.events, branchId),
            profileOffset: sourceState.profileOffset,
            terrainSeed: sourceState.terrainSeed,
          }
        : createBranchState(branchId, input.name, branches.size, hashString(branchId));
      state.detail = {
        ...state.detail,
        source_branch_id: input.source_branch_id ?? null,
      };
      branches.set(branchId, state);
      return clone(state.detail);
    },
    async getBranch(branchId: string) {
      const state = branches.get(branchId);
      if (!state) throw new Error(`Unknown branch ${branchId}`);
      return clone(state.detail);
    },
    async listEvents(branchId: string) {
      const state = branches.get(branchId);
      if (!state) throw new Error(`Unknown branch ${branchId}`);
      return clone(state.events);
    },
    async createEvent(branchId: string, event: BranchEvent) {
      const state = branches.get(branchId);
      if (!state) throw new Error(`Unknown branch ${branchId}`);
      state.events = [...state.events, clone(event)];
      syncDetail(branchId);
      return clone(event);
    },
    async updateEvent(branchId: string, eventId: string, event: BranchEvent) {
      const state = branches.get(branchId);
      if (!state) throw new Error(`Unknown branch ${branchId}`);
      state.events = state.events.map((existing) => (existing.event_id === eventId ? clone(event) : existing));
      syncDetail(branchId);
      return clone(event);
    },
    async deleteEvent(branchId: string, eventId: string) {
      const state = branches.get(branchId);
      if (!state) throw new Error(`Unknown branch ${branchId}`);
      state.events = state.events.filter((event) => event.event_id !== eventId);
      syncDetail(branchId);
    },
    async replayBranch(branchId: string, input: ReplayInput) {
      const state = branches.get(branchId);
      if (!state) throw new Error(`Unknown branch ${branchId}`);
      state.detail = {
        ...state.detail,
        start_year: Math.min(state.detail.start_year, input.from_year),
      };
      return replay(branchId);
    },
    async getMetrics(branchId: string) {
      const state = branches.get(branchId);
      if (!state) throw new Error(`Unknown branch ${branchId}`);
      return clone(state.detail.metrics);
    },
    getTileUrl(branchId: string, layer: TileLayerKey, year: number, z: number, x: number, y: number) {
      const state = branches.get(branchId);
      if (!state) {
        throw new Error(`Unknown branch ${branchId}`);
      }
      return renderMockTile(state, layer, year);
    },
    async exportGeoTiff(branchId: string, year: number, layer: TileLayerKey): Promise<ExportArtifact> {
      return {
        path: `/tmp/mock-exports/${branchId}/${layer}-${year}.tif`,
        branch_id: branchId,
        layer,
        year,
      };
    },
    async exportNetcdf(branchId: string, year: number, layer: TileLayerKey): Promise<ExportArtifact> {
      return {
        path: `/tmp/mock-exports/${branchId}/${layer}-${year}.nc`,
        branch_id: branchId,
        layer,
        year,
      };
    },
  };
}
