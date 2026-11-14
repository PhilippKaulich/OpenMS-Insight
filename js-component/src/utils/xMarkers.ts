/**
 * Labelled x markers on a LinePlot (x_markers).
 *
 * Each marker gets a dotted guide at its x, in its own colour. With a
 * tolerance, the most intense peak within it of the marker is the marker's
 * peak: it gets a dot in the marker colour, and the label sits above it (at
 * the plot's top for a marker without a peak, whose guide is then fainter).
 * No guide crosses a dot or a label: above a peak it runs from the label up,
 * otherwise from the axis up to the label, and it is cut where it would pass
 * another marker's dot or label (markers closer together than a label is
 * wide, such as neighbouring reporter channels). Labels are left out where they would overlap a label already
 * placed, left to right, so zooming in shows more of them.
 */

import type Plotly from 'plotly.js-dist-min'

export interface XMarker {
  x: number
  label: string
  color?: string
}

export interface MarkerMatch extends XMarker {
  color: string
  /** Index of the matched peak, or undefined without one in tolerance. */
  index?: number
}

export interface MarkerOverlay {
  shapes: Partial<Plotly.Shape>[]
  annotations: Partial<Plotly.Annotations>[]
}

const FONT_SIZE = 11
/** Pixels kept between marker labels. */
const LABEL_GAP_PX = 3
/** Height of a label line, in pixels. */
const LABEL_HEIGHT_PX = Math.ceil(FONT_SIZE * 1.4)
/** Space kept between a guide and the dot or label it leads to, in pixels. */
const GUIDE_GAP_PX = 3
/** Radius of a marker's dot, in pixels. */
const DOT_RADIUS_PX = 3.5

/** A distinct colour per marker, evenly spaced around the hue circle. */
export function markerColor(i: number, n: number): string {
  const hue = Math.round((i * 360) / Math.max(n, 1) + 200) % 360
  return `hsl(${hue}, 70%, 45%)`
}

/** First index in `order` (x ascending) whose x is at or right of target. */
function lowerBound(x: ArrayLike<number>, order: ArrayLike<number>, target: number): number {
  let lo = 0
  let hi = order.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (x[order[mid]] < target) lo = mid + 1
    else hi = mid
  }
  return lo
}

/** Peak indices sorted by x. */
export function sortedByX(x: ArrayLike<number>): Uint32Array {
  const order = new Uint32Array(x.length)
  for (let i = 0; i < order.length; i++) order[i] = i
  order.sort((a, b) => x[a] - x[b])
  return order
}

/**
 * Each marker with its colour and the most intense peak within `tolerance`
 * of it (no peak without a tolerance).
 */
export function matchMarkers(
  markers: XMarker[],
  x: ArrayLike<number>,
  y: ArrayLike<number>,
  order: ArrayLike<number>,
  tolerance: number | null | undefined,
): MarkerMatch[] {
  return markers.map((marker, i) => {
    const match: MarkerMatch = { ...marker, color: marker.color || markerColor(i, markers.length) }
    if (!tolerance || !(tolerance > 0)) return match
    let best = -Infinity
    for (let k = lowerBound(x, order, marker.x - tolerance); k < order.length; k++) {
      const j = order[k]
      if (x[j] > marker.x + tolerance) break
      if (y[j] > best) {
        best = y[j]
        match.index = j
      }
    }
    return match
  })
}

export interface MarkerOverlayInput {
  matches: MarkerMatch[]
  x: ArrayLike<number>
  y: ArrayLike<number>
  xRange: number[]
  yRange: number[]
  /** Width of the plot area, in pixels. */
  widthPx: number
  /** Height of the plot area, in pixels. */
  heightPx: number
  /** Whether markers are matched to peaks; unmatched guides are then fainter. */
  matching: boolean
  textWidth: (text: string, fontSize: number) => number
}

/** Guides and labels for the markers in the visible x range. */
export function markerOverlay(input: MarkerOverlayInput): MarkerOverlay {
  const { matches, x, y, xRange, yRange, widthPx } = input
  const span = xRange[1] - xRange[0]
  const shapes: Partial<Plotly.Shape>[] = []
  const annotations: Partial<Plotly.Annotations>[] = []
  if (!(span > 0) || widthPx <= 0) return { shapes, annotations }

  const ySpan = yRange[1] - yRange[0]
  const px2paper = (px: number) => (input.heightPx > 0 ? px / input.heightPx : 0)
  const toPx = (value: number) => ((value - xRange[0]) / span) * widthPx

  // What each marker draws besides its guide: boxes in pixels across and
  // paper units up, which no guide may cross
  interface Box {
    left: number
    right: number
    bottom: number
    top: number
  }
  const boxes: Box[] = []
  const guides: { m: MarkerMatch; px: number; y0: number; y1: number }[] = []

  let labelRight = -Infinity
  for (const m of matches) {
    if (m.x < xRange[0] || m.x > xRange[1]) continue
    const matched = m.index !== undefined
    const peakY = matched ? y[m.index as number] : undefined
    const onPeak = matched && (peakY as number) < yRange[1] && ySpan > 0
    const peak = onPeak ? Math.max(0, ((peakY as number) - yRange[0]) / ySpan) : 0
    // The label sits over the marker's peak, or at the top without one;
    // it is left out where it would overlap a label placed before it
    let labelled = false
    const labelX = matched ? x[m.index as number] : m.x
    if (m.label) {
      const px = toPx(labelX)
      const width = input.textWidth(m.label, FONT_SIZE)
      if (px - width / 2 >= labelRight + LABEL_GAP_PX) {
        labelRight = px + width / 2
        labelled = true
        annotations.push({
          x: labelX,
          y: onPeak ? (peakY as number) : 1,
          xref: 'x',
          yref: onPeak ? 'y' : 'paper',
          yanchor: onPeak ? 'bottom' : 'top',
          yshift: onPeak ? 6 : 0,
          text: m.label,
          showarrow: false,
          font: { size: FONT_SIZE, color: m.color },
          captureevents: false,
        })
        const bottom = onPeak ? peak + px2paper(6) : 1 - px2paper(LABEL_HEIGHT_PX)
        boxes.push({
          left: px - width / 2,
          right: px + width / 2,
          bottom,
          top: bottom + px2paper(LABEL_HEIGHT_PX),
        })
      }
    }
    if (onPeak) {
      const px = toPx(labelX)
      boxes.push({
        left: px - DOT_RADIUS_PX,
        right: px + DOT_RADIUS_PX,
        bottom: peak - px2paper(DOT_RADIUS_PX),
        top: peak + px2paper(DOT_RADIUS_PX),
      })
      // From above the dot (and its label) to the top
      const above = labelled ? 6 + LABEL_HEIGHT_PX : DOT_RADIUS_PX
      guides.push({ m, px: toPx(m.x), y0: peak + px2paper(above + GUIDE_GAP_PX), y1: 1 })
    } else {
      // From the axis to below the label at the top
      const y1 = labelled ? 1 - px2paper(LABEL_HEIGHT_PX + GUIDE_GAP_PX) : 1
      guides.push({ m, px: toPx(m.x), y0: 0, y1 })
    }
  }

  // Each guide is cut where it would cross another marker's dot or label
  // (markers closer than a label's width, such as neighbouring channels)
  const gap = px2paper(GUIDE_GAP_PX)
  const minLength = px2paper(4)
  for (const g of guides) {
    let pieces: [number, number][] = [[g.y0, g.y1]]
    for (const box of boxes) {
      if (g.px < box.left - GUIDE_GAP_PX || g.px > box.right + GUIDE_GAP_PX) continue
      const lo = box.bottom - gap
      const hi = box.top + gap
      pieces = pieces.flatMap(([a, b]): [number, number][] => {
        if (hi <= a || lo >= b) return [[a, b]]
        const out: [number, number][] = []
        if (lo > a) out.push([a, lo])
        if (hi < b) out.push([hi, b])
        return out
      })
    }
    for (const [y0, y1] of pieces) {
      if (y1 - y0 < minLength) continue
      shapes.push({
        type: 'line',
        xref: 'x',
        yref: 'paper',
        x0: g.m.x,
        x1: g.m.x,
        y0,
        y1,
        line: { color: g.m.color, width: 1, dash: 'dot' },
        opacity: g.m.index !== undefined || !input.matching ? 0.9 : 0.45,
        layer: 'below',
      })
    }
  }

  return { shapes, annotations }
}

/** Dots on the markers' peaks, as a trace without hover or clicks. */
export function markerDots(
  matches: MarkerMatch[],
  x: ArrayLike<number>,
  y: ArrayLike<number>,
): Plotly.Data | undefined {
  const found = matches.filter((m) => m.index !== undefined)
  if (found.length === 0) return undefined
  return {
    x: found.map((m) => x[m.index as number]),
    y: found.map((m) => y[m.index as number]),
    type: 'scatter',
    mode: 'markers',
    marker: { color: found.map((m) => m.color), size: 7 },
    hoverinfo: 'skip',
    showlegend: false,
  }
}
