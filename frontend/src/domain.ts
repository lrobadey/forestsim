import type { BranchEvent, BranchSummary, EventDraft, EventGeometry, SupportedEventType } from "./types";

export const supportedEventLabels: Record<SupportedEventType, string> = {
  fire_ignition: "Fire ignition",
  prescribed_burn: "Prescribed burn",
  windstorm: "Windstorm",
  harvest: "Harvest",
  grazing_start: "Grazing start",
  grazing_end: "Grazing end",
  river_shift: "River shift",
  flood: "Flood",
  climate_shift: "Climate shift",
  planting: "Planting",
  insect_outbreak: "Insect outbreak",
  custom: "Custom",
};

export const eventParamPresets: Record<SupportedEventType, Record<string, unknown>> = {
  fire_ignition: { wind_speed_ms: 10, wind_dir_deg: 220, duration_hr: 6 },
  prescribed_burn: { wind_speed_ms: 6, wind_dir_deg: 160, duration_hr: 4, severity: 0.5 },
  windstorm: { wind_speed_ms: 24, wind_dir_deg: 240, damage_scalar: 1 },
  harvest: { method: "selection", retention_frac: 0.2, min_biomass_kg_ha: 0 },
  grazing_start: { intensity: 0.45 },
  grazing_end: {},
  river_shift: { scour_frac: 0.35, moisture_bonus: 0.18, recruitment_scalar: 1.15 },
  flood: { severity: 0.55, mortality_frac: 0.35, moisture_bonus: 0.25, recruitment_scalar: 1.2 },
  climate_shift: { gdd_delta: 120, precip_delta_mm: -40, drought_delta: 0.08, frost_free_delta: -5 },
  planting: { species_id: 0, density_stems_ha: 220, biomass_kg_ha: 60, age: 0 },
  insect_outbreak: { severity: 0.55, min_age: 10 },
  custom: { delegate_event_type: "harvest", method: "selection", retention_frac: 0.2, min_biomass_kg_ha: 0 },
};

function branchGeometryContext(branch?: Pick<BranchSummary, "origin_xy" | "extent_m"> | null) {
  const origin = branch?.origin_xy ?? [0, 0];
  const extent = branch?.extent_m ?? [1280, 1280];
  const center: [number, number] = [origin[0] + extent[0] / 2, origin[1] + extent[1] / 2];
  const radius = Math.max(100, Math.min(extent[0], extent[1]) * 0.25);
  return { origin, extent, center, radius };
}

export function defaultEventDraft(type: SupportedEventType, branch?: Pick<BranchSummary, "origin_xy" | "extent_m"> | null): EventDraft {
  const { center, radius } = branchGeometryContext(branch);
  return {
    event_type: type,
    year: 2025,
    day_of_year: 180,
    priority: 0,
    geometry: {
      kind: "circle",
      center_xy: center,
      radius_m: radius,
    },
    params: structuredClone(eventParamPresets[type]),
    notes: "",
  };
}

export function eventToDraft(event: BranchEvent): EventDraft {
  const geometry = eventGeometryFromEvent(event);
  return {
    event_type: event.event_type as SupportedEventType,
    year: event.year,
    day_of_year: event.day_of_year,
    priority: event.priority,
    geometry,
    params: structuredClone(event.params ?? {}),
    notes: event.notes ?? "",
  };
}

export function eventGeometryFromEvent(event: BranchEvent): EventGeometry {
  if (event.polygon_vertices?.length) {
    return { kind: "polygon", polygon_vertices: structuredClone(event.polygon_vertices) };
  }
  if (event.affected_cells?.length) {
    return { kind: "mask", affected_cells: structuredClone(event.affected_cells) };
  }
  if (event.center_xy && typeof event.radius_m === "number") {
    return { kind: "circle", center_xy: structuredClone(event.center_xy), radius_m: event.radius_m };
  }
  return {
    kind: "circle",
    center_xy: [640, 640],
    radius_m: 250,
  };
}

export function draftToEvent(
  draft: EventDraft,
  branchId: string,
  eventId: string,
  createdAt: string,
): BranchEvent {
  const base = {
    event_id: eventId,
    event_type: draft.event_type,
    year: draft.year,
    day_of_year: draft.day_of_year,
    priority: draft.priority,
    params: structuredClone(draft.params),
    branch_id: branchId,
    created_at: createdAt,
    notes: draft.notes,
  } as BranchEvent;

  switch (draft.geometry.kind) {
    case "circle":
      return {
        ...base,
        center_xy: structuredClone(draft.geometry.center_xy),
        radius_m: draft.geometry.radius_m,
      };
    case "polygon":
      return {
        ...base,
        polygon_vertices: structuredClone(draft.geometry.polygon_vertices),
      };
    case "mask":
      return {
        ...base,
        affected_cells: structuredClone(draft.geometry.affected_cells),
      };
  }
}

export function earliestAffectedYear(events: BranchEvent[], priorYear: number, nextYear: number): number {
  const years = events.map((event) => event.year);
  return Math.min(priorYear, nextYear, ...years);
}

export function buildEventGeometryLabel(event: BranchEvent): string {
  if (event.polygon_vertices?.length) {
    return `${event.polygon_vertices.length} vertices`;
  }
  if (event.affected_cells?.length) {
    return `${event.affected_cells.length} cells`;
  }
  if (event.center_xy && typeof event.radius_m === "number") {
    return `circle ${Math.round(event.radius_m)} m`;
  }
  return "unresolved geometry";
}
