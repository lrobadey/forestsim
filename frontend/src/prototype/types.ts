export const TEMPERAMENTS = [
  "large_gambler",
  "small_gambler",
  "large_struggler",
  "small_struggler",
] as const;

export type Temperament = (typeof TEMPERAMENTS)[number];

export const TEMPERAMENT_LABELS: Record<Temperament, string> = {
  large_gambler: "Large Gambler",
  small_gambler: "Small Gambler",
  large_struggler: "Large Struggler",
  small_struggler: "Small Struggler",
};

export const TEMPERAMENT_SHORT_LABELS: Record<Temperament, string> = {
  large_gambler: "LG",
  small_gambler: "SG",
  large_struggler: "LS",
  small_struggler: "SS",
};

export const TEMPERAMENT_COLORS: Record<Temperament, string> = {
  large_gambler: "#f2a33a",
  small_gambler: "#ffcf70",
  large_struggler: "#2aa57d",
  small_struggler: "#97d8bf",
};

export const SPEED_OPTIONS = ["0.5x", "1x", "2x", "4x", "10x", "20x"] as const;

export type PlaybackSpeed = (typeof SPEED_OPTIONS)[number];
export type SizeClass = "seedling" | "juvenile" | "canopy_candidate" | "large_canopy";
export type CanopyRole = "canopy" | "subcanopy" | "suppressed";
export type ReproductiveState = "immature" | "maturing" | "active";
export type GapSource = "canopy_loss" | "fire";

export type TemperamentRecord = Record<Temperament, number>;

export interface ForestTree {
  id: number;
  temperament: Temperament;
  age: number;
  alive: boolean;
  x: number;
  y: number;
  size: number;
  sizeClass: SizeClass;
  canopyRole: CanopyRole;
  vigor: number;
  suppressionLevel: number;
  reproductiveState: ReproductiveState;
  disturbanceDamage: number;
  suppressionYears: number;
}

export interface ForestGap {
  id: number;
  x: number;
  y: number;
  radius: number;
  age: number;
  intensity: number;
  source: GapSource;
}

export interface ForestControls {
  heat: number;
  wind: number;
  growthAdvantage: number;
  mortalityPressure: number;
}

export interface ForestDerivedState {
  droughtStress: number;
  fireRisk: number;
  regrowthOpportunity: number;
  turnoverRate: number;
  disturbanceFrequency: number;
  gapFraction: number;
  canopyClosure: number;
  livingTreeCount: number;
  meanVigor: number;
  recentDisturbancePulse: number;
  shareByTemperament: TemperamentRecord;
  growthRateByTemperament: TemperamentRecord;
  mortalityRiskByTemperament: TemperamentRecord;
}

export interface ForestHistoryPoint {
  year: number;
  livingTreeCount: number;
  turnoverRate: number;
  disturbanceFrequency: number;
  gapFraction: number;
  shareByTemperament: TemperamentRecord;
}

export interface ForestPrototypeState {
  seed: number;
  year: number;
  trees: ForestTree[];
  gaps: ForestGap[];
  controls: ForestControls;
  derived: ForestDerivedState;
  history: ForestHistoryPoint[];
  rngState: number;
  nextTreeId: number;
  nextGapId: number;
  isPlaying: boolean;
  speed: PlaybackSpeed;
}
