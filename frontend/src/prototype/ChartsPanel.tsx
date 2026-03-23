import { useState } from "react";
import { TEMPERAMENT_COLORS, TEMPERAMENT_LABELS, TEMPERAMENTS } from "./types";
import type { ForestHistoryPoint } from "./types";

interface ChartsPanelProps {
  history: ForestHistoryPoint[];
}

function buildPolyline(points: number[], min: number, max: number, width = 220, height = 80, topPadding = 6, bottomPadding = 6): string {
  return points
    .map((point, index) => {
      const x = points.length === 1 ? 0 : (index / (points.length - 1)) * width;
      const usableHeight = Math.max(height - topPadding - bottomPadding, 1);
      const y = height - bottomPadding - ((point - min) / Math.max(max - min, 1e-6)) * usableHeight;
      return `${x},${y}`;
    })
    .join(" ");
}

function formatMetric(trendKey: "living" | "temperament" | "turnover" | "disturbance", value: number): string {
  if (trendKey === "living") {
    return `${Math.round(value)}`;
  }

  return `${Math.round(value * 100)}%`;
}

export function ChartsPanel({ history }: ChartsPanelProps) {
  const [activeTrend, setActiveTrend] = useState<"living" | "temperament" | "turnover" | "disturbance">("living");
  const points = history.slice(-80);
  const livingCounts = points.map((point) => point.livingTreeCount);
  const turnoverRates = points.map((point) => point.turnoverRate);
  const disturbanceRates = points.map((point) => point.disturbanceFrequency);
  const trendMap = {
    living: {
      title: "Living tree count",
      shortLabel: "Living trees",
      subtitle: "Population trend",
      description: "The clearest single signal for stand trajectory.",
      color: "#f2a33a",
      points: livingCounts,
      min: Math.min(...livingCounts, 0),
      max: Math.max(...livingCounts, 1),
      ariaLabel: "Living tree count trend",
      hasLegend: false,
    },
    temperament: {
      title: "Share by temperament",
      shortLabel: "Temperaments",
      subtitle: "Living-tree share",
      description: "The composition split behind the count.",
      color: "#97d8bf",
      points: points.map((point) => Math.max(...TEMPERAMENTS.map((temperament) => point.shareByTemperament[temperament]))),
      min: 0,
      max: 1,
      ariaLabel: "Share by temperament trend",
      hasLegend: true,
    },
    turnover: {
      title: "Turnover rate",
      shortLabel: "Turnover",
      subtitle: "Deaths plus recruits",
      description: "Replacement pressure over the recent window.",
      color: "#d8f2d9",
      points: turnoverRates,
      min: 0,
      max: 1,
      ariaLabel: "Turnover rate trend",
      hasLegend: false,
    },
    disturbance: {
      title: "Disturbance frequency",
      shortLabel: "Disturbance",
      subtitle: "Recent fire and gap activity",
      description: "How often the stand is being jolted.",
      color: "#97d8bf",
      points: disturbanceRates,
      min: 0,
      max: 1,
      ariaLabel: "Disturbance frequency trend",
      hasLegend: false,
    },
  } as const;
  const active = trendMap[activeTrend];
  const selectorOrder = Object.keys(trendMap) as Array<keyof typeof trendMap>;
  const activeLatest = active.points.at(-1) ?? 0;

  return (
    <section className="charts-panel panel" aria-label="Trend charts">
      <div className="panel-copy">
        <p className="eyebrow">Trends</p>
        <h2>How the stand has been moving over time.</h2>
      </div>
      <div className="charts-panel-body">
        <article className="chart-card chart-card-primary">
          <div className="chart-card-head">
            <div className="chart-copy">
              <strong>{active.title}</strong>
              <span>{active.subtitle}</span>
            </div>
            <strong className="chart-value-pill">{formatMetric(activeTrend, activeLatest)}</strong>
          </div>
          <svg viewBox="0 0 320 88" role="img" aria-label={active.ariaLabel} className="chart-primary-svg">
            {activeTrend === "temperament" ? (
              TEMPERAMENTS.map((temperament) => (
                <polyline
                  key={temperament}
                  fill="none"
                  stroke={TEMPERAMENT_COLORS[temperament]}
                  strokeWidth="2.5"
                  points={buildPolyline(points.map((point) => point.shareByTemperament[temperament]), 0, 1, 320, 88, 8, 10)}
                />
              ))
            ) : (
              <polyline fill="none" stroke={active.color} strokeWidth="3" points={buildPolyline(active.points, active.min, active.max, 320, 88, 8, 10)} />
            )}
            <path d="M0 76 H320" className="chart-axis" />
          </svg>
          {active.hasLegend ? (
            <div className="chart-meta">
              <div className="chart-legend">
                {TEMPERAMENTS.map((temperament) => (
                  <span key={temperament}>
                    <i style={{ background: TEMPERAMENT_COLORS[temperament] }} />
                    {TEMPERAMENT_LABELS[temperament]}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </article>
        <div className="trend-toggle-grid">
          {selectorOrder.map((trendKey) => {
            const trend = trendMap[trendKey];
            const isActive = activeTrend === trendKey;
            return (
              <button
                key={trendKey}
                type="button"
                onClick={() => setActiveTrend(trendKey)}
                aria-pressed={isActive}
                className={isActive ? "trend-toggle trend-toggle-active" : "trend-toggle"}
              >
                <div className="chart-copy trend-toggle-copy">
                  <strong>{trend.shortLabel}</strong>
                </div>
                <strong className="trend-toggle-value">{formatMetric(trendKey, trend.points.at(-1) ?? 0)}</strong>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
