import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { App } from "../src/App";
import { TreemapPanel } from "../src/prototype/TreemapPanel";
import { TEMPERAMENT_COLORS, TEMPERAMENTS } from "../src/prototype/types";
import type { ForestTree, SizeClass, Temperament } from "../src/prototype/types";

const SIZE_CLASS_ORDER: SizeClass[] = ["large_canopy", "canopy_candidate", "juvenile", "seedling"];

const SIZE_CLASS_SIZES: Record<SizeClass, number> = {
  large_canopy: 0.82,
  canopy_candidate: 0.58,
  juvenile: 0.32,
  seedling: 0.14,
};

function buildTreemapTrees(
  counts: Record<Temperament, Partial<Record<SizeClass, number>>>,
): ForestTree[] {
  let nextId = 1;
  const trees: ForestTree[] = [];

  for (const temperament of TEMPERAMENTS) {
    for (const sizeClass of SIZE_CLASS_ORDER) {
      const total = counts[temperament]?.[sizeClass] ?? 0;
      for (let index = 0; index < total; index += 1) {
        trees.push({
          id: nextId,
          temperament,
          age: 20,
          alive: true,
          x: 0.1,
          y: 0.1,
          size: SIZE_CLASS_SIZES[sizeClass],
          sizeClass,
          canopyRole: sizeClass === "large_canopy" ? "canopy" : sizeClass === "canopy_candidate" ? "subcanopy" : "suppressed",
          vigor: 0.7,
          suppressionLevel: 0.1,
          reproductiveState: "active",
          disturbanceDamage: 0,
          suppressionYears: 0,
        });
        nextId += 1;
      }
    }
  }

  return trees;
}

describe("Forest systems prototype app", () => {
  it("renders the prototype dashboard with controls and required graph nodes", async () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: /See succession through one stand/i })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Heat" })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Wind" })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Growth Advantage" })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Mortality Pressure" })).toBeInTheDocument();
    expect(screen.getByTestId("node-droughtStress")).toHaveTextContent("Drought stress");
    expect(screen.getByTestId("node-fireRisk")).toHaveTextContent("Fire risk");
    expect(screen.getByTestId("node-regrowthOpportunity")).toHaveTextContent("Regrowth opportunity");
    expect(screen.getByRole("img", { name: "Temperament share treemap" })).toBeInTheDocument();
    expect(screen.queryByTestId("graph-node-droughtStress")).not.toBeInTheDocument();
  });

  it("opens and closes the full causal graph modal", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /open causal graph/i }));

    const dialog = screen.getByRole("dialog", { name: /forest causal graph/i });
    expect(within(dialog).getByTestId("graph-node-droughtStress")).toBeInTheDocument();
    expect(within(dialog).getByTestId("graph-node-fireRisk")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: /forest causal graph/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /open causal graph/i }));
    expect(screen.getByRole("dialog", { name: /forest causal graph/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /close graph/i }));
    expect(screen.queryByRole("dialog", { name: /forest causal graph/i })).not.toBeInTheDocument();
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
    expect(within(screen.getByLabelText("Composition treemap")).getByText(/living trees\./i)).toHaveTextContent(`${total} living trees`);
  });

  it("keeps temperament colors tied to temperament identity even when shares reorder", () => {
    render(
      <TreemapPanel
        trees={buildTreemapTrees({
          large_gambler: { large_canopy: 4, juvenile: 8 },
          small_gambler: { large_canopy: 16, canopy_candidate: 12, juvenile: 9, seedling: 4 },
          large_struggler: { large_canopy: 11, canopy_candidate: 12, juvenile: 7, seedling: 3 },
          small_struggler: { large_canopy: 4, canopy_candidate: 5, juvenile: 3, seedling: 2 },
        })}
      />,
    );

    expect(screen.getByTestId("treemap-large_gambler")).toHaveStyle(`background: linear-gradient(165deg, ${TEMPERAMENT_COLORS.large_gambler}, rgba(5, 9, 8, 0.42))`);
    expect(screen.getByTestId("treemap-small_gambler")).toHaveStyle(`background: linear-gradient(165deg, ${TEMPERAMENT_COLORS.small_gambler}, rgba(5, 9, 8, 0.42))`);
    expect(screen.getByTestId("treemap-large_struggler")).toHaveStyle(`background: linear-gradient(165deg, ${TEMPERAMENT_COLORS.large_struggler}, rgba(5, 9, 8, 0.42))`);
    expect(screen.getByTestId("treemap-small_struggler")).toHaveStyle(`background: linear-gradient(165deg, ${TEMPERAMENT_COLORS.small_struggler}, rgba(5, 9, 8, 0.42))`);
  });

  it("keeps each temperament anchored to a stable side of the treemap", () => {
    const { rerender } = render(
      <TreemapPanel
        trees={buildTreemapTrees({
          large_gambler: { large_canopy: 24, canopy_candidate: 14, juvenile: 6, seedling: 2 },
          small_gambler: { large_canopy: 5, juvenile: 3 },
          large_struggler: { large_canopy: 16, canopy_candidate: 10, juvenile: 3, seedling: 1 },
          small_struggler: { large_canopy: 8, canopy_candidate: 5, juvenile: 2, seedling: 1 },
        })}
      />,
    );

    expect(screen.getByTestId("treemap-large_gambler")).toHaveStyle({ left: "0%", top: "0%" });
    expect(screen.getByTestId("treemap-cell-large_gambler-large_canopy")).toBeInTheDocument();

    rerender(
      <TreemapPanel
        trees={buildTreemapTrees({
          large_gambler: { large_canopy: 20, canopy_candidate: 12, juvenile: 6, seedling: 2 },
          small_gambler: { large_canopy: 18, canopy_candidate: 10, juvenile: 8, seedling: 5 },
          large_struggler: { large_canopy: 17, canopy_candidate: 10, juvenile: 4, seedling: 1 },
          small_struggler: { large_canopy: 11, canopy_candidate: 7, juvenile: 3, seedling: 1 },
        })}
      />,
    );

    expect(screen.getByTestId("treemap-large_gambler")).toHaveStyle({ left: "0%", top: "0%" });
    expect(screen.getByTestId("treemap-cell-small_gambler-large_canopy")).toBeInTheDocument();
  });

  it("renders nested size-class tiles inside each temperament block", () => {
    render(
      <TreemapPanel
        trees={buildTreemapTrees({
          large_gambler: { large_canopy: 9, canopy_candidate: 5, juvenile: 3, seedling: 1 },
          small_gambler: { large_canopy: 7, canopy_candidate: 6, juvenile: 4, seedling: 2 },
          large_struggler: { large_canopy: 8, canopy_candidate: 5, juvenile: 4, seedling: 3 },
          small_struggler: { large_canopy: 6, canopy_candidate: 4, juvenile: 3, seedling: 2 },
        })}
      />,
    );

    expect(screen.getByTestId("treemap-cell-large_gambler-large_canopy")).toBeInTheDocument();
    expect(screen.getByTestId("treemap-cell-small_gambler-canopy_candidate")).toBeInTheDocument();
    expect(screen.getByTestId("treemap-cell-large_struggler-juvenile")).toBeInTheDocument();
    expect(screen.getByTestId("treemap-cell-small_struggler-seedling")).toBeInTheDocument();
  });
});
