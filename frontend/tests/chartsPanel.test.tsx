import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChartsPanel } from "../src/prototype/ChartsPanel";
import { TEMPERAMENT_COLORS } from "../src/prototype/types";
import type { ForestHistoryPoint } from "../src/prototype/types";

const history: ForestHistoryPoint[] = [
  {
    year: 2025,
    livingTreeCount: 120,
    turnoverRate: 0.12,
    disturbanceFrequency: 0.08,
    gapFraction: 0.16,
    shareByTemperament: {
      large_gambler: 0.34,
      small_gambler: 0.22,
      large_struggler: 0.28,
      small_struggler: 0.16,
    },
  },
  {
    year: 2026,
    livingTreeCount: 128,
    turnoverRate: 0.18,
    disturbanceFrequency: 0.11,
    gapFraction: 0.19,
    shareByTemperament: {
      large_gambler: 0.31,
      small_gambler: 0.24,
      large_struggler: 0.27,
      small_struggler: 0.18,
    },
  },
];

describe("ChartsPanel", () => {
  it("switches to the composition trend and shows the temperament legend", async () => {
    const user = userEvent.setup();
    render(<ChartsPanel history={history} />);

    expect(screen.getByRole("img", { name: "Living trees trend" })).toBeInTheDocument();
    expect(screen.queryByText("Large Gambler")).not.toBeInTheDocument();

    const button = screen.getByRole("button", { name: /composition by temperament/i });

    await user.click(button);

    const chart = screen.getByRole("img", { name: "Composition by temperament trend" });
    const strokes = Array.from(chart.querySelectorAll("polyline")).map((line) => line.getAttribute("stroke"));

    expect(strokes).toEqual([
      TEMPERAMENT_COLORS.large_gambler,
      TEMPERAMENT_COLORS.small_gambler,
      TEMPERAMENT_COLORS.large_struggler,
      TEMPERAMENT_COLORS.small_struggler,
    ]);
    expect(screen.getByText("Large Gambler")).toBeInTheDocument();
    expect(screen.getByText("Small Gambler")).toBeInTheDocument();
    expect(screen.getByText("Large Struggler")).toBeInTheDocument();
    expect(screen.getByText("Small Struggler")).toBeInTheDocument();
  });
});
