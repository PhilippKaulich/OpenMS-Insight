/**
 * Your own text labels on peaks (`peak_labels` on the Python side). Used by
 * the spectrum views, LinePlot and MirrorPlot.
 *
 * The "Label peaks" button in Plotly's mode bar (`modeBarButtons()`) switches
 * clicks from selecting to labelling; a second button removes every label of
 * the spectrum shown. In label mode a click on a peak opens a small text box
 * at the peak (PeakLabelEditor): Enter keeps the text, Esc closes the box.
 * Clicking one of your labels opens it again to change the text; an empty
 * text removes the label.
 *
 * Labels are plain Plotly annotations with an arrow to their peak (see
 * `overlay()`), so the image download includes them. They are kept per
 * spectrum for as long as the plot is on the page: `setDataKey()` switches to
 * the labels of the data now plotted, and switching back shows the earlier
 * labels again.
 *
 * With label mode off nothing here reacts to clicks, so selection works as it
 * does without the tool.
 */

import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import type Plotly from 'plotly.js-dist-min'

/** Annotation names of peak labels start with this. */
export const PEAK_LABEL_NAME_PREFIX = 'peak-label-'

/** A labelled peak. `group` is a mirror plot's half ('top' or 'bottom'). */
export interface PeakLabel {
  id: number
  x: number
  y: number
  group: string
  text: string
}

/** The label being written or changed in the text box. */
export interface PeakLabelDraft {
  /** The label being changed; absent for a new one. */
  id?: number
  x: number
  y: number
  group: string
  text: string
}

export interface PeakLabelOverlayOptions {
  /** Arrow and text colour. */
  color: string
  /** Label background. */
  background: string
  /** Direction a group's labels sit in: -1 for a mirror plot's lower half. */
  ySign?: (group: string) => 1 | -1
}

const DEFAULT_GROUP = ''
/** Longest label text kept. */
export const MAX_LABEL_LENGTH = 80

/** Mode bar titles; the first also styles the active state. */
const LABEL_TITLE_PREFIX = 'Label peaks'
const CLEAR_TITLE = 'Remove peak labels'
/** Class on the plot element while label mode is on. */
const ACTIVE_CLASS = 'peak-label-active'

// A tag, and a tag crossed out (Material icons, 24 x 24)
const TAG_PATH =
  'M21.41 11.58l-9-9C12.05 2.22 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58.55 0 1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41 0-.55-.23-1.06-.59-1.42zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7z'
const CLEAR_PATH =
  'M21.41 11.58 12.41 2.58C12.05 2.22 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l1.3 1.3L2.1 15.5l1.4 1.4L20.5 3.9l-1.4-1.4-3.2 3.2zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7zm6.09 14.42c.36.36.86.58 1.41.58s1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41 0-.55-.23-1.06-.59-1.42l-1.84-1.84-9.83 9.83z'

let styleInstalled = false

/** The highlighted "Label peaks" button while label mode is on (once per page). */
function installStyle(): void {
  if (styleInstalled || typeof document === 'undefined') return
  styleInstalled = true
  const style = document.createElement('style')
  style.textContent =
    `.${ACTIVE_CLASS} .modebar-btn[data-title^="${LABEL_TITLE_PREFIX}"] path` +
    ' { fill: #ff4b4b !important; }' +
    `.${ACTIVE_CLASS} .modebar-btn[data-title^="${LABEL_TITLE_PREFIX}"]` +
    ' { opacity: 1 !important; }'
  document.head.appendChild(style)
}

/** Text as kept: trimmed, one line, at most MAX_LABEL_LENGTH characters. */
export function cleanLabelText(text: string): string {
  return text.replace(/\s+/g, ' ').trim().slice(0, MAX_LABEL_LENGTH)
}

/** Plotly annotation text is HTML-like; show what was typed. */
function escapeText(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export function usePeakLabels(enabled: () => boolean) {
  const mode = ref(false)
  /** Labels per data key, so going back to a spectrum shows its labels again. */
  const byKey = reactive(new Map<string, PeakLabel[]>())
  const dataKey = ref('')
  const draft = ref<PeakLabelDraft | null>(null)
  /** Changes whenever what is drawn changes; components redraw on it. */
  const revision = ref(0)
  let nextId = 1
  /** The plot element last drawn, which carries the active class. */
  let plotElement: HTMLElement | null = null
  installStyle()

  function markActive(): void {
    plotElement?.classList.toggle(ACTIVE_CLASS, mode.value && enabled())
  }
  watch(mode, markActive)

  const active = computed(() => enabled() && mode.value)
  const labels = computed<PeakLabel[]>(() => byKey.get(dataKey.value) ?? [])

  const hint = computed(() => {
    if (!mode.value) return ''
    if (draft.value) return 'Labelling: type a label, Enter keeps it, Esc closes'
    if (labels.value.length > 0) return 'Labelling: click a peak, or a label to change it'
    return 'Labelling: click a peak to label it'
  })

  function changed(): void {
    revision.value += 1
  }

  function setLabels(next: PeakLabel[]): void {
    if (next.length > 0) byKey.set(dataKey.value, next)
    else byKey.delete(dataKey.value)
    changed()
  }

  function toggle(): void {
    mode.value = !mode.value
    if (!mode.value && draft.value) {
      draft.value = null
      changed()
    }
  }

  /** Leave label mode (another tool was switched on). */
  function stop(): void {
    if (mode.value) toggle()
  }

  function clear(): void {
    draft.value = null
    if (labels.value.length === 0) {
      changed()
      return
    }
    setLabels([])
  }

  /** Show the labels kept for the data now plotted. */
  function setDataKey(key: string): void {
    if (key === dataKey.value) return
    dataKey.value = key
    draft.value = null
    changed()
  }

  /**
   * A click in label mode: open the text box for this peak, or for its label
   * if it has one. Returns false when label mode is off, so the caller
   * handles the click as usual.
   */
  function pick(point: { x: number; y: number; group?: string }): boolean {
    if (!active.value) return false
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return true
    const group = point.group ?? DEFAULT_GROUP
    const existing = labels.value.find((l) => l.group === group && l.x === point.x)
    draft.value = existing ? { ...existing } : { x: point.x, y: point.y, group, text: '' }
    changed()
    return true
  }

  /** Open the text box for a label (a click on it). */
  function edit(id: number): void {
    const label = labels.value.find((l) => l.id === id)
    if (!label) return
    draft.value = { ...label }
    changed()
  }

  /** Keep the text box's text: add, change, or (empty) remove the label. */
  function commit(text: string): void {
    const current = draft.value
    if (!current) return
    draft.value = null
    const clean = cleanLabelText(text)
    const others = labels.value.filter((l) =>
      current.id !== undefined
        ? l.id !== current.id
        : !(l.group === current.group && l.x === current.x),
    )
    if (!clean) {
      setLabels(others)
      return
    }
    const id = current.id ?? nextId++
    setLabels([...others, { id, x: current.x, y: current.y, group: current.group, text: clean }])
  }

  function cancel(): void {
    if (!draft.value) return
    draft.value = null
    changed()
  }

  function onKeyDown(event: KeyboardEvent): void {
    if (event.key === 'Escape' && draft.value) cancel()
  }

  onMounted(() => window.addEventListener('keydown', onKeyDown))
  onBeforeUnmount(() => window.removeEventListener('keydown', onKeyDown))

  /** In label mode a click on one of your labels opens it for changing. */
  function onClickAnnotation(event: Plotly.ClickAnnotationEvent): void {
    if (!active.value) return
    const name = (event.annotation as { name?: string } | undefined)?.name
    if (name?.startsWith(PEAK_LABEL_NAME_PREFIX)) {
      edit(Number(name.slice(PEAK_LABEL_NAME_PREFIX.length)))
    }
  }

  /**
   * Listen for clicks on labels and mark the plot element while labelling.
   * Call after each Plotly.newPlot (which drops listeners); calling it again
   * on the same plot is harmless.
   */
  function bindLabelClicks(element: HTMLElement | null): void {
    plotElement = element
    markActive()
    const plot = element as unknown as {
      on?: (event: string, handler: (event: Plotly.ClickAnnotationEvent) => void) => void
      removeListener?: (
        event: string,
        handler: (event: Plotly.ClickAnnotationEvent) => void,
      ) => void
    } | null
    if (!plot?.on) return
    plot.removeListener?.('plotly_clickannotation', onClickAnnotation)
    plot.on('plotly_clickannotation', onClickAnnotation)
  }

  /**
   * The labels as annotations with an arrow to their peak. Plain layout
   * items, so they are part of the image download.
   */
  function overlay(options: PeakLabelOverlayOptions): Partial<Plotly.Annotations>[] {
    if (!enabled()) return []
    const { color, background } = options
    const signOf = options.ySign ?? (() => 1 as const)
    return labels.value.map((label) => {
      const sign = signOf(label.group)
      return {
        name: `${PEAK_LABEL_NAME_PREFIX}${label.id}`,
        x: label.x,
        y: label.y,
        xref: 'x',
        yref: 'y',
        text: escapeText(label.text),
        showarrow: true,
        arrowhead: 0,
        arrowwidth: 1,
        arrowcolor: color,
        // Up and to the right, so a peak's own annotation above it stays readable
        ax: 22,
        ay: -26 * sign,
        xanchor: 'left',
        font: { size: 12, color },
        bgcolor: background,
        bordercolor: color,
        borderwidth: 1,
        borderpad: 2,
        captureevents: true,
        hovertext: 'Your label (in label mode, click to change it)',
        // Plotly accepts a name on annotations; its typings omit it
      } as Partial<Plotly.Annotations>
    })
  }

  /**
   * The label toggle and the remove button for Plotly's mode bar (none when
   * the tool is off). Mode bar buttons are left out of the image download.
   */
  function modeBarButtons(): Plotly.ModeBarButton[] {
    if (!enabled()) return []
    return [
      {
        name: 'labelPeaks',
        title: `${LABEL_TITLE_PREFIX}: click a peak to add your own label`,
        icon: { width: 24, height: 24, path: TAG_PATH },
        click: () => toggle(),
      },
      {
        name: 'clearPeakLabels',
        title: CLEAR_TITLE,
        icon: { width: 24, height: 24, path: CLEAR_PATH },
        click: () => clear(),
      },
    ] as unknown as Plotly.ModeBarButton[]
  }

  return reactive({
    mode,
    active,
    labels,
    draft,
    revision,
    hint,
    toggle,
    stop,
    clear,
    pick,
    edit,
    commit,
    cancel,
    setDataKey,
    bindLabelClicks,
    modeBarButtons,
    overlay,
  })
}

export type PeakLabelState = ReturnType<typeof usePeakLabels>

/**
 * Pixel position of a data point within `container` (an ancestor of the
 * Plotly element), for placing the text box; null before the plot is drawn.
 */
export function plotPointPosition(
  plotElement: HTMLElement | null,
  container: HTMLElement | null,
  x: number,
  y: number,
): { left: number; top: number } | null {
  const layout = (
    plotElement as unknown as {
      _fullLayout?: {
        _size?: { l: number; t: number }
        xaxis?: { l2p?: (v: number) => number }
        yaxis?: { l2p?: (v: number) => number }
      }
    } | null
  )?._fullLayout
  if (!plotElement || !container || !layout?._size || !layout.xaxis?.l2p || !layout.yaxis?.l2p) {
    return null
  }
  const plotRect = plotElement.getBoundingClientRect()
  const containerRect = container.getBoundingClientRect()
  const left = plotRect.left - containerRect.left + layout._size.l + layout.xaxis.l2p(x)
  const top = plotRect.top - containerRect.top + layout._size.t + layout.yaxis.l2p(y)
  return Number.isFinite(left) && Number.isFinite(top) ? { left, top } : null
}
