import { MAX_LIVING_TREES, MIN_TREE_SPACING } from "../src/prototype/seed";
import { clamp } from "../src/prototype/seed";
import { createForestPrototypeState, findRecruitPosition, recomputeForestState, simulateTreefallCascade, stepForestState, updateForestControls } from "../src/prototype/sim";

describe("forest prototype simulation", () => {
  it("resets deterministically from the fixed seed", () => {
    const first = createForestPrototypeState();
    const second = createForestPrototypeState();

    expect(first.trees).toEqual(second.trees);
    expect(first.derived).toEqual(second.derived);
  });

  it("seeds initial trees onto distinct stand positions", () => {
    const state = createForestPrototypeState();
    const positions = new Set(state.trees.map((tree) => `${tree.x.toFixed(4)}:${tree.y.toFixed(4)}`));

    expect(positions.size).toBe(state.trees.length);
  });

  it("raises drought stress and fire risk when heat increases", () => {
    const base = createForestPrototypeState();
    const hotter = updateForestControls(base, { heat: 1 });

    expect(hotter.derived.droughtStress).toBeGreaterThan(base.derived.droughtStress);
    expect(hotter.derived.fireRisk).toBeGreaterThan(base.derived.fireRisk);
  });

  it("increases turnover under higher mortality pressure", () => {
    let low = updateForestControls(createForestPrototypeState(), { mortalityPressure: 0.1 });
    let high = updateForestControls(createForestPrototypeState(), { mortalityPressure: 1 });
    let lowTurnover = 0;
    let highTurnover = 0;

    for (let index = 0; index < 8; index += 1) {
      low = stepForestState(low);
      high = stepForestState(high);
      lowTurnover += low.derived.turnoverRate;
      highTurnover += high.derived.turnoverRate;
    }

    expect(highTurnover / 8).toBeGreaterThan(lowTurnover / 8);
  });

  it("keeps the live population under the hard cap", () => {
    let state = updateForestControls(createForestPrototypeState(), {
      heat: 0.2,
      wind: 0.1,
      growthAdvantage: 1,
      mortalityPressure: 0.05,
    });

    for (let index = 0; index < 50; index += 1) {
      state = stepForestState(state);
    }

    expect(state.derived.livingTreeCount).toBeLessThanOrEqual(MAX_LIVING_TREES);
  });

  it("keeps a neutral run forested instead of collapsing into a tiny remnant", () => {
    let state = createForestPrototypeState();

    for (let index = 0; index < 60; index += 1) {
      state = stepForestState(state);
    }

    expect(state.derived.livingTreeCount).toBeGreaterThan(60);
  });

  it("makes large-tree loss create more regrowth opportunity than small-tree loss", () => {
    const base = createForestPrototypeState();
    const largeTree = base.trees.find((tree) => tree.temperament === "large_gambler")!;
    const smallTree = base.trees.find((tree) => tree.temperament === "small_gambler")!;

    const afterLargeLoss = recomputeForestState({
      ...base,
      trees: base.trees.filter((tree) => tree.id !== largeTree.id),
      derived: {
        ...base.derived,
        gapFraction: clamp(base.derived.gapFraction * 0.55 + 0.035),
        recentDisturbancePulse: clamp(0.14 * 0.75),
      },
    });

    const afterSmallLoss = recomputeForestState({
      ...base,
      trees: base.trees.filter((tree) => tree.id !== smallTree.id),
      derived: {
        ...base.derived,
        gapFraction: clamp(base.derived.gapFraction * 0.55 + 0.008),
        recentDisturbancePulse: clamp(0.04 * 0.75),
      },
    });

    expect(afterLargeLoss.derived.regrowthOpportunity).toBeGreaterThan(afterSmallLoss.derived.regrowthOpportunity);
  });

  it("lets a falling large tree damage and occasionally kill neighbors in its path", () => {
    const source = {
      ...createForestPrototypeState().trees.find((tree) => tree.temperament === "large_gambler")!,
      x: 0.2,
      y: 0.5,
      size: 0.95,
      canopyRole: "canopy" as const,
    };
    const inPath = {
      ...createForestPrototypeState().trees.find((tree) => tree.temperament === "small_gambler")!,
      id: 9001,
      x: 0.32,
      y: 0.5,
      size: 0.3,
      canopyRole: "subcanopy" as const,
    };
    const offPath = {
      ...createForestPrototypeState().trees.find((tree) => tree.temperament === "small_struggler")!,
      id: 9002,
      x: 0.32,
      y: 0.78,
      size: 0.3,
      canopyRole: "subcanopy" as const,
    };

    const outcome = simulateTreefallCascade(source, [inPath, offPath], 1, 1, true);

    expect(outcome.impactedIds).toContain(inPath.id);
    expect(outcome.damageById.get(inPath.id)).toBeGreaterThan(0);
    expect(outcome.damageById.get(offPath.id) ?? 0).toBe(0);
  });

  it("places recruits away from occupied coordinates and can bias toward a gap anchor", () => {
    const occupied = [
      { x: 0.5, y: 0.5 },
      { x: 0.54, y: 0.5 },
      { x: 0.5, y: 0.54 },
    ];

    const outcome = findRecruitPosition(occupied, 1234, [{ x: 0.2, y: 0.2 }]);
    const nearest = Math.min(
      ...occupied.map((point) => Math.hypot(point.x - outcome.point.x, point.y - outcome.point.y)),
    );

    expect(nearest).toBeGreaterThan(MIN_TREE_SPACING * 0.8);
    expect(Math.hypot(outcome.point.x - 0.2, outcome.point.y - 0.2)).toBeLessThan(0.16);
  });

  it("favors gamblers under strong growth advantage after repeated opening", () => {
    let baseline = updateForestControls(createForestPrototypeState(), {
      wind: 0.9,
      growthAdvantage: 0.5,
    });
    let advantaged = updateForestControls(createForestPrototypeState(), {
      wind: 0.9,
      growthAdvantage: 1,
    });

    let baselineGamblerGrowth = 0;
    let advantagedGamblerGrowth = 0;

    for (let index = 0; index < 24; index += 1) {
      baseline = stepForestState(baseline);
      advantaged = stepForestState(advantaged);
      baselineGamblerGrowth +=
        baseline.derived.growthRateByTemperament.large_gambler + baseline.derived.growthRateByTemperament.small_gambler;
      advantagedGamblerGrowth +=
        advantaged.derived.growthRateByTemperament.large_gambler + advantaged.derived.growthRateByTemperament.small_gambler;
    }

    expect(advantagedGamblerGrowth / 24).toBeGreaterThan(baselineGamblerGrowth / 24);
  });

  it("keeps strugglers less exposed to suppression-driven mortality than gamblers", () => {
    const state = createForestPrototypeState();
    const gamblerRisk = (state.derived.mortalityRiskByTemperament.large_gambler + state.derived.mortalityRiskByTemperament.small_gambler) / 2;
    const strugglerRisk = (state.derived.mortalityRiskByTemperament.large_struggler + state.derived.mortalityRiskByTemperament.small_struggler) / 2;

    expect(strugglerRisk).toBeLessThan(gamblerRisk);
  });

  it("can recover from complete stand loss through external recolonization", () => {
    let state = createForestPrototypeState();
    state = {
      ...state,
      trees: [],
      derived: {
        ...state.derived,
        livingTreeCount: 0,
        gapFraction: 0.9,
        recentDisturbancePulse: 0.7,
      },
    };

    for (let index = 0; index < 6; index += 1) {
      state = stepForestState(state);
      if (state.derived.livingTreeCount > 0) {
        break;
      }
    }

    expect(state.derived.livingTreeCount).toBeGreaterThan(0);
  });
});
