<template>
  <div class="series-plot">
    <div v-if="views.length > 1" class="view-switch" role="tablist" :style="switchStyle">
      <button
        v-for="[value, label] in views"
        :key="value"
        type="button"
        role="tab"
        class="view-button"
        :class="{ active: value === currentView }"
        :aria-selected="value === currentView"
        @click="pickView(value)"
      >
        {{ label }}
      </button>
    </div>
    <MeasureHint v-if="measurable" :measure="measure" />
    <PlotToolbar :plot-id="id" :tools="toolbarTools" :stepper="args.stepper" />
    <div :id="id" class="plot-container"></div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
// The cartesian bundle: scatter, bar and box traces
import Plotly from '@/plotly/cartesian'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { SeriesPlotComponentArgs } from '@/types/component'
import { useMeasure, type MeasureOverlay, type MeasureSpec } from '@/composables/useMeasure'
import { axisQuantity, pointsKey } from '@/utils/measure'
import MeasureHint from './MeasureHint.vue'
import { imageFormatOf } from '@/utils/imageExport'
import { downloadTool } from '@/utils/plotlyDownload'
import { ICONS, TOOLBAR_HEIGHT, type PlotTool } from '@/utils/plotTools'
import { useLayers, type Layer } from '@/composables/useLayers'
import PlotToolbar from './PlotToolbar.vue'
import { useZoomState, withZoom, type ZoomValue } from '@/composables/useZoomState'

let plotIdCounter = 0

/** Height of the row of view buttons in pixels. */
const VIEW_SWITCH_HEIGHT = 34
/** Space of the title and the value axis around the bars of a growing plot. */
const BAR_PLOT_MARGIN = 110

export default defineComponent({
  name: 'PlotlySeries',
  components: { MeasureHint, PlotToolbar },
  props: {
    args: {
      type: Object as PropType<SeriesPlotComponentArgs>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
  },
  setup(props) {
    const streamlitDataStore = useStreamlitDataStore()
    const selectionStore = useSelectionStore()
    // Bars and boxes stand on categories: nothing to measure between them
    const measure = useMeasure(
      () => !!props.args.measure && props.args.mode !== 'bars' && props.args.mode !== 'box',
    )
    const zoom = useZoomState(() => props.args.zoomIdentifier)
    return {
      streamlitDataStore,
      selectionStore,
      measure,
      layers: useLayers(),
      zoom,
      zoomStamp: zoom.stamp,
      uniqueId: `series-plot-${++plotIdCounter}`,
    }
  },
  data() {
    return {
      drawPending: false,
      // The zoom the plot shows, kept across redraws (Plotly.newPlot resets it)
      nativeZoom: null as ZoomValue | null,
      // The view and the number of rows picked in this browser
      pickedView: null as string | null,
      pickedTop: null as number | null,
    }
  },
  computed: {
    /** [value, label] of every view, in view_names order then order of appearance. */
    views(): Array<[string, string]> {
      const column = this.args.viewColumn
      if (!column) return []
      const names = new Map<string, string>((this.args.viewNames || []).map(([k, v]) => [String(k), v]))
      const out = new Map<string, string>(names)
      for (const value of (this.columns[column] as unknown[]) || []) {
        const key = String(value)
        if (!out.has(key)) out.set(key, key)
      }
      return [...out.entries()]
    },
    /** The view shown: the state's value, else this browser's pick, else the default. */
    currentView(): string | null {
      const values = this.views.map(([value]) => value)
      if (!values.length) return null
      const identifier = this.args.viewIdentifier
      const fromState = identifier ? this.selectionStore.$state[identifier] : undefined
      for (const candidate of [fromState, this.pickedView, this.args.viewDefault]) {
        if (candidate !== undefined && candidate !== null && values.includes(String(candidate))) {
          return String(candidate)
        }
      }
      return values[0]
    },
    currentViewLabel(): string {
      const view = this.views.find(([value]) => value === this.currentView)
      return view ? view[1] : ''
    },
    topCount(): number | null {
      const choices = this.args.topChoices
      if (!choices || !choices.length) return null
      if (this.pickedTop !== null && choices.includes(this.pickedTop)) return this.pickedTop
      return this.args.topDefault ?? choices[Math.floor(choices.length / 2)]
    },
    /** Rows drawn: those of the view shown, up to the first `topCount` x values. */
    shownRows(): number[] {
      const xs = (this.columns[this.args.xColumn] as unknown[]) || []
      const viewColumn = this.args.viewColumn
      const viewValues = viewColumn ? (this.columns[viewColumn] as unknown[]) || [] : []
      const view = this.currentView
      const limit = this.topCount
      const kept = new Set<string>()
      const rows: number[] = []
      for (let i = 0; i < xs.length; i++) {
        if (view !== null && String(viewValues[i]) !== view) continue
        if (limit !== null) {
          const x = String(xs[i])
          if (!kept.has(x)) {
            if (kept.size >= limit) continue
            kept.add(x)
          }
        }
        rows.push(i)
      }
      return rows
    },
    /** Categories drawn (distinct x values of the rows shown). */
    shownCategories(): number {
      const xs = (this.columns[this.args.xColumn] as unknown[]) || []
      return new Set(this.shownRows.map((i) => String(xs[i]))).size
    },
    /** Height of the whole component: grows with the bars when bar_height is set. */
    totalHeight(): number {
      const base = this.args.height || 400
      const barHeight = this.args.barHeight
      if (!barHeight || !this.horizontal) return base
      const extra = this.views.length > 1 ? VIEW_SWITCH_HEIGHT : 0
      return Math.max(base, BAR_PLOT_MARGIN + TOOLBAR_HEIGHT + extra + barHeight * this.shownCategories)
    },
    plotHeight(): number {
      return this.totalHeight - TOOLBAR_HEIGHT - (this.views.length > 1 ? VIEW_SWITCH_HEIGHT : 0)
    },
    shownTitle(): string | undefined {
      const title = this.args.title
      if (!title) return undefined
      return title.split('{view}').join(this.currentViewLabel)
    },
    switchStyle(): Record<string, string> {
      const theme = this.theme
      return {
        '--vs-text': theme?.textColor || '#262730',
        '--vs-background': theme?.backgroundColor || '#ffffff',
        '--vs-accent': theme?.primaryColor || '#1436b8',
        '--vs-font': theme?.font || 'sans-serif',
        height: `${VIEW_SWITCH_HEIGHT}px`,
      }
    },
    measurable(): boolean {
      return !!this.args.measure && this.args.mode !== 'bars' && this.args.mode !== 'box'
    },
    horizontal(): boolean {
      return this.args.orientation === 'h'
    },
    toolbarTools(): PlotTool[] {
      const choices = this.args.topChoices || []
      const top: PlotTool[] = choices.length && this.topCount !== null
        ? [{
            id: 'top',
            group: 'show',
            icon: ICONS.number,
            label: 'Rows shown',
            short: `Top ${this.topCount}`,
            help: 'how many of the first rows the plot shows',
            menu: [{
              kind: 'choice',
              label: 'Show the first',
              options: choices.map((n) => ({ value: String(n), label: String(n) })),
              value: String(this.topCount),
              select: (value: string) => { this.pickedTop = Number(value) },
            }],
            run: () => {},
          }]
        : []
      return [
        ...top,
        ...(this.measurable ? this.measure.tools(this.measureTitle) : []),
        ...this.layers.tool(this.layerList, 'Series'),
        downloadTool({
          plotId: this.id,
          format: () => imageFormatOf(this.args.imageFormat),
          filename: () => this.args.svgFilename || this.args.title || 'plot',
          height: this.totalHeight,
        }),
      ]
    },
    argsKey(): string {
      return JSON.stringify(this.args)
    },
    id(): string {
      return this.uniqueId
    },
    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },
    columns(): Record<string, unknown[]> {
      return (this.streamlitDataStore.allDataForDrawing?.plotData as Record<string, unknown[]>) || {}
    },
    /** True when some position holds points of two or more series. */
    sharedPositions(): boolean {
      const seen = new Map<unknown, string>()
      for (const group of this.series) {
        for (const x of group.x) {
          const owner = seen.get(x)
          if (owner !== undefined && owner !== group.key) return true
          seen.set(x, group.key)
        }
      }
      return false
    },
    /** Points grouped by series, in series_names order then order of appearance. */
    series(): Array<{ key: string; name: string; x: number[]; y: number[]; rows: number[]; text: string[] }> {
      const hoverColumn = this.args.hoverColumn
      const hover = hoverColumn ? (this.columns[hoverColumn] as unknown[]) || [] : []
      const xs = (this.columns[this.args.xColumn] as number[]) || []
      const ys = (this.columns[this.args.yColumn] as number[]) || []
      const seriesColumn = this.args.seriesColumn
      const seriesValues = seriesColumn ? (this.columns[seriesColumn] as unknown[]) || [] : []
      const names = new Map<string, string>((this.args.seriesNames || []).map(([k, v]) => [String(k), v]))

      const groups = new Map<string, { key: string; name: string; x: number[]; y: number[]; rows: number[]; text: string[] }>()
      for (const key of names.keys()) {
        groups.set(key, { key, name: names.get(key) as string, x: [], y: [], rows: [], text: [] })
      }
      for (const i of this.shownRows) {
        const key = seriesColumn ? String(seriesValues[i]) : ''
        if (!groups.has(key)) {
          groups.set(key, { key, name: names.get(key) ?? key, x: [], y: [], rows: [], text: [] })
        }
        const group = groups.get(key)!
        group.x.push(xs[i])
        group.y.push(ys[i])
        group.rows.push(i)
        if (hoverColumn) group.text.push(String(hover[i] ?? ''))
      }
      return [...groups.values()]
    },
    /** The series the toolbar shows or hides. */
    layerList(): Layer[] {
      const colors = this.args.seriesColors || {}
      return this.series.map((s) => ({ key: s.key, label: s.name, color: colors[s.key] }))
    },
    traces(): Plotly.Data[] {
      const colors = this.args.seriesColors || {}
      return this.series.filter((s) => this.layers.visible(s.key)).map((s) => {
        const mode = this.args.mode || 'lines+markers'
        // Horizontal: the categories (x column) on the vertical axis
        const [x, y] = this.horizontal ? [s.y, s.x] : [s.x, s.y]
        const trace: Record<string, unknown> = { x, y, name: s.name }
        if (mode === 'bars') {
          trace.type = 'bar'
          trace.orientation = this.horizontal ? 'h' : 'v'
        } else if (mode === 'box') {
          trace.type = 'box'
          trace.orientation = this.horizontal ? 'h' : 'v'
          trace.boxpoints = 'outliers'
        } else {
          trace.type = 'scatter'
          trace.mode = mode
        }
        if (this.args.hoverColumn) {
          trace.text = s.text
          trace.hovertemplate = '%{text}<br>%{x}, %{y}<extra>%{fullData.name}</extra>'
          // Hover text only: a bar would otherwise print it on itself
          if (mode === 'bars') trace.textposition = 'none'
        }
        const color = colors[s.key]
        if (color) {
          trace.marker = { color }
          trace.line = { color }
          if (mode === 'box') trace.fillcolor = color + '55'
        }
        return trace as Plotly.Data
      })
    },
    /** x positions of the points selected through this plot's interactivity
     * identifiers, also when the selection was made in another component. */
    selectedX(): number[] {
      const interactivity = this.args.interactivity || {}
      const xs = (this.columns[this.args.xColumn] as number[]) || []
      const out: number[] = []
      for (const [identifier, column] of Object.entries(interactivity)) {
        const selected = this.selectionStore.$state[identifier]
        const values = this.columns[column] as unknown[] | undefined
        if (selected === undefined || selected === null || !values) continue
        for (let i = 0; i < values.length; i++) {
          if (values[i] === selected) out.push(xs[i])
        }
      }
      return out
    },
    /** Differences along x only: a series has no residue masses to match. */
    measureSpec(): MeasureSpec {
      return { kind: 'span', xQuantity: axisQuantity(this.args.xLabel, 'x') }
    },
    measureTitle(): string {
      return `click two points for their ${this.measureSpec.xQuantity} difference (Esc cancels)`
    },
    /** Identity of the plotted points: other data drops the measurements. */
    measureKey(): string {
      return pointsKey(this.columns[this.args.xColumn], this.columns[this.args.yColumn])
    },
    /** Brackets of the measurements, spaced by the tallest point. */
    measureOverlay(): MeasureOverlay {
      const ys = (this.columns[this.args.yColumn] as number[]) || []
      let yScale = 0
      for (const y of ys) {
        if (Number.isFinite(y) && Math.abs(y) > yScale) yScale = Math.abs(y)
      }
      return this.measure.overlay({
        color: this.theme?.textColor || '#262730',
        background: this.theme?.backgroundColor || 'white',
        yScale,
      })
    },
    layout(): Partial<Plotly.Layout> {
      const line = { color: '#d62728', width: 1.5, dash: 'dash' }
      const selectionShapes = this.selectedX.map((x) =>
        this.horizontal
          ? { type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: x, y1: x, line }
          : { type: 'line', xref: 'x', yref: 'paper', x0: x, x1: x, y0: 0, y1: 1, line },
      ) as Partial<Plotly.Shape>[]
      const mode = this.args.mode || 'lines+markers'
      // The axis along the x column (positions or categories) and the value axis
      const positionAxis: Record<string, unknown> = {
        title: this.args.xLabel ? { text: this.args.xLabel } : undefined,
        showgrid: false,
        automargin: true,
      }
      const valueAxis: Record<string, unknown> = {
        title: this.args.yLabel ? { text: this.args.yLabel } : undefined,
        showgrid: true,
        rangemode: this.args.yRangeMode || 'nonnegative',
        fixedrange: !!this.args.fixedYRange,
        automargin: true,
      }
      // Horizontal categories read from the top, in the order of the data
      if (this.horizontal) positionAxis.autorange = 'reversed'
      const xaxis = this.horizontal ? valueAxis : positionAxis
      const yaxis = this.horizontal ? positionAxis : valueAxis
      return {
        shapes: [...selectionShapes, ...this.measureOverlay.shapes],
        annotations: this.measureOverlay.annotations,
        title: this.shownTitle ? { text: `<b>${this.shownTitle}</b>` } : undefined,
        showlegend: this.args.showLegend !== false,
        height: this.plotHeight,
        xaxis,
        yaxis,
        // Side by side only where series share a position, else full width
        ...(mode === 'bars' ? { barmode: this.sharedPositions ? 'group' : 'overlay' } : {}),
        ...(mode === 'box' ? { boxmode: this.sharedPositions ? 'group' : 'overlay' } : {}),
        paper_bgcolor: this.theme?.backgroundColor || 'white',
        plot_bgcolor: this.theme?.backgroundColor || 'white',
        font: {
          color: this.theme?.textColor || 'black',
          family: this.theme?.font || 'Arial',
          ...(this.args.font || {}),
        },
      }
    },
  },
  watch: {
    // A series shown or hidden from the toolbar
    'layers.state.hidden'() {
      this.requestRender()
    },
    // A zoom set from Python (a saved view opened)
    zoomStamp() {
      const incoming = this.zoom.incoming()
      if (incoming === undefined) return
      this.nativeZoom = incoming
      const element = document.getElementById(this.id)
      if (element && (element as unknown as { _fullLayout?: unknown })._fullLayout) {
        void Plotly.relayout(element, this.zoom.layoutFor(incoming))
      }
    },
    measureKey: {
      handler(key: string) {
        this.measure.setDataKey(key)
      },
      immediate: true,
    },
    // Measurements added or removed: redraw the overlay only. The height goes
    // along, or the relayout autosizes the figure to its container
    'measure.revision'() {
      const element = document.getElementById(this.id)
      if (!element || !(element as unknown as { _fullLayout?: unknown })._fullLayout) return
      void Plotly.relayout(element, {
        shapes: this.layout.shapes,
        annotations: this.layout.annotations,
        height: this.layout.height,
      })
    },
    'streamlitDataStore.allDataForDrawing.plotData': {
      handler() {
        this.requestRender()
      },
      deep: true,
    },
    selectedX(next: number[], previous: number[]) {
      if (JSON.stringify(next) !== JSON.stringify(previous)) this.requestRender()
    },
    // Another view or number of rows: a fresh drawing of its own extent
    shownRows(next: number[], previous: number[]) {
      if (next.length === previous.length && next.every((v, i) => v === previous[i])) return
      this.nativeZoom = null
      this.requestRender()
    },
    // By value: the arguments arrive as a new object on every rerun
    argsKey() {
      this.requestRender()
    },
  },
  mounted() {
    this.nativeZoom = this.zoom.incoming() ?? null
    this.requestRender()
  },
  methods: {
    /** Draw once per tick: one update often changes several watched values
     * (the data and the selection), and each drawing costs a full Plotly render. */
    requestRender(): void {
      if (this.drawPending) return
      this.drawPending = true
      this.$nextTick(() => {
        this.drawPending = false
        this.renderPlot()
      })
    },
    async renderPlot(): Promise<void> {
      const element = document.getElementById(this.id)
      if (!element) return
      await Plotly.newPlot(element, this.traces, withZoom(this.layout, this.nativeZoom), {
        modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
        displaylogo: false,
        responsive: true,
      })
      const plotElement = element as unknown as {
        on: (event: string, handler: (data: { points: Array<{ curveNumber: number; pointIndex: number }> }) => void) => void
      }
      plotElement.on('plotly_click', (eventData) => this.onClick(eventData))
      this.zoom.bindNative(element as unknown as Plotly.PlotlyHTMLElement, (z) => { this.nativeZoom = z })
      this.measure.bindLabelClicks(element)
      this.$nextTick(() => Streamlit.setFrameHeight())
    },
    pickView(value: string): void {
      this.pickedView = value
      const identifier = this.args.viewIdentifier
      // Skip no-op writes (see ProteinSequenceView)
      if (identifier && this.selectionStore.$state[identifier] !== value) {
        this.selectionStore.updateSelection(identifier, value)
      }
    },
    onClick(eventData: { points: Array<{ curveNumber: number; pointIndex: number }> }): void {
      // In measure mode a click picks a point to measure, not a selection
      if (this.measure.active) {
        const point = eventData.points?.[0]
        const s = point ? this.series[point.curveNumber] : undefined
        if (point && s && point.pointIndex < s.x.length) {
          this.measure.pick({ x: s.x[point.pointIndex], y: s.y[point.pointIndex] }, this.measureSpec)
        }
        return
      }
      const interactivity = this.args.interactivity || {}
      if (Object.keys(interactivity).length === 0 || !eventData.points?.length) return
      const point = eventData.points[0]
      // A box stands for many rows: a click on it picks none
      if (this.args.mode === 'box') return
      const row = this.series[point.curveNumber]?.rows[point.pointIndex]
      if (row === undefined) return
      for (const [identifier, column] of Object.entries(interactivity)) {
        const values = this.columns[column] as unknown[] | undefined
        // Skip no-op writes (see ProteinSequenceView)
        if (values && this.selectionStore.$state[identifier] !== values[row]) {
          this.selectionStore.updateSelection(identifier, values[row])
        }
      }
    },
  },
})
</script>

<style scoped>
.series-plot {
  position: relative;
}

.plot-container {
  width: 100%;
}

.view-switch {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: nowrap;
  overflow-x: auto;
  font-family: var(--vs-font);
  font-size: 13px;
}

.view-button {
  height: 28px;
  padding: 0 12px;
  border: 1px solid color-mix(in srgb, var(--vs-text) 16%, transparent);
  border-radius: 999px;
  background: var(--vs-background);
  color: color-mix(in srgb, var(--vs-text) 72%, transparent);
  font: inherit;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
}

.view-button:hover {
  background: color-mix(in srgb, var(--vs-text) 7%, var(--vs-background));
  color: var(--vs-text);
}

.view-button:focus-visible {
  outline: 2px solid var(--vs-accent);
  outline-offset: 1px;
}

.view-button.active {
  background: color-mix(in srgb, var(--vs-accent) 13%, var(--vs-background));
  border-color: var(--vs-accent);
  color: var(--vs-accent);
}
</style>
