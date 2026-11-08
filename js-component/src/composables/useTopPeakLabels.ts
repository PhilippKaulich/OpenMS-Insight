/**
 * The "Label top peaks" button in Plotly's mode bar of LinePlot.
 *
 * Switched on, the most intense peaks in the visible x range carry their x
 * value (the m/z of a spectrum) above the stick. The labels are placed again
 * on every zoom or pan: the most intense peaks come first, and a label that
 * would overlap one already placed is left out, so zooming in shows more of
 * them. The labels are part of the layout, so the image download has them.
 *
 * The component's `top_peak_labels` sets how many peaks are labelled (0
 * removes the button); `show_top_peak_labels` switches the labels on from
 * the start.
 */

import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import type Plotly from 'plotly.js-dist-min'

/** Mode bar title of the button; also selects it for the active style. */
const TOP_TITLE = 'Label top peaks: show the m/z of the most intense peaks in view'
/** Class on the plot element while the labels are shown. */
const ACTIVE_CLASS = 'top-peaks-labelled'

// A number sign (Material Design "tag")
const NUMBER_PATH =
  'M20.5 10L21 8h-4l1-4h-2l-1 4h-4l1-4h-2L9 8H5l-.5 2h4l-1 4h-4L3 16h4l-1 4h2l1-4h4l-1 4h2l1-4h4l.5-2h-4l1-4h4zm-7 4h-4l1-4h4l-1 4z'

const FONT_SIZE = 11
/** Space kept free around each label, in pixels. */
const GAP_PX = 3
/** Pixels between the top of a peak and its label. */
const LIFT_PX = 2
/** Peaks looked at per label before giving up (a crowded view stays cheap). */
const CANDIDATES_PER_LABEL = 50

let styleInstalled = false

/** The highlighted button while the labels are shown (once per page). */
function installStyle(): void {
  if (styleInstalled || typeof document === 'undefined') return
  styleInstalled = true
  const style = document.createElement('style')
  style.textContent =
    `.${ACTIVE_CLASS} .modebar-btn[data-title="${TOP_TITLE}"] path` +
    ' { fill: #ff4b4b !important; }' +
    `.${ACTIVE_CLASS} .modebar-btn[data-title="${TOP_TITLE}"]` +
    ' { opacity: 1 !important; }'
  document.head.appendChild(style)
}

export interface TopPeakLabelInput {
  x: ArrayLike<number>
  y: ArrayLike<number>
  xRange: number[]
  yRange: number[]
  /** Size of the plot area (inside the axes), in pixels. */
  widthPx: number
  heightPx: number
  /** Width of a label's text, in pixels. */
  textWidth: (text: string, fontSize: number) => number
  /** Peaks that already carry a label of another kind. */
  skip?: (index: number) => boolean
  color: string
}

/** The x value as shown on a label: 4 decimals below 10, else 2. */
export function formatPeakX(x: number): string {
  return Math.abs(x) < 10 ? x.toFixed(4) : x.toFixed(2)
}

/** Peak indices from the most to the least intense (ties: smaller x first). */
export function intensityOrder(x: ArrayLike<number>, y: ArrayLike<number>): Uint32Array {
  const order = new Uint32Array(y.length)
  for (let i = 0; i < order.length; i++) order[i] = i
  order.sort((a, b) => y[b] - y[a] || x[a] - x[b])
  return order
}

/**
 * The labels for the most intense peaks in view, at most `count` of them,
 * none overlapping another. `order` comes from `intensityOrder()`.
 */
export function placeTopPeakLabels(
  input: TopPeakLabelInput,
  order: Uint32Array,
  count: number,
): Partial<Plotly.Annotations>[] {
  const { x, y, xRange, yRange, widthPx, heightPx } = input
  const xSpan = xRange[1] - xRange[0]
  const ySpan = yRange[1] - yRange[0]
  if (count <= 0 || !(xSpan > 0) || !(ySpan > 0) || widthPx <= 0 || heightPx <= 0) return []

  const placed: Array<[number, number, number, number]> = []
  const labels: Partial<Plotly.Annotations>[] = []
  const textHeight = FONT_SIZE + 2
  const limit = count * CANDIDATES_PER_LABEL
  let looked = 0

  for (let k = 0; k < order.length && labels.length < count && looked < limit; k++) {
    const i = order[k]
    const px = x[i]
    const py = y[i]
    if (!(py > 0) || px < xRange[0] || px > xRange[1] || !Number.isFinite(px)) continue
    looked += 1
    if (input.skip?.(i)) continue

    const text = formatPeakX(px)
    const width = input.textWidth(text, FONT_SIZE)
    const cx = ((px - xRange[0]) / xSpan) * widthPx
    // Pixel y from the top of the plot area
    const bottom = heightPx - ((Math.min(py, yRange[1]) - yRange[0]) / ySpan) * heightPx - LIFT_PX
    const box: [number, number, number, number] = [
      cx - width / 2 - GAP_PX,
      bottom - textHeight - GAP_PX,
      cx + width / 2 + GAP_PX,
      bottom + GAP_PX,
    ]
    // Fully inside the plot area
    if (box[0] < 0 || box[2] > widthPx || box[1] < 0) continue
    const overlaps = placed.some(
      (p) => box[0] < p[2] && box[2] > p[0] && box[1] < p[3] && box[3] > p[1],
    )
    if (overlaps) continue

    placed.push(box)
    labels.push({
      x: px,
      y: py,
      xref: 'x',
      yref: 'y',
      yanchor: 'bottom',
      yshift: LIFT_PX,
      text,
      showarrow: false,
      font: { size: FONT_SIZE, color: input.color },
      captureevents: false,
    })
  }
  return labels
}

export function useTopPeakLabels(count: () => number, initial: () => boolean) {
  const on = ref(initial())
  let plotElement: HTMLElement | null = null
  let orderFor: { x: ArrayLike<number>; y: ArrayLike<number>; order: Uint32Array } | null = null
  installStyle()

  function markActive(): void {
    plotElement?.classList.toggle(ACTIVE_CLASS, on.value && count() > 0)
  }

  const stopInitial = watch(initial, (value) => {
    on.value = value
  })
  watch(on, markActive)
  onBeforeUnmount(stopInitial)

  function toggle(): void {
    on.value = !on.value
  }

  /** Remember the plot element (after each draw) so it carries the state. */
  function bind(element: HTMLElement | null): void {
    plotElement = element
    markActive()
  }

  /** The labels to add to the layout (none while switched off). */
  function annotations(input: TopPeakLabelInput): Partial<Plotly.Annotations>[] {
    const n = count()
    if (!on.value || n <= 0 || !input.x || input.x.length === 0) return []
    // Sorted once per spectrum; zooming only walks the order again
    if (!orderFor || orderFor.x !== input.x || orderFor.y !== input.y) {
      orderFor = { x: input.x, y: input.y, order: intensityOrder(input.x, input.y) }
    }
    return placeTopPeakLabels(input, orderFor.order, n)
  }

  function modeBarButtons(): Plotly.ModeBarButton[] {
    if (count() <= 0) return []
    return [
      {
        name: 'labelTopPeaks',
        title: TOP_TITLE,
        icon: { width: 24, height: 24, path: NUMBER_PATH },
        click: () => toggle(),
      },
    ] as unknown as Plotly.ModeBarButton[]
  }

  return reactive({ on, toggle, bind, annotations, modeBarButtons })
}
