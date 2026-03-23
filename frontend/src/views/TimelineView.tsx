import { useEffect, useRef } from "react";
import { defaultEventDraft, supportedEventLabels } from "../domain";
import type { BranchDetail, BranchEvent, EventDraft, SupportedEventType } from "../types";

interface TimelineViewProps {
  branch: BranchDetail | null;
  events: BranchEvent[];
  saving: boolean;
  selectedEvent: BranchEvent | null;
  draft: EventDraft;
  onSelectEvent(eventId: string | null): void;
  onDraftChange(draft: EventDraft): void;
  onSave(): Promise<void>;
  onDelete(eventId: string): Promise<void>;
  onReplay(): Promise<void> | void;
}

function updateDraft(draft: EventDraft, patch: Partial<EventDraft>): EventDraft {
  return { ...draft, ...patch };
}

export function TimelineView({
  branch,
  events,
  saving,
  selectedEvent,
  draft,
  onSelectEvent,
  onDraftChange,
  onSave,
  onDelete,
  onReplay,
}: TimelineViewProps) {
  const sortedEvents = [...events].sort((a, b) => a.year - b.year || a.day_of_year - b.day_of_year || a.priority - b.priority);
  const origin = branch?.origin_xy ?? [0, 0];
  const extent = branch?.extent_m ?? [1280, 1280];
  const centerX = origin[0] + extent[0] / 2;
  const centerY = origin[1] + extent[1] / 2;
  const defaultRadius = Math.max(100, Math.min(extent[0], extent[1]) * 0.25);
  const previousBranchId = useRef<string | null>(null);

  useEffect(() => {
    const branchId = branch?.branch_id ?? null;
    if (branchId && branchId !== previousBranchId.current) {
      previousBranchId.current = branchId;
      if (!selectedEvent) {
        onDraftChange(defaultEventDraft("prescribed_burn", branch));
      }
      return;
    }
    if (!branchId) {
      previousBranchId.current = null;
    }
  }, [branch?.branch_id, branch, selectedEvent, onDraftChange]);

  return (
    <section className="panel timeline-panel" aria-label="Timeline view">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Timeline</p>
          <h2>Event CRUD with replay after mutation</h2>
        </div>
        <div className="inline-status">
          <span>{branch?.name ?? "No branch loaded"}</span>
          <button type="button" className="ghost" onClick={() => void onReplay()} disabled={!branch || saving}>
            Replay selected draft year
          </button>
        </div>
      </div>

      <div className="timeline-grid">
        <div className="timeline-rail">
          <div className="timeline-rail-head">
            <button type="button" onClick={() => onSelectEvent(null)} disabled={saving}>
              New event
            </button>
            <span>{sortedEvents.length} events</span>
          </div>
          <ul className="event-list">
            {sortedEvents.map((event) => (
              <li key={event.event_id}>
                <button
                  type="button"
                  className={selectedEvent?.event_id === event.event_id ? "event-row event-row-active" : "event-row"}
                  onClick={() => onSelectEvent(event.event_id)}
                >
                  <div>
                    <strong>{supportedEventLabels[event.event_type as SupportedEventType] ?? event.event_type}</strong>
                    <span>
                      {event.year} / {String(event.day_of_year).padStart(3, "0")} / p{event.priority}
                    </span>
                  </div>
                  <small>{event.notes ?? "No notes"}</small>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <form
          className="timeline-editor"
          onSubmit={async (event) => {
            event.preventDefault();
            await onSave();
          }}
        >
          <div className="editor-grid">
            <label>
              <span>Event type</span>
              <select
                value={draft.event_type}
                onChange={(event) => {
                  const nextType = event.target.value as SupportedEventType;
                  onDraftChange({
                    ...defaultEventDraft(nextType, branch),
                    year: draft.year,
                    day_of_year: draft.day_of_year,
                    priority: draft.priority,
                    notes: draft.notes,
                  });
                }}
              >
                {Object.entries(supportedEventLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Year</span>
              <input type="number" value={draft.year} onChange={(event) => onDraftChange(updateDraft(draft, { year: Number(event.target.value) }))} />
            </label>
            <label>
              <span>Day</span>
              <input
                type="number"
                min={1}
                max={366}
                value={draft.day_of_year}
                onChange={(event) => onDraftChange(updateDraft(draft, { day_of_year: Number(event.target.value) }))}
              />
            </label>
            <label>
              <span>Priority</span>
              <input type="number" value={draft.priority} onChange={(event) => onDraftChange(updateDraft(draft, { priority: Number(event.target.value) }))} />
            </label>
          </div>

          <fieldset className="geometry-fieldset">
            <legend>Geometry</legend>
            <label>
              <span>Mode</span>
              <select
                value={draft.geometry.kind}
                onChange={(event) => {
                  const kind = event.target.value as EventDraft["geometry"]["kind"];
                  if (kind === "circle") {
                    onDraftChange({
                      ...draft,
                      geometry: { kind, center_xy: [centerX, centerY], radius_m: defaultRadius },
                    });
                    return;
                  }
                  if (kind === "polygon") {
                    onDraftChange({
                      ...draft,
                      geometry: {
                        kind,
                        polygon_vertices: [
                          [centerX - defaultRadius * 0.8, centerY - defaultRadius * 0.9],
                          [centerX + defaultRadius * 0.75, centerY - defaultRadius * 0.85],
                          [centerX + defaultRadius, centerY + defaultRadius * 0.65],
                          [centerX - defaultRadius * 0.7, centerY + defaultRadius * 0.85],
                        ],
                      },
                    });
                    return;
                  }
                  onDraftChange({
                    ...draft,
                    geometry: {
                      kind,
                      affected_cells: [
                        [2, 2],
                        [2, 3],
                        [3, 2],
                        [3, 3],
                      ],
                    },
                  });
                }}
              >
                <option value="circle">Circle</option>
                <option value="polygon">Polygon</option>
                <option value="mask">Mask</option>
              </select>
            </label>

            {draft.geometry.kind === "circle" ? (
              <div className="editor-grid three-up">
                <label>
                  <span>Center X</span>
                  <input
                    type="number"
                    value={draft.geometry.center_xy[0]}
                    onChange={(event) =>
                      onDraftChange({
                        ...draft,
                        geometry: {
                          ...draft.geometry,
                          center_xy: [Number(event.target.value), draft.geometry.center_xy[1]],
                        },
                      })
                    }
                  />
                </label>
                <label>
                  <span>Center Y</span>
                  <input
                    type="number"
                    value={draft.geometry.center_xy[1]}
                    onChange={(event) =>
                      onDraftChange({
                        ...draft,
                        geometry: {
                          ...draft.geometry,
                          center_xy: [draft.geometry.center_xy[0], Number(event.target.value)],
                        },
                      })
                    }
                  />
                </label>
                <label>
                  <span>Radius m</span>
                  <input
                    type="number"
                    value={draft.geometry.radius_m}
                    onChange={(event) => onDraftChange({ ...draft, geometry: { ...draft.geometry, radius_m: Number(event.target.value) } })}
                  />
                </label>
              </div>
            ) : null}

            {draft.geometry.kind === "polygon" ? (
              <label>
                <span>Vertices</span>
                <textarea
                  value={draft.geometry.polygon_vertices.map(([x, y]) => `${x},${y}`).join("\n")}
                  onChange={(event) => {
                    const vertices = event.target.value
                      .split("\n")
                      .map((line) => line.trim())
                      .filter(Boolean)
                      .map((line) => line.split(",").map((value) => Number(value.trim())) as [number, number]);
                    onDraftChange({ ...draft, geometry: { kind: "polygon", polygon_vertices: vertices } });
                  }}
                />
              </label>
            ) : null}

            {draft.geometry.kind === "mask" ? (
              <label>
                <span>Cell mask</span>
                <textarea
                  value={draft.geometry.affected_cells.map(([row, col]) => `${row},${col}`).join("\n")}
                  onChange={(event) => {
                    const cells = event.target.value
                      .split("\n")
                      .map((line) => line.trim())
                      .filter(Boolean)
                      .map((line) => line.split(",").map((value) => Number(value.trim())) as [number, number]);
                    onDraftChange({ ...draft, geometry: { kind: "mask", affected_cells: cells } });
                  }}
                />
              </label>
            ) : null}
          </fieldset>

          <label>
            <span>Parameters as JSON</span>
            <textarea
              value={JSON.stringify(draft.params, null, 2)}
              onChange={(event) => {
                try {
                  onDraftChange({ ...draft, params: JSON.parse(event.target.value) as Record<string, unknown> });
                } catch {
                  onDraftChange({ ...draft, params: draft.params });
                }
              }}
            />
          </label>

          <label>
            <span>Notes</span>
            <textarea value={draft.notes} onChange={(event) => onDraftChange(updateDraft(draft, { notes: event.target.value }))} />
          </label>

          <div className="editor-actions">
            <button type="submit" disabled={saving}>
              {selectedEvent ? "Save event" : "Create event"}
            </button>
            <button type="button" className="ghost" onClick={() => onDraftChange(defaultEventDraft("prescribed_burn", branch))} disabled={saving}>
              Reset
            </button>
            {selectedEvent ? (
              <button type="button" className="danger" onClick={() => void onDelete(selectedEvent.event_id)} disabled={saving}>
                Delete
              </button>
            ) : null}
          </div>
        </form>
      </div>
    </section>
  );
}
