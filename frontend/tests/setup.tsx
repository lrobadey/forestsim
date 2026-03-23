import "@testing-library/jest-dom/vitest";
import type { ReactNode } from "react";
import { vi } from "vitest";

vi.stubEnv("VITE_WATTFOREST_API_MODE", "mock");

class MockLayer {
  props: unknown;
  constructor(props: unknown) {
    this.props = props;
  }
}

const leafletMap = {
  getCenter: () => ({ lat: 640, lng: 640 }),
  getZoom: () => 2,
  getSize: () => ({ x: 960, y: 720 }),
};

vi.mock("leaflet", () => ({
  default: {
    CRS: {
      Simple: {},
    },
  },
  CRS: {
    Simple: {},
  },
}));

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: ReactNode }) => <div data-testid="leaflet-map">{children}</div>,
  useMap: () => leafletMap,
  useMapEvents: () => ({}),
}));

vi.mock("@deck.gl/react", () => ({
  default: ({ children }: { children: ReactNode }) => <div data-testid="deckgl">{children}</div>,
}));

vi.mock("@deck.gl/core", () => ({
  OrthographicView: class {
    props: unknown;
    constructor(props: unknown) {
      this.props = props;
    }
  },
}));

vi.mock("@deck.gl/layers", () => ({
  BitmapLayer: MockLayer,
  PolygonLayer: MockLayer,
  ScatterplotLayer: MockLayer,
}));

Object.defineProperty(globalThis, "ResizeObserver", {
  writable: true,
  value: class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
});

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    media: query,
    matches: false,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {
      return false;
    },
  }),
});
