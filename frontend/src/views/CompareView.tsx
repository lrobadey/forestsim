import type { BranchDetail, BranchMetrics, BranchSummary } from "../types";

interface CompareViewProps {
  branches: BranchSummary[];
  selectedBranchId: string | null;
  selectedCompareBranchId: string | null;
  selectedBranch: BranchDetail | null;
  selectedCompareBranch: BranchSummary | null;
  metrics: BranchMetrics | null;
  onBranchChange(branchId: string): void;
  onCompareBranchChange(branchId: string): void;
  onCreateBranch(input: { name: string; source_branch_id?: string | null }): Promise<void>;
  onRefresh(): Promise<void>;
}

function SeriesChart({
  title,
  points,
  color,
}: {
  title: string;
  points: Array<{ year: number; value: number }>;
  color: string;
}) {
  const width = 640;
  const height = 200;
  const values = points.map((point) => point.value);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const xStep = points.length > 1 ? width / (points.length - 1) : width;
  const yScale = (value: number) => height - 24 - ((value - min) / Math.max(max - min, 1e-6)) * (height - 48);
  const line = points.map((point, index) => `${index * xStep},${yScale(point.value)}`).join(" ");

  return (
    <div className="series-chart">
      <div className="series-chart-head">
        <strong>{title}</strong>
        <span>{points.length} years</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
        <polyline fill="none" stroke={color} strokeWidth="3" points={line} />
        {points.map((point, index) => (
          <g key={point.year}>
            <circle cx={index * xStep} cy={yScale(point.value)} r="4" fill={color} />
            <text x={index * xStep} y={height - 6} className="chart-axis">
              {point.year}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

export function CompareView({
  branches,
  selectedBranchId,
  selectedCompareBranchId,
  selectedBranch,
  selectedCompareBranch,
  metrics,
  onBranchChange,
  onCompareBranchChange,
  onCreateBranch,
  onRefresh,
}: CompareViewProps) {
  const series = metrics?.series ?? [];
  const compareMetrics = selectedCompareBranch?.metrics;

  return (
    <section className="panel compare-panel" aria-label="Compare dashboard">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Compare</p>
          <h2>Branch series and endpoint snapshots</h2>
        </div>
        <div className="inline-status">
          <button type="button" className="ghost" onClick={() => void onRefresh()}>
            Refresh truth
          </button>
          <button
            type="button"
            onClick={() => void onCreateBranch({ name: `Branch ${branches.length + 1}`, source_branch_id: selectedBranchId })}
          >
            Clone branch
          </button>
        </div>
      </div>

      <div className="compare-toolbar">
        <label>
          <span>Base branch</span>
          <select value={selectedBranchId ?? ""} onChange={(event) => onBranchChange(event.target.value)}>
            {branches.map((branch) => (
              <option key={branch.branch_id} value={branch.branch_id}>
                {branch.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Comparison branch</span>
          <select value={selectedCompareBranchId ?? ""} onChange={(event) => onCompareBranchChange(event.target.value)}>
            <option value="">None</option>
            {branches
              .filter((branch) => branch.branch_id !== selectedBranchId)
              .map((branch) => (
                <option key={branch.branch_id} value={branch.branch_id}>
                  {branch.name}
                </option>
              ))}
          </select>
        </label>
      </div>

      <div className="compare-grid">
        <div className="compare-stack">
          <SeriesChart
            title="Mean gap fraction"
            points={series.map((point) => ({ year: point.year, value: point.mean_gap_fraction }))}
            color="#f8b645"
          />
          <SeriesChart
            title="Moran's I canopy height"
            points={series.map((point) => ({ year: point.year, value: point.morans_i_canopy_height }))}
            color="#3cd0b5"
          />
          <SeriesChart
            title="Species richness"
            points={series.map((point) => ({ year: point.year, value: point.species_richness }))}
            color="#a6b4cc"
          />
        </div>

        <aside className="compare-inspector">
          <div className="snapshot">
            <p className="eyebrow">Base snapshot</p>
            <strong>{selectedBranch?.name ?? "No branch"}</strong>
            <dl>
              <div>
                <dt>Canopy mean</dt>
                <dd>{metrics?.endpoint_snapshots.canopy_height_mean.toFixed(1) ?? "—"}</dd>
              </div>
              <div>
                <dt>Fire severity max</dt>
                <dd>{metrics?.endpoint_snapshots.recent_fire_severity_max.toFixed(2) ?? "—"}</dd>
              </div>
              <div>
                <dt>Events</dt>
                <dd>{metrics?.endpoint_snapshots.event_count ?? 0}</dd>
              </div>
            </dl>
          </div>

          <div className="snapshot">
            <p className="eyebrow">Comparison snapshot</p>
            <strong>{selectedCompareBranch?.name ?? "None"}</strong>
            <dl>
              <div>
                <dt>Canopy mean</dt>
                <dd>{compareMetrics?.endpoint_snapshots.canopy_height_mean.toFixed(1) ?? "—"}</dd>
              </div>
              <div>
                <dt>Fire severity max</dt>
                <dd>{compareMetrics?.endpoint_snapshots.recent_fire_severity_max.toFixed(2) ?? "—"}</dd>
              </div>
              <div>
                <dt>Events</dt>
                <dd>{compareMetrics?.endpoint_snapshots.event_count ?? 0}</dd>
              </div>
            </dl>
          </div>
        </aside>
      </div>
    </section>
  );
}
