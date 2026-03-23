import type {
  BranchCreateInput,
  BranchDetail,
  BranchEvent,
  ExportArtifact,
  BranchMetrics,
  BranchSummary,
  ReplayInput,
  ScenarioApi,
  TileLayerKey,
} from "./types";

const jsonHeaders = {
  "Content-Type": "application/json",
};

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

export function createHttpScenarioApi(baseUrl = "/api"): ScenarioApi {
  const path = (suffix: string) => `${baseUrl}${suffix}`;

  return {
    async listBranches() {
      const response = await fetch(path("/branches"));
      return readJson<BranchSummary[]>(response);
    },
    async createBranch(input: BranchCreateInput) {
      const response = await fetch(path("/branches"), {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify(input),
      });
      return readJson<BranchDetail>(response);
    },
    async getBranch(branchId: string) {
      const response = await fetch(path(`/branches/${encodeURIComponent(branchId)}`));
      return readJson<BranchDetail>(response);
    },
    async listEvents(branchId: string) {
      const response = await fetch(path(`/branches/${encodeURIComponent(branchId)}/events`));
      return readJson<BranchEvent[]>(response);
    },
    async createEvent(branchId: string, event: BranchEvent) {
      const response = await fetch(path(`/branches/${encodeURIComponent(branchId)}/events`), {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify(event),
      });
      return readJson<BranchEvent>(response);
    },
    async updateEvent(branchId: string, eventId: string, event: BranchEvent) {
      const response = await fetch(path(`/branches/${encodeURIComponent(branchId)}/events/${encodeURIComponent(eventId)}`), {
        method: "PUT",
        headers: jsonHeaders,
        body: JSON.stringify(event),
      });
      return readJson<BranchEvent>(response);
    },
    async deleteEvent(branchId: string, eventId: string) {
      const response = await fetch(path(`/branches/${encodeURIComponent(branchId)}/events/${encodeURIComponent(eventId)}`), {
        method: "DELETE",
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Request failed with ${response.status}`);
      }
    },
    async replayBranch(branchId: string, input: ReplayInput) {
      const response = await fetch(path(`/branches/${encodeURIComponent(branchId)}/replay`), {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify(input),
      });
      return readJson<BranchDetail>(response);
    },
    async getMetrics(branchId: string) {
      const response = await fetch(path(`/branches/${encodeURIComponent(branchId)}/metrics`));
      return readJson<BranchMetrics>(response);
    },
    getTileUrl(branchId: string, layer: TileLayerKey, year: number, z: number, x: number, y: number) {
      return path(`/branches/${encodeURIComponent(branchId)}/tiles/${layer}/${year}/${z}/${x}/${y}.png`);
    },
    async exportGeoTiff(branchId: string, year: number, layer: TileLayerKey) {
      const response = await fetch(path("/exports/geotiff"), {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify({ branch_id: branchId, year, layer }),
      });
      return readJson<ExportArtifact>(response);
    },
    async exportNetcdf(branchId: string, year: number, layer: TileLayerKey) {
      const response = await fetch(path("/exports/netcdf"), {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify({ branch_id: branchId, year, layer }),
      });
      return readJson<ExportArtifact>(response);
    },
  };
}
