<template>
  <div>
    <!-- As tall as the plot: a relayout that autosizes (Plotly does one when a
         box or lasso selection ends) measures this element -->
    <PlotToolbar :plot-id="id" :tools="toolbarTools" :stepper="args.stepper" />
    <div :id="id" class="clustered-heatmap-container" :style="{ minHeight: `${plotHeight}px` }"></div>
    <ColorbarLegend v-if="isDataReady" :items="legendItems" @change="setColorSpec" />
  </div>
</template>

<script lang="ts">
import { defineComponent, computed, type PropType } from 'vue'
import Plotly from '@/plotly/cartesian'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { usePlotlyScatter } from '@/composables/usePlotlyScatter'
import { clearSelectionTool, SELECTION_ACCENT, SELECTION_LAYOUT, useMultiSelect } from '@/composables/useMultiSelect'
import { TOOLBAR_HEIGHT, type PlotTool } from '@/utils/plotTools'
import PlotToolbar from './PlotToolbar.vue'
import ColorbarLegend, { type ColorbarLegendItem } from './ColorbarLegend.vue'
import { scaleStops, specToStops, type ColorStops, type ColorbarSpec } from '@/utils/colorscale'
import type { ClusteredHeatmapComponentArgs, ClusteredHeatmapData, DendrogramData } from '@/types/component'

// The figure is laid out in pixels from the width the component gets, so
// the heatmap fills it whatever the number of rows and columns, and the row
// labels, colorbar and dendrograms each keep a lane of their own.
const FONT_SIZE = 11
/** Pixels a row needs before every row label can be shown. */
const ROW_LABEL_PX = FONT_SIZE + 3
/** Longest row or column label drawn before it is cut (the full one is on hover). */
const ROW_LABEL_CHARS = 28
const COL_LABEL_CHARS = 18
const GROUP_BAR_PX = 12
const GAP_PX = 4
/** Room right of the row labels for the group key (the colorbar is below the plot). */
const KEY_LANE_PX = 76
/** Height of the colorbar row below the plot. */
const LEGEND_HEIGHT = 30
/** Low and high end of the default diverging scale (OpenMS corporate blue and orange). */
const SCALE_LOW = '#3157e9'
const SCALE_HIGH = '#ff7501'

let measureContext: CanvasRenderingContext2D | null = null

/** Width of text in pixels, in the given font. */
function textWidth(text: string, font: string): number {
  if (!measureContext && typeof document !== 'undefined') {
    measureContext = document.createElement('canvas').getContext('2d')
  }
  if (!measureContext) return text.length * FONT_SIZE * 0.6
  measureContext.font = `${FONT_SIZE}px ${font}`
  return measureContext.measureText(text).width
}

/** A label cut to at most `max` characters. */
function shorten(label: string, max: number): string {
  return label.length > max ? `${label.slice(0, max - 1)}…` : label
}

/** English ordinal suffix: 2nd, 3rd, 4th, 21st. */
function ordinal(n: number): string {
  const mod100 = n % 100
  if (mod100 >= 11 && mod100 <= 13) return 'th'
  return { 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th'
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), high)
}

/** Pixel geometry of the figure; recomputed when the width changes. */
interface Geometry {
  margin: { l: number; r: number; t: number; b: number }
  plotWidth: number
  plotHeight: number
  /** x-domain of the row dendrogram and of the heatmap, as fractions of the plot width. */
  rowDendro: [number, number]
  heatmapX: [number, number]
  /** y-domains as fractions of the plot height. */
  heatmapY: [number, number]
  groupBarY: [number, number]
  colDendroY: [number, number]
  /** Every rowStep-th row is labelled. */
  rowStep: number
  rowLabelLane: number
  colTickAngle: number
}

export default defineComponent({
  name: 'PlotlyClusteredHeatmap',
  components: { PlotToolbar, ColorbarLegend },
  props: {
    args: {
      type: Object as PropType<ClusteredHeatmapComponentArgs>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
  },
  setup(props) {
    const streamlitDataStore = useStreamlitDataStore()

    // Reuse shared theming/toolbar/resize behavior. No click-to-select or
    // zoom in this first version, so getData/interactivity are no-ops.
    const plotlyScatter = usePlotlyScatter({
      id: computed(() => `clustered-heatmap-${props.index}`),
      interactivity: computed(() => ({})),
      getData: () => [],
      title: computed(() => props.args.title),
      imageFormat: computed(() => props.args.imageFormat),
    })

    const multi = useMultiSelect(computed(() => props.args.multiSelect))

    return {
      streamlitDataStore,
      ...plotlyScatter,
      multiSelectEnabled: multi.enabled,
      selectedCount: multi.selectedCount,
      multiSelectionKey: multi.selectionKey,
      selectedSets: multi.selectedSets,
      applySelectedRows: multi.applyRows,
      clearSelection: multi.clear,
    }
  },
  data() {
    return {
      isInitialized: false as boolean,
      plotInitialized: false as boolean,
      dragmode: 'select' as string,
      removingOutline: false,
      selectModifier: 'replace' as 'replace' | 'add' | 'remove',
      /** Colors the user picked in the colorbar editor; null: the plot's own scale. */
      colorSpec: null as ColorbarSpec | null,
    }
  },
  computed: {
    /** Height of the plot below its toolbar; the frame keeps args.height. */
    plotHeight(): number {
      return (this.args.height || 500) - TOOLBAR_HEIGHT - LEGEND_HEIGHT
    },

    /** The scale drawn: the user's colors, args.colorscale, or the diverging default. */
    colorStops(): ColorStops {
      if (this.colorSpec) return specToStops(this.colorSpec, this.theme?.backgroundColor || '#ffffff')
      const ownScale = this.args.colorscale as string | ColorStops | undefined
      return ownScale ? scaleStops(ownScale, this.args.reversescale ?? true) : this.defaultColorscale
    },

    /** Value range of the scale: centred on 0 by default, the data's own range for args.colorscale. */
    zRange(): [number, number] {
      if (!this.args.colorscale) return [-this.zLimit, this.zLimit]
      let lo = Infinity
      let hi = -Infinity
      for (const row of this.zValues) {
        for (const v of row) {
          if (typeof v === 'number' && Number.isFinite(v)) {
            lo = Math.min(lo, v)
            hi = Math.max(hi, v)
          }
        }
      }
      return Number.isFinite(lo) ? [lo, hi > lo ? hi : lo + 1] : [0, 1]
    },

    legendItems(): ColorbarLegendItem[] {
      const [lo, hi] = this.zRange
      const text = (v: number) => String(Number(v.toPrecision(3)))
      return [
        {
          id: 'value',
          label: this.args.intensityLabel || 'Value',
          stops: this.colorStops,
          spec: this.colorSpec,
          low: text(lo),
          high: text(hi),
          editable: this.args.colorbarEditor !== false,
        },
      ]
    },

    toolbarTools(): PlotTool[] {
      return [
        ...(this.multiSelectEnabled ? [clearSelectionTool(() => this.clearSelection(), this.selectedCount)] : []),
        this.downloadTool(),
      ]
    },

    id(): string {
      return `clustered-heatmap-${this.index}`
    },

    matrixRows(): ClusteredHeatmapData[] {
      const data = this.streamlitDataStore.allDataForDrawing?.heatmapMatrix
      return (data as ClusteredHeatmapData[]) || []
    },

    isDataReady(): boolean {
      return Array.isArray(this.matrixRows) && this.matrixRows.length > 0
    },

    rowLabels(): string[] {
      return this.args.rowLabels || []
    },

    colLabels(): string[] {
      return this.args.colLabels || []
    },

    /** z-values for the main heatmap trace: rows x cols, in rowLabels/colLabels order. */
    zValues(): number[][] {
      if (!this.isDataReady) return []
      const idCol = this.args.idCol
      const byId = new Map(this.matrixRows.map((row) => [row[idCol], row]))
      return this.rowLabels.map((rowLabel) => {
        const row = byId.get(rowLabel)
        return this.colLabels.map((col) => (row ? (row[col] as number) : 0))
      })
    },

    hasRowDendrogram(): boolean {
      return !!this.args.rowDendrogram
    },

    hasColDendrogram(): boolean {
      return !!this.args.colDendrogram
    },

    hasGroupBar(): boolean {
      return this.args.colGroups?.some((g) => g !== null && g !== undefined) ?? false
    },

    fontFamily(): string {
      return this.theme?.font || 'sans-serif'
    },

    isDark(): boolean {
      return this.theme?.base === 'dark'
    },

    textColor(): string {
      return this.theme?.textColor || (this.isDark ? '#fafafa' : '#262730')
    },

    /** Row and column labels as drawn: cut to a readable length. */
    shortRowLabels(): string[] {
      return this.rowLabels.map((l) => shorten(String(l), ROW_LABEL_CHARS))
    },

    shortColLabels(): string[] {
      return this.colLabels.map((l) => shorten(String(l), COL_LABEL_CHARS))
    },

    uniqueGroups(): string[] {
      return Array.from(new Set((this.args.colGroups || []).filter((g): g is string => !!g)))
    },

    geometry(): Geometry {
      const width = Math.max(this.plotWidth, 280)
      const height = this.plotHeight
      const font = this.fontFamily
      const nRows = Math.max(this.rowLabels.length, 1)
      const nCols = Math.max(this.colLabels.length, 1)

      // Rows: label every row when there is room, else every rowStep-th one
      const top = this.args.title ? 44 : 12
      const xTitle = this.args.xLabel ? 22 : 0

      // Columns: horizontal labels when they fit their column, else at 45 degrees
      const colLabelWidth = Math.max(0, ...this.shortColLabels.map((l) => textWidth(l, font)))
      const rowLabelWidth = Math.max(0, ...this.shortRowLabels.map((l) => textWidth(l, font)))
      const rowLabelLane = Math.ceil(rowLabelWidth) + 14
      const left = 8
      const right = rowLabelLane + KEY_LANE_PX
      const plotWidth = Math.max(width - left - right, 80)
      const rowDendroPx = this.hasRowDendrogram ? clamp(plotWidth * 0.12, 36, 110) : 0
      const heatmapWidthPx = plotWidth - rowDendroPx - (rowDendroPx ? GAP_PX : 0)
      const colPx = heatmapWidthPx / nCols
      const colTickAngle = colLabelWidth + 6 <= colPx ? 0 : -45
      const tickBand = colTickAngle === 0 ? FONT_SIZE + 10 : Math.ceil(colLabelWidth * Math.SQRT1_2) + FONT_SIZE + 8
      const bottom = tickBand + xTitle + 8

      const plotHeight = Math.max(height - top - bottom, 80)
      const colDendroPx = this.hasColDendrogram ? clamp(plotHeight * 0.14, 32, 90) : 0
      const groupPx = this.hasGroupBar ? GROUP_BAR_PX : 0
      const above = colDendroPx + groupPx + (colDendroPx ? GAP_PX : 0) + (groupPx ? GAP_PX : 0)
      const heatmapHeightPx = plotHeight - above
      const rowStep = Math.max(1, Math.ceil(ROW_LABEL_PX / (heatmapHeightPx / nRows)))

      const fx = (px: number) => px / plotWidth
      const fy = (px: number) => px / plotHeight
      const heatmapTop = 1 - fy(above)
      const groupBottom = heatmapTop + fy(groupPx ? GAP_PX : 0)
      return {
        margin: { l: left, r: right, t: top, b: bottom },
        plotWidth,
        plotHeight,
        rowDendro: [0, fx(rowDendroPx)],
        heatmapX: [rowDendroPx ? fx(rowDendroPx + GAP_PX) : 0, 1],
        heatmapY: [0, heatmapTop],
        groupBarY: [groupBottom, groupBottom + fy(groupPx)],
        colDendroY: [1 - fy(colDendroPx), 1],
        rowStep,
        rowLabelLane,
        colTickAngle,
      }
    },

    /** Diverging scale from the theme: blue, the page colour, orange. */
    defaultColorscale(): [number, string][] {
      const middle = this.isDark ? this.theme?.secondaryBackgroundColor || '#262730' : '#ffffff'
      return [
        [0, SCALE_LOW],
        [0.5, middle],
        [1, SCALE_HIGH],
      ]
    },

    /** Largest absolute value, so the scale is centred on 0. */
    zLimit(): number {
      let limit = 0
      for (const row of this.zValues) {
        for (const v of row) {
          if (typeof v === 'number' && Number.isFinite(v)) limit = Math.max(limit, Math.abs(v))
        }
      }
      return limit || 1
    },

    /**
     * Rescale scipy dendrogram leaf coordinates (spaced 10 units apart,
     * starting at 5) to the 0..n-1 numeric axis used by the heatmap, so
     * dendrogram lines land exactly at each leaf's heatmap position.
     */
    rescaleLeafCoord(): (v: number) => number {
      return (v: number) => (v - 5) / 10
    },

    /** Build scatter line traces for a dendrogram, in (x, y) or (y, x) order. */
    buildDendrogramTraces(): (
      dendro: DendrogramData,
      xAxis: string,
      yAxis: string,
      swapXY: boolean
    ) => Plotly.Data[] {
      const rescale = this.rescaleLeafCoord
      const color = this.textColor
      return (dendro, xAxis, yAxis, swapXY) => {
        const traces: Plotly.Data[] = []
        for (let i = 0; i < dendro.icoord.length; i++) {
          const leafCoords = dendro.icoord[i].map(rescale)
          const distCoords = dendro.dcoord[i]
          const x = swapXY ? distCoords : leafCoords
          const y = swapXY ? leafCoords : distCoords
          traces.push({
            type: 'scatter',
            mode: 'lines',
            x,
            y,
            xaxis: xAxis,
            yaxis: yAxis,
            line: { color, width: 1 },
            opacity: 0.45,
            hoverinfo: 'skip',
            showlegend: false,
          } as Plotly.Data)
        }
        return traces
      }
    },

    groupBarTrace(): Plotly.Data | null {
      if (!this.hasGroupBar) return null
      const groupColors = this.args.groupColors || {}
      const colGroups = this.args.colGroups || []
      const uniqueGroups = this.uniqueGroups
      const groupToIndex = new Map(uniqueGroups.map((g, i) => [g, i]))

      const z = [colGroups.map((g) => (g && groupToIndex.has(g) ? groupToIndex.get(g)! : -1))]
      const colorscale: [number, string][] =
        uniqueGroups.length > 0
          ? uniqueGroups.flatMap((g, i) => {
              const color = groupColors[g] || '#cccccc'
              const t0 = uniqueGroups.length === 1 ? 0 : i / uniqueGroups.length
              const t1 = uniqueGroups.length === 1 ? 1 : (i + 1) / uniqueGroups.length
              return [
                [t0, color],
                [t1, color],
              ] as [number, string][]
            })
          : [[0, '#cccccc'], [1, '#cccccc']]

      return {
        type: 'heatmap',
        z,
        x: this.colLabels.map((_, i) => i),
        y: ['Group'],
        xaxis: 'x',
        yaxis: 'y4',
        colorscale,
        zmin: 0,
        zmax: Math.max(uniqueGroups.length - 1, 1),
        showscale: false,
        xgap: 1,
        customdata: [colGroups.map((g, i) => [this.colLabels[i], g ?? ''])],
        hovertemplate: '%{customdata[0]}: %{customdata[1]}<extra></extra>',
      } as unknown as Plotly.Data
    },

    data(): Plotly.Data[] {
      if (!this.isDataReady) {
        return this.getFallbackData()
      }

      const geometry = this.geometry
      const groups = this.args.colGroups || []
      const yLabel = this.args.yLabel || 'Row'
      const xLabel = this.args.xLabel || 'Column'
      const valueLabel = this.args.intensityLabel || 'Value'
      const customdata = this.rowLabels.map((row) =>
        this.colLabels.map((col, c) => [row, groups[c] ? `${col} (${groups[c]})` : col])
      )
      const traces: Plotly.Data[] = [
        {
          type: 'heatmap',
          z: this.zValues,
          x: this.colLabels.map((_, i) => i),
          y: this.rowLabels.map((_, i) => i),
          xaxis: 'x',
          yaxis: 'y',
          customdata,
          colorscale: this.colorStops,
          zmin: this.zRange[0],
          zmax: this.zRange[1],
          // The colorbar is drawn below the plot (ColorbarLegend), where it can be edited
          showscale: false,
          hovertemplate:
            `${yLabel}: <b>%{customdata[0]}</b><br>${xLabel}: %{customdata[1]}` +
            `<br>${valueLabel}: %{z:.2f}<extra></extra>`,
        } as unknown as Plotly.Data,
      ]

      if (this.args.colDendrogram) {
        traces.push(...this.buildDendrogramTraces(this.args.colDendrogram, 'x2', 'y2', false))
      }
      if (this.args.rowDendrogram) {
        traces.push(...this.buildDendrogramTraces(this.args.rowDendrogram, 'x3', 'y3', true))
      }
      const groupBar = this.groupBarTrace
      if (groupBar) {
        traces.push(groupBar)
      }
      const cells = this.selectableCells
      if (cells) {
        traces.push(cells)
      }

      return traces
    },

    /**
     * multi_select: an invisible point in every cell, which box and lasso drags
     * select (Plotly cannot select a heatmap trace). Its customdata is the row.
     */
    selectableCells(): Plotly.Data | null {
      if (!this.multiSelectEnabled) return null
      const x: number[] = []
      const y: number[] = []
      const rows: number[] = []
      for (let r = 0; r < this.rowLabels.length; r++) {
        for (let c = 0; c < this.colLabels.length; c++) {
          x.push(c)
          y.push(r)
          rows.push(r)
        }
      }
      return {
        type: 'scatter',
        mode: 'markers',
        x,
        y,
        customdata: rows,
        xaxis: 'x',
        yaxis: 'y',
        marker: { size: 6, opacity: 0 },
        selected: { marker: { opacity: 0 } },
        unselected: { marker: { opacity: 0 } },
        hoverinfo: 'none',
        showlegend: false,
      } as unknown as Plotly.Data
    },

    /** Outlines of the selected rows (runs of adjacent rows share one). */
    selectionShapes(): Partial<Plotly.Shape>[] {
      if (!this.multiSelectEnabled) return []
      void this.multiSelectionKey
      const identifier = Object.keys(this.args.multiSelect || {})[0]
      const selected = this.selectedSets[identifier]
      if (!selected || selected.size === 0) return []
      const shapes: Partial<Plotly.Shape>[] = []
      const nCols = this.colLabels.length
      let start = -1
      for (let r = 0; r <= this.rowLabels.length; r++) {
        const isSelected = r < this.rowLabels.length && selected.has(this.rowLabels[r])
        if (isSelected && start < 0) start = r
        if (!isSelected && start >= 0) {
          shapes.push({
            type: 'rect', xref: 'x', yref: 'y',
            x0: -0.5, x1: nCols - 0.5, y0: start - 0.5, y1: r - 0.5,
            line: { color: SELECTION_ACCENT, width: 2.5 },
            fillcolor: 'rgba(30, 136, 229, 0.12)',
          })
          start = -1
        }
      }
      return shapes
    },

    layout(): Partial<Plotly.Layout> {
      const nCols = this.colLabels.length
      const nRows = this.rowLabels.length
      const g = this.geometry
      const muted = { color: this.textColor, size: FONT_SIZE }
      const hidden = { showticklabels: false, showgrid: false, zeroline: false, showline: false, ticks: '' }
      const labelled = this.rowLabels.map((_, i) => i).filter((i) => i % g.rowStep === 0)

      const annotations: Partial<Plotly.Annotations>[] = []
      if (this.args.yLabel || g.rowStep > 1) {
        // Heading of the row label lane; says when not every row is labelled
        const name = this.args.yLabel || 'Rows'
        const chars = Math.max(10, Math.floor(g.rowLabelLane / 6))
        let text = shorten(`${name} (${nRows})`, chars)
        if (g.rowStep > 1) text += `<br>${shorten(`every ${g.rowStep}${ordinal(g.rowStep)} labelled`, chars)}`
        annotations.push({
          xref: 'paper', yref: 'paper', x: 1 + 6 / g.plotWidth, y: g.heatmapY[1],
          xanchor: 'left', yanchor: 'bottom', yshift: 3, showarrow: false, align: 'left',
          text, font: { ...muted, size: FONT_SIZE - 0.5 }, opacity: 0.7,
        })
      }
      if (this.hasGroupBar && this.uniqueGroups.length > 0) {
        // Group key in the lane right of the column dendrogram, wrapped to its width
        const colors = this.args.groupColors || {}
        const lines: string[] = []
        let line = ''
        let lineWidth = 0
        for (const name of this.uniqueGroups) {
          const label = shorten(name, 16)
          const width = textWidth(`■ ${label}`, this.fontFamily) + 12
          if (line && lineWidth + width > g.rowLabelLane + KEY_LANE_PX - 12) {
            lines.push(line)
            line = ''
            lineWidth = 0
          }
          line += `${line ? '&nbsp;&nbsp;' : ''}<span style="color:${colors[name] || '#cccccc'}">■</span> ${label}`
          lineWidth += width
        }
        if (line) lines.push(line)
        annotations.push({
          xref: 'paper', yref: 'paper', x: 1 + 6 / g.plotWidth, y: 1, xanchor: 'left', yanchor: 'top',
          showarrow: false, align: 'left', font: muted, text: lines.join('<br>'),
        })
      }

      const layout: Record<string, unknown> = {
        ...this.themeLayout,
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { ...(this.themeLayout.font || {}), size: FONT_SIZE },
        title: this.args.title
          ? {
              text: `<b>${this.args.title}</b>`,
              x: 0, xref: 'paper', xanchor: 'left',
              y: 1, yref: 'paper', yanchor: 'bottom', pad: { b: 12 },
              font: { size: FONT_SIZE + 4 },
            }
          : undefined,
        showlegend: false,
        height: this.plotHeight,
        margin: g.margin,
        annotations,
        hoverlabel: { font: { family: this.fontFamily, size: FONT_SIZE + 1 } },
        ...(this.multiSelectEnabled
          ? { dragmode: this.dragmode, shapes: this.selectionShapes, hovermode: 'closest', ...SELECTION_LAYOUT }
          : {}),
        xaxis: {
          ...hidden,
          domain: g.heatmapX,
          anchor: 'y',
          range: [-0.5, nCols - 0.5],
          showticklabels: true,
          tickvals: this.colLabels.map((_, i) => i),
          ticktext: this.shortColLabels,
          tickangle: g.colTickAngle,
          automargin: false,
          title: this.args.xLabel ? { text: this.args.xLabel, standoff: 6, font: { size: FONT_SIZE + 1 } } : undefined,
        },
        yaxis: {
          ...hidden,
          domain: g.heatmapY,
          anchor: 'x',
          range: [-0.5, nRows - 0.5],
          showticklabels: true,
          tickvals: labelled,
          ticktext: labelled.map((i) => this.shortRowLabels[i]),
          // Labels in the lane right of the heatmap; the dendrogram is left of it
          side: 'right',
          ticks: 'outside',
          ticklen: 4,
          tickcolor: 'rgba(0,0,0,0)',
          automargin: false,
        },
      }

      if (this.hasColDendrogram) {
        layout.xaxis2 = { ...hidden, domain: g.heatmapX, anchor: 'y2', range: [-0.5, nCols - 0.5] }
        layout.yaxis2 = { ...hidden, domain: g.colDendroY, anchor: 'x2', rangemode: 'tozero' }
      }

      if (this.hasRowDendrogram) {
        layout.xaxis3 = { ...hidden, domain: g.rowDendro, anchor: 'y3', autorange: 'reversed', rangemode: 'tozero' }
        layout.yaxis3 = { ...hidden, domain: g.heatmapY, anchor: 'x3', range: [-0.5, nRows - 0.5] }
      }

      if (this.hasGroupBar) {
        layout.yaxis4 = { ...hidden, domain: g.groupBarY, anchor: 'x' }
      }

      return layout as Partial<Plotly.Layout>
    },
  },

  watch: {
    isDataReady: {
      handler(newVal: boolean) {
        if (newVal && this.isInitialized) {
          this.renderPlot()
        }
      },
      immediate: true,
    },
    'streamlitDataStore.allDataForDrawing.heatmapMatrix': {
      handler() {
        if (this.isInitialized) {
          this.renderPlot()
        }
      },
      deep: true,
    },
    multiSelectionKey() {
      if (this.isInitialized && this.isDataReady) {
        this.renderPlot()
      }
    },
    // The layout is in pixels: lay it out again when the width changes
    plotWidth() {
      if (this.plotInitialized && this.isDataReady) {
        this.renderPlot()
      }
    },
  },

  mounted() {
    this.isInitialized = true
    this.$nextTick(() => {
      const element = document.getElementById(this.id)
      if (element && element.clientWidth > 0) this.plotWidth = element.clientWidth
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
    /** New colors from the colorbar editor (null: the plot's own scale). */
    setColorSpec(_id: string, spec: ColorbarSpec | null): void {
      this.colorSpec = spec
      if (this.plotInitialized) void this.renderPlot()
    },

    /**
     * This composite figure hand-wires 4 regions (heatmap, column
     * dendrogram, row dendrogram, group bar) via manual axis anchors
     * rather than Plotly's grid subplot system, and some axes (the
     * dendrograms' distance axes) have no fixed range. Mouse-wheel zoom
     * (scrollZoom) recomputes axis ranges on the fly and gets confused by
     * this non-standard layout, blanking out the traces. This component
     * isn't designed for interactive zooming in the first place (unlike
     * the scattergl Heatmap, which uses zoom for level-of-detail
     * downsampling), so it's disabled here rather than fixed at the
     * layout level.
     */
    getHeatmapPlotConfig(): Partial<Plotly.Config> {
      return { ...this.getPlotConfig(), scrollZoom: false }
    },

    async renderPlot(): Promise<void> {
      try {
        const element = document.getElementById(this.id)
        if (!element) {
          console.warn(`PlotlyClusteredHeatmap: DOM element with id '${this.id}' not found`)
          return
        }

        if (!this.plotInitialized) {
          await Plotly.newPlot(this.id, this.data, this.layout, this.getHeatmapPlotConfig())
          this.plotInitialized = true
          this.setupSelectHandlers()
        } else {
          await Plotly.react(this.id, this.data, this.layout, this.getHeatmapPlotConfig())
        }

        this.$nextTick(() => {
          this.updateFrameHeight()
        })
      } catch (error) {
        console.error('PlotlyClusteredHeatmap: Error rendering plot:', error)
        this.plotInitialized = false
        this.renderFallback()
      }
    },

    setupSelectHandlers(): void {
      if (!this.multiSelectEnabled) return
      const element = document.getElementById(this.id) as Plotly.PlotlyHTMLElement | null
      if (!element) return
      element.addEventListener('mousedown', (e: MouseEvent) => {
        this.selectModifier = e.shiftKey ? 'add' : 'replace'
      }, true)
      // Keep the mode picked in the mode bar across re-renders
      element.on('plotly_relayout', (eventData: Plotly.PlotRelayoutEvent) => {
        const mode = (eventData as Record<string, unknown>).dragmode
        if (typeof mode === 'string') this.dragmode = mode
      })
      element.on('plotly_selected', (eventData: Plotly.PlotSelectionEvent | undefined) => {
        if (!eventData || !eventData.points) return
        // Plotly reports the removed outline as an empty selection
        if (this.removingOutline) return
        const idCol = this.args.idCol
        const rows = new Set<number>()
        for (const point of eventData.points) {
          const row = (point as unknown as { customdata?: unknown }).customdata
          if (typeof row === 'number') rows.add(row)
        }
        const picked = Array.from(rows).map((r) => ({ [idCol]: this.rowLabels[r] }))
        if (picked.length === 0 && this.selectModifier === 'replace') {
          this.clearSelection()
        } else {
          this.applySelectedRows(picked, this.selectModifier)
        }
        // The rows are outlined; Plotly's own outline would only show the last region.
        // Removing it fires plotly_deselect, which must not clear the rows just picked.
        this.removingOutline = true
        Promise.resolve(
          Plotly.relayout(this.id, { selections: [] } as unknown as Partial<Plotly.Layout>)
        ).finally(() => {
          this.removingOutline = false
        })
      })
      element.on('plotly_deselect', () => {
        if (this.removingOutline) return
        this.clearSelection()
      })
    },

    getFallbackData(): Plotly.Data[] {
      return [
        {
          type: 'heatmap',
          z: [[0]],
          x: [0],
          y: [0],
          showscale: false,
        } as unknown as Plotly.Data,
      ]
    },

    async renderFallback(): Promise<void> {
      try {
        const fallbackLayout: Partial<Plotly.Layout> = {
          ...this.themeLayout,
          title: { text: '<b>No Data Available</b>' },
          showlegend: false,
        }
        await Plotly.newPlot(this.id, this.getFallbackData(), fallbackLayout, { staticPlot: true })
      } catch (error) {
        console.error('PlotlyClusteredHeatmap: Failed to render fallback:', error)
      }
    },
  },
})
</script>

<style scoped>
.clustered-heatmap-container {
  position: relative;
  width: 100%;
  min-height: 100px;
}
</style>
