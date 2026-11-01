<template>
  <div :id="id" class="plot-container" :class="{ bordered: args.border !== false }"></div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { Plot3DComponentArgs } from '@/types/component'

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
    maxZ(): number {
      let max = 0
      for (const s of this.series) {
        for (const z of s.z) {
          if (z !== null && z > max) max = z
        }
      }
      return max
    },
    traces(): Plotly.Data[] {
      return this.series.map(
        (s) =>
          ({
            name: s.name,
            type: 'scatter3d',
            mode: 'lines',
            x: s.x,
            y: s.y,
            z: s.z,
            line: { color: s.color },
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
      if (this.args.cameraEye) {
        scene.camera = { eye: this.args.cameraEye }
      }
      return {
        title: { text: this.args.titleBold === false ? this.title : `<b>${this.title}</b>` },
        paper_bgcolor: this.theme?.backgroundColor,
        plot_bgcolor: this.theme?.secondaryBackgroundColor,
        height: this.args.height || 800,
        font: {
          color: this.theme?.textColor,
          family: this.theme?.font,
        },
        scene: scene as Partial<Plotly.Scene>,
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
      const height = this.args.height || 800
      // react keeps the WebGL scene of the previous render; newPlot builds a new one
      // exportFormat 'png': Plotly's own download button
      const exportButtons =
        this.args.exportFormat === 'png'
          ? {}
          : {
              modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
              modeBarButtonsToAdd: [
                {
                  title: 'Download as SVG',
                  name: 'toImageSvg',
                  icon: Plotly.Icons.camera,
                  click: (plotElement: HTMLElement) => {
                    Plotly.downloadImage(plotElement, {
                      filename: this.args.svgFilename || this.title || 'plot3d',
                      height,
                      width: height,
                      format: 'svg',
                    })
                  },
                },
              ],
            }
      await Plotly.react(element, this.traces, this.layout, {
        ...exportButtons,
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
