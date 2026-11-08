/**
 * Hover read-out for stick spectra: the peak nearest the mouse along x.
 *
 * Plotly's own hover picks the nearest drawn point, and a stick is drawn as
 * three points (baseline, top, baseline), so over the lower part of a tall
 * peak it shows a neighbour's top or nothing at all. Here the mouse's x is
 * matched to the nearest peak by a binary search over the peaks sorted by x
 * (sorted once per spectrum), anywhere in the plot area's height; within two
 * pixels of the mouse the most intense peak wins, as that is the one drawn in a
 * dense profile spectrum. A small box beside the peak top shows its x and y. A dot marks the peak. Peaks more
 * than SNAP_PX pixels away from the mouse are not shown.
 */

import { onBeforeUnmount, reactive, ref } from 'vue'
import { plotPointPosition } from './usePeakLabels'

/** Peaks closer than this to the right edge get the box on their left. */
const FLIP_MARGIN_PX = 200
/** Farthest a peak may be from the mouse, in pixels along x. */
export const SNAP_PX = 12

export interface PeakHoverSource {
  x: ArrayLike<number> | undefined
  y: ArrayLike<number> | undefined
  /** Extra line for a peak, e.g. its annotation. */
  extra?: (index: number) => string | undefined
  xName: string
  yName: string
}

export interface PeakHoverTip {
  /** Peak top, relative to the container. */
  left: number
  top: number
  index: number
  lines: string[]
  /** Box to the left of the peak (near the right edge). */
  flip: boolean
}

/** Peak indices sorted by x (NaN last). */
export function xOrder(x: ArrayLike<number>): Uint32Array {
  const order = new Uint32Array(x.length)
  for (let i = 0; i < order.length; i++) order[i] = i
  order.sort((a, b) => {
    const xa = x[a]
    const xb = x[b]
    if (Number.isNaN(xa)) return Number.isNaN(xb) ? 0 : 1
    if (Number.isNaN(xb)) return -1
    return xa - xb
  })
  return order
}

/** Index of the peak whose x is nearest `target` (undefined when empty). */
export function nearestByX(
  x: ArrayLike<number>,
  order: Uint32Array,
  target: number,
): number | undefined {
  const n = finiteCount(x, order)
  if (n === 0) return undefined
  const lo = lowerBound(x, order, n, target)
  if (lo === n) return order[n - 1]
  // lo: first peak at or right of target; compare with its left neighbour
  if (lo > 0 && Math.abs(x[order[lo - 1]] - target) <= Math.abs(x[order[lo]] - target)) {
    return order[lo - 1]
  }
  return order[lo]
}

/**
 * The most intense peak with x within `halfWidth` of `target`, else the
 * nearest one. In a dense profile spectrum many peaks share a pixel, and the
 * tallest is the one drawn. At most MAX_SCAN peaks are looked at.
 */
export function peakAt(
  x: ArrayLike<number>,
  y: ArrayLike<number>,
  order: Uint32Array,
  target: number,
  halfWidth: number,
): number | undefined {
  const n = finiteCount(x, order)
  if (n === 0) return undefined
  const lo = lowerBound(x, order, n, target)
  let best: number | undefined
  let scanned = 0
  for (let k = lo - 1; k >= 0 && scanned < MAX_SCAN && target - x[order[k]] <= halfWidth; k--, scanned++) {
    if (best === undefined || y[order[k]] > y[best]) best = order[k]
  }
  scanned = 0
  for (let k = lo; k < n && scanned < MAX_SCAN && x[order[k]] - target <= halfWidth; k++, scanned++) {
    if (best === undefined || y[order[k]] > y[best]) best = order[k]
  }
  return best ?? nearestByX(x, order, target)
}

/** Peaks looked at on each side of the mouse. */
const MAX_SCAN = 5000
/** Half the width, in pixels, of the window where the tallest peak wins. */
export const PIXEL_WINDOW = 2

/** Number of leading non-NaN entries of `order` (NaN sorts last). */
function finiteCount(x: ArrayLike<number>, order: Uint32Array): number {
  let n = order.length
  while (n > 0 && Number.isNaN(x[order[n - 1]])) n -= 1
  return n
}

/** First position in `order` (of n) whose x is at or right of target. */
function lowerBound(x: ArrayLike<number>, order: Uint32Array, n: number, target: number): number {
  let lo = 0
  let hi = n
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (x[order[mid]] < target) lo = mid + 1
    else hi = mid
  }
  return lo
}

/** x with 4 decimals; y rounded (4 significant digits below 100, exponent from 1e6). */
export function formatHoverValues(x: number, y: number): [string, string] {
  const ay = Math.abs(y)
  let ys: string
  if (ay >= 1e6 || (ay > 0 && ay < 0.01)) ys = y.toExponential(3)
  else if (ay >= 100) ys = Math.round(y).toLocaleString('en-US')
  else ys = String(Number(y.toPrecision(4)))
  return [x.toFixed(4), ys]
}

interface PlotLayout {
  _size?: { l: number; t: number; w: number; h: number }
  xaxis?: { p2l?: (px: number) => number; l2p?: (v: number) => number }
}

export function usePeakHover() {
  const tip = ref<PeakHoverTip | null>(null)
  let element: HTMLElement | null = null
  let container: HTMLElement | null = null
  let source: () => PeakHoverSource = () => ({ x: undefined, y: undefined, xName: 'x', yName: 'y' })
  let sorted: { x: ArrayLike<number>; order: Uint32Array } | null = null
  let frame = 0
  let lastEvent: MouseEvent | null = null

  function hide(): void {
    tip.value = null
  }

  function update(): void {
    frame = 0
    const event = lastEvent
    const layout = (element as unknown as { _fullLayout?: PlotLayout } | null)?._fullLayout
    const size = layout?._size
    const xaxis = layout?.xaxis
    const { x, y, extra, xName, yName } = source()
    if (!event || !element || !size || !xaxis?.p2l || !xaxis.l2p || !x || !y || x.length === 0) {
      return hide()
    }
    // Hidden while a button is held (a zoom box or pan)
    if (event.buttons !== 0) return hide()
    const rect = element.getBoundingClientRect()
    const px = event.clientX - rect.left - size.l
    const py = event.clientY - rect.top - size.t
    if (px < 0 || px > size.w || py < 0 || py > size.h) return hide()

    if (!sorted || sorted.x !== x) sorted = { x, order: xOrder(x) }
    const target = xaxis.p2l(px)
    const halfWidth = Math.abs(xaxis.p2l(px + PIXEL_WINDOW) - target)
    const index = peakAt(x, y, sorted.order, target, halfWidth)
    if (index === undefined || Math.abs(xaxis.l2p(x[index]) - px) > SNAP_PX) return hide()

    const position = plotPointPosition(element, container, x[index], y[index])
    if (!position) return hide()
    const [xs, ys] = formatHoverValues(x[index], y[index])
    const lines = [`${xName} ${xs}`, `${yName} ${ys}`]
    const note = extra?.(index)
    if (note) lines.push(note)
    // Keep the dot inside the plot area for peaks above the visible y range
    const plotTop = rect.top - (container?.getBoundingClientRect().top ?? rect.top) + size.t
    const width = container?.clientWidth ?? rect.width
    tip.value = {
      left: position.left,
      top: Math.max(position.top, plotTop),
      index,
      lines,
      flip: position.left > width - FLIP_MARGIN_PX,
    }
  }

  function onMove(event: MouseEvent): void {
    lastEvent = event
    if (!frame) frame = requestAnimationFrame(update)
  }

  function onLeave(): void {
    lastEvent = null
    if (frame) cancelAnimationFrame(frame)
    frame = 0
    hide()
  }

  /**
   * Follow the mouse over a plot element (once per element). `getSource`
   * gives the peaks drawn now.
   */
  function bind(
    plotElement: HTMLElement | null,
    root: HTMLElement | null,
    getSource: () => PeakHoverSource,
  ): void {
    source = getSource
    container = root
    if (!plotElement || plotElement === element) return
    unbind()
    element = plotElement
    element.addEventListener('mousemove', onMove)
    element.addEventListener('mouseleave', onLeave)
    element.addEventListener('mousedown', hide)
    element.addEventListener('wheel', hide, { passive: true })
  }

  function unbind(): void {
    if (!element) return
    element.removeEventListener('mousemove', onMove)
    element.removeEventListener('mouseleave', onLeave)
    element.removeEventListener('mousedown', hide)
    element.removeEventListener('wheel', hide)
    element = null
  }

  onBeforeUnmount(() => {
    if (frame) cancelAnimationFrame(frame)
    unbind()
  })

  return reactive({ tip, bind, hide })
}
