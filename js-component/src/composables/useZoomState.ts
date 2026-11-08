/**
 * The zoom of a plot, kept in the shared selection state under the
 * component's `zoom_identifier`.
 *
 * The plot reports its axis ranges there after a zoom or pan (debounced), and
 * a value set from Python (a saved view opened, say) zooms the plot. The value
 * is plain JSON, so it can be written without the plot ever having been drawn:
 *
 *     {"x": [lo, hi], "y": [lo, hi]}
 *
 * Either axis may be missing: that axis shows its full extent. `null` (or no
 * value) is the full view. The heatmap's older `{"xRange", "yRange"}` form,
 * with `[-1, -1]` for no zoom, is read too.
 *
 * Without a `zoom_identifier` nothing is reported or read.
 */

import { computed, onBeforeUnmount } from 'vue'
import type Plotly from 'plotly.js-dist-min'
import { useSelectionStore } from '../stores/selection'

export type Range = [number, number]

export interface ZoomValue {
  x?: Range
  y?: Range
}

/** How long after the last zoom or pan the range is reported (ms). */
const REPORT_DELAY = 400

/** How long a zoom set from outside still applies to data arriving after it (ms). */
const RECENT_FOR = 2000

function range(value: unknown): Range | undefined {
  if (!Array.isArray(value) || value.length !== 2) return undefined
  const [a, b] = value
  if (typeof a !== 'number' || typeof b !== 'number') return undefined
  if (!Number.isFinite(a) || !Number.isFinite(b) || a === b) return undefined
  // The heatmap's sentinel for "no zoom"
  if (a === -1 && b === -1) return undefined
  return a < b ? [a, b] : [b, a]
}

/** A stored value as a zoom, or null for the full view. */
export function normalizeZoom(value: unknown): ZoomValue | null {
  if (!value || typeof value !== 'object') return null
  const v = value as Record<string, unknown>
  const x = range(v.x ?? v.xRange)
  const y = range(v.y ?? v.yRange)
  if (!x && !y) return null
  const zoom: ZoomValue = {}
  if (x) zoom.x = x
  if (y) zoom.y = y
  return zoom
}

function key(value: ZoomValue | null): string {
  return JSON.stringify(value)
}

export function useZoomState(identifier: () => string | undefined | null) {
  const selectionStore = useSelectionStore()
  // The value last reported or applied; a store value that differs is new
  let seen = key(null)
  // A value just applied: the data of the same update (opening a view changes
  // the selection and the zoom at once) may arrive a moment later and keeps it
  let recent: { value: ZoomValue | null; at: number } | undefined
  let timer: ReturnType<typeof setTimeout> | null = null
  let pending: ZoomValue | null = null

  function active(): boolean {
    return !!identifier()
  }

  function flush(): void {
    timer = null
    recent = undefined
    const id = identifier()
    if (!id) return
    const k = key(pending)
    if (k === seen) return
    seen = k
    selectionStore.updateSelection(id, pending)
  }

  /** Report the plot's ranges (debounced). `null` reports the full view. */
  function report(value: ZoomValue | null): void {
    if (!active()) return
    recent = undefined
    pending = value ? normalizeZoom(value) : null
    if (timer) clearTimeout(timer)
    timer = setTimeout(flush, REPORT_DELAY)
  }

  /**
   * A zoom set from outside since the last call, or undefined if there is
   * none. `null` means: show the full view.
   */
  function incoming(): ZoomValue | null | undefined {
    const id = identifier()
    if (!id) return undefined
    const value = normalizeZoom(selectionStore.$state[id])
    const k = key(value)
    if (k === seen) {
      if (recent && Date.now() - recent.at > RECENT_FOR) recent = undefined
      return recent ? recent.value : undefined
    }
    seen = k
    // A report still waiting would undo the value just set
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    recent = { value, at: Date.now() }
    return value
  }

  /** The zoom the plot should show now, from the state (for a first draw). */
  function current(): ZoomValue | null {
    const id = identifier()
    return id ? normalizeZoom(selectionStore.$state[id]) : null
  }

  /**
   * The ranges of a plot whose zoom Plotly keeps itself, as a zoom value:
   * read after a relayout. Axes left on autorange are left out.
   */
  function fromPlot(element: Plotly.PlotlyHTMLElement | null): ZoomValue | null {
    const full = (element as unknown as { _fullLayout?: Record<string, any> })?._fullLayout
    if (!full) return null
    const zoom: ZoomValue = {}
    for (const axis of ['x', 'y'] as const) {
      const a = full[`${axis}axis`]
      if (a && a.autorange === false) {
        const r = range(a.range)
        if (r) zoom[axis] = r
      }
    }
    return zoom.x || zoom.y ? zoom : null
  }

  /** Layout settings that show `zoom` on a plot whose zoom Plotly keeps. */
  function layoutFor(zoom: ZoomValue | null): Record<string, unknown> {
    const update: Record<string, unknown> = {}
    for (const axis of ['x', 'y'] as const) {
      const r = zoom?.[axis]
      if (r) {
        update[`${axis}axis.range`] = [...r]
        update[`${axis}axis.autorange`] = false
      } else {
        update[`${axis}axis.autorange`] = true
      }
    }
    return update
  }

  /**
   * Follow a zoom Plotly keeps itself (volcano, series, PCA): after each
   * zoom or pan, `onZoom` gets the ranges and they are reported. Bind again
   * after every `Plotly.newPlot`, which drops the plot's listeners.
   */
  function bindNative(
    element: Plotly.PlotlyHTMLElement | null,
    onZoom: (zoom: ZoomValue | null) => void,
  ): void {
    if (!element) return
    element.on('plotly_relayout', (event: Plotly.PlotRelayoutEvent) => {
      const keys = Object.keys(event || {})
      if (!keys.some((k) => k.startsWith('xaxis') || k.startsWith('yaxis'))) return
      const zoom = fromPlot(element)
      onZoom(zoom)
      report(zoom)
    })
  }

  /**
   * Changes whenever the stored zoom does: return it from `setup()` and watch
   * it, then apply `incoming()`.
   */
  const stamp = computed(() => {
    const id = identifier()
    return id ? key(normalizeZoom(selectionStore.$state[id])) : ''
  })

  onBeforeUnmount(() => {
    if (timer) {
      clearTimeout(timer)
      flush()
    }
  })

  return { active, report, incoming, current, fromPlot, layoutFor, bindNative, stamp }
}

/**
 * `layout` with the axes set to `zoom`, for a plot drawn with `Plotly.newPlot`
 * (which would otherwise start at the full extent again).
 */
export function withZoom<T extends Record<string, any>>(layout: T, zoom: ZoomValue | null): T {
  if (!zoom) return layout
  const result: Record<string, any> = { ...layout }
  for (const axis of ['x', 'y'] as const) {
    const r = zoom[axis]
    if (r) result[`${axis}axis`] = { ...(layout[`${axis}axis`] || {}), range: [...r], autorange: false }
  }
  return result as T
}
