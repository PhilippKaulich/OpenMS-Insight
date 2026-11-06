/**
 * The Plotly bundle the current view loaded.
 *
 * Each view runs in an iframe of its own and loads only the partial Plotly
 * bundle its traces need (src/plotly/*.ts), instead of the full 4.6 MB build.
 * Shared code that calls Plotly at run time (mode bar icons, image export)
 * takes it from here, so it does not pull in a bundle of its own.
 */
import type Plotly from 'plotly.js-dist-min'

let current: typeof Plotly | null = null

export function setPlotly(plotly: typeof Plotly): void {
  current = plotly
}

export function plotly(): typeof Plotly {
  if (!current) throw new Error('No Plotly bundle loaded')
  return current
}
