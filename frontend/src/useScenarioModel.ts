import { useEffect, useState } from "react";
import { createHttpScenarioApi } from "./api";
import { draftToEvent, earliestAffectedYear } from "./domain";
import { createMockScenarioApi } from "./mockApi";
import type {
  BranchCreateInput,
  BranchDetail,
  BranchEvent,
  ExportArtifact,
  BranchMetrics,
  BranchSummary,
  EventDraft,
  ReplayInput,
  ScenarioApi,
  TileLayerKey,
  ViewKey,
} from "./types";

const liveApi = createHttpScenarioApi(import.meta.env.VITE_WATTFOREST_API_BASE_URL ?? "/api");

export interface ScenarioModel {
  api: ScenarioApi;
  activeView: ViewKey;
  setActiveView(view: ViewKey): void;
  branches: BranchSummary[];
  selectedBranchId: string | null;
  selectedBranch: BranchDetail | null;
  selectedCompareBranchId: string | null;
  selectedCompareBranch: BranchSummary | null;
  events: BranchEvent[];
  metrics: BranchMetrics | null;
  selectedYear: number;
  selectedLayer: TileLayerKey;
  lastExport: ExportArtifact | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
  setSelectedBranchId(branchId: string): void;
  setSelectedCompareBranchId(branchId: string): void;
  setSelectedYear(year: number): void;
  setSelectedLayer(layer: TileLayerKey): void;
  refreshAll(): Promise<void>;
  saveEvent(draft: EventDraft, eventId?: string): Promise<void>;
  deleteEvent(eventId: string): Promise<void>;
  createBranch(input: BranchCreateInput): Promise<void>;
  exportGeoTiff(): Promise<void>;
  exportNetcdf(): Promise<void>;
  replayFrom(year: number): Promise<void>;
}

function resolveApi(): ScenarioApi {
  return import.meta.env.VITE_WATTFOREST_API_MODE === "mock" ? createMockScenarioApi() : liveApi;
}

export function useScenarioModel() {
  const [api] = useState(resolveApi);
  const [activeView, setActiveView] = useState<ViewKey>("map");
  const [branches, setBranches] = useState<BranchSummary[]>([]);
  const [selectedBranchId, setSelectedBranchId] = useState<string | null>(null);
  const [selectedCompareBranchId, setSelectedCompareBranchId] = useState<string | null>(null);
  const [selectedBranch, setSelectedBranch] = useState<BranchDetail | null>(null);
  const [events, setEvents] = useState<BranchEvent[]>([]);
  const [metrics, setMetrics] = useState<BranchMetrics | null>(null);
  const [selectedYear, setSelectedYear] = useState(2025);
  const [selectedLayer, setSelectedLayer] = useState<TileLayerKey>("canopy_height");
  const [lastExport, setLastExport] = useState<ExportArtifact | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const clampYear = (year: number, branch: Pick<BranchSummary, "start_year" | "current_year">) =>
    Math.max(branch.start_year, Math.min(year, branch.current_year));

  const mergeBranchSummary = (nextBranch: BranchDetail) => {
    setBranches((current) => {
      const index = current.findIndex((branch) => branch.branch_id === nextBranch.branch_id);
      if (index === -1) {
        return [...current, nextBranch];
      }
      const next = [...current];
      next[index] = { ...current[index], ...nextBranch };
      return next;
    });
  };

  const refreshBranchData = async (
    branchId: string,
    options: {
      preserveSelectedYear?: boolean;
      focusYear?: number;
    } = {},
  ) => {
    const [nextBranch, nextEvents, nextMetrics] = await Promise.all([
      api.getBranch(branchId),
      api.listEvents(branchId),
      api.getMetrics(branchId),
    ]);
    setSelectedBranch(nextBranch);
    setEvents(nextEvents);
    setMetrics(nextMetrics);
    mergeBranchSummary({ ...nextBranch, metrics: nextMetrics });
    setSelectedYear((currentYear) => {
      if (typeof options.focusYear === "number") {
        return clampYear(options.focusYear, nextBranch);
      }
      if (options.preserveSelectedYear) {
        return clampYear(currentYear, nextBranch);
      }
      return nextBranch.current_year;
    });
  };

  const refreshAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const nextBranches = await api.listBranches();
      setBranches(nextBranches);
      const branchId = selectedBranchId ?? nextBranches[0]?.branch_id ?? null;
      const compareBranchId =
        (selectedCompareBranchId && selectedCompareBranchId !== branchId && nextBranches.some((branch) => branch.branch_id === selectedCompareBranchId)
          ? selectedCompareBranchId
          : nextBranches.find((branch) => branch.branch_id !== branchId)?.branch_id) ?? null;
      setSelectedCompareBranchId(compareBranchId);
      if (branchId) {
        setSelectedBranchId(branchId);
        await refreshBranchData(branchId);
      } else {
        setSelectedBranch(null);
        setEvents([]);
        setMetrics(null);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load scenario data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refreshAll();
  }, []);

  useEffect(() => {
    if (!selectedBranchId || loading) {
      return;
    }
    void refreshBranchData(selectedBranchId).catch((cause) => {
      setError(cause instanceof Error ? cause.message : "Unable to refresh branch");
    });
  }, [selectedBranchId]);

  const selectedCompareBranch = selectedCompareBranchId
    ? branches.find((branch) => branch.branch_id === selectedCompareBranchId) ?? null
    : null;

  const replayFrom = async (year: number) => {
    if (!selectedBranchId) {
      return;
    }
    const payload: ReplayInput = { from_year: year };
    await api.replayBranch(selectedBranchId, payload);
    await refreshBranchData(selectedBranchId, { focusYear: year });
  };

  const saveEvent = async (draft: EventDraft, eventId?: string) => {
    if (!selectedBranchId) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const existing = eventId ? events.find((event) => event.event_id === eventId) : null;
      const nextEventId = eventId ?? crypto.randomUUID();
      const nextEvent = draftToEvent(draft, selectedBranchId, nextEventId, existing?.created_at ?? new Date().toISOString());
      if (eventId) {
        await api.updateEvent(selectedBranchId, eventId, nextEvent);
      } else {
        await api.createEvent(selectedBranchId, nextEvent);
      }
      const earliest = earliestAffectedYear(events, existing?.year ?? draft.year, draft.year);
      await api.replayBranch(selectedBranchId, { from_year: earliest });
      await refreshBranchData(selectedBranchId, { focusYear: draft.year });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save event");
    } finally {
      setSaving(false);
    }
  };

  const deleteEvent = async (eventId: string) => {
    if (!selectedBranchId) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const target = events.find((event) => event.event_id === eventId);
      await api.deleteEvent(selectedBranchId, eventId);
      await api.replayBranch(selectedBranchId, { from_year: target?.year ?? selectedYear });
      await refreshBranchData(selectedBranchId, { preserveSelectedYear: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to delete event");
    } finally {
      setSaving(false);
    }
  };

  const createBranch = async (input: BranchCreateInput) => {
    setSaving(true);
    setError(null);
    try {
      const branch = await api.createBranch(input);
      const nextBranches = await api.listBranches();
      setBranches(nextBranches);
      setSelectedBranchId(branch.branch_id);
      setSelectedCompareBranchId(nextBranches.find((item) => item.branch_id !== branch.branch_id)?.branch_id ?? null);
      await refreshBranchData(branch.branch_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to create branch");
    } finally {
      setSaving(false);
    }
  };

  const exportGeoTiff = async () => {
    if (!selectedBranchId || !selectedBranch) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const artifact = await api.exportGeoTiff(selectedBranchId, selectedYear, selectedLayer);
      setLastExport(artifact);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to export GeoTIFF");
    } finally {
      setSaving(false);
    }
  };

  const exportNetcdf = async () => {
    if (!selectedBranchId || !selectedBranch) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const artifact = await api.exportNetcdf(selectedBranchId, selectedYear, selectedLayer);
      setLastExport(artifact);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to export NetCDF");
    } finally {
      setSaving(false);
    }
  };

  return {
    api,
    activeView,
    setActiveView,
    branches,
    selectedBranchId,
    selectedBranch,
    selectedCompareBranchId,
    selectedCompareBranch,
    events,
    metrics,
    selectedYear,
    selectedLayer,
    lastExport,
    loading,
    saving,
    error,
    setSelectedBranchId,
    setSelectedCompareBranchId,
    setSelectedYear,
    setSelectedLayer,
    refreshAll,
    saveEvent,
    deleteEvent,
    createBranch,
    exportGeoTiff,
    exportNetcdf,
    replayFrom,
  } satisfies ScenarioModel;
}
