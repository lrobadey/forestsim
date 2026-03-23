import { createMockScenarioApi } from "../src/mockApi";

describe("mock scenario api", () => {
  it("returns a browser-renderable generated tile that changes with scenario state", async () => {
    const api = createMockScenarioApi();
    const before = api.getTileUrl("main", "canopy_height", 2025, 0, 0, 0);

    expect(before.startsWith("data:image/svg+xml")).toBe(true);

    await api.createEvent("main", {
      event_id: "main-custom-burn",
      event_type: "prescribed_burn",
      year: 2025,
      day_of_year: 210,
      priority: 0,
      center_xy: [620, 620],
      radius_m: 220,
      params: { severity: 0.9 },
      branch_id: "main",
      created_at: "2026-03-21T19:00:00.000Z",
      notes: "High severity burn pulse",
    });
    await api.replayBranch("main", { from_year: 2025 });

    const after = api.getTileUrl("main", "canopy_height", 2025, 0, 0, 0);
    expect(after).not.toBe(before);
  });

  it("clones branch state from the selected source branch instead of reseeding unrelated data", async () => {
    const api = createMockScenarioApi();
    const sourceEvents = await api.listEvents("main");
    const fork = await api.createBranch({ name: "Fork", source_branch_id: "main" });
    const forkEvents = await api.listEvents(fork.branch_id);

    expect(fork.source_branch_id).toBe("main");
    expect(forkEvents).toHaveLength(sourceEvents.length);
    expect(forkEvents.every((event) => event.branch_id === fork.branch_id)).toBe(true);
  });
});
