import {
  clamp,
  createHistoryPoint,
  createRng,
  BASELINE_TREE_COUNT,
  DEFAULT_CONTROLS,
  DEFAULT_SEED,
  DEFAULT_YEAR,
  deriveReproductiveState,
  deriveSizeClass,
  EMPTY_RECORD,
  HISTORY_LIMIT,
  INITIAL_TREE_COUNT,
  INITIAL_GAP_FRACTION,
  INITIAL_RECENT_DISTURBANCE,
  MAX_LIVING_TREES,
  MIN_TREE_SPACING,
  nextRandom,
  randomBetween,
  randomChance,
  roleWeight,
  seedInitialTrees,
  zeroDerivedState,
} from "./seed";
import type { ForestControls, ForestDerivedState, ForestPrototypeState, ForestTree, Temperament, TemperamentRecord } from "./types";
import { SPEED_OPTIONS, TEMPERAMENTS } from "./types";

interface TemperamentParams {
  baseGrowth: number;
  suppressionTolerance: number;
  fecundity: number;
  openingBonus: number;
  heatSensitivity: number;
  backgroundMortality: number;
  maxSize: number;
}

interface ProjectionSignals {
  gapFraction: number;
  recentDisturbancePulse: number;
}

interface ProjectedStand {
  trees: ForestTree[];
  canopyClosure: number;
  meanVigor: number;
  droughtStress: number;
  fireRisk: number;
  regrowthOpportunity: number;
  shareByTemperament: TemperamentRecord;
  growthRateByTemperament: TemperamentRecord;
  mortalityRiskByTemperament: TemperamentRecord;
  livingTreeCount: number;
}

interface StepAccumulators {
  growthTotals: TemperamentRecord;
  growthCounts: TemperamentRecord;
  riskTotals: TemperamentRecord;
  riskCounts: TemperamentRecord;
}

interface StepCandidate {
  sourceTree: ForestTree;
  nextTree: ForestTree;
  mortalityRisk: number;
  directDeath: boolean;
  directWindFailure: boolean;
  fireDamage: number;
}

interface FallQueueItem {
  tree: ForestTree;
  strength: number;
  angle: number;
}

interface StandPoint {
  x: number;
  y: number;
}

const TEMPERAMENT_PARAMS: Record<Temperament, TemperamentParams> = {
  large_gambler: {
    baseGrowth: 0.06,
    suppressionTolerance: 0.6,
    fecundity: 0.9,
    openingBonus: 1,
    heatSensitivity: 0.65,
    backgroundMortality: 0.02,
    maxSize: 1,
  },
  small_gambler: {
    baseGrowth: 0.07,
    suppressionTolerance: 0.55,
    fecundity: 1,
    openingBonus: 0.9,
    heatSensitivity: 0.7,
    backgroundMortality: 0.028,
    maxSize: 0.63,
  },
  large_struggler: {
    baseGrowth: 0.045,
    suppressionTolerance: 0.9,
    fecundity: 0.55,
    openingBonus: 0.45,
    heatSensitivity: 0.45,
    backgroundMortality: 0.016,
    maxSize: 1,
  },
  small_struggler: {
    baseGrowth: 0.04,
    suppressionTolerance: 1,
    fecundity: 0.5,
    openingBonus: 0.35,
    heatSensitivity: 0.4,
    backgroundMortality: 0.018,
    maxSize: 0.6,
  },
};

// TODO: Map these parameters to documented ecological interpretations and
// calibration notes. The current ordering is directionally sensible, but the
// values are still hand-tuned rather than literature-calibrated.

function emptyRecord(): TemperamentRecord {
  return EMPTY_RECORD();
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function mean(values: number[]): number {
  if (!values.length) {
    return 0;
  }
  return sum(values) / values.length;
}

function isGambler(temperament: Temperament): boolean {
  return temperament.includes("gambler");
}

function isLarge(temperament: Temperament): boolean {
  return temperament.startsWith("large");
}

function shadeSensitivity(temperament: Temperament): number {
  return isGambler(temperament) ? 1 : 0.7;
}

function intensifiedControl(value: number, power = 1.08, extremeBonus = 0.7): number {
  const normalized = clamp(value);
  const highEnd = Math.max(0, normalized - 0.58) / 0.42;
  return normalized ** power * (1 + extremeBonus * highEnd * highEnd);
}

function signedControlDelta(value: number, power = 1.12, extremeBonus = 0.65): number {
  const centered = clamp(value) * 2 - 1;
  const magnitude = Math.abs(centered);
  const highEnd = Math.max(0, magnitude - 0.55) / 0.45;
  const curved = magnitude ** power * (1 + extremeBonus * highEnd * highEnd);
  return Math.sign(centered) * curved;
}

function standingCountByTemperament(trees: ForestTree[]): TemperamentRecord {
  const counts = emptyRecord();
  for (const tree of trees) {
    counts[tree.temperament] += 1;
  }
  return counts;
}

function normalizeRecord(counts: TemperamentRecord, total: number): TemperamentRecord {
  const normalized = emptyRecord();
  for (const temperament of TEMPERAMENTS) {
    normalized[temperament] = total > 0 ? counts[temperament] / total : 0;
  }
  return normalized;
}

function totalRecordValue(record: TemperamentRecord): number {
  return TEMPERAMENTS.reduce((sum, temperament) => sum + record[temperament], 0);
}

function computeCanopyClosure(trees: ForestTree[]): number {
  const densityScale = Math.max(trees.length, BASELINE_TREE_COUNT) / BASELINE_TREE_COUNT;
  const closure = sum(trees.map((tree) => tree.size ** 1.35)) / (70 * densityScale);
  return clamp(closure);
}

function assignCanopyRoles(trees: ForestTree[]): Map<number, ForestTree["canopyRole"]> {
  const sortedIds = [...trees]
    .sort((left, right) => right.size - left.size || right.age - left.age || left.id - right.id)
    .map((tree) => tree.id);
  const canopyCount = Math.max(1, Math.round(trees.length * 0.22));
  const subcanopyCount = Math.max(1, Math.round(trees.length * 0.28));
  const roleMap = new Map<number, ForestTree["canopyRole"]>();

  sortedIds.forEach((id, index) => {
    if (index < canopyCount) {
      roleMap.set(id, "canopy");
      return;
    }
    if (index < canopyCount + subcanopyCount) {
      roleMap.set(id, "subcanopy");
      return;
    }
    roleMap.set(id, "suppressed");
  });

  return roleMap;
}

function refreshTreeStructure(trees: ForestTree[]): { trees: ForestTree[]; canopyClosure: number; meanVigor: number } {
  const canopyClosure = computeCanopyClosure(trees);
  const roleMap = assignCanopyRoles(trees);
  const refreshed = trees.map((tree) => {
    const canopyRole = roleMap.get(tree.id) ?? "suppressed";
    const suppressionLevel = clamp(canopyClosure * shadeSensitivity(tree.temperament) * roleWeight(canopyRole));

    return {
      ...tree,
      alive: true,
      sizeClass: deriveSizeClass(tree.size),
      canopyRole,
      suppressionLevel,
      reproductiveState: deriveReproductiveState(tree.age, tree.size, tree.vigor),
    };
  });

  return {
    trees: refreshed,
    canopyClosure,
    meanVigor: mean(refreshed.map((tree) => tree.vigor)),
  };
}

function applyGrowthAdvantage(temperament: Temperament, growth: number, controls: ForestControls): number {
  const delta = signedControlDelta(controls.growthAdvantage);
  if (isGambler(temperament)) {
    return Math.max(0, growth * (1 + 0.95 * delta));
  }
  return Math.max(0, growth * (1 - 0.55 * delta));
}

function estimateGrowthPotential(tree: ForestTree, controls: ForestControls, droughtStress: number, regrowthOpportunity: number): number {
  const params = TEMPERAMENT_PARAMS[tree.temperament];
  const heatLoad = intensifiedControl(controls.heat);
  let growth =
    params.baseGrowth *
    (0.45 + 0.55 * tree.vigor) *
    (1 - tree.suppressionLevel * (1 / params.suppressionTolerance) * 0.72) *
    (1 - droughtStress * params.heatSensitivity * (0.28 + heatLoad * 0.24));

  growth = applyGrowthAdvantage(tree.temperament, growth, controls);

  if (regrowthOpportunity > 0.42) {
    growth *= 1 + params.openingBonus * (regrowthOpportunity - 0.42) * 1.15;
  }

  return Math.max(0, growth);
}

function estimateMortalityRisk(tree: ForestTree, controls: ForestControls, droughtStress: number, disturbanceDamage: number, suppressionYears: number): number {
  const params = TEMPERAMENT_PARAMS[tree.temperament];
  const mortalityLoad = intensifiedControl(controls.mortalityPressure);
  const windLoad = intensifiedControl(controls.wind);
  const heatLoad = intensifiedControl(controls.heat);
  let risk =
    params.backgroundMortality +
    mortalityLoad * 0.085 +
    droughtStress * params.heatSensitivity * (0.035 + heatLoad * 0.04) +
    suppressionYears * 0.004 +
    disturbanceDamage * 0.3 +
    Math.max(tree.age - 130, 0) * 0.0011;

  if (tree.canopyRole === "canopy" || isLarge(tree.temperament)) {
    risk += windLoad * tree.size * (0.035 + disturbanceDamage * 0.1);
  }

  if (tree.canopyRole === "suppressed") {
    risk += tree.suppressionLevel * (isGambler(tree.temperament) ? 0.055 : 0.028);
  }

  return clamp(risk, 0, 0.95);
}

function projectStand(trees: ForestTree[], controls: ForestControls, signals: ProjectionSignals): ProjectedStand {
  const structural = refreshTreeStructure(trees);
  const heatLoad = intensifiedControl(controls.heat);
  const mortalityLoad = intensifiedControl(controls.mortalityPressure);
  const standing = structural.trees;
  const livingTreeCount = standing.length;
  // TODO: Rebalance the baseline drought/fire/opening feedbacks so mid-control
  // runs do not settle into chronically high stress. Add multi-seed acceptance
  // tests once the neutral baseline target band is defined.
  const droughtStress = clamp(0.04 + heatLoad * 0.7 + signals.recentDisturbancePulse * 0.12 + (1 - structural.meanVigor) * 0.14);
  const standVulnerability = clamp(
    (1 - structural.meanVigor) * 0.65 + signals.gapFraction * 0.22 + signals.recentDisturbancePulse * 0.32 + droughtStress * 0.18,
  );
  const fireRisk = clamp(0.04 + heatLoad * 0.58 + droughtStress * 0.42 + standVulnerability * 0.34);
  const regrowthOpportunity = clamp(
    0.12 +
      signals.gapFraction * 0.82 +
      signals.recentDisturbancePulse * 0.34 +
      mortalityLoad * 0.18 -
      structural.canopyClosure * 0.28 -
      droughtStress * 0.16,
  );
  const growthTotals = emptyRecord();
  const mortalityTotals = emptyRecord();
  const counts = standingCountByTemperament(standing);

  for (const tree of standing) {
    growthTotals[tree.temperament] += estimateGrowthPotential(tree, controls, droughtStress, regrowthOpportunity);
    mortalityTotals[tree.temperament] += estimateMortalityRisk(tree, controls, droughtStress, tree.disturbanceDamage, tree.suppressionYears);
  }

  const growthRateByTemperament = emptyRecord();
  const mortalityRiskByTemperament = emptyRecord();
  for (const temperament of TEMPERAMENTS) {
    growthRateByTemperament[temperament] = counts[temperament] > 0 ? growthTotals[temperament] / counts[temperament] : 0;
    mortalityRiskByTemperament[temperament] = counts[temperament] > 0 ? mortalityTotals[temperament] / counts[temperament] : 0;
  }

  return {
    trees: standing,
    canopyClosure: structural.canopyClosure,
    meanVigor: structural.meanVigor,
    droughtStress,
    fireRisk,
    regrowthOpportunity,
    shareByTemperament: normalizeRecord(counts, livingTreeCount),
    growthRateByTemperament,
    mortalityRiskByTemperament,
    livingTreeCount,
  };
}

function externalSeedWeights(regrowthOpportunity: number): TemperamentRecord {
  const weights: TemperamentRecord = {
    large_gambler: 0.24,
    small_gambler: 0.28,
    large_struggler: 0.22,
    small_struggler: 0.26,
  };

  if (regrowthOpportunity >= 0.45) {
    weights.large_gambler *= 1.2;
    weights.small_gambler *= 1.3;
  } else {
    weights.large_struggler *= 1.18;
    weights.small_struggler *= 1.14;
  }

  const total = totalRecordValue(weights);
  return normalizeRecord(weights, total);
}

function externalSeedRain(postProjection: ProjectedStand, gapFraction: number, hasLocalSeedSource: boolean): TemperamentRecord {
  const weights = externalSeedWeights(postProjection.regrowthOpportunity);
  const pressure = clamp(
    0.42 +
      postProjection.regrowthOpportunity * 1.1 +
      gapFraction * 0.45 -
      postProjection.droughtStress * 0.35 +
      (hasLocalSeedSource ? 0 : 0.18),
    0,
    1.6,
  );
  const seeded = emptyRecord();

  for (const temperament of TEMPERAMENTS) {
    seeded[temperament] = pressure * weights[temperament];
  }

  return seeded;
}

function stockingRecoveryPressure(livingTreeCount: number): number {
  return clamp(1 - livingTreeCount / INITIAL_TREE_COUNT);
}

function buildDerivedState(
  projection: ProjectedStand,
  overrides: Partial<Pick<ForestDerivedState, "turnoverRate" | "disturbanceFrequency" | "gapFraction" | "recentDisturbancePulse" | "growthRateByTemperament" | "mortalityRiskByTemperament">> = {},
): ForestDerivedState {
  return {
    droughtStress: projection.droughtStress,
    fireRisk: projection.fireRisk,
    regrowthOpportunity: projection.regrowthOpportunity,
    turnoverRate: overrides.turnoverRate ?? 0,
    disturbanceFrequency: overrides.disturbanceFrequency ?? 0,
    gapFraction: overrides.gapFraction ?? INITIAL_GAP_FRACTION,
    canopyClosure: projection.canopyClosure,
    livingTreeCount: projection.livingTreeCount,
    meanVigor: projection.meanVigor,
    recentDisturbancePulse: overrides.recentDisturbancePulse ?? INITIAL_RECENT_DISTURBANCE,
    shareByTemperament: projection.shareByTemperament,
    growthRateByTemperament: overrides.growthRateByTemperament ?? projection.growthRateByTemperament,
    mortalityRiskByTemperament: overrides.mortalityRiskByTemperament ?? projection.mortalityRiskByTemperament,
  };
}

function clampHistory(history: ForestPrototypeState["history"]): ForestPrototypeState["history"] {
  return history.slice(-HISTORY_LIMIT);
}

function pushHistory(state: ForestPrototypeState, derived: ForestDerivedState): ForestPrototypeState["history"] {
  return clampHistory([...state.history, createHistoryPoint(state.year, derived)]);
}

function replaceLatestHistory(state: ForestPrototypeState, derived: ForestDerivedState): ForestPrototypeState["history"] {
  if (!state.history.length) {
    return [createHistoryPoint(state.year, derived)];
  }
  const next = [...state.history];
  next[next.length - 1] = createHistoryPoint(state.year, derived);
  return next;
}

function createAccumulators(): StepAccumulators {
  return {
    growthTotals: emptyRecord(),
    growthCounts: emptyRecord(),
    riskTotals: emptyRecord(),
    riskCounts: emptyRecord(),
  };
}

function finalizeRates(totals: TemperamentRecord, counts: TemperamentRecord, fallback: TemperamentRecord): TemperamentRecord {
  const next = emptyRecord();
  for (const temperament of TEMPERAMENTS) {
    next[temperament] = counts[temperament] > 0 ? totals[temperament] / counts[temperament] : fallback[temperament];
  }
  return next;
}

function angleJitter(baseAngle: number, cursor: ReturnType<typeof createRng>, amount = 0.45): number {
  return baseAngle + randomBetween(cursor, -amount, amount);
}

function treefallStrength(tree: ForestTree, wind: number, windDriven: boolean): number {
  const base = 0.5 + tree.size * 0.7 + (tree.canopyRole === "canopy" ? 0.15 : 0);
  return base * (windDriven ? 0.92 + intensifiedControl(wind, 1.02, 0.55) * 1.08 : 0.72);
}

function treefallDirection(cursor: ReturnType<typeof createRng>, prevailingAngle: number, windDriven: boolean): number {
  if (windDriven) {
    return angleJitter(prevailingAngle, cursor, 0.3);
  }
  return randomBetween(cursor, 0, Math.PI * 2);
}

function squaredDistance(a: StandPoint, b: StandPoint): number {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return dx * dx + dy * dy;
}

function nearestSpacing(candidate: StandPoint, occupied: StandPoint[]): number {
  if (!occupied.length) {
    return 1;
  }

  let nearest = Number.POSITIVE_INFINITY;
  for (const point of occupied) {
    const distance = Math.sqrt(squaredDistance(candidate, point));
    if (distance < nearest) {
      nearest = distance;
    }
  }

  return nearest;
}

function randomStandPoint(cursor: ReturnType<typeof createRng>): StandPoint {
  return {
    x: randomBetween(cursor, 0.03, 0.97),
    y: randomBetween(cursor, 0.03, 0.97),
  };
}

function randomGapPoint(anchor: StandPoint, cursor: ReturnType<typeof createRng>): StandPoint {
  return {
    x: clamp(anchor.x + randomBetween(cursor, -0.08, 0.08), 0.03, 0.97),
    y: clamp(anchor.y + randomBetween(cursor, -0.08, 0.08), 0.03, 0.97),
  };
}

export function findRecruitPosition(
  occupied: StandPoint[],
  rngState: number,
  preferredAnchors: StandPoint[] = [],
): { point: StandPoint; nextRngState: number; spacing: number } {
  const rng = createRng(rngState);
  let bestPoint = randomStandPoint(rng);
  let bestSpacing = nearestSpacing(bestPoint, occupied);

  if (preferredAnchors.length > 0) {
    let anchoredBestPoint = bestPoint;
    let anchoredBestSpacing = -1;

    for (let index = 0; index < 12; index += 1) {
      const anchor = preferredAnchors[Math.floor(nextRandom(rng) * preferredAnchors.length)];
      const candidate = randomGapPoint(anchor, rng);
      const spacing = nearestSpacing(candidate, occupied);
      if (spacing > anchoredBestSpacing) {
        anchoredBestPoint = candidate;
        anchoredBestSpacing = spacing;
      }
    }

    if (anchoredBestSpacing >= MIN_TREE_SPACING * 0.75) {
      return {
        point: anchoredBestPoint,
        nextRngState: rng.state,
        spacing: anchoredBestSpacing,
      };
    }
  }

  for (let index = 0; index < 20; index += 1) {
    const useAnchor = preferredAnchors.length > 0 && randomChance(rng, 0.72);
    const anchor = useAnchor ? preferredAnchors[Math.floor(nextRandom(rng) * preferredAnchors.length)] : null;
    const candidate = anchor ? randomGapPoint(anchor, rng) : randomStandPoint(rng);
    const spacing = nearestSpacing(candidate, occupied);
    const score = spacing + (anchor && spacing >= MIN_TREE_SPACING * 0.75 ? 0.18 : 0);

    if (score > bestSpacing) {
      bestPoint = candidate;
      bestSpacing = score;
      if (spacing >= MIN_TREE_SPACING) {
        break;
      }
    }
  }

  return {
    point: bestPoint,
    nextRngState: rng.state,
    spacing: bestSpacing,
  };
}

function fallGeometry(tree: ForestTree, strength: number): { length: number; width: number } {
  return {
    length: 0.04 + tree.size * 0.2 * clamp(strength, 0.45, 1.6),
    width: 0.018 + tree.size * 0.035,
  };
}

function treefallImpact(source: ForestTree, target: ForestTree, angle: number, strength: number): { damage: number; mortality: number } {
  const { length, width } = fallGeometry(source, strength);
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const along = dx * Math.cos(angle) + dy * Math.sin(angle);
  const across = Math.abs(-dx * Math.sin(angle) + dy * Math.cos(angle));

  if (along <= 0 || along >= length || across >= width) {
    return { damage: 0, mortality: 0 };
  }

  const corridorFactor = (1 - along / length) * (1 - across / width);
  const targetVulnerability =
    (target.canopyRole === "suppressed" ? 1.25 : target.canopyRole === "subcanopy" ? 1.1 : 0.95) *
    (isLarge(target.temperament) ? 0.85 : 1.05);
  const damage = corridorFactor * strength * 0.46 * targetVulnerability;
  const mortality = clamp(damage * (isLarge(target.temperament) ? 0.26 : 0.42), 0, 0.9);

  return { damage, mortality };
}

export function simulateTreefallCascade(
  deadTree: ForestTree,
  survivors: ForestTree[],
  rngState: number,
  wind: number,
  windDriven = true,
  prevailingAngle = 0,
): {
  impactedIds: number[];
  damageById: Map<number, number>;
  killedIds: Set<number>;
  nextRngState: number;
} {
  const rng = createRng(rngState);
  const queue: FallQueueItem[] = [
    {
      tree: deadTree,
      strength: treefallStrength(deadTree, wind, windDriven),
      angle: treefallDirection(rng, prevailingAngle, windDriven),
    },
  ];
  const damageById = new Map<number, number>();
  const killedIds = new Set<number>();
  const impactedIds: number[] = [];

  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const target of survivors) {
      if (target.id === current.tree.id || killedIds.has(target.id)) {
        continue;
      }

      const impact = treefallImpact(current.tree, target, current.angle, current.strength);
      if (impact.damage <= 0) {
        continue;
      }

      damageById.set(target.id, (damageById.get(target.id) ?? 0) + impact.damage);
      if (!impactedIds.includes(target.id)) {
        impactedIds.push(target.id);
      }

      if (randomChance(rng, impact.mortality)) {
        killedIds.add(target.id);
        if (isLarge(target.temperament) && impact.damage > 0.18) {
          queue.push({
            tree: target,
            strength: current.strength * 0.62,
            angle: angleJitter(current.angle, rng, 0.38),
          });
        }
      }
    }
  }

  return {
    impactedIds,
    damageById,
    killedIds,
    nextRngState: rng.state,
  };
}

export function createForestPrototypeState(seed = DEFAULT_SEED): ForestPrototypeState {
  const seeded = seedInitialTrees(seed);
  const projection = projectStand(seeded.trees, DEFAULT_CONTROLS, {
    gapFraction: INITIAL_GAP_FRACTION,
    recentDisturbancePulse: INITIAL_RECENT_DISTURBANCE,
  });
  const derived = buildDerivedState(projection);
  const baseState: ForestPrototypeState = {
    seed,
    year: DEFAULT_YEAR,
    trees: projection.trees,
    controls: { ...DEFAULT_CONTROLS },
    derived,
    history: [],
    rngState: seeded.rngState,
    nextTreeId: seeded.nextTreeId,
    isPlaying: false,
    speed: SPEED_OPTIONS[1],
  };

  return {
    ...baseState,
    history: pushHistory(baseState, derived),
  };
}

export function recomputeForestState(state: ForestPrototypeState, nextControls = state.controls): ForestPrototypeState {
  const projection = projectStand(state.trees, nextControls, {
    gapFraction: state.derived.gapFraction,
    recentDisturbancePulse: state.derived.recentDisturbancePulse,
  });
  const derived = buildDerivedState(projection, {
    turnoverRate: state.derived.turnoverRate,
    disturbanceFrequency: state.derived.disturbanceFrequency,
    gapFraction: state.derived.gapFraction,
    recentDisturbancePulse: state.derived.recentDisturbancePulse,
  });

  const nextState = {
    ...state,
    controls: { ...nextControls },
    trees: projection.trees,
    derived,
  };

  return {
    ...nextState,
    history: replaceLatestHistory(nextState, derived),
  };
}

export function updateForestControls(state: ForestPrototypeState, patch: Partial<ForestControls>): ForestPrototypeState {
  return recomputeForestState(state, {
    ...state.controls,
    ...patch,
  });
}

export function setPlaybackSpeed(state: ForestPrototypeState, speed: ForestPrototypeState["speed"]): ForestPrototypeState {
  return { ...state, speed };
}

export function setPlaybackState(state: ForestPrototypeState, isPlaying: boolean): ForestPrototypeState {
  return { ...state, isPlaying };
}

export function stepForestState(state: ForestPrototypeState): ForestPrototypeState {
  const rng = createRng(state.rngState);
  const projection = projectStand(state.trees, state.controls, {
    gapFraction: state.derived.gapFraction,
    recentDisturbancePulse: state.derived.recentDisturbancePulse,
  });
  const workingTrees = projection.trees.map((tree) => ({ ...tree }));
  const accumulators = createAccumulators();
  const windLoad = intensifiedControl(state.controls.wind);
  const fireOccurred = randomChance(rng, projection.fireRisk * 0.28);
  const fireTargetIds = new Set<number>();
  const prevailingWindAngle = randomBetween(rng, 0, Math.PI * 2);

  if (fireOccurred && workingTrees.length > 0) {
    const fraction = randomBetween(rng, 0.42, 0.82);
    const fireTargetCount = Math.max(1, Math.round(workingTrees.length * fraction));
    const shuffled = [...workingTrees].sort(() => nextRandom(rng) - 0.5);
    for (const tree of shuffled.slice(0, fireTargetCount)) {
      fireTargetIds.add(tree.id);
    }
  }

  const survivors: ForestTree[] = [];
  const activeCounts = emptyRecord();
  const candidates: StepCandidate[] = [];
  const deadTreeAnchors: StandPoint[] = [];
  let deadAnyThisYear = 0;
  let deadLargeThisYear = 0;
  let largeWindDeaths = 0;
  let gapPulse = 0;

  for (const tree of workingTrees) {
    const growthPotential = estimateGrowthPotential(tree, state.controls, projection.droughtStress, projection.regrowthOpportunity);
    const fireDamage = fireTargetIds.has(tree.id) ? randomBetween(rng, 0.42, 0.9) : 0;
    const nextVigor = clamp(
      tree.vigor +
        growthPotential * 0.42 -
        tree.suppressionLevel * 0.22 -
        projection.droughtStress * TEMPERAMENT_PARAMS[tree.temperament].heatSensitivity * 0.28 -
        (tree.disturbanceDamage + fireDamage) * 0.26,
    );
    const nextSuppressionYears =
      tree.canopyRole === "suppressed" && tree.suppressionLevel > 0.45 ? tree.suppressionYears + 1 : Math.max(0, tree.suppressionYears - 1);
    const nextSize = clamp(tree.size + growthPotential, 0.08, TEMPERAMENT_PARAMS[tree.temperament].maxSize);
    const nextDamage = clamp(tree.disturbanceDamage + fireDamage - 0.12);
    let mortalityRisk = estimateMortalityRisk(
      tree,
      state.controls,
      projection.droughtStress,
      nextDamage,
      nextSuppressionYears,
    );

    if (fireTargetIds.has(tree.id)) {
      mortalityRisk = clamp(mortalityRisk + 0.18, 0, 0.98);
    }

    accumulators.growthTotals[tree.temperament] += growthPotential;
    accumulators.growthCounts[tree.temperament] += 1;
    accumulators.riskTotals[tree.temperament] += mortalityRisk;
    accumulators.riskCounts[tree.temperament] += 1;

    const nextTree: ForestTree = {
      ...tree,
      age: tree.age + 1,
      size: nextSize,
      vigor: nextVigor,
      disturbanceDamage: nextDamage,
      suppressionYears: nextSuppressionYears,
      sizeClass: deriveSizeClass(nextSize),
      reproductiveState: deriveReproductiveState(tree.age + 1, nextSize, nextVigor),
    };

    const directDeath = randomChance(rng, mortalityRisk);
    const directWindFailure =
      directDeath &&
      isLarge(tree.temperament) &&
      (state.controls.wind > 0.45 || tree.canopyRole === "canopy");

    candidates.push({
      sourceTree: tree,
      nextTree,
      mortalityRisk,
      directDeath,
      directWindFailure,
      fireDamage,
    });
  }

  const secondaryKilledIds = new Set<number>();
  const knockdownDamageById = new Map<number, number>();
  const fallEvents = candidates.filter((candidate) => candidate.directDeath && isLarge(candidate.sourceTree.temperament));

  for (const fallEvent of fallEvents) {
    const standingTargets = candidates
      .filter((candidate) => !candidate.directDeath && !secondaryKilledIds.has(candidate.sourceTree.id))
      .map((candidate) => candidate.nextTree);
    const outcome = simulateTreefallCascade(
      fallEvent.nextTree,
      standingTargets,
      rng.state,
      state.controls.wind,
      fallEvent.directWindFailure,
      prevailingWindAngle,
    );
    rng.state = outcome.nextRngState;

    for (const [id, damage] of outcome.damageById.entries()) {
      knockdownDamageById.set(id, (knockdownDamageById.get(id) ?? 0) + damage);
    }
    for (const id of outcome.killedIds) {
      secondaryKilledIds.add(id);
    }
  }

  for (const candidate of candidates) {
    const totalImpactDamage = knockdownDamageById.get(candidate.sourceTree.id) ?? 0;
    const died = candidate.directDeath || secondaryKilledIds.has(candidate.sourceTree.id);
    const nextTree = {
      ...candidate.nextTree,
      disturbanceDamage: clamp(candidate.nextTree.disturbanceDamage + totalImpactDamage),
    };

    if (died) {
      deadAnyThisYear += 1;
      deadTreeAnchors.push({ x: candidate.sourceTree.x, y: candidate.sourceTree.y });
      if (isLarge(candidate.sourceTree.temperament)) {
        deadLargeThisYear += 1;
        gapPulse += 0.2;
        if (candidate.directWindFailure || secondaryKilledIds.has(candidate.sourceTree.id)) {
          largeWindDeaths += 1;
        }
      } else {
        gapPulse += 0.06;
      }
      continue;
    }

    if (nextTree.reproductiveState === "active") {
      activeCounts[nextTree.temperament] += 1;
    }

    survivors.push(nextTree);
  }

  const eventScale = Math.max(projection.livingTreeCount, BASELINE_TREE_COUNT) / BASELINE_TREE_COUNT;
  const gapFraction = clamp(
    (deadLargeThisYear / eventScale) * 0.055 + (deadAnyThisYear / eventScale) * 0.012 + state.derived.gapFraction * 0.42,
  );
  const recentDisturbancePulse = clamp(
    state.derived.recentDisturbancePulse * 0.28 +
      (fireOccurred ? 0.72 : 0) +
      (gapPulse / eventScale) * 0.95 +
      Math.min(0.28, windLoad * (largeWindDeaths / eventScale) * 0.08),
  );
  const disturbanceFrequency = clamp(
    state.derived.recentDisturbancePulse * 0.12 +
      (fireOccurred ? 0.62 : 0) +
      Math.min(0.42, (deadLargeThisYear / eventScale) * 0.14) +
      windLoad * 0.22,
  );
  const postProjection = projectStand(survivors, state.controls, {
    gapFraction,
    recentDisturbancePulse,
  });

  const seedRain = emptyRecord();
  const hasLocalSeedSource = totalRecordValue(activeCounts) > 0;
  const regionalSeedRain = externalSeedRain(postProjection, gapFraction, hasLocalSeedSource);
  // TODO: External recolonization is currently doing important stability work.
  // Calibrate how much recovery should come from local seed sources versus
  // regional rain so the prototype does not recover too quickly or too
  // uniformly after disturbance.
  const recoveryPressure = stockingRecoveryPressure(postProjection.livingTreeCount);
  for (const temperament of TEMPERAMENTS) {
    seedRain[temperament] = activeCounts[temperament] * TEMPERAMENT_PARAMS[temperament].fecundity * 0.11;
    seedRain[temperament] += regionalSeedRain[temperament] * (0.18 + recoveryPressure * 2.2);
  }

  const recruits: ForestTree[] = [];
  let nextTreeId = state.nextTreeId;
  const recruitBase =
    (0.22 + postProjection.regrowthOpportunity * 1.45 + recoveryPressure * 1.3) *
    (1 - postProjection.droughtStress * 0.62);

  for (const temperament of TEMPERAMENTS) {
    let expected = seedRain[temperament] * recruitBase;
    if (isGambler(temperament) && postProjection.regrowthOpportunity >= 0.35) {
      expected *=
        1 +
        TEMPERAMENT_PARAMS[temperament].openingBonus *
          Math.max(postProjection.regrowthOpportunity - 0.2, 0) *
          (0.95 + intensifiedControl(state.controls.growthAdvantage) * 0.72);
    }

    const whole = Math.floor(expected);
    let recruitCount = whole + (randomChance(rng, expected - whole) ? 1 : 0);

    if (recoveryPressure > 0.45 && regionalSeedRain[temperament] > 0) {
      recruitCount = Math.max(recruitCount, randomChance(rng, recoveryPressure * 0.8) ? 3 : 2);
    }

    while (recruitCount > 0 && survivors.length + recruits.length < MAX_LIVING_TREES) {
      const occupied = [...survivors, ...recruits].map((tree) => ({ x: tree.x, y: tree.y }));
      const recruitPosition = findRecruitPosition(occupied, rng.state, deadTreeAnchors);
      rng.state = recruitPosition.nextRngState;

      recruits.push({
        id: nextTreeId,
        temperament,
        age: 1,
        alive: true,
        x: recruitPosition.point.x,
        y: recruitPosition.point.y,
        size: 0.08,
        sizeClass: "seedling",
        canopyRole: "suppressed",
        vigor: 0.72,
        suppressionLevel: 0,
        reproductiveState: "immature",
        disturbanceDamage: 0,
        suppressionYears: 0,
      });
      nextTreeId += 1;
      recruitCount -= 1;
    }
  }

  const finalTrees = [...survivors, ...recruits];
  const finalProjection = projectStand(finalTrees, state.controls, {
    gapFraction,
    recentDisturbancePulse,
  });
  const growthRateByTemperament = finalizeRates(
    accumulators.growthTotals,
    accumulators.growthCounts,
    finalProjection.growthRateByTemperament,
  );
  const mortalityRiskByTemperament = finalizeRates(
    accumulators.riskTotals,
    accumulators.riskCounts,
    finalProjection.mortalityRiskByTemperament,
  );
  const turnoverRate = clamp((deadAnyThisYear + recruits.length) / Math.max(projection.livingTreeCount, 1));
  const derived = buildDerivedState(finalProjection, {
    turnoverRate,
    disturbanceFrequency,
    gapFraction,
    recentDisturbancePulse,
    growthRateByTemperament,
    mortalityRiskByTemperament,
  });

  const nextState: ForestPrototypeState = {
    ...state,
    year: state.year + 1,
    trees: finalProjection.trees,
    derived,
    rngState: rng.state,
    nextTreeId,
  };

  return {
    ...nextState,
    history: pushHistory(nextState, derived),
  };
}

export function resetForestState(state: ForestPrototypeState): ForestPrototypeState {
  return createForestPrototypeState(state.seed);
}

export function dominantStatusText(state: ForestPrototypeState): string {
  const metrics: Array<{ label: string; value: number; sentence: string }> = [
    {
      label: "heat",
      value: state.derived.fireRisk + state.derived.droughtStress,
      sentence: "Heat is amplifying drought stress and fire risk.",
    },
    {
      label: "wind",
      value: state.controls.wind + state.derived.disturbanceFrequency * 0.7,
      sentence: "Wind pressure is driving structural failure and openings.",
    },
    {
      label: "turnover",
      value: state.derived.turnoverRate + state.controls.mortalityPressure * 0.6,
      sentence: "Baseline turnover is creating replacement pressure.",
    },
    {
      label: "release",
      value: state.derived.regrowthOpportunity + state.controls.growthAdvantage * 0.35,
      sentence: "Regrowth opportunity is rewarding opportunistic temperaments.",
    },
  ];

  metrics.sort((left, right) => right.value - left.value);
  return metrics[0]?.sentence ?? "The stand is in a relatively steady state.";
}
