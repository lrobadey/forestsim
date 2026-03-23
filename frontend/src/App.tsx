import { ChartsPanel } from "./prototype/ChartsPanel";
import { ControlsPanel } from "./prototype/ControlsPanel";
import { TreemapPanel } from "./prototype/TreemapPanel";
import { NodeGraphPanel } from "./prototype/NodeGraphPanel";
import { useForestPrototype } from "./prototype/useForestPrototype";
import { SPEED_OPTIONS, TEMPERAMENT_LABELS, TEMPERAMENTS } from "./prototype/types";

function dominantTemperamentLabel(shares: Record<(typeof TEMPERAMENTS)[number], number>): string {
  const [winner] = [...TEMPERAMENTS].sort((left, right) => shares[right] - shares[left]);
  return TEMPERAMENT_LABELS[winner];
}

export function App() {
  const model = useForestPrototype();
  const dominantTemperament = dominantTemperamentLabel(model.state.derived.shareByTemperament);

  return (
    <div className="prototype-shell">
      <header className="top-bar">
        <div className="top-bar-copy">
          {/* TODO: This app currently renders the abstract stand prototype,
          not the Python landscape engine. Keep the wording aligned with that
          scope until backend-driven runs are calibrated and promoted to the
          primary experience. */}
          <p className="eyebrow">Forest Systems Prototype</p>
          <h1>Build the smallest simulator that makes succession legible.</h1>
        </div>
        <div className="top-bar-rail">
          <div className="top-bar-metrics">
            <div className="metric-pill">
              <span>Year</span>
              <strong>{model.state.year}</strong>
            </div>
            <div className="metric-pill">
              <span>Dominant role</span>
              <strong>{dominantTemperament}</strong>
            </div>
            <div className="status-pill" aria-live="polite">
              {model.statusText}
            </div>
          </div>
          <div className="top-bar-actions" aria-label="Playback controls">
            <label className="speed-select">
              <span>Simulation speed</span>
              <select aria-label="Simulation speed" value={model.state.speed} onChange={(event) => model.setSpeed(event.target.value as (typeof SPEED_OPTIONS)[number])}>
                {SPEED_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <div className="playback-group">
              <button type="button" onClick={model.play}>
                Play
              </button>
              <button type="button" onClick={model.pause}>
                Pause
              </button>
              <button type="button" onClick={model.reset}>
                Reset
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="dashboard-body">
        <ControlsPanel controls={model.state.controls} onChange={model.setControl} />
        <TreemapPanel livingTreeCount={model.state.derived.livingTreeCount} shareByTemperament={model.state.derived.shareByTemperament} />
        <div className="dashboard-rail">
          <NodeGraphPanel controls={model.state.controls} derived={model.state.derived} />
          <ChartsPanel history={model.state.history} />
        </div>
      </main>
    </div>
  );
}
