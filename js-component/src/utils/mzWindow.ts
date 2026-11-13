/**
 * A shaded x window on a spectrum, kept in the shared state under the
 * component's `window_identifier` (for example the m/z window of an XIC).
 *
 * The stored value is a centre, widened by the tolerance on each side, a
 * `[low, high]` pair, or nothing for no band.
 */

import type Plotly from "plotly.js-dist-min";
import { ICONS, type PlotTool } from "./plotTools";

/** "Da" and "m/z" are absolute widths on the x axis, "ppm" is relative. */
export type ToleranceUnit = "Da" | "ppm" | "m/z";

/** The stored value as `[low, high]`, or undefined for no band. */
export function windowRange(
  value: unknown,
  tolerance: number,
  unit: ToleranceUnit,
): [number, number] | undefined {
  if (typeof value === "number" && Number.isFinite(value)) {
    const half =
      unit === "ppm" ? (Math.abs(value) * tolerance) / 1e6 : tolerance;
    return half > 0 ? [value - half, value + half] : undefined;
  }
  if (Array.isArray(value) && value.length === 2) {
    const [a, b] = value.map(Number);
    if (!Number.isFinite(a) || !Number.isFinite(b) || a === b) return undefined;
    return a < b ? [a, b] : [b, a];
  }
  return undefined;
}

/** How the window reads in its label: `523.2711 ± 10 ppm`, `± 0.5 m/z` or `523.20–523.40`. */
export function windowText(
  value: unknown,
  range: [number, number],
  tolerance: number,
  unit: ToleranceUnit,
): string {
  if (typeof value === "number") {
    return `${value.toFixed(4)} ± ${Number(tolerance.toPrecision(4))} ${unit}`;
  }
  return `${range[0].toFixed(4)}–${range[1].toFixed(4)}`;
}

export interface WindowOverlay {
  shapes: Partial<Plotly.Shape>[];
  annotations: Partial<Plotly.Annotations>[];
}

/** Label anchor for a position (0 = left edge, 1 = right edge of the view). */
function edgeAnchor(position: number): "left" | "center" | "right" {
  if (position > 0.85) return "right";
  if (position < 0.15) return "left";
  return "center";
}

/**
 * The band over the plot's height (at least `minWidthPx` wide, so a 10 ppm
 * window stays visible at full range) and its label at the top.
 */
export function windowOverlay(
  range: [number, number] | undefined,
  text: string,
  xRange: number[],
  widthPx: number,
  color: string,
  minWidthPx = 3,
): WindowOverlay {
  if (!range || !(xRange[1] > xRange[0]) || widthPx <= 0)
    return { shapes: [], annotations: [] };
  if (range[1] < xRange[0] || range[0] > xRange[1])
    return { shapes: [], annotations: [] };
  const centre = (range[0] + range[1]) / 2;
  const minHalf = ((xRange[1] - xRange[0]) / widthPx) * (minWidthPx / 2);
  const half = Math.max((range[1] - range[0]) / 2, minHalf);
  return {
    shapes: [
      {
        type: "rect",
        xref: "x",
        yref: "paper",
        x0: centre - half,
        x1: centre + half,
        y0: 0,
        y1: 1,
        fillcolor: color,
        opacity: 0.18,
        line: { width: 0 },
        layer: "below",
      },
    ],
    annotations: [
      {
        x: centre,
        y: 1,
        xref: "x",
        yref: "paper",
        yanchor: "bottom",
        // Near an edge the label runs inwards, so it is not cut off
        xanchor: edgeAnchor((centre - xRange[0]) / (xRange[1] - xRange[0])),
        text,
        showarrow: false,
        font: { size: 11, color },
        captureevents: false,
      },
    ],
  };
}

export interface CurrentWindow {
  value: unknown;
  range: [number, number];
  tolerance: number;
  unit: ToleranceUnit;
}

/** The window a plot's args point to in the selection state, if one is set. */
export function currentWindow(
  args: {
    windowIdentifier?: string | null;
    windowTolerance?: number;
    windowToleranceUnit?: string;
  },
  state: Record<string, unknown>,
): CurrentWindow | null {
  const id = args.windowIdentifier;
  if (!id) return null;
  const value = state[id];
  const tolerance = args.windowTolerance ?? 0.01;
  const unit: ToleranceUnit =
    args.windowToleranceUnit === "ppm" || args.windowToleranceUnit === "m/z"
      ? args.windowToleranceUnit
      : "Da";
  const range = windowRange(value, tolerance, unit);
  return range ? { value, range, tolerance, unit } : null;
}

/** The toolbar switch that hides the shaded window and shows it again. */
export function windowTool(shown: boolean, toggle: () => void): PlotTool {
  return {
    id: "x-window",
    group: "annotate",
    icon: ICONS.window,
    label: "Show window",
    short: "Window",
    help: shown ? "hide the shaded window" : "show the shaded window",
    active: shown,
    run: toggle,
  };
}
