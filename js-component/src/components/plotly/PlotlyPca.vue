<template>
  <div class="pca-plot">
    <MeasureHint v-if="args.measure" :measure="measure" />
    <div :id="id" class="pca-container"></div>
  </div>
</template>

<script lang="ts">
import { defineComponent, computed, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { usePlotlyScatter } from '@/composables/usePlotlyScatter'
import type { PCAPlotComponentArgs, PCAData } from '@/types/component'
import { useMeasure, type MeasureOverlay, type MeasureSpec } from '@/composables/useMeasure'
import { axisQuantity, pointsKey } from '@/utils/measure'
import MeasureHint from './MeasureHint.vue'

/** Default qualitative palette, shared with PlotlyHeatmap's categorical mode. */
const DEFAULT_GROUP_COLORS = [
  '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
  '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
]

/** Chi-square critical value, 2 degrees of freedom, p = 0.95. */
const CHI2_95 = 5.991

export interface GroupPoints {
  x: number[]
  y: number[]
  text: string[]
  indices: number[]
}

/**
 * Compute a 95% confidence ellipse for a 2D point cloud from the
 * eigen-decomposition of its covariance matrix. Returns null when there
 * are too few points to estimate a covariance matrix.
 */
function computeEllipse(xs: number[], ys: number[], nPoints = 60): { x: number[]; y: number[] } | null {
  const n = xs.length
  if (n < 3) return null

  const meanX = xs.reduce((a, b) => a + b, 0) / n
  const meanY = ys.reduce((a, b) => a + b, 0) / n

  let sxx = 0
  let syy = 0
  let sxy = 0
  for (let i = 0; i < n; i++) {
    const dx = xs[i] - meanX
    const dy = ys[i] - meanY
    sxx += dx * dx
    syy += dy * dy
    sxy += dx * dy
  }
  sxx /= n - 1
  syy /= n - 1
  sxy /= n - 1

  // Eigen-decomposition of the 2x2 symmetric covariance matrix
  const trace = sxx + syy
  const det = sxx * syy - sxy * sxy
  const disc = Math.sqrt(Math.max((trace * trace) / 4 - det, 0))
  const eig1 = trace / 2 + disc
  const eig2 = trace / 2 - disc

  // Orientation angle from the eigenvector of the larger eigenvalue
  let angle: number
  if (Math.abs(sxy) > 1e-12) {
    angle = Math.atan2(eig1 - sxx, sxy)
  } else {
    angle = sxx >= syy ? 0 : Math.PI / 2
  }

  const a = Math.sqrt(Math.max(eig1, 0) * CHI2_95)
  const b = Math.sqrt(Math.max(eig2, 0) * CHI2_95)
  const cosA = Math.cos(angle)
  const sinA = Math.sin(angle)

  const x: number[] = []
  const y: number[] = []
  for (let i = 0; i <= nPoints; i++) {
    const t = (2 * Math.PI * i) / nPoints
    const ex = a * Math.cos(t)
    const ey = b * Math.sin(t)
    x.push(meanX + ex * cosA - ey * sinA)
    y.push(meanY + ex * sinA + ey * cosA)
  }

  return { x, y }
}

export default defineComponent({
  name: 'PlotlyPca',
  components: { MeasureHint },
  props: {
    args: {
      type: Object as PropType<PCAPlotComponentArgs>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
  },
  setup(props) {
    const streamlitDataStore = useStreamlitDataStore()

    // Use shared Plotly scatter composable (resize, theme, image download).
    // Click handling is NOT taken from here - see setupPcaClickHandler().
    const plotlyScatter = usePlotlyScatter({
      id: computed(() => `pca-${props.index}`),
      interactivity: computed(() => props.args.interactivity || {}),
      getData: () => {
        const data = streamlitDataStore.allDataForDrawing?.pcaData
        return (data as PCAData[]) || []
      },
      title: computed(() => props.args.title),
      imageFormat: computed(() => props.args.imageFormat),
    })

    return {
      streamlitDataStore,
      ...plotlyScatter,
      measure: useMeasure(() => !!props.args.measure),
    }
  },
  data() {
    return {
      isInitialized: false as boolean,
    }
  },
  computed: {
    id(): string {
      return `pca-${this.index}`
    },

    /**
     * Get PCA data from Python.
     */
    pcaData(): PCAData[] {
      const data = this.streamlitDataStore.allDataForDrawing?.pcaData
      return (data as PCAData[]) || []
    },

    /**
     * Check if data is ready for rendering.
     */
    isDataReady(): boolean {
      return Array.isArray(this.pcaData) && this.pcaData.length > 0
    },

    showEllipses(): boolean {
      return this.args.showEllipses !== false
    },

    /**
     * Group data points by their group column value, preserving each
     * point's ORIGINAL index into pcaData (in `indices`). Each group is
     * rendered as its own Plotly trace (for a proper legend), which means
     * Plotly's built-in `pointIndex` on click events is only relative to
     * that trace - not to the full pcaData array. We stash the original
     * index in `customdata` instead and read it back in
     * setupPcaClickHandler(), rather than reusing the shared composable's
     * click handler (which indexes getData() with the trace-relative
     * pointIndex and would pick the wrong row for any non-first group).
     */
    groupedPoints(): Map<string, GroupPoints> {
      const groups = new Map<string, GroupPoints>()
      if (!this.isDataReady) return groups

      const xCol = this.args.xColumn
      const yCol = this.args.yColumn
      const groupCol = this.args.groupColumn
      const sampleCol = this.args.sampleIdColumn

      this.pcaData.forEach((row, idx) => {
        const x = Number(row[xCol])
        const y = Number(row[yCol])
        if (!Number.isFinite(x) || !Number.isFinite(y)) return

        const groupKey = groupCol ? String(row[groupCol] ?? 'Unknown') : 'All samples'
        const sampleLabel = sampleCol ? String(row[sampleCol] ?? '') : ''
        const hoverText = sampleLabel
          ? `<b>${sampleLabel}</b><br>${xCol}: ${x.toFixed(2)}<br>${yCol}: ${y.toFixed(2)}`
          : `${xCol}: ${x.toFixed(2)}<br>${yCol}: ${y.toFixed(2)}`

        if (!groups.has(groupKey)) {
          groups.set(groupKey, { x: [], y: [], text: [], indices: [] })
        }
        const bucket = groups.get(groupKey)!
        bucket.x.push(x)
        bucket.y.push(y)
        bucket.text.push(hoverText)
        bucket.indices.push(idx)
      })

      return groups
    },

    /** Group keys in first-appearance order (stable legend/color order). */
    orderedGroupKeys(): string[] {
      return Array.from(this.groupedPoints.keys())
    },

    getGroupColor(): (group: string) => string {
      const customColors = this.args.groupColors || {}
      const keys = this.orderedGroupKeys
      return (group: string): string => {
        if (customColors[group]) return customColors[group]
        const idx = keys.indexOf(group)
        return DEFAULT_GROUP_COLORS[idx % DEFAULT_GROUP_COLORS.length]
      }
    },

    /**
     * Build Plotly data traces: one marker trace per group, plus an
     * optional (legend-hidden) confidence-ellipse trace per group.
     */
    plotData(): Plotly.Data[] {
      if (!this.isDataReady) {
        return this.getFallbackData()
      }

      const traces: Plotly.Data[] = []
      const getColor = this.getGroupColor

      for (const groupKey of this.orderedGroupKeys) {
        const points = this.groupedPoints.get(groupKey)!
        const color = getColor(groupKey)

        if (this.showEllipses) {
          const ellipse = computeEllipse(points.x, points.y)
          if (ellipse) {
            traces.push({
              type: 'scatter',
              mode: 'lines',
              x: ellipse.x,
              y: ellipse.y,
              line: { color, width: 1.5, dash: 'dot' },
              fill: 'toself',
              fillcolor: color,
              opacity: 0.12,
              showlegend: false,
              hoverinfo: 'skip',
            } as Plotly.Data)
          }
        }

        traces.push({
          type: 'scattergl',
          name: groupKey,
          x: points.x,
          y: points.y,
          mode: 'markers',
          marker: {
            color,
            size: 9,
            line: { color: 'rgba(0, 0, 0, 0.3)', width: 1 },
          },
          text: points.text,
          hoverinfo: 'text',
          customdata: points.indices,
        })
      }

      return traces
    },

    /**
     * Axis range computed from the actual sample points only (NOT the
     * confidence ellipses). With small group sizes (n=3-4) the covariance
     * ellipse is a statistically unstable, often wildly elongated estimate;
     * letting Plotly auto-range over every trace (ellipses included) zooms
     * the plot out to fit them, leaving the real points crammed into a
     * corner surrounded by empty space. Fixing the range to the point cloud
     * (plus padding) keeps the zoom level tied to the data that actually
     * matters; oversized ellipses simply extend past the visible area.
     */
    pointsRange(): { x: [number, number]; y: [number, number] } | null {
      if (!this.isDataReady) return null

      let xMin = Infinity
      let xMax = -Infinity
      let yMin = Infinity
      let yMax = -Infinity

      for (const points of this.groupedPoints.values()) {
        for (const x of points.x) {
          if (x < xMin) xMin = x
          if (x > xMax) xMax = x
        }
        for (const y of points.y) {
          if (y < yMin) yMin = y
          if (y > yMax) yMax = y
        }
      }

      if (![xMin, xMax, yMin, yMax].every(Number.isFinite)) return null

      // 10% padding on each side; fall back to a fixed pad when all points
      // share the same coordinate (zero-width range).
      const xPad = (xMax - xMin) * 0.1 || 1
      const yPad = (yMax - yMin) * 0.1 || 1

      return {
        x: [xMin - xPad, xMax + xPad],
        y: [yMin - yPad, yMax + yPad],
      }
    },

    /** Two points, labelled with their differences along both components. */
    measureSpec(): MeasureSpec {
      return {
        kind: 'points',
        xQuantity: axisQuantity(this.args.xLabel, this.args.xColumn || 'x'),
        yQuantity: axisQuantity(this.args.yLabel, this.args.yColumn || 'y'),
      }
    },

    /** Identity of the plotted points: other data drops the measurements. */
    measureKey(): string {
      const x = this.args.xColumn
      const y = this.args.yColumn
      return `${x}|${y}|${pointsKey(
        this.pcaData.map((row) => row[x]),
        this.pcaData.map((row) => row[y]),
      )}`
    },

    /** Lines of the measurements. */
    measureOverlay(): MeasureOverlay {
      return this.measure.overlay({
        color: this.theme?.textColor || '#262730',
        background: this.theme?.backgroundColor || 'white',
      })
    },

    /**
     * Build Plotly layout.
     */
    layout(): Partial<Plotly.Layout> {
      const range = this.pointsRange

      return {
        ...this.themeLayout,
        title: this.args.title ? { text: `<b>${this.args.title}</b>` } : undefined,
        showlegend: true,
        legend: {
          orientation: 'h',
          yanchor: 'bottom',
          y: 1.02,
          xanchor: 'right',
          x: 1,
        },
        height: this.args.height || 400,
        xaxis: {
          title: { text: this.args.xLabel || this.args.xColumn },
          zeroline: true,
          zerolinecolor: 'rgba(150, 150, 150, 0.4)',
          zerolinewidth: 1,
          ...(range ? { range: range.x } : {}),
        },
        yaxis: {
          title: { text: this.args.yLabel || this.args.yColumn },
          zeroline: true,
          zerolinecolor: 'rgba(150, 150, 150, 0.4)',
          zerolinewidth: 1,
          ...(range ? { range: range.y } : {}),
        },
        margin: {
          l: 60,
          r: 20,
          t: this.args.title ? 80 : 40,
          b: 60,
        },
        shapes: this.measureOverlay.shapes,
        annotations: this.measureOverlay.annotations,
      }
    },
  },

  watch: {
    measureKey: {
      handler(key: string) {
        this.measure.setDataKey(key)
      },
      immediate: true,
    },

    // Measurements added or removed: redraw the overlay only. The height goes
    // along, or the relayout autosizes the figure to its container
    'measure.revision'() {
      if (!this.isInitialized || !this.isDataReady) return
      const element = document.getElementById(this.id)
      if (!element || !(element as unknown as { _fullLayout?: unknown })._fullLayout) return
      void Plotly.relayout(element, {
        shapes: this.layout.shapes,
        annotations: this.layout.annotations,
        height: this.layout.height,
      })
    },

    isDataReady: {
      handler(newVal: boolean) {
        if (newVal && this.isInitialized) {
          this.renderPlot()
        }
      },
      immediate: true,
    },

    'streamlitDataStore.allDataForDrawing.pcaData': {
      handler() {
        if (this.isInitialized) {
          this.renderPlot()
        }
      },
      deep: true,
    },
  },

  mounted() {
    this.isInitialized = true
    this.$nextTick(() => {
      if (this.isDataReady) {
        this.renderPlot()
      }
      this.setupResizeObserver()
    })
  },

  beforeUnmount() {
    this.cleanupResizeObserver()
  },

  methods: {
    async renderPlot(): Promise<void> {
      try {
        const element = document.getElementById(this.id)
        if (!element) {
          console.warn(`PlotlyPca: DOM element with id '${this.id}' not found`)
          return
        }

        await Plotly.newPlot(this.id, this.plotData, this.layout, this.getPlotConfig(this.measure.modeBarButtons()))
        this.setupPcaClickHandler()
        this.measure.bindLabelClicks(element)

        // Update Streamlit iframe height after plot is rendered
        this.$nextTick(() => {
          this.updateFrameHeight()
        })
      } catch (error) {
        console.error('PlotlyPca: Error rendering plot:', error)
        this.renderFallback()
      }
    },

    /**
     * Custom click handler. Does NOT use the shared composable's
     * setupClickHandler() - see the note on groupedPoints() for why:
     * points are split across per-group traces, so we read the original
     * pcaData index back from `customdata` rather than the trace-relative
     * `pointIndex`.
     */
    setupPcaClickHandler(): void {
      const plotElement = document.getElementById(this.id) as Plotly.PlotlyHTMLElement | null
      if (!plotElement) return

      plotElement.on('plotly_click', (eventData: Plotly.PlotMouseEvent) => {
        // In measure mode a click picks a point to measure, not a selection
        const clicked = eventData.points?.[0]
        if (clicked && this.measure.pick({ x: Number(clicked.x), y: Number(clicked.y) }, this.measureSpec)) {
          return
        }
        const interactivityMap = this.args.interactivity || {}
        if (Object.keys(interactivityMap).length === 0) return
        if (!eventData.points || eventData.points.length === 0) return

        const originalIndex = eventData.points[0].customdata as number | undefined
        if (originalIndex === undefined) return

        const rowData = this.pcaData[originalIndex]
        if (!rowData) return

        for (const [identifier, column] of Object.entries(interactivityMap)) {
          const value = rowData[column]
          if (value !== undefined) {
            this.selectionStore.updateSelection(identifier, value)
          }
        }
      })
    },

    getFallbackData(): Plotly.Data[] {
      return [
        {
          type: 'scattergl',
          x: [0],
          y: [0],
          mode: 'markers',
          marker: { color: 'grey' },
          name: 'No Data',
        },
      ]
    },

    async renderFallback(): Promise<void> {
      try {
        const fallbackLayout: Partial<Plotly.Layout> = {
          ...this.themeLayout,
          title: { text: '<b>No Data Available</b>' },
          showlegend: false,
          xaxis: { title: { text: this.args.xLabel || 'PC1' } },
          yaxis: { title: { text: this.args.yLabel || 'PC2' } },
        }

        await Plotly.newPlot(this.id, this.getFallbackData(), fallbackLayout, {
          staticPlot: true,
        })
      } catch (error) {
        console.error('PlotlyPca: Failed to render fallback:', error)
      }
    },
  },
})
</script>

<style scoped>
.pca-plot {
  position: relative;
}

.pca-container {
  position: relative;
  width: 100%;
  min-height: 100px;
}
</style>
