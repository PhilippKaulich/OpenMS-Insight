/**
 * The tools of a plot, as the plot toolbar (PlotToolbar.vue) shows them.
 *
 * Every Plotly component lists its own tools (measure, labels, show/hide
 * toggles, download, ...) as `PlotTool`s; the toolbar adds Plotly's own
 * navigation buttons (zoom, pan, select, reset) itself. On a wide panel the
 * toolbar shows the tools as labelled groups above the plot; on a narrow one
 * it keeps the tools that are on and Reset, and puts the rest in a menu.
 */

/** Height of the toolbar row in pixels; a component takes it from its plot's height. */
export const TOOLBAR_HEIGHT = 36

/** Where a tool sits: its group in the toolbar and its section in the menu. */
export type ToolGroup = 'view' | 'annotate' | 'show' | 'export'

export const GROUP_ORDER: ToolGroup[] = ['view', 'annotate', 'show', 'export']

export const GROUP_LABELS: Record<ToolGroup, string> = {
  view: 'View',
  annotate: 'Annotate',
  show: 'Show',
  export: 'Download',
}

/** An icon: a path in a 24 x 24 box, or the inner markup of an SVG with its viewBox. */
export type ToolIcon = string | { viewBox: string; markup: string }

export interface PlotTool {
  id: string
  group: ToolGroup
  icon: ToolIcon
  /** Name in the menu and first part of the tooltip, e.g. "Measure". */
  label: string
  /** Name on the toolbar button; absent: the button shows only its icon. */
  short?: string
  /** Tooltip after the label, e.g. what a click does next. */
  help?: string
  /** A mode or switch that is on. */
  active?: boolean
  /** Things the tool made (measurements, labels), shown beside its name. */
  count?: number
  /** Removes what the tool made; shown as × on its button while count > 0. */
  clear?: { label: string; run: () => void }
  run: () => void
}

/** Icons of the tools (Material Design, 24 x 24). */
export const ICONS = {
  ruler:
    'M21 6H3c-1.1 0-2 .9-2 2v8c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm0 10H3V8h2v4h2V8h2v4h2V8h2v4h2V8h2v4h2V8h2v8z',
  tag: 'M21.41 11.58l-9-9C12.05 2.22 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58.55 0 1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41 0-.55-.23-1.06-.59-1.42zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7z',
  number:
    'M20.5 10L21 8h-4l1-4h-2l-1 4h-4l1-4h-2L9 8H5l-.5 2h4l-1 4h-4L3 16h4l-1 4h2l1-4h4l-1 4h2l1-4h4l.5-2h-4l1-4h4zm-7 4h-4l1-4h4l-1 4z',
  pin: 'M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
  more: 'M6 10c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm12 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm-6 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  check: 'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z',
  comment:
    'M21.99 4c0-1.1-.89-2-1.99-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h14l4 4-.01-18zM18 14H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z',
  fragments: 'M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z',
  peaks: 'M5 20h2V10H5v10zm4 0h2V4H9v16zm4 0h2v-7h-2v7zm4 0h2v-12h-2v12z',
  colorbar: 'M5 3h5v18H5V3zm2 2v14h1V5H7zm6 1h6v2h-6v-2zm0 5h6v2h-6v-2zm0 5h6v2h-6v-2z',
  deselect:
    'M3 5h2V3c-1.1 0-2 .9-2 2zm0 8h2v-2H3v2zm4 8h2v-2H7v2zM3 9h2V7H3v2zm10-6h-2v2h2V3zm6 0v2h2c0-1.1-.9-2-2-2zM5 21v-2H3c0 1.1.9 2 2 2zm-2-4h2v-2H3v2zM9 3H7v2h2V3zm2 18h2v-2h-2v2zm8-8h2v-2h-2v2zm0 8c1.1 0 2-.9 2-2h-2v2zm0-12h2V7h-2v2zm0 8h2v-2h-2v2zm-4 4h2v-2h-2v2zm0-16h2V3h-2v2z',
} as const

/** Plotly's own mode bar buttons the toolbar takes over: their title there and here. */
const PLOTLY_BUTTONS: Record<string, { label: string; short?: string; order: number; keep?: boolean }> = {
  'dragmode:zoom': { label: 'Box zoom', order: 0 },
  'dragmode:pan': { label: 'Pan', order: 1 },
  'dragmode:select': { label: 'Box select', order: 2 },
  'dragmode:lasso': { label: 'Lasso select', order: 3 },
  'scene.dragmode:orbit': { label: 'Orbit', order: 0 },
  'scene.dragmode:turntable': { label: 'Turntable', order: 1 },
  'scene.dragmode:zoom': { label: 'Zoom', order: 2 },
  'scene.dragmode:pan': { label: 'Pan', order: 3 },
  'zoom:in': { label: 'Zoom in', order: 4 },
  'zoom:out': { label: 'Zoom out', order: 5 },
  'zoom:auto': { label: 'Autoscale', order: 6 },
  'zoom:reset': { label: 'Reset axes', order: 7, keep: true },
  'resetLastSave:': { label: 'Reset camera', order: 7, keep: true },
  'resetDefault:': { label: 'Reset camera', order: 7, keep: true },
}

/** A Plotly button the toolbar shows: the tool, and whether it stays on a narrow toolbar. */
export interface PlotlyTool extends PlotTool {
  order: number
  keep: boolean
}

/**
 * Plotly's navigation buttons of the plot in `element`, read from its (hidden)
 * mode bar. A click clicks Plotly's own button, so zoom, pan and reset behave
 * exactly as Plotly's do; `active` follows Plotly's highlighted drag mode.
 */
export function plotlyTools(element: HTMLElement | null): PlotlyTool[] {
  if (!element) return []
  const tools: PlotlyTool[] = []
  const seen = new Set<string>()
  element.querySelectorAll<HTMLElement>('.modebar-btn').forEach((button) => {
    const key = `${button.getAttribute('data-attr') ?? ''}:${button.getAttribute('data-val') ?? ''}`
    const known = PLOTLY_BUTTONS[key]
    if (!known || seen.has(known.label)) return
    seen.add(known.label)
    const svg = button.querySelector('svg')
    tools.push({
      id: `plotly-${key}`,
      group: 'view',
      label: known.label,
      icon: {
        viewBox: svg?.getAttribute('viewBox') ?? '0 0 24 24',
        markup: svg?.innerHTML ?? '',
      },
      active: button.classList.contains('active'),
      run: () => button.click(),
      order: known.order,
      keep: !!known.keep,
    })
  })
  return tools.sort((a, b) => a.order - b.order)
}

/** Tooltip of a tool: its name, then what it does. */
export function toolTitle(tool: PlotTool): string {
  return tool.help ? `${tool.label}: ${tool.help}` : tool.label
}
