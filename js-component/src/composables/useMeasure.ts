/**
 * Measuring the distance between two points of a plot (`measure` on the
 * Python side). Shared by every 2D Plotly component.
 *
 * The "Measure" button in Plotly's mode bar (`modeBarButtons()`) switches
 * clicks from selecting to measuring; a second button clears all
 * measurements. While measure mode is on, the button is highlighted and
 * MeasureHint shows a short note over the plot. The first click picks a point, the second completes a
 * measurement. Two kinds:
 *
 * - `span` (spectra and other x-axis plots): a bracket above the two points,
 *   labelled with their x difference and, where the axis is m/z or mass, the
 *   amino-acid residues that difference matches.
 * - `points` (scatter plots): a line between the two points, labelled with
 *   their x and y differences.
 *
 * Measurements are plain Plotly shapes and annotations (see `overlay()`), so
 * the image download includes them. Esc cancels a half-finished measurement,
 * clicking a label removes its measurement and "Clear" removes all. They
 * belong to the data they were taken on: `setDataKey()` drops them when the
 * plotted data changes.
 *
 * With measure mode off nothing here reacts to clicks, so selection works as
 * it does without the tool.
 */

import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import type Plotly from 'plotly.js-dist-min'
import {
  DEFAULT_MEASURE_TOLERANCE,
  formatMeasureLabel,
  formatPointLabel,
  matchResidues,
} from '@/utils/measure'

/** Annotation and shape names of measurements start with this. */
export const MEASURE_NAME_PREFIX = 'measure-'

/** What a click measures and how the result is labelled. */
export interface MeasureSpec {
  kind: 'span' | 'points'
  /** Name of the x quantity in labels, e.g. "m/z" (label: "Δm/z"). */
  xQuantity: string
  /** Name of the y quantity (`points` only). */
  yQuantity?: string
  /** Charges to match residue masses at; empty or absent: no matching. */
  charges?: readonly number[]
  /** Per-point tolerance in Da for residue matching. */
  tolerance?: number
  /** Extra named masses besides the standard residues. */
  residues?: Record<string, number>
}

/** A clicked point. `group` keeps a measurement in one part of a plot (a mirror plot's half). */
export interface MeasurePoint {
  x: number
  y: number
  group?: string
}

export interface Measurement {
  id: number
  kind: 'span' | 'points'
  group: string
  /** Points in click order. */
  x1: number
  y1: number
  x2: number
  y2: number
  /** Stacking level among overlapping span measurements of the same group. */
  level: number
  label: string
}

export interface MeasureOverlayOptions {
  /** Line and label colour. */
  color: string
  /** Label background. */
  background: string
  /**
   * Height in data units that brackets of `span` measurements are spaced by,
   * normally the tallest visible point (default: the tallest measured point).
   */
  yScale?: number
  /** Direction a group's brackets extend in: -1 for a mirror plot's lower half. */
  ySign?: (group: string) => 1 | -1
  /** Axis references of the overlay (default 'x' / 'y'). */
  xref?: string
  yref?: string
}

export interface MeasureOverlay {
  shapes: Partial<Plotly.Shape>[]
  annotations: Partial<Plotly.Annotations>[]
}

/** The first point of a measurement still waiting for its second point. */
interface PendingPoint extends MeasurePoint {
  kind: 'span' | 'points'
}

const DEFAULT_GROUP = ''

/** Mode bar titles of the two buttons; the first also styles the active state. */
const MEASURE_TITLE_PREFIX = 'Measure'
const CLEAR_TITLE = 'Clear measurements'
/** Class on the plot element while measure mode is on. */
const ACTIVE_CLASS = 'measure-active'

// A ruler, and a ruler crossed out
const RULER_PATH =
  'M21 6H3c-1.1 0-2 .9-2 2v8c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm0 10H3V8h2v4h2V8h2v4h2V8h2v4h2V8h2v4h2V8h2v8z'
const CLEAR_PATH =
  'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z'

let styleInstalled = false

/** The highlighted Measure button while measure mode is on (once per page). */
function installStyle(): void {
  if (styleInstalled || typeof document === 'undefined') return
  styleInstalled = true
  const style = document.createElement('style')
  style.textContent =
    `.${ACTIVE_CLASS} .modebar-btn[data-title^="${MEASURE_TITLE_PREFIX}"] path` +
    ' { fill: #ff4b4b !important; }' +
    `.${ACTIVE_CLASS} .modebar-btn[data-title^="${MEASURE_TITLE_PREFIX}"]` +
    ' { opacity: 1 !important; }'
  document.head.appendChild(style)
}

export function useMeasure(enabled: () => boolean) {
  const mode = ref(false)
  const measurements = ref<Measurement[]>([])
  const pending = ref<PendingPoint | null>(null)
  /** Changes whenever what is drawn changes; components redraw on it. */
  const revision = ref(0)
  let nextId = 1
  let dataKey: string | undefined
  /** The plot element last drawn, which carries the active class. */
  let plotElement: HTMLElement | null = null
  installStyle()

  function markActive(): void {
    plotElement?.classList.toggle(ACTIVE_CLASS, mode.value && enabled())
  }
  watch(mode, markActive)

  const active = computed(() => enabled() && mode.value)

  const hint = computed(() => {
    if (!mode.value) return ''
    if (pending.value) return 'Measuring: click a second point (Esc cancels)'
    if (measurements.value.length > 0) return 'Measuring: click a point, or a label to remove it'
    return 'Measuring: click a point'
  })

  function changed(): void {
    revision.value += 1
  }

  function toggle(): void {
    mode.value = !mode.value
    if (!mode.value && pending.value) {
      pending.value = null
      changed()
    }
  }

  function clear(): void {
    if (measurements.value.length === 0 && !pending.value) return
    measurements.value = []
    pending.value = null
    changed()
  }

  function remove(id: number): void {
    const before = measurements.value.length
    measurements.value = measurements.value.filter((m) => m.id !== id)
    if (measurements.value.length !== before) changed()
  }

  /**
   * Measurements belong to the data they were taken on: a new key (other
   * data plotted) drops them. The first key only records it.
   */
  function setDataKey(key: string): void {
    if (key === dataKey) return
    const first = dataKey === undefined
    dataKey = key
    if (!first) clear()
  }

  function label(spec: MeasureSpec, a: MeasurePoint, b: MeasurePoint): string {
    if (spec.kind === 'points') {
      return formatPointLabel(b.x - a.x, b.y - a.y, spec.xQuantity, spec.yQuantity || 'y')
    }
    const delta = b.x - a.x
    const charges = spec.charges ?? []
    const matches =
      charges.length > 0
        ? matchResidues(delta, spec.tolerance ?? DEFAULT_MEASURE_TOLERANCE, spec.residues ?? {}, charges)
        : []
    return formatMeasureLabel(delta, matches, spec.xQuantity)
  }

  /**
   * A click in measure mode. The first click remembers the point, a second
   * one (in the same group) completes a measurement; the same point twice
   * cancels. Returns false when measure mode is off, so the caller handles
   * the click as usual.
   */
  function pick(point: MeasurePoint, spec: MeasureSpec): boolean {
    if (!active.value) return false
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return true
    const group = point.group ?? DEFAULT_GROUP
    const first = pending.value
    if (!first || (first.group ?? DEFAULT_GROUP) !== group) {
      // Start, or restart in another group: a measurement stays in one group
      pending.value = { ...point, group, kind: spec.kind }
    } else if (first.x === point.x && first.y === point.y) {
      pending.value = null
    } else {
      add(spec, first, { ...point, group })
      pending.value = null
    }
    changed()
    return true
  }

  function add(spec: MeasureSpec, a: MeasurePoint, b: MeasurePoint): void {
    const group = a.group ?? DEFAULT_GROUP
    let level = 0
    if (spec.kind === 'span') {
      // Stack above the brackets of this group it would overlap
      const x1 = Math.min(a.x, b.x)
      const x2 = Math.max(a.x, b.x)
      const height = Math.max(Math.abs(a.y), Math.abs(b.y))
      const overlapping = measurements.value.filter(
        (m) =>
          m.kind === 'span' &&
          m.group === group &&
          Math.min(m.x1, m.x2) <= x2 &&
          x1 <= Math.max(m.x1, m.x2),
      )
      while (
        overlapping.some(
          (m) => m.level === level && Math.max(Math.abs(m.y1), Math.abs(m.y2)) >= height * 0.8,
        )
      ) {
        level += 1
      }
    }
    measurements.value = [
      ...measurements.value,
      {
        id: nextId++,
        kind: spec.kind,
        group,
        x1: a.x,
        y1: a.y,
        x2: b.x,
        y2: b.y,
        level,
        label: label(spec, a, b),
      },
    ]
  }

  function onKeyDown(event: KeyboardEvent): void {
    if (event.key === 'Escape' && pending.value) {
      pending.value = null
      changed()
    }
  }

  onMounted(() => window.addEventListener('keydown', onKeyDown))
  onBeforeUnmount(() => window.removeEventListener('keydown', onKeyDown))

  /** A click on a measurement's label removes it. */
  function onClickAnnotation(event: Plotly.ClickAnnotationEvent): void {
    const name = (event.annotation as { name?: string } | undefined)?.name
    if (name?.startsWith(MEASURE_NAME_PREFIX)) {
      remove(Number(name.slice(MEASURE_NAME_PREFIX.length)))
    }
  }

  /**
   * Listen for clicks on measurement labels and mark the plot element while
   * measuring. Call after each Plotly.newPlot (which drops listeners);
   * calling it again on the same plot is harmless.
   */
  function bindLabelClicks(element: HTMLElement | null): void {
    plotElement = element
    markActive()
    const plot = element as unknown as {
      on?: (event: string, handler: (event: Plotly.ClickAnnotationEvent) => void) => void
      removeListener?: (event: string, handler: (event: Plotly.ClickAnnotationEvent) => void) => void
    } | null
    if (!plot?.on) return
    plot.removeListener?.('plotly_clickannotation', onClickAnnotation)
    plot.on('plotly_clickannotation', onClickAnnotation)
  }

  /**
   * Shapes and annotations drawing the measurements and the pending point.
   * Plain layout items, so they are part of the image download.
   */
  function overlay(options: MeasureOverlayOptions): MeasureOverlay {
    const shapes: Partial<Plotly.Shape>[] = []
    const annotations: Partial<Plotly.Annotations>[] = []
    if (!enabled()) return { shapes, annotations }
    const { color, background } = options
    const xref = (options.xref ?? 'x') as Plotly.Shape['xref']
    const yref = (options.yref ?? 'y') as Plotly.Shape['yref']
    const signOf = options.ySign ?? (() => 1 as const)
    const spans = measurements.value.filter((m) => m.kind === 'span')
    let yScale = options.yScale ?? 0
    if (!(yScale > 0)) {
      for (const m of spans) yScale = Math.max(yScale, Math.abs(m.y1), Math.abs(m.y2))
      if (!(yScale > 0)) yScale = 1
    }
    const gap = yScale * 0.05
    const levelStep = yScale * 0.14

    const labelBase = {
      xref,
      yref,
      showarrow: false,
      font: { size: 12, color },
      bgcolor: background,
      bordercolor: color,
      borderwidth: 1,
      borderpad: 2,
      captureevents: true,
      hovertext: 'Click to remove this measurement',
    }

    for (const m of measurements.value) {
      const name = `${MEASURE_NAME_PREFIX}${m.id}`
      if (m.kind === 'span') {
        const sign = signOf(m.group)
        const top = Math.max(sign * m.y1, sign * m.y2)
        const bracketY = top + gap + m.level * levelStep
        // A horizontal bar above the taller point with legs down to each point
        shapes.push(
          {
            type: 'line',
            name,
            xref,
            yref,
            x0: m.x1,
            x1: m.x2,
            y0: sign * bracketY,
            y1: sign * bracketY,
            line: { color, width: 1.5 },
          },
          {
            type: 'line',
            xref,
            yref,
            x0: m.x1,
            x1: m.x1,
            y0: m.y1 + sign * gap * 0.3,
            y1: sign * bracketY,
            line: { color, width: 1, dash: 'dot' },
          },
          {
            type: 'line',
            xref,
            yref,
            x0: m.x2,
            x1: m.x2,
            y0: m.y2 + sign * gap * 0.3,
            y1: sign * bracketY,
            line: { color, width: 1, dash: 'dot' },
          },
        )
        annotations.push({
          ...labelBase,
          name,
          x: (m.x1 + m.x2) / 2,
          y: sign * bracketY,
          text: m.label,
          xanchor: 'center',
          yanchor: sign > 0 ? 'bottom' : 'top',
          yshift: sign > 0 ? 2 : -2,
          // Plotly accepts a name on annotations; its typings omit it
        } as Partial<Plotly.Annotations>)
      } else {
        shapes.push(
          {
            type: 'line',
            name,
            xref,
            yref,
            x0: m.x1,
            y0: m.y1,
            x1: m.x2,
            y1: m.y2,
            line: { color, width: 1.5 },
          },
          endpoint(m.x1, m.y1, color, xref, yref, false),
          endpoint(m.x2, m.y2, color, xref, yref, false),
        )
        annotations.push({
          ...labelBase,
          name,
          x: (m.x1 + m.x2) / 2,
          y: (m.y1 + m.y2) / 2,
          text: m.label,
          align: 'left',
          xanchor: 'left',
          yanchor: 'bottom',
          xshift: 6,
          yshift: 4,
        } as Partial<Plotly.Annotations>)
      }
    }

    const first = pending.value
    if (first && first.kind === 'span') {
      // A dashed stick over the picked point
      const sign = signOf(first.group ?? DEFAULT_GROUP)
      shapes.push({
        type: 'line',
        xref,
        yref,
        x0: first.x,
        x1: first.x,
        y0: 0,
        y1: first.y + sign * gap,
        line: { color, width: 2, dash: 'dash' },
      })
    } else if (first) {
      shapes.push(endpoint(first.x, first.y, color, xref, yref, true))
    }
    return { shapes, annotations }
  }

  /**
   * The Measure toggle and the Clear button for Plotly's mode bar (none when
   * the tool is off). Mode bar buttons are left out of the image download.
   * `title` is the Measure button's tooltip; it must start with "Measure".
   */
  function modeBarButtons(
    title = 'Measure: click two points to measure the distance between them (Esc cancels)',
  ): Plotly.ModeBarButton[] {
    if (!enabled()) return []
    return [
      {
        name: 'measure',
        title,
        icon: { width: 24, height: 24, path: RULER_PATH },
        click: () => toggle(),
      },
      {
        name: 'clearMeasurements',
        title: CLEAR_TITLE,
        icon: { width: 24, height: 24, path: CLEAR_PATH },
        click: () => clear(),
      },
    ] as unknown as Plotly.ModeBarButton[]
  }

  return reactive({
    mode,
    active,
    measurements,
    pending,
    revision,
    hint,
    toggle,
    clear,
    remove,
    pick,
    setDataKey,
    bindLabelClicks,
    modeBarButtons,
    overlay,
  })
}

/** A circle of fixed pixel size around a data point (dashed while pending). */
function endpoint(
  x: number,
  y: number,
  color: string,
  xref: Plotly.Shape['xref'],
  yref: Plotly.Shape['yref'],
  isPending: boolean,
): Partial<Plotly.Shape> {
  const r = isPending ? 7 : 4
  return {
    type: 'circle',
    xref,
    yref,
    xsizemode: 'pixel',
    ysizemode: 'pixel',
    xanchor: x,
    yanchor: y,
    x0: -r,
    x1: r,
    y0: -r,
    y1: r,
    line: { color, width: isPending ? 2 : 1.5, dash: isPending ? 'dash' : 'solid' },
    fillcolor: isPending ? 'rgba(0,0,0,0)' : color,
  } as Partial<Plotly.Shape>
}

export type MeasureState = ReturnType<typeof useMeasure>
