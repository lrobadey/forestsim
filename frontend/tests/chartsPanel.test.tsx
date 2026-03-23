import { render, screen } from "@testing-library/react";
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
  it("shows all temperament series colors in the selector preview", () => {
    const { container } = render(<ChartsPanel history={history} />);

    const button = screen.getByRole("button", { name: /share by temperament/i });
    const preview = button.querySelector("svg");

    expect(preview).not.toBeNull();

    const strokes = Array.from(preview!.querySelectorAll("polyline")).map((line) => line.getAttribute("stroke"));

    expect(strokes).toEqual([
      TEMPERAMENT_COLORS.large_gambler,
      TEMPERAMENT_COLORS.small_gambler,
      TEMPERAMENT_COLORS.large_struggler,
      TEMPERAMENT_COLORS.small_struggler,
    ]);
    expect(container.querySelectorAll("svg polyline").length).toBeGreaterThanOrEqual(5);
  });
});
