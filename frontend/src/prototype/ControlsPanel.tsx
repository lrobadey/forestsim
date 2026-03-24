import type { ForestControls } from "./types";

interface ControlsPanelProps {
  controls: ForestControls;
  onChange(control: keyof ForestControls, value: number): void;
}

const CONTROL_COPY: Array<{
  key: keyof ForestControls;
  title: string;
  summary: string;
}> = [
  {
    key: "heat",
    title: "Heat",
    summary: "Raises drought stress and fire pressure.",
  },
  {
    key: "wind",
    title: "Wind",
    summary: "Raises canopy failure and structural disturbance.",
  },
  {
    key: "growthAdvantage",
    title: "Growth Advantage",
    summary: "Helps opportunists turn good years into size gain.",
  },
  {
    key: "mortalityPressure",
    title: "Mortality Pressure",
    summary: "Raises background death and replacement.",
  },
];

export function ControlsPanel({ controls, onChange }: ControlsPanelProps) {
  return (
    <section className="controls-panel panel" aria-label="Controls panel">
      <div className="panel-copy">
        <p className="eyebrow">Controls</p>
        <h2>Set the four forces.</h2>
        <p>Move a slider, then read the response in composition, signals, and history.</p>
      </div>
      <div className="control-grid">
        {CONTROL_COPY.map((control) => (
          <article className="control-card control-card-compact" key={control.key}>
            <div className="control-head control-head-compact">
              <div className="control-copy-compact">
                <strong id={`${control.key}-label`}>
                  {control.title}
                </strong>
                <p>{control.summary}</p>
              </div>
              <span aria-hidden="true" className="control-value-pill">
                {controls[control.key].toFixed(2)}
              </span>
            </div>
            <input
              className="control-slider"
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
          </article>
        ))}
      </div>
    </section>
  );
}
