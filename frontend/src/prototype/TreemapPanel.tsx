import { TEMPERAMENT_COLORS, TEMPERAMENT_LABELS, TEMPERAMENT_SHORT_LABELS, TEMPERAMENTS } from "./types";
import type { TemperamentRecord } from "./types";

interface TreemapPanelProps {
  livingTreeCount: number;
  shareByTemperament: TemperamentRecord;
}

interface Rect {
  temperament: (typeof TEMPERAMENTS)[number];
  x: number;
  y: number;
  width: number;
  height: number;
}

function buildTreemap(entries: Array<{ temperament: (typeof TEMPERAMENTS)[number]; value: number }>, x: number, y: number, width: number, height: number, vertical: boolean): Rect[] {
  if (!entries.length) {
    return [];
  }
  if (entries.length === 1) {
    return [{ temperament: entries[0].temperament, x, y, width, height }];
  }

  const total = entries.reduce((sum, entry) => sum + entry.value, 0);
  let running = 0;
  let splitIndex = 1;

  for (; splitIndex < entries.length; splitIndex += 1) {
    running += entries[splitIndex - 1].value;
    if (running >= total / 2) {
      break;
    }
  }

  if (splitIndex >= entries.length) {
    splitIndex = entries.length - 1;
  }

  const leftEntries = entries.slice(0, splitIndex);
  const rightEntries = entries.slice(splitIndex);
  const leftValue = leftEntries.reduce((sum, entry) => sum + entry.value, 0);
  const ratio = total > 0 ? leftValue / total : 0.5;

  if (vertical) {
    const leftWidth = width * ratio;
    return [
      ...buildTreemap(leftEntries, x, y, leftWidth, height, !vertical),
      ...buildTreemap(rightEntries, x + leftWidth, y, width - leftWidth, height, !vertical),
    ];
  }

  const topHeight = height * ratio;
  return [
    ...buildTreemap(leftEntries, x, y, width, topHeight, !vertical),
    ...buildTreemap(rightEntries, x, y + topHeight, width, height - topHeight, !vertical),
  ];
}

export function TreemapPanel({ livingTreeCount, shareByTemperament }: TreemapPanelProps) {
  const entries = TEMPERAMENTS.map((temperament) => ({
    temperament,
    value: Math.max(shareByTemperament[temperament], 0.0001),
  }));
  const rectangles = buildTreemap(entries, 0, 0, 100, 100, true);
  const [dominant, runnerUp] = [...entries].sort((left, right) => right.value - left.value);
  const dominantShare = Math.round(dominant.value * 100);
  const runnerUpShare = Math.round(runnerUp.value * 100);

  return (
    <section
      className="treemap-panel panel"
      aria-label="Composition treemap"
      style={{
        display: "grid",
        gridTemplateRows: "auto auto minmax(0, 1fr)",
        minHeight: 0,
      }}
    >
      <div className="panel-copy" style={{ marginBottom: "0.55rem" }}>
        <p className="eyebrow">Composition</p>
        <h2>Who owns the forest right now?</h2>
        <p>{livingTreeCount} living trees across four temperaments.</p>
      </div>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.55rem",
          marginBottom: "0.7rem",
        }}
        aria-label="Treemap summary"
      >
        <article
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: "0.65rem",
            flex: "1 1 140px",
            minWidth: 0,
            padding: "0.55rem 0.75rem",
            borderRadius: "16px",
            background: "rgba(255, 248, 236, 0.08)",
            border: "1px solid rgba(255, 241, 223, 0.14)",
          }}
        >
          <span className="eyebrow" style={{ marginBottom: 0 }}>
            Living trees
          </span>
          <strong style={{ fontVariantNumeric: "tabular-nums" }}>{livingTreeCount}</strong>
        </article>
        <article
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: "0.65rem",
            flex: "1 1 140px",
            minWidth: 0,
            padding: "0.55rem 0.75rem",
            borderRadius: "16px",
            background: "rgba(255, 248, 236, 0.08)",
            border: "1px solid rgba(255, 241, 223, 0.14)",
          }}
        >
          <span className="eyebrow" style={{ marginBottom: 0 }}>
            Dominant share
          </span>
          <strong style={{ fontVariantNumeric: "tabular-nums" }}>
            {TEMPERAMENT_SHORT_LABELS[dominant.temperament]} {dominantShare}%
          </strong>
        </article>
        <article
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: "0.65rem",
            flex: "1 1 140px",
            minWidth: 0,
            padding: "0.55rem 0.75rem",
            borderRadius: "16px",
            background: "rgba(255, 248, 236, 0.08)",
            border: "1px solid rgba(255, 241, 223, 0.14)",
          }}
        >
          <span className="eyebrow" style={{ marginBottom: 0 }}>
            Next up
          </span>
          <strong style={{ fontVariantNumeric: "tabular-nums" }}>
            {TEMPERAMENT_SHORT_LABELS[runnerUp.temperament]} {runnerUpShare}%
          </strong>
        </article>
      </div>
      <div
        className="treemap-stage"
        role="img"
        aria-label="Temperament share treemap"
        style={{
          position: "relative",
          minHeight: 0,
          flex: "1 1 auto",
        }}
      >
        {rectangles.map((rect) => {
          const count = Math.round(shareByTemperament[rect.temperament] * livingTreeCount);
          const percentage = Math.round(shareByTemperament[rect.temperament] * 100);
          return (
            <article
              key={rect.temperament}
              className="treemap-block"
              data-testid={`treemap-${rect.temperament}`}
              data-count={count}
              aria-label={`${TEMPERAMENT_LABELS[rect.temperament]} ${count} trees, ${percentage}%`}
              title={`${TEMPERAMENT_LABELS[rect.temperament]} ${count} trees, ${percentage}%`}
              style={{
                left: `${rect.x}%`,
                top: `${rect.y}%`,
                width: `${rect.width}%`,
                height: `${rect.height}%`,
                background: `linear-gradient(160deg, ${TEMPERAMENT_COLORS[rect.temperament]}, rgba(5, 9, 8, 0.28))`,
              }}
            >
              <span>{TEMPERAMENT_SHORT_LABELS[rect.temperament]}</span>
              <strong>{percentage}%</strong>
            </article>
          );
        })}
      </div>
    </section>
  );
}
