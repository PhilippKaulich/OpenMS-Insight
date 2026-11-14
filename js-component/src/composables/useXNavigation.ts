/**
 * Mouse navigation along x for stick spectra (LinePlot).
 *
 * - The wheel zooms x around the mouse; y follows the peaks in view, as after
 *   any zoom. Zooming out past the full extent shows the full view.
 * - Shift + wheel, or a sideways wheel (trackpad), pans x.
 * - Dragging with the middle button pans x.
 * Panning stops at the ends of the data.
 *
 * Plotly's own scroll zoom is left off: it zooms y as well, so the baseline
 * jumped while the wheel turned and every step drew twice. Here all steps of a
 * frame become one new x range, handed to `apply`. Only the plot area reacts;
 * elsewhere the wheel scrolls the page.
 */

import { onBeforeUnmount } from 'vue'

/** Zoom factor per pixel of wheel movement (100 px ≈ ×1.22). */
export const ZOOM_PER_PX = 0.002
/** Pixels per line or page for wheels that report in those units. */
const LINE_PX = 40
const PAGE_PX = 800

export type XRange = [number, number]

export interface XNavigationTarget {
  /** The x range drawn now. */
  current: () => XRange | undefined
  /** The full x extent of the data (the double-click view). */
  full: () => XRange | undefined
  /** Draw this x range, or the full view for null. */
  apply: (range: XRange | null) => void
}

/** The range after a wheel zoom by `factor` (>1 zooms out) around `anchor`. */
export function zoomRange(range: XRange, anchor: number, factor: number): XRange {
  return [anchor - (anchor - range[0]) * factor, anchor + (range[1] - anchor) * factor]
}

/** The range moved by `dx` data units. */
export function panRange(range: XRange, dx: number): XRange {
  return [range[0] + dx, range[1] + dx]
}

/** The range moved back inside the full extent, keeping its width. */
export function keepInside(range: XRange, full: XRange | undefined): XRange {
  if (!full) return range
  const span = range[1] - range[0]
  if (span >= full[1] - full[0]) return range
  if (range[0] < full[0]) return [full[0], full[0] + span]
  if (range[1] > full[1]) return [full[1] - span, full[1]]
  return range
}

/** Null when `range` covers the full extent (show the full view instead). */
export function clampToFull(range: XRange, full: XRange | undefined): XRange | null {
  if (!full) return range
  if (range[1] - range[0] >= full[1] - full[0]) return null
  return range
}

/** Wheel movement in pixels. */
export function wheelPixels(event: WheelEvent): { dx: number; dy: number } {
  const unit = event.deltaMode === 1 ? LINE_PX : event.deltaMode === 2 ? PAGE_PX : 1
  return { dx: event.deltaX * unit, dy: event.deltaY * unit }
}

interface PlotSize {
  l: number
  t: number
  w: number
  h: number
}

export function useXNavigation() {
  let element: HTMLElement | null = null
  let target: XNavigationTarget | null = null
  let pending: XRange | null | undefined
  let frame = 0
  let drag: { x: number; range: XRange; span: number } | null = null

  function size(): PlotSize | undefined {
    return (element as unknown as { _fullLayout?: { _size?: PlotSize } } | null)?._fullLayout?._size
  }

  /** Mouse position inside the plot area, in pixels from its left edge. */
  function plotX(event: MouseEvent): number | undefined {
    const s = size()
    if (!element || !s) return undefined
    const rect = element.getBoundingClientRect()
    const px = event.clientX - rect.left - s.l
    const py = event.clientY - rect.top - s.t
    if (px < 0 || px > s.w || py < 0 || py > s.h) return undefined
    return px
  }

  /** The range a step starts from: one already waiting for the frame, else the drawn one. */
  function base(): XRange | undefined {
    if (pending === null) return target?.full()
    return pending ?? target?.current()
  }

  function schedule(range: XRange | null): void {
    pending = range
    if (!frame) {
      frame = requestAnimationFrame(() => {
        frame = 0
        const next = pending
        pending = undefined
        if (next !== undefined) target?.apply(next)
      })
    }
  }

  function onWheel(event: WheelEvent): void {
    const px = plotX(event)
    const range = base()
    const s = size()
    if (px === undefined || !range || !s) return
    event.preventDefault()
    const span = range[1] - range[0]
    const { dx, dy } = wheelPixels(event)
    if (event.shiftKey || Math.abs(dx) > Math.abs(dy)) {
      const move = event.shiftKey && dx === 0 ? dy : dx
      schedule(keepInside(panRange(range, (move / s.w) * span), target?.full()))
      return
    }
    const anchor = range[0] + (px / s.w) * span
    schedule(clampToFull(zoomRange(range, anchor, Math.exp(dy * ZOOM_PER_PX)), target?.full()))
  }

  function onMouseDown(event: MouseEvent): void {
    if (event.button !== 1) return
    const px = plotX(event)
    const range = target?.current()
    const s = size()
    if (px === undefined || !range || !s) return
    // No autoscroll, and no zoom box from Plotly
    event.preventDefault()
    event.stopPropagation()
    drag = { x: event.clientX, range, span: range[1] - range[0] }
    element?.classList.add('x-panning')
    window.addEventListener('mousemove', onDragMove)
    window.addEventListener('mouseup', onDragEnd)
  }

  function onDragMove(event: MouseEvent): void {
    const s = size()
    if (!drag || !s) return
    const dx = -((event.clientX - drag.x) / s.w) * drag.span
    schedule(keepInside(panRange(drag.range, dx), target?.full()))
  }

  function onDragEnd(): void {
    drag = null
    element?.classList.remove('x-panning')
    window.removeEventListener('mousemove', onDragMove)
    window.removeEventListener('mouseup', onDragEnd)
  }

  /** Follow the wheel and the middle button over a plot element (once per element). */
  function bind(plotElement: HTMLElement | null, navigationTarget: XNavigationTarget): void {
    target = navigationTarget
    if (!plotElement || plotElement === element) return
    unbind()
    element = plotElement
    // Capture: before Plotly's drag box sees the middle button
    element.addEventListener('wheel', onWheel, { passive: false, capture: true })
    element.addEventListener('mousedown', onMouseDown, { capture: true })
  }

  function unbind(): void {
    onDragEnd()
    if (!element) return
    element.removeEventListener('wheel', onWheel, { capture: true })
    element.removeEventListener('mousedown', onMouseDown, { capture: true })
    element = null
  }

  onBeforeUnmount(() => {
    if (frame) cancelAnimationFrame(frame)
    unbind()
  })

  return { bind }
}
