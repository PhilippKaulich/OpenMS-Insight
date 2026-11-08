<template>
  <div class="plot3d">
    <PlotToolbar :plot-id="id" :tools="toolbarTools" />
    <div :id="id" class="plot-container" :class="{ bordered: args.border !== false }"></div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from '@/plotly/gl3d'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { Plot3DComponentArgs } from '@/types/component'
import { imageFormatOf } from '@/utils/imageExport'
import { downloadTool } from '@/utils/plotlyDownload'
import { TOOLBAR_HEIGHT, type PlotTool } from '@/utils/plotTools'
import PlotToolbar from './PlotToolbar.vue'

// Floor the stems and trace starts drop to. Far below zero so the vertical
// segment always reaches the bottom of the z range, which starts at 0.
const STEM_FLOOR = -100000
const TRACE_FLOOR = -1000

let plotIdCounter = 0

interface SeriesPoints {
  key: string
  name: string
  color: string
  x: (number | null)[]
  y: (number | null)[]
  z: (number | null)[]
}

export default defineComponent({
  name: 'Plotly3D',
  components: { PlotToolbar },
  props: {
    args: {
      type: Object as PropType<Plot3DComponentArgs>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
  },
  setup() {
    const streamlitDataStore = useStreamlitDataStore()
    const selectionStore = useSelectionStore()
    return { streamlitDataStore, selectionStore, uniqueId: `plot3d-${++plotIdCounter}` }
  },
  data() {
    return {
      drawPending: false,
    }
  },
  computed: {
    toolbarTools(): PlotTool[] {
      const height = this.args.height || 800
      return [
        downloadTool({
          plotId: this.id,
          format: () => imageFormatOf(this.args.imageFormat),
          filename: () => this.args.svgFilename || this.title || 'plot3d',
          width: height,
          height,
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
    title(): string {
      for (const [identifier, title] of this.args.selectionTitles || []) {
        const value = this.selectionStore.$state[identifier]
        if (value !== undefined && value !== null) return title
      }
      return this.args.title || ''
    },
    seriesName(): (key: string) => string {
      const names = new Map<string, string>((this.args.seriesNames || []).map(([k, v]) => [String(k), v]))
      const template = this.args.seriesNameTemplate
      return (key: string) => names.get(key) ?? (template ? template.replace('{}', key) : key)
    },
    series(): SeriesPoints[] {
      const xs = (this.columns[this.args.xColumn] as number[]) || []
      const ys = (this.columns[this.args.yColumn] as number[]) || []
      const zs = (this.columns[this.args.zColumn] as number[]) || []
      const seriesColumn = this.args.seriesColumn
      const seriesValues = seriesColumn ? (this.columns[seriesColumn] as unknown[]) || [] : []
      const traceColumn = this.args.traceColumn
      const traceValues = traceColumn ? (this.columns[traceColumn] as unknown[]) || [] : []
      const colors = this.args.seriesColors || {}
      const stems = this.args.mode !== 'lines'

      // Named series are listed (even without points of their own) whenever
      // there is anything to draw
      const groups = new Map<string, SeriesPoints>()
      for (const [k] of xs.length > 0 ? this.args.seriesNames || [] : []) {
        const key = String(k)
        groups.set(key, { key, name: this.seriesName(key), color: colors[key] || this.args.color, x: [], y: [], z: [] })
      }
      // Last trace seen per series, to start a new polyline when it changes
      const lastTrace = new Map<string, unknown>()

      for (let i = 0; i < xs.length; i++) {
        const key = seriesColumn ? String(seriesValues[i]) : ''
        if (!groups.has(key)) {
          groups.set(key, { key, name: this.seriesName(key), color: colors[key] || this.args.color, x: [], y: [], z: [] })
        }
        const group = groups.get(key)!
        const x = xs[i]
        const y = ys[i]
        const z = zs[i]

        if (stems) {
          // Points at or below the floor of the z range draw nothing
          if (!(z > 0)) continue
          group.x.push(x, x, x)
          group.y.push(y, y, y)
          group.z.push(STEM_FLOOR, z, STEM_FLOOR)
          continue
        }

        const trace = traceColumn ? traceValues[i] : undefined
        if (!lastTrace.has(key) || lastTrace.get(key) !== trace) {
          if (lastTrace.has(key)) {
            // Break the line between two traces of the same series
            group.x.push(null)
            group.y.push(null)
            group.z.push(null)
          }
          // Each trace rises from the floor at its first point
          group.x.push(x)
          group.y.push(y)
          group.z.push(TRACE_FLOOR)
          lastTrace.set(key, trace)
        }
        group.x.push(x)
        group.y.push(y)
        group.z.push(z)
      }
      return [...groups.values()]
    },
    /** Points of the selected value of a `highlight` identifier, sent apart by Python */
    highlightSeries(): SeriesPoints | null {
      if (!this.args.highlight) return null
      const points = this.streamlitDataStore.allDataForDrawing?.highlightData as
        | { x: number[]; y: number[]; z: number[] }
        | undefined
      const group: SeriesPoints = {
        key: '__highlight__',
        name: this.args.highlightName || 'Selected',
        color: this.args.highlightColor || '#ff7501',
        x: [],
        y: [],
        z: [],
      }
      const xs = points?.x || []
      const ys = points?.y || []
      const zs = points?.z || []
      const stems = this.args.mode !== 'lines'
      for (let i = 0; i < xs.length; i++) {
        if (stems) {
          if (!(zs[i] > 0)) continue
          group.x.push(xs[i], xs[i], xs[i])
          group.y.push(ys[i], ys[i], ys[i])
          group.z.push(STEM_FLOOR, zs[i], STEM_FLOOR)
        } else {
          group.x.push(xs[i])
          group.y.push(ys[i])
          group.z.push(zs[i])
        }
      }
      return group.x.length > 0 ? group : null
    },
    allSeries(): SeriesPoints[] {
      // The highlighted points last, so they are drawn on top
      return this.highlightSeries ? [...this.series, this.highlightSeries] : this.series
    },
    maxZ(): number {
      let max = 0
      for (const s of this.allSeries) {
        for (const z of s.z) {
          if (z !== null && z > max) max = z
        }
      }
      return max
    },
    traces(): Plotly.Data[] {
      return this.allSeries.map(
        (s) =>
          ({
            name: s.name,
            type: 'scatter3d',
            mode: 'lines',
            x: s.x,
            y: s.y,
            z: s.z,
            line: { color: s.color, width: s.key === '__highlight__' ? 4 : 2 },
            connectgaps: false,
          }) as Plotly.Data
      )
    },
    layout(): Partial<Plotly.Layout> {
      const yaxis: Record<string, unknown> = { title: { text: this.args.yLabel } }
      if (this.args.yDtick !== undefined && this.args.yDtick !== null) {
        yaxis.dtick = this.args.yDtick
        yaxis.tick0 = 0
      }
      const scene: Record<string, unknown> = {
        xaxis: { title: { text: this.args.xLabel } },
        yaxis,
        zaxis: { title: { text: this.args.zLabel }, range: [0, this.maxZ] },
      }
      if (this.args.cameraEye || this.args.cameraCenter) {
        scene.camera = {
          ...(this.args.cameraEye ? { eye: this.args.cameraEye } : {}),
          ...(this.args.cameraCenter ? { center: this.args.cameraCenter } : {}),
        }
      }
      if (this.args.aspectRatio) {
        scene.aspectmode = 'manual'
        scene.aspectratio = this.args.aspectRatio
      }
      // Plotly's default margins (80 px on every side) leave a wide empty frame
      // around a 3D scene; keep room for the title only
      const margin = { l: 0, r: 0, b: 0, t: this.title ? 50 : 10 }
      return {
        title: { text: this.args.titleBold === false ? this.title : `<b>${this.title}</b>` },
        paper_bgcolor: this.theme?.backgroundColor,
        plot_bgcolor: this.theme?.secondaryBackgroundColor,
        height: (this.args.height || 800) - TOOLBAR_HEIGHT,
        font: {
          color: this.theme?.textColor,
          family: this.theme?.font,
        },
        scene: scene as Partial<Plotly.Scene>,
        margin,
        showlegend: this.args.showLegend !== false,
      }
    },
  },
  watch: {
    'streamlitDataStore.allDataForDrawing.plotData': {
      handler() {
        this.requestRender()
      },
      deep: true,
    },
    'streamlitDataStore.allDataForDrawing.highlightData': {
      handler() {
        this.requestRender()
      },
      deep: true,
    },
    title() {
      this.requestRender()
    },
    // By value: the arguments arrive as a new object on every rerun
    argsKey() {
      this.requestRender()
    },
  },
  mounted() {
    this.requestRender()
  },
  methods: {
    /** Draw once per update: one update often changes several watched values
     * (the data and the selection), and each drawing costs a full Plotly render.
     * Drawn in a task of its own, so the other views of the page, which share
     * this thread and receive the same update, are not held up by the scene. */
    requestRender(): void {
      if (this.drawPending) return
      this.drawPending = true
      setTimeout(() => {
        this.drawPending = false
        this.renderPlot()
      }, 0)
    },
    async renderPlot(): Promise<void> {
      const element = document.getElementById(this.id)
      if (!element) return
      // react keeps the WebGL scene of the previous render; newPlot builds a new one
      await Plotly.react(element, this.traces, this.layout, {
        modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
        displaylogo: false,
        responsive: true,
        // No "double-click to isolate" notice on a legend click
        showTips: false,
      } as Partial<Plotly.Config>)
      this.$nextTick(() => Streamlit.setFrameHeight())
    },
  },
})
</script>

<style scoped>
.plot-container {
  width: 100%;
  box-sizing: border-box;
}
.plot-container.bordered {
  border: 1px solid #cccccc;
}
</style>
