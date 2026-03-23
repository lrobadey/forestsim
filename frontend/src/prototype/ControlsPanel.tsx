import type { ForestControls } from "./types";

interface ControlsPanelProps {
  controls: ForestControls;
  onChange(control: keyof ForestControls, value: number): void;
}

const CONTROL_COPY: Array<{
  key: keyof ForestControls;
  title: string;
  meaning: string;
  effect: string;
}> = [
  {
    key: "heat",
    title: "Heat",
    meaning: "Climate burden and drought pressure.",
    effect: "Raises drought stress, mortality risk, and fire risk.",
  },
  {
    key: "wind",
    title: "Wind",
    meaning: "Structural disturbance pressure.",
    effect: "Raises failure risk for vulnerable canopy trees and opens gaps.",
  },
  {
    key: "growthAdvantage",
    title: "Growth Advantage",
    meaning: "How strongly opportunists convert good conditions into size gain.",
    effect: "Widens the growth gap between gamblers and strugglers.",
  },
  {
    key: "mortalityPressure",
    title: "Mortality Pressure",
    meaning: "Baseline turnover and background stress intensity.",
    effect: "Raises death rates and replacement opportunity even without a big event.",
  },
];

export function ControlsPanel({ controls, onChange }: ControlsPanelProps) {
  return (
    <section className="controls-panel panel" aria-label="Controls panel">
      <div className="panel-copy">
        <p className="eyebrow">Controls</p>
        <h2>Change the forces, then watch the stand answer back.</h2>
      </div>
      <div className="control-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))" }}>
        {CONTROL_COPY.map((control) => (
          <article
            className="control-card"
            key={control.key}
            style={{
              gap: "0.6rem",
              padding: "0.9rem",
              background: "rgba(255, 248, 236, 0.06)",
            }}
          >
            <div className="control-head" style={{ alignItems: "baseline" }}>
              <div style={{ minWidth: 0 }}>
                <strong id={`${control.key}-label`} style={{ display: "block", lineHeight: 1.1 }}>
                  {control.title}
                </strong>
                <p style={{ marginTop: "0.2rem" }}>{control.meaning}</p>
              </div>
              <span aria-hidden="true" style={{ flex: "0 0 auto" }}>
                {controls[control.key].toFixed(2)}
              </span>
            </div>
            <input
              id={`${control.key}-control`}
              type="range"
              min={0}
              max={1}
              step={0.01}
              aria-labelledby={`${control.key}-label`}
              aria-valuetext={controls[control.key].toFixed(2)}
              value={controls[control.key]}
              onChange={(event) => onChange(control.key, Number(event.target.value))}
            />
            <details style={{ marginTop: "0.1rem" }}>
              <summary style={{ cursor: "pointer", color: "var(--muted)", listStyle: "none" }}>
                What it changes
              </summary>
              <small style={{ display: "block", marginTop: "0.5rem", lineHeight: 1.45, color: "var(--muted)" }}>{control.effect}</small>
            </details>
          </article>
        ))}
      </div>
    </section>
  );
}
