import { useEffect, useState } from "react";
import { MAX_LIVING_TREES } from "./seed";
import { TEMPERAMENT_SHORT_LABELS } from "./types";
import type { ForestControls, ForestDerivedState, TemperamentRecord } from "./types";

interface NodeGraphPanelProps {
  controls: ForestControls;
  derived: ForestDerivedState;
}

type NodeId =
  | "heat"
  | "wind"
  | "growthAdvantage"
  | "mortalityPressure"
  | "droughtStress"
  | "fireRisk"
  | "growthRate"
  | "mortalityRisk"
  | "regrowthOpportunity"
  | "livingTreeCount"
  | "shareByTemperament"
  | "turnoverRate"
  | "disturbanceFrequency";

type SignalCard = {
  id: "droughtStress" | "fireRisk" | "regrowthOpportunity";
  label: string;
  value: string;
  note: string;
};

function meanPair(record: TemperamentRecord, matcher: (key: keyof TemperamentRecord) => boolean): number {
  const values = Object.entries(record)
    .filter(([key]) => matcher(key as keyof TemperamentRecord))
    .map(([, value]) => value);
  return values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1);
}

function formatShare(record: TemperamentRecord): string {
  return Object.entries(record)
    .sort((left, right) => right[1] - left[1])
    .slice(0, 2)
    .map(([key, value]) => `${TEMPERAMENT_SHORT_LABELS[key as keyof TemperamentRecord]} ${Math.round(value * 100)}%`)
    .join(" ");
}

function GraphSvg({
  controls,
  derived,
  nodeTestIdPrefix = "graph-node",
}: {
  controls: ForestControls;
  derived: ForestDerivedState;
  nodeTestIdPrefix?: string;
}) {
  const nodes: Array<{
    id: NodeId;
    title: string;
    value: number;
    display: string;
    x: number;
    y: number;
  }> = [
    { id: "heat", title: "Heat", value: controls.heat, display: controls.heat.toFixed(2), x: 28, y: 28 },
    { id: "wind", title: "Wind", value: controls.wind, display: controls.wind.toFixed(2), x: 28, y: 104 },
    { id: "growthAdvantage", title: "Growth Advantage", value: controls.growthAdvantage, display: controls.growthAdvantage.toFixed(2), x: 28, y: 180 },
    { id: "mortalityPressure", title: "Mortality Pressure", value: controls.mortalityPressure, display: controls.mortalityPressure.toFixed(2), x: 28, y: 256 },
    { id: "droughtStress", title: "Drought Stress", value: derived.droughtStress, display: derived.droughtStress.toFixed(2), x: 252, y: 28 },
    { id: "fireRisk", title: "Fire Risk", value: derived.fireRisk, display: derived.fireRisk.toFixed(2), x: 252, y: 104 },
    {
      id: "growthRate",
      title: "Growth Rate by Temperament",
      value: meanPair(derived.growthRateByTemperament, () => true) * 10,
      display: `G ${meanPair(derived.growthRateByTemperament, (key) => String(key).includes("gambler")).toFixed(2)} / S ${meanPair(derived.growthRateByTemperament, (key) => String(key).includes("struggler")).toFixed(2)}`,
      x: 252,
      y: 180,
    },
    {
      id: "mortalityRisk",
      title: "Mortality Risk by Temperament",
      value: meanPair(derived.mortalityRiskByTemperament, () => true),
      display: `G ${meanPair(derived.mortalityRiskByTemperament, (key) => String(key).includes("gambler")).toFixed(2)} / S ${meanPair(derived.mortalityRiskByTemperament, (key) => String(key).includes("struggler")).toFixed(2)}`,
      x: 252,
      y: 256,
    },
    {
      id: "regrowthOpportunity",
      title: "Regrowth Opportunity",
      value: derived.regrowthOpportunity,
      display: derived.regrowthOpportunity.toFixed(2),
      x: 252,
      y: 332,
    },
    {
      id: "livingTreeCount",
      title: "Living Tree Count",
      value: derived.livingTreeCount / MAX_LIVING_TREES,
      display: String(derived.livingTreeCount),
      x: 476,
      y: 28,
    },
    {
      id: "shareByTemperament",
      title: "Share by Temperament",
      value: Math.max(...Object.values(derived.shareByTemperament)),
      display: formatShare(derived.shareByTemperament),
      x: 476,
      y: 104,
    },
    {
      id: "turnoverRate",
      title: "Turnover Rate",
      value: derived.turnoverRate,
      display: derived.turnoverRate.toFixed(2),
      x: 476,
      y: 180,
    },
    {
      id: "disturbanceFrequency",
      title: "Disturbance Frequency",
      value: derived.disturbanceFrequency,
      display: derived.disturbanceFrequency.toFixed(2),
      x: 476,
      y: 256,
    },
  ];

  const edges: Array<[NodeId, NodeId]> = [
    ["heat", "droughtStress"],
    ["heat", "fireRisk"],
    ["wind", "disturbanceFrequency"],
    ["growthAdvantage", "growthRate"],
    ["mortalityPressure", "mortalityRisk"],
    ["mortalityPressure", "turnoverRate"],
    ["droughtStress", "growthRate"],
    ["droughtStress", "mortalityRisk"],
    ["fireRisk", "disturbanceFrequency"],
    ["growthRate", "livingTreeCount"],
    ["mortalityRisk", "livingTreeCount"],
    ["disturbanceFrequency", "regrowthOpportunity"],
    ["turnoverRate", "regrowthOpportunity"],
    ["regrowthOpportunity", "shareByTemperament"],
  ];

  const nodeMap = new Map(nodes.map((node) => [node.id, node]));

  return (
    <svg className="node-graph" viewBox="0 0 720 420" role="img" aria-label="Forest systems graph" preserveAspectRatio="xMidYMid meet">
      <defs>
        <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(242, 214, 187, 0.6)" />
        </marker>
      </defs>
      {edges.map(([from, to]) => {
        const start = nodeMap.get(from);
        const end = nodeMap.get(to);
        if (!start || !end) {
          return null;
        }
        return (
          <line
            key={`${from}-${to}`}
            x1={start.x + 136}
            y1={start.y + 32}
            x2={end.x}
            y2={end.y + 32}
            stroke="rgba(242, 214, 187, 0.34)"
            strokeWidth="2.5"
            markerEnd="url(#arrow)"
          />
        );
      })}
      {nodes.map((node) => {
        const intensity = 0.25 + node.value * 0.65;
        return (
          <g key={node.id} className="graph-node" data-testid={`${nodeTestIdPrefix}-${node.id}`} transform={`translate(${node.x}, ${node.y})`}>
            <rect
              width="136"
              height="64"
              rx="16"
              fill={`rgba(242, 163, 58, ${Math.min(0.16 + intensity * 0.18, 0.36)})`}
              stroke={`rgba(242, 214, 187, ${Math.min(0.3 + intensity * 0.4, 0.9)})`}
            />
            <text x="12" y="20" className="graph-node-title">
              {node.title}
            </text>
            <text x="12" y="44" className="graph-node-value">
              {node.display}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function NodeGraphPanel({ controls, derived }: NodeGraphPanelProps) {
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!expanded) {
      return undefined;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setExpanded(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [expanded]);

  const highlights: SignalCard[] = [
    {
      id: "droughtStress",
      label: "Drought stress",
      value: derived.droughtStress.toFixed(2),
      note: derived.droughtStress > 0.7 ? "High moisture pressure" : "Tracking moisture pressure",
    },
    {
      id: "fireRisk",
      label: "Fire risk",
      value: derived.fireRisk.toFixed(2),
      note: derived.fireRisk > 0.7 ? "Elevated disturbance risk" : "Low to moderate disturbance risk",
    },
    {
      id: "regrowthOpportunity",
      label: "Regrowth opportunity",
      value: derived.regrowthOpportunity.toFixed(2),
      note: derived.regrowthOpportunity > 0.7 ? "Strong replacement window" : "Replacement window is tighter",
    },
  ];

  return (
    <section className="node-panel panel" aria-label="Causal node graph">
      <div className="panel-copy">
        <p className="eyebrow">Signals</p>
        <h2>What is acting on the forest right now?</h2>
      </div>
      <div style={{ display: "grid", gap: "0.6rem" }} aria-label="Causal graph highlights">
        {highlights.map((highlight) => (
          <article
            key={highlight.id}
            data-testid={`node-${highlight.id}`}
            style={{
              display: "grid",
              gap: "0.28rem",
              padding: "0.75rem 0.8rem",
              borderRadius: "16px",
              background: "rgba(255, 248, 236, 0.08)",
              border: "1px solid rgba(255, 241, 223, 0.14)",
            }}
          >
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "0.6rem" }}>
              <span className="eyebrow" style={{ marginBottom: 0 }}>
                {highlight.label}
              </span>
              <strong style={{ fontSize: "1rem", letterSpacing: "-0.02em" }}>{highlight.value}</strong>
            </div>
            <small style={{ color: "var(--muted)", lineHeight: 1.35 }}>{highlight.note}</small>
          </article>
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "0.6rem" }}>
        <button type="button" aria-expanded={expanded} aria-controls="forest-causal-graph-modal" onClick={() => setExpanded(true)}>
          Open causal graph
        </button>
      </div>
      {expanded ? (
        <div
          role="presentation"
          onClick={() => setExpanded(false)}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 60,
            display: "grid",
            placeItems: "center",
            padding: "1rem",
            background: "rgba(11, 9, 7, 0.62)",
            backdropFilter: "blur(10px)",
          }}
        >
          <div
            id="forest-causal-graph-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Forest causal graph"
            onClick={(event) => event.stopPropagation()}
            style={{
              width: "min(80vw, 1120px)",
              height: "min(80vh, 760px)",
              display: "grid",
              gridTemplateRows: "auto minmax(0, 1fr)",
              gap: "0.75rem",
              padding: "1rem",
              borderRadius: "24px",
              background: "linear-gradient(180deg, rgba(32, 28, 22, 0.98), rgba(21, 18, 15, 0.96))",
              border: "1px solid rgba(255, 241, 223, 0.18)",
              boxShadow: "0 28px 80px rgba(0, 0, 0, 0.42)",
              minHeight: 0,
              minWidth: 0,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
              <div>
                <p className="eyebrow" style={{ marginBottom: "0.25rem" }}>
                  Causal graph
                </p>
                <h2 style={{ margin: 0, fontSize: "1.35rem" }}>Full signal map</h2>
              </div>
              <button type="button" onClick={() => setExpanded(false)}>
                Close graph
              </button>
            </div>
            <div style={{ minHeight: 0, minWidth: 0 }}>
              <GraphSvg controls={controls} derived={derived} />
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
