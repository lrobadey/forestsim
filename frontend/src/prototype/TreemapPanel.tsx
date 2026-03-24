import { TEMPERAMENT_COLORS, TEMPERAMENT_LABELS, TEMPERAMENT_SHORT_LABELS, TEMPERAMENTS } from "./types";
import type { ForestTree, SizeClass, Temperament } from "./types";

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

const SIZE_CLASS_META: Record<
  SizeClass,
  {
    short: string;
    label: string;
    hint: string;
    level: number;
  }
> = {
  large_canopy: {
    short: "LC",
    label: "Large Canopy",
    hint: "Upper canopy hold",
    level: 4,
  },
  canopy_candidate: {
    short: "CC",
    label: "Canopy Candidate",
    hint: "Ready to break upward",
    level: 3,
  },
  juvenile: {
    short: "JV",
    label: "Juvenile",
    hint: "Understory growth",
    level: 2,
  },
  seedling: {
    short: "SD",
    label: "Seedling",
    hint: "Newest recruits",
    level: 1,
  },
};

const SIZE_CLASS_TAILS: Record<SizeClass, string> = {
  large_canopy: "rgba(9, 12, 16, 0.16)",
  canopy_candidate: "rgba(54, 33, 12, 0.34)",
  juvenile: "rgba(7, 10, 12, 0.48)",
  seedling: "rgba(209, 229, 224, 0.28)",
};

type Orientation = "vertical" | "horizontal";

const CORNER_LAYOUT: readonly [Temperament, Temperament, Temperament, Temperament] = [
  "large_gambler",
  "small_gambler",
  "large_struggler",
  "small_struggler",
];

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

function percentage(value: number, total: number): number {
  return total > 0 ? Math.round((value / total) * 100) : 0;
}

function childBackground(color: string, sizeClass: SizeClass): string {
  return `linear-gradient(165deg, ${color}, ${SIZE_CLASS_TAILS[sizeClass]})`;
}

function buildCornerLayout(counts: Record<Temperament, number>): Rect<Temperament>[] {
  const [topLeft, topRight, bottomLeft, bottomRight] = CORNER_LAYOUT;
  const total = Math.max(
    counts[topLeft] + counts[topRight] + counts[bottomLeft] + counts[bottomRight],
    0.001,
  );
  const leftTotal = counts[topLeft] + counts[bottomLeft];
  const rightTotal = counts[topRight] + counts[bottomRight];
  const leftWidth = Math.max(18, Math.min(82, (leftTotal / total) * 100));
  const rightWidth = 100 - leftWidth;
  const leftTopHeight = leftTotal > 0 ? (counts[topLeft] / leftTotal) * 100 : 50;
  const rightTopHeight = rightTotal > 0 ? (counts[topRight] / rightTotal) * 100 : 50;

  return [
    { id: topLeft, x: 0, y: 0, width: leftWidth, height: leftTopHeight, value: counts[topLeft] },
    { id: topRight, x: leftWidth, y: 0, width: rightWidth, height: rightTopHeight, value: counts[topRight] },
    { id: bottomLeft, x: 0, y: leftTopHeight, width: leftWidth, height: 100 - leftTopHeight, value: counts[bottomLeft] },
    { id: bottomRight, x: leftWidth, y: rightTopHeight, width: rightWidth, height: 100 - rightTopHeight, value: counts[bottomRight] },
  ];
}

function StageMarker({ level }: { level: number }) {
  return (
    <span className="treemap-stage-marker" aria-hidden="true">
      {Array.from({ length: 4 }, (_, index) => (
        <i key={index} className={index < level ? "is-active" : undefined} />
      ))}
    </span>
  );
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
  const temperamentRects = buildCornerLayout(temperamentCounts);
  const rectMap = new Map(temperamentRects.map((rect) => [rect.id, rect]));
  const topLeftRect = rectMap.get("large_gambler");
  const topRightRect = rectMap.get("small_gambler");

  const [dominant, runnerUp] = [...TEMPERAMENTS].sort((left, right) => temperamentCounts[right] - temperamentCounts[left]);

  return (
    <section
      className="treemap-panel panel"
      aria-label="Composition treemap"
      style={{
        display: "grid",
        gap: 0,
      }}
    >
      <div className="panel-copy" style={{ marginBottom: "0.55rem" }}>
        <p className="eyebrow">Composition</p>
        <h2>Who owns the forest right now?</h2>
        <p>{livingTreeCount} living trees across four temperaments.</p>
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
      <div className="treemap-key" aria-label="Tree size legend">
        {SIZE_CLASS_ORDER.map((sizeClass) => (
          <article key={sizeClass} className="treemap-key-item">
            <div className="treemap-key-flag">
              <StageMarker level={SIZE_CLASS_META[sizeClass].level} />
              <strong>{SIZE_CLASS_META[sizeClass].short}</strong>
            </div>
            <div className="treemap-key-copy">
              <span>{SIZE_CLASS_META[sizeClass].label}</span>
              <small>{SIZE_CLASS_META[sizeClass].hint}</small>
            </div>
          </article>
        ))}
      </div>
      <div
        className="treemap-stage"
        role="img"
        aria-label="Temperament share treemap"
        style={{
          position: "relative",
        }}
      >
        {topLeftRect && topRightRect ? (
          <>
            <div
              aria-hidden="true"
              className="treemap-seam treemap-seam-vertical"
              style={{
                left: `${topLeftRect.width}%`,
                top: 0,
                height: "100%",
              }}
            />
            <div
              aria-hidden="true"
              className="treemap-seam treemap-seam-horizontal"
              style={{
                left: 0,
                top: `${topLeftRect.height}%`,
                width: `${topLeftRect.width}%`,
              }}
            />
            <div
              aria-hidden="true"
              className="treemap-seam treemap-seam-horizontal"
              style={{
                left: `${topRightRect.x}%`,
                top: `${topRightRect.height}%`,
                width: `${topRightRect.width}%`,
              }}
            />
          </>
        ) : null}
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
                  const sizeMeta = SIZE_CLASS_META[childRect.id];
                  const area = childRect.width * childRect.height;
                  const showLabel = area > 150;
                  const showLongLabel = area > 300;
                  const showHint = area > 520;
                  const showChildValue = area > 250;

                  return (
                    <div
                      key={`${rect.id}-${childRect.id}`}
                      className="treemap-cell"
                      data-testid={`treemap-cell-${rect.id}-${childRect.id}`}
                      aria-label={`${TEMPERAMENT_LABELS[rect.id]} ${sizeMeta.label} ${childCount} trees`}
                      title={`${TEMPERAMENT_LABELS[rect.id]} ${sizeMeta.label} ${childCount} trees`}
                      style={{
                        left: `${childRect.x}%`,
                        top: `${childRect.y}%`,
                        width: `${childRect.width}%`,
                        height: `${childRect.height}%`,
                        background: childBackground(TEMPERAMENT_COLORS[rect.id], childRect.id),
                      }}
                    >
                      <div className="treemap-cell-head">
                        <div className="treemap-cell-badge">
                          <StageMarker level={sizeMeta.level} />
                          {showLabel ? <span>{showLongLabel ? sizeMeta.label : sizeMeta.short}</span> : null}
                        </div>
                        {showChildValue ? <strong>{childCount}</strong> : null}
                      </div>
                      {showHint ? <small>{sizeMeta.hint}</small> : null}
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
