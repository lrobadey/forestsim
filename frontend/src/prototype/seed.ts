import type { CanopyRole, ForestControls, ForestDerivedState, ForestHistoryPoint, ForestTree, ReproductiveState, SizeClass, Temperament } from "./types";
import { TEMPERAMENTS } from "./types";

export const DEFAULT_SEED = 42017;
export const DEFAULT_YEAR = 2025;
export const BASELINE_TREE_COUNT = 120;
export const INITIAL_TREE_COUNT = 240;
export const MAX_LIVING_TREES = 480;
export const HISTORY_LIMIT = 80;
export const INITIAL_GAP_FRACTION = 0.16;
export const INITIAL_RECENT_DISTURBANCE = 0.12;
export const MIN_TREE_SPACING = 0.018;

export const DEFAULT_CONTROLS: ForestControls = {
  heat: 0.5,
  wind: 0.5,
  growthAdvantage: 0.5,
  mortalityPressure: 0.5,
};

// TODO: Re-center these defaults so a neutral run behaves like a believable
// reference stand. Current research-backed review found that baseline runs
// remain too open and too disturbance-prone to serve as a convincing normal
// forest state.

export const EMPTY_RECORD = (): Record<Temperament, number> => ({
  large_gambler: 0,
  small_gambler: 0,
  large_struggler: 0,
  small_struggler: 0,
});

export const INITIAL_SHARES: Record<Temperament, number> = {
  large_gambler: 0.22,
  small_gambler: 0.28,
  large_struggler: 0.24,
  small_struggler: 0.26,
};

export interface RngCursor {
  state: number;
}

export function clamp(value: number, min = 0, max = 1): number {
  return Math.max(min, Math.min(max, value));
}

export function createRng(seed: number): RngCursor {
  return { state: (seed >>> 0) || 1 };
}

export function nextRandom(cursor: RngCursor): number {
  let state = cursor.state || 1;
  state ^= state << 13;
  state ^= state >>> 17;
  state ^= state << 5;
  cursor.state = state >>> 0;
  return cursor.state / 4294967296;
}

export function randomBetween(cursor: RngCursor, min: number, max: number): number {
  return min + (max - min) * nextRandom(cursor);
}

export function randomInt(cursor: RngCursor, min: number, max: number): number {
  return Math.floor(randomBetween(cursor, min, max + 1));
}

export function randomChance(cursor: RngCursor, probability: number): boolean {
  return nextRandom(cursor) < clamp(probability, 0, 1);
}

function shuffleInPlace<T>(items: T[], cursor: RngCursor): T[] {
  for (let index = items.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(nextRandom(cursor) * (index + 1));
    [items[index], items[swapIndex]] = [items[swapIndex], items[index]];
  }
  return items;
}

function generateStandPositions(total: number, cursor: RngCursor): Array<{ x: number; y: number }> {
  const columns = Math.ceil(Math.sqrt(total));
  const rows = Math.ceil(total / columns);
  const cellWidth = 1 / columns;
  const cellHeight = 1 / rows;
  const positions: Array<{ x: number; y: number }> = [];

  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      if (positions.length >= total) {
        break;
      }
      positions.push({
        x: clamp(column * cellWidth + randomBetween(cursor, cellWidth * 0.15, cellWidth * 0.85), 0.02, 0.98),
        y: clamp(row * cellHeight + randomBetween(cursor, cellHeight * 0.15, cellHeight * 0.85), 0.02, 0.98),
      });
    }
  }

  return shuffleInPlace(positions, cursor);
}

export function deriveSizeClass(size: number): SizeClass {
  if (size < 0.22) {
    return "seedling";
  }
  if (size < 0.48) {
    return "juvenile";
  }
  if (size < 0.72) {
    return "canopy_candidate";
  }
  return "large_canopy";
}

export function deriveReproductiveState(age: number, size: number, vigor: number): ReproductiveState {
  if (age >= 18 && size >= 0.25 && vigor >= 0.42) {
    return "active";
  }
  if (age >= 12 && size >= 0.18) {
    return "maturing";
  }
  return "immature";
}

function maxSizeForTemperament(temperament: Temperament): number {
  return temperament.startsWith("large") ? 1 : temperament === "small_gambler" ? 0.63 : 0.6;
}

function targetCounts(total: number): Record<Temperament, number> {
  const counts = EMPTY_RECORD();
  let assigned = 0;

  for (const temperament of TEMPERAMENTS) {
    const count = Math.floor(INITIAL_SHARES[temperament] * total);
    counts[temperament] = count;
    assigned += count;
  }

  let index = 0;
  while (assigned < total) {
    const temperament = TEMPERAMENTS[index % TEMPERAMENTS.length];
    counts[temperament] += 1;
    assigned += 1;
    index += 1;
  }

  return counts;
}

export function seedInitialTrees(seed: number): { trees: ForestTree[]; rngState: number; nextTreeId: number } {
  const rng = createRng(seed);
  const counts = targetCounts(INITIAL_TREE_COUNT);
  const positions = generateStandPositions(INITIAL_TREE_COUNT, rng);
  const trees: ForestTree[] = [];
  let nextTreeId = 1;
  let positionIndex = 0;

  for (const temperament of TEMPERAMENTS) {
    const isLarge = temperament.startsWith("large");
    const maxAge = isLarge ? 220 : 160;
    const maxSize = maxSizeForTemperament(temperament);
    const vigorBias = temperament.includes("struggler") ? 0.06 : 0;

    for (let index = 0; index < counts[temperament]; index += 1) {
      const age = randomInt(rng, 5, maxAge);
      const maturity = clamp((age - 5) / Math.max(maxAge - 5, 1));
      const baseSize = isLarge ? 0.18 + maturity * 0.8 : 0.12 + maturity * 0.48;
      const size = clamp(baseSize + randomBetween(rng, -0.12, 0.12), 0.08, maxSize);
      const vigor = clamp(0.58 + vigorBias + randomBetween(rng, -0.2, 0.16) - (age > 150 ? 0.08 : 0));
      const suppressionYears = size < 0.28 ? randomInt(rng, 1, 18) : randomInt(rng, 0, 8);

      trees.push({
        id: nextTreeId,
        temperament,
        age,
        alive: true,
        x: positions[positionIndex]?.x ?? randomBetween(rng, 0.05, 0.95),
        y: positions[positionIndex]?.y ?? randomBetween(rng, 0.05, 0.95),
        size,
        sizeClass: deriveSizeClass(size),
        canopyRole: "suppressed",
        vigor,
        suppressionLevel: 0,
        reproductiveState: deriveReproductiveState(age, size, vigor),
        disturbanceDamage: randomBetween(rng, 0, 0.15),
        suppressionYears,
      });

      nextTreeId += 1;
      positionIndex += 1;
    }
  }

  return {
    trees,
    rngState: rng.state,
    nextTreeId,
  };
}

export function zeroDerivedState(): ForestDerivedState {
  return {
    droughtStress: 0,
    fireRisk: 0,
    regrowthOpportunity: 0,
    turnoverRate: 0,
    disturbanceFrequency: 0,
    gapFraction: 0,
    canopyClosure: 0,
    livingTreeCount: 0,
    meanVigor: 0,
    recentDisturbancePulse: 0,
    shareByTemperament: EMPTY_RECORD(),
    growthRateByTemperament: EMPTY_RECORD(),
    mortalityRiskByTemperament: EMPTY_RECORD(),
  };
}

export function createHistoryPoint(year: number, derived: ForestDerivedState): ForestHistoryPoint {
  return {
    year,
    livingTreeCount: derived.livingTreeCount,
    turnoverRate: derived.turnoverRate,
    disturbanceFrequency: derived.disturbanceFrequency,
    gapFraction: derived.gapFraction,
    shareByTemperament: { ...derived.shareByTemperament },
  };
}

export function roleWeight(role: CanopyRole): number {
  if (role === "canopy") {
    return 0.4;
  }
  if (role === "subcanopy") {
    return 0.72;
  }
  return 1;
}
