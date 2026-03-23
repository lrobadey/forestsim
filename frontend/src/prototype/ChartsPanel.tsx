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

function renderTrendPreview(
  trendKey: "living" | "temperament" | "turnover" | "disturbance",
  points: ForestHistoryPoint[],
  color: string,
): JSX.Element {
  if (trendKey === "temperament") {
    return (
      <>
        {TEMPERAMENTS.map((temperament) => (
          <polyline
            key={temperament}
            fill="none"
            stroke={TEMPERAMENT_COLORS[temperament]}
            strokeWidth="2.5"
            points={buildPolyline(points.map((point) => point.shareByTemperament[temperament]), 0, 1, 180, 44, 4, 5)}
          />
        ))}
      </>
    );
  }

  const series =
    trendKey === "living"
      ? points.map((point) => point.livingTreeCount)
      : trendKey === "turnover"
        ? points.map((point) => point.turnoverRate)
        : points.map((point) => point.disturbanceFrequency);
  const min = trendKey === "living" ? Math.min(...series, 0) : 0;
  const max = trendKey === "living" ? Math.max(...series, 1) : 1;

  return <polyline fill="none" stroke={color} strokeWidth="2.5" points={buildPolyline(series, min, max, 180, 44, 4, 5)} />;
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

  return (
    <section className="charts-panel panel" aria-label="Trend charts">
      <div className="panel-copy">
        <p className="eyebrow">Trends</p>
        <h2>How the stand has been moving over time.</h2>
      </div>
      <div style={{ display: "grid", gap: "0.7rem" }}>
        <article
          className="chart-card"
          style={{
            minWidth: 0,
            padding: "0.8rem",
            background: "rgba(255, 248, 236, 0.08)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "baseline", marginBottom: "0.45rem" }}>
            <div className="chart-copy">
              <strong>{active.title}</strong>
              <span>{active.subtitle}</span>
            </div>
            <span
              style={{
                flex: "0 0 auto",
                padding: "0.24rem 0.55rem",
                borderRadius: "999px",
                background: "rgba(255, 208, 134, 0.16)",
                color: "var(--accent-strong)",
                fontSize: "0.7rem",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
              }}
            >
              Primary
            </span>
          </div>
          <svg viewBox="0 0 320 104" role="img" aria-label={active.ariaLabel} style={{ width: "100%", height: "auto" }}>
            {activeTrend === "temperament" ? (
              TEMPERAMENTS.map((temperament) => (
                <polyline
                  key={temperament}
                  fill="none"
                  stroke={TEMPERAMENT_COLORS[temperament]}
                  strokeWidth="2.5"
                  points={buildPolyline(points.map((point) => point.shareByTemperament[temperament]), 0, 1, 320, 104, 8, 10)}
                />
              ))
            ) : (
              <polyline fill="none" stroke={active.color} strokeWidth="3" points={buildPolyline(active.points, active.min, active.max, 320, 104, 8, 10)} />
            )}
            <path d="M0 92 H320" className="chart-axis" />
          </svg>
          <div style={{ display: "grid", gap: "0.5rem", marginTop: "0.35rem" }}>
            <p style={{ margin: 0, color: "var(--muted)", lineHeight: 1.35 }}>{active.description}</p>
            {active.hasLegend ? (
              <div className="chart-legend">
                {TEMPERAMENTS.map((temperament) => (
                  <span key={temperament}>
                    <i style={{ background: TEMPERAMENT_COLORS[temperament] }} />
                    {TEMPERAMENT_LABELS[temperament]}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        </article>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.45rem",
            alignItems: "stretch",
          }}
        >
          {selectorOrder.map((trendKey) => {
            const trend = trendMap[trendKey];
            const isActive = activeTrend === trendKey;
            return (
              <button
                key={trendKey}
                type="button"
                onClick={() => setActiveTrend(trendKey)}
                aria-pressed={isActive}
                style={{
                  flex: "1 1 150px",
                  minWidth: 0,
                  textAlign: "left",
                  padding: "0.55rem 0.65rem",
                  borderRadius: "16px",
                  background: isActive ? "rgba(255, 249, 239, 0.14)" : "rgba(255, 248, 236, 0.06)",
                  border: isActive ? "1px solid rgba(255, 213, 146, 0.42)" : "1px solid rgba(255, 241, 223, 0.14)",
                  color: "inherit",
                  display: "grid",
                  gap: "0.4rem",
                }}
              >
                <div className="chart-copy" style={{ gap: "0.18rem" }}>
                  <strong>{trend.title}</strong>
                  <span>{trend.subtitle}</span>
                </div>
                <svg viewBox="0 0 180 40" aria-hidden="true" focusable="false" style={{ width: "100%", height: "auto" }}>
                  <path d="M0 34 H180" className="chart-axis" />
                  {renderTrendPreview(trendKey, points, trend.color)}
                </svg>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
