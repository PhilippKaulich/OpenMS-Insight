<template>
  <div class="series-plot">
    <MeasureHint v-if="args.measure" :measure="measure" />
    <PlotToolbar :plot-id="id" :tools="toolbarTools" :stepper="args.stepper" />
    <div :id="id" class="plot-container"></div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from '@/plotly/basic'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { SeriesPlotComponentArgs } from '@/types/component'
import { useMeasure, type MeasureOverlay, type MeasureSpec } from '@/composables/useMeasure'
import { axisQuantity, pointsKey } from '@/utils/measure'
import MeasureHint from './MeasureHint.vue'
import { imageFormatOf } from '@/utils/imageExport'
import { downloadTool } from '@/utils/plotlyDownload'
import { TOOLBAR_HEIGHT, type PlotTool } from '@/utils/plotTools'
import { useLayers, type Layer } from '@/composables/useLayers'
import PlotToolbar from './PlotToolbar.vue'
import { useZoomState, withZoom, type ZoomValue } from '@/composables/useZoomState'

let plotIdCounter = 0

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
    const measure = useMeasure(() => !!props.args.measure)
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
    }
  },
  computed: {
    toolbarTools(): PlotTool[] {
      return [
        ...this.measure.tools(this.measureTitle),
        ...this.layers.tool(this.layerList, 'Series'),
        downloadTool({
          plotId: this.id,
          format: () => imageFormatOf(this.args.imageFormat),
          filename: () => this.args.svgFilename || this.args.title || 'plot',
          height: this.args.height || 400,
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
      for (let i = 0; i < xs.length; i++) {
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
        const trace: Record<string, unknown> = {
          x: s.x,
          y: s.y,
          mode: this.args.mode || 'lines+markers',
          type: 'scatter',
          name: s.name,
        }
        if (this.args.hoverColumn) {
          trace.text = s.text
          trace.hovertemplate = '%{text}<br>%{x}, %{y}<extra>%{fullData.name}</extra>'
        }
        const color = colors[s.key]
        if (color) {
          trace.marker = { color }
          trace.line = { color }
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
      const selectionShapes = this.selectedX.map((x) => ({
          type: 'line',
          xref: 'x',
          yref: 'paper',
          x0: x,
          x1: x,
          y0: 0,
          y1: 1,
          line: { color: '#d62728', width: 1.5, dash: 'dash' },
        })) as Partial<Plotly.Shape>[]
      return {
        shapes: [...selectionShapes, ...this.measureOverlay.shapes],
        annotations: this.measureOverlay.annotations,
        title: this.args.title ? { text: `<b>${this.args.title}</b>` } : undefined,
        showlegend: this.args.showLegend !== false,
        height: (this.args.height || 400) - TOOLBAR_HEIGHT,
        xaxis: {
          title: this.args.xLabel ? { text: this.args.xLabel } : undefined,
          showgrid: false,
        },
        yaxis: {
          title: this.args.yLabel ? { text: this.args.yLabel } : undefined,
          showgrid: true,
          rangemode: this.args.yRangeMode || 'nonnegative',
          fixedrange: !!this.args.fixedYRange,
        },
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
</style>
