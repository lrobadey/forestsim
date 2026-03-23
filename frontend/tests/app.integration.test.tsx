import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { App } from "../src/App";
import { TreemapPanel } from "../src/prototype/TreemapPanel";
import { TEMPERAMENT_COLORS } from "../src/prototype/types";

describe("Forest systems prototype app", () => {
  it("renders the prototype dashboard with controls and required graph nodes", async () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: /Build the smallest simulator/i })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Heat" })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Wind" })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Growth Advantage" })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Mortality Pressure" })).toBeInTheDocument();
    expect(screen.getByTestId("node-droughtStress")).toHaveTextContent("Drought Stress");
    expect(screen.getByTestId("node-fireRisk")).toHaveTextContent("Fire Risk");
    expect(screen.getByTestId("node-regrowthOpportunity")).toHaveTextContent("Regrowth Opportunity");
    expect(screen.getByRole("img", { name: "Temperament share treemap" })).toBeInTheDocument();
  });

  it("updates node values live when a control changes", async () => {
    render(<App />);

    const droughtNode = screen.getByTestId("node-droughtStress");
    expect(droughtNode).toHaveTextContent("0.45");

    fireEvent.change(screen.getByRole("slider", { name: "Heat" }), { target: { value: "1" } });

    expect(screen.getByTestId("node-droughtStress")).toHaveTextContent("1.00");
    expect(screen.getByTestId("node-fireRisk")).not.toHaveTextContent("0.00");
  });

  it("plays, pauses, and resets the simulation", async () => {
    vi.useFakeTimers();
    try {
      render(<App />);
      expect(screen.getByText("2025")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Play" }));
      await act(async () => {
        vi.advanceTimersByTime(900);
      });
      expect(screen.getByText("2026")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Pause" }));
      await act(async () => {
        vi.advanceTimersByTime(1200);
      });
      expect(screen.getByText("2026")).toBeInTheDocument();

      fireEvent.change(screen.getByRole("slider", { name: "Wind" }), { target: { value: "1" } });
      fireEvent.click(screen.getByRole("button", { name: "Reset" }));

      expect(screen.getByText("2025")).toBeInTheDocument();
      expect(screen.getByRole("slider", { name: "Wind" })).toHaveValue("0.5");
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps treemap block totals aligned to the living tree count", () => {
    render(<App />);

    const treemapBlocks = [
      screen.getByTestId("treemap-large_gambler"),
      screen.getByTestId("treemap-small_gambler"),
      screen.getByTestId("treemap-large_struggler"),
      screen.getByTestId("treemap-small_struggler"),
    ];

    const total = treemapBlocks.reduce((sum, block) => sum + Number(block.getAttribute("data-count")), 0);
    expect(within(screen.getByLabelText("Composition treemap")).getByText(/living trees across four temperaments/i)).toHaveTextContent(`${total} living trees`);
  });

  it("keeps temperament colors tied to temperament identity even when shares reorder", () => {
    render(
      <TreemapPanel
        livingTreeCount={100}
        shareByTemperament={{
          large_gambler: 0.12,
          small_gambler: 0.41,
          large_struggler: 0.33,
          small_struggler: 0.14,
        }}
      />,
    );

    expect(screen.getByTestId("treemap-large_gambler")).toHaveStyle(`background: linear-gradient(160deg, ${TEMPERAMENT_COLORS.large_gambler}, rgba(5, 9, 8, 0.28))`);
    expect(screen.getByTestId("treemap-small_gambler")).toHaveStyle(`background: linear-gradient(160deg, ${TEMPERAMENT_COLORS.small_gambler}, rgba(5, 9, 8, 0.28))`);
    expect(screen.getByTestId("treemap-large_struggler")).toHaveStyle(`background: linear-gradient(160deg, ${TEMPERAMENT_COLORS.large_struggler}, rgba(5, 9, 8, 0.28))`);
    expect(screen.getByTestId("treemap-small_struggler")).toHaveStyle(`background: linear-gradient(160deg, ${TEMPERAMENT_COLORS.small_struggler}, rgba(5, 9, 8, 0.28))`);
  });
});
