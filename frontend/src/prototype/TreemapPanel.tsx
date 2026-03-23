import { useRef } from "react";
import { TEMPERAMENT_COLORS, TEMPERAMENT_LABELS, TEMPERAMENT_SHORT_LABELS, TEMPERAMENTS } from "./types";
import type { ForestTree, SizeClass, Temperament, TemperamentRecord } from "./types";

interface TreemapPanelProps {
  trees: ForestTree[];
}

interface Rect<Key extends string> {
  id: Key;
  x: number;
  y: number;
  width: number;
  height: number;
  value: number;
}

const SIZE_CLASS_ORDER: SizeClass[] = ["large_canopy", "canopy_candidate", "juvenile", "seedling"];

const SIZE_CLASS_SHORT_LABELS: Record<SizeClass, string> = {
  large_canopy: "LC",
  canopy_candidate: "CC",
  juvenile: "JV",
  seedling: "SD",
};

const SIZE_CLASS_TAILS: Record<SizeClass, string> = {
  large_canopy: "rgba(9, 12, 16, 0.16)",
  canopy_candidate: "rgba(54, 33, 12, 0.34)",
  juvenile: "rgba(7, 10, 12, 0.48)",
  seedling: "rgba(209, 229, 224, 0.28)",
};

type Orientation = "vertical" | "horizontal";

function buildStripLayout<Key extends string>(
  entries: Array<{ id: Key; value: number }>,
  x: number,
  y: number,
  width: number,
  height: number,
  orientation: Orientation,
): Rect<Key>[] {
  if (!entries.length || width <= 0 || height <= 0) {
    return [];
  }

  if (entries.length === 1) {
    const [entry] = entries;
    return [{ id: entry.id, x, y, width, height, value: entry.value }];
  }

  const [first, ...rest] = entries;
  const total = entries.reduce((sum, entry) => sum + entry.value, 0);
  const ratio = total > 0 ? first.value / total : 1 / entries.length;

  if (orientation === "vertical") {
    const firstWidth = width * ratio;
    return [
      { id: first.id, x, y, width: firstWidth, height, value: first.value },
      ...buildStripLayout(rest, x + firstWidth, y, width - firstWidth, height, "horizontal"),
    ];
  }

  const firstHeight = height * ratio;
  return [
    { id: first.id, x, y, width, height: firstHeight, value: first.value },
    ...buildStripLayout(rest, x, y + firstHeight, width, height - firstHeight, "vertical"),
  ];
}

function countByTemperamentAndSize(trees: ForestTree[]): Record<Temperament, Record<SizeClass, number>> {
  const counts = Object.fromEntries(
    TEMPERAMENTS.map((temperament) => [
      temperament,
      Object.fromEntries(SIZE_CLASS_ORDER.map((sizeClass) => [sizeClass, 0])) as Record<SizeClass, number>,
    ]),
  ) as Record<Temperament, Record<SizeClass, number>>;

  for (const tree of trees) {
    if (!tree.alive) {
      continue;
    }
    counts[tree.temperament][tree.sizeClass] += 1;
  }

  return counts;
}

function stabilizeTemperamentOrder(previous: Temperament[], shares: TemperamentRecord, minLead = 0.035): Temperament[] {
  const next = [...previous];
  let moved = true;

  while (moved) {
    moved = false;
    for (let index = 1; index < next.length; index += 1) {
      const current = next[index];
      const ahead = next[index - 1];
      if (shares[current] > shares[ahead] + minLead) {
        next[index - 1] = current;
        next[index] = ahead;
        moved = true;
      }
    }
  }

  return next;
}

function percentage(value: number, total: number): number {
  return total > 0 ? Math.round((value / total) * 100) : 0;
}

function childBackground(color: string, sizeClass: SizeClass): string {
  return `linear-gradient(165deg, ${color}, ${SIZE_CLASS_TAILS[sizeClass]})`;
}

export function TreemapPanel({ trees }: TreemapPanelProps) {
  const livingTrees = trees.filter((tree) => tree.alive);
  const livingTreeCount = livingTrees.length;
  const byTemperamentAndSize = countByTemperamentAndSize(livingTrees);
  const temperamentCounts = Object.fromEntries(
    TEMPERAMENTS.map((temperament) => [
      temperament,
      SIZE_CLASS_ORDER.reduce((sum, sizeClass) => sum + byTemperamentAndSize[temperament][sizeClass], 0),
    ]),
  ) as Record<Temperament, number>;
  const shareByTemperament = Object.fromEntries(
    TEMPERAMENTS.map((temperament) => [temperament, livingTreeCount > 0 ? temperamentCounts[temperament] / livingTreeCount : 0]),
  ) as TemperamentRecord;

  const temperamentOrderRef = useRef<Temperament[] | null>(null);
  if (temperamentOrderRef.current === null) {
    temperamentOrderRef.current = [...TEMPERAMENTS].sort((left, right) => shareByTemperament[right] - shareByTemperament[left]);
  } else {
    temperamentOrderRef.current = stabilizeTemperamentOrder(temperamentOrderRef.current, shareByTemperament);
  }

  const orderedTemperaments = temperamentOrderRef.current;
  const temperamentRects = buildStripLayout(
    orderedTemperaments.map((temperament) => ({
      id: temperament,
      value: Math.max(temperamentCounts[temperament], 0.001),
    })),
    0,
    0,
    100,
    100,
    "vertical",
  );

  const [dominant, runnerUp] = [...TEMPERAMENTS].sort((left, right) => temperamentCounts[right] - temperamentCounts[left]);

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
        <p>{livingTreeCount} living trees split across four temperament groups.</p>
      </div>
      <div
        className="treemap-summary"
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.55rem",
          marginBottom: "0.7rem",
        }}
        aria-label="Treemap summary"
      >
        <article className="treemap-summary-pill">
          <span className="eyebrow" style={{ marginBottom: 0 }}>
            Living trees
          </span>
          <strong style={{ fontVariantNumeric: "tabular-nums" }}>{livingTreeCount}</strong>
        </article>
        <article className="treemap-summary-pill">
          <span className="eyebrow" style={{ marginBottom: 0 }}>
            Dominant share
          </span>
          <strong style={{ fontVariantNumeric: "tabular-nums" }}>
            {TEMPERAMENT_SHORT_LABELS[dominant]} {percentage(temperamentCounts[dominant], livingTreeCount)}%
          </strong>
        </article>
        <article className="treemap-summary-pill">
          <span className="eyebrow" style={{ marginBottom: 0 }}>
            Next up
          </span>
          <strong style={{ fontVariantNumeric: "tabular-nums" }}>
            {TEMPERAMENT_SHORT_LABELS[runnerUp]} {percentage(temperamentCounts[runnerUp], livingTreeCount)}%
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
        {temperamentRects.map((rect) => {
          const count = temperamentCounts[rect.id];
          const temperamentShare = percentage(count, livingTreeCount);
          const childRects = buildStripLayout(
            SIZE_CLASS_ORDER.filter((sizeClass) => byTemperamentAndSize[rect.id][sizeClass] > 0).map((sizeClass) => ({
              id: sizeClass,
              value: byTemperamentAndSize[rect.id][sizeClass],
            })),
            0,
            0,
            100,
            100,
            rect.width >= rect.height ? "vertical" : "horizontal",
          );
          const showGroupCopy = rect.width * rect.height > 120;

          return (
            <article
              key={rect.id}
              className="treemap-block"
              data-testid={`treemap-${rect.id}`}
              data-count={count}
              aria-label={`${TEMPERAMENT_LABELS[rect.id]} ${count} trees, ${temperamentShare}%`}
              title={`${TEMPERAMENT_LABELS[rect.id]} ${count} trees, ${temperamentShare}%`}
              style={{
                left: `${rect.x}%`,
                top: `${rect.y}%`,
                width: `${rect.width}%`,
                height: `${rect.height}%`,
                background: `linear-gradient(165deg, ${TEMPERAMENT_COLORS[rect.id]}, rgba(5, 9, 8, 0.42))`,
              }}
            >
              {showGroupCopy ? (
                <div className="treemap-block-copy">
                  <span>{TEMPERAMENT_LABELS[rect.id]}</span>
                  <strong>{temperamentShare}%</strong>
                </div>
              ) : null}
              <div className="treemap-block-inner">
                {childRects.map((childRect) => {
                  const childCount = byTemperamentAndSize[rect.id][childRect.id];
                  const showChildCopy = childRect.width * childRect.height > 240;
                  const showChildValue = childRect.width * childRect.height > 420;

                  return (
                    <div
                      key={`${rect.id}-${childRect.id}`}
                      className="treemap-cell"
                      data-testid={`treemap-cell-${rect.id}-${childRect.id}`}
                      title={`${TEMPERAMENT_LABELS[rect.id]} ${SIZE_CLASS_SHORT_LABELS[childRect.id]} ${childCount} trees`}
                      style={{
                        left: `${childRect.x}%`,
                        top: `${childRect.y}%`,
                        width: `${childRect.width}%`,
                        height: `${childRect.height}%`,
                        background: childBackground(TEMPERAMENT_COLORS[rect.id], childRect.id),
                      }}
                    >
                      {showChildCopy ? <span>{SIZE_CLASS_SHORT_LABELS[childRect.id]}</span> : null}
                      {showChildValue ? <strong>{childCount}</strong> : null}
                    </div>
                  );
                })}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
