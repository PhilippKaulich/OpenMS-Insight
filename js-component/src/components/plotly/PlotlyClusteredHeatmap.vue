<template>
  <div>
    <!-- As tall as the plot: a relayout that autosizes (Plotly does one when a
         box or lasso selection ends) measures this element -->
    <div :id="id" class="clustered-heatmap-container" :style="{ minHeight: `${args.height || 500}px` }"></div>
  </div>
</template>

<script lang="ts">
import { defineComponent, computed, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { usePlotlyScatter } from '@/composables/usePlotlyScatter'
import { clearSelectionButton, SELECTION_ACCENT, SELECTION_LAYOUT, useMultiSelect } from '@/composables/useMultiSelect'
import type { ClusteredHeatmapComponentArgs, ClusteredHeatmapData, DendrogramData } from '@/types/component'

// Layout fractions for the 4 regions of the composite figure.
const ROW_DENDRO_WIDTH = 0.14
const GROUP_BAR_HEIGHT = 0.015
const COL_DENDRO_HEIGHT = 0.13
const GAP = 0.01
// The heatmap's own domain stops short of x=1, reserving a dedicated lane
// to the right (from HEATMAP_RIGHT to 1) for row labels + axis title, with
// the colorbar positioned further out still, past that lane, so none of
// the three fight over the same space.
const HEATMAP_RIGHT = 0.8

export default defineComponent({
  name: 'PlotlyClusteredHeatmap',
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
    }
  },
  computed: {
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

    /** Top of the main heatmap's y-domain; shrinks to make room for whichever
     * of the column dendrogram / group bar are actually present. */
    heatmapTop(): number {
      let top = 1
      if (this.hasColDendrogram) top -= COL_DENDRO_HEIGHT + GAP
      if (this.hasGroupBar) top -= GROUP_BAR_HEIGHT + GAP
      return top
    },

    heatmapLeft(): number {
      return this.hasRowDendrogram ? ROW_DENDRO_WIDTH + GAP : 0
    },

    heatmapRight(): number {
      return HEATMAP_RIGHT
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
            line: { color: '#888', width: 1 },
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
      const uniqueGroups = Array.from(new Set(colGroups.filter((g): g is string => !!g)))
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
        hoverinfo: 'skip',
      } as unknown as Plotly.Data
    },

    data(): Plotly.Data[] {
      if (!this.isDataReady) {
        return this.getFallbackData()
      }

      const traces: Plotly.Data[] = [
        {
          type: 'heatmap',
          z: this.zValues,
          x: this.colLabels.map((_, i) => i),
          y: this.rowLabels.map((_, i) => i),
          xaxis: 'x',
          yaxis: 'y',
          colorscale: this.args.colorscale || 'RdBu',
          reversescale: this.args.reversescale ?? true,
          // Vertical colorbar, offset from the row-label lane by a FIXED
          // PIXEL gap (xpad), not a domain/paper fraction. Fractions are
          // relative to the total figure width, which shrinks on a
          // narrower monitor/window (via `responsive: true`), while the
          // row labels' automargin-reserved width stays a constant pixel
          // amount - a fraction-based offset would drift into the labels
          // on narrower screens, which is exactly what xpad avoids.
          colorbar: {
            title: { text: this.args.intensityLabel || 'Value' },
            xpad: 130,
            len: 0.7,
            thickness: 15,
          },
          hovertemplate: '%{x}, %{y}: %{z}<extra></extra>',
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
      const heatmapTop = this.heatmapTop
      const heatmapLeft = this.heatmapLeft

      const layout: Record<string, unknown> = {
        ...this.themeLayout,
        title: this.args.title ? { text: `<b>${this.args.title}</b>` } : undefined,
        showlegend: false,
        height: this.args.height || 500,
        // The heatmap's own domain stops at heatmapRight, leaving a
        // dedicated lane (heatmapRight..1) for row labels + axis title,
        // with the colorbar positioned further out still (see its `x`
        // above) - each gets its own space instead of fighting over the
        // same fixed margin.
        margin: { l: 40, r: 200, t: this.args.title ? 60 : 20, b: 80 },
        ...(this.multiSelectEnabled
          ? { dragmode: this.dragmode, shapes: this.selectionShapes, hovermode: 'closest', ...SELECTION_LAYOUT }
          : {}),
        xaxis: {
          domain: [heatmapLeft, this.heatmapRight],
          anchor: 'y',
          range: [-0.5, nCols - 0.5],
          tickvals: this.colLabels.map((_, i) => i),
          ticktext: this.colLabels,
          title: this.args.xLabel ? { text: this.args.xLabel } : undefined,
        },
        yaxis: {
          domain: [0, heatmapTop],
          anchor: 'x',
          range: [-0.5, nRows - 0.5],
          tickvals: this.rowLabels.map((_, i) => i),
          ticktext: this.rowLabels,
          // Row labels on the right, in the dedicated lane after
          // heatmapRight, so they don't overlap the row dendrogram (which
          // stays on the left) or the colorbar (further right still).
          // automargin lets Plotly grow the margin as needed to fit both
          // the tick labels and the axis title without them overlapping.
          side: 'right',
          automargin: true,
          title: this.args.yLabel ? { text: this.args.yLabel, standoff: 30 } : undefined,
        },
      }

      if (this.hasColDendrogram) {
        layout.xaxis2 = {
          domain: [heatmapLeft, this.heatmapRight],
          anchor: 'y2',
          range: [-0.5, nCols - 0.5],
          showticklabels: false,
          showgrid: false,
          zeroline: false,
        }
        layout.yaxis2 = {
          domain: [1 - COL_DENDRO_HEIGHT, 1],
          anchor: 'x2',
          showticklabels: false,
          showgrid: false,
          zeroline: false,
        }
      }

      if (this.hasRowDendrogram) {
        layout.xaxis3 = {
          domain: [0, ROW_DENDRO_WIDTH],
          anchor: 'y3',
          autorange: 'reversed',
          showticklabels: false,
          showgrid: false,
          zeroline: false,
        }
        layout.yaxis3 = {
          domain: [0, heatmapTop],
          anchor: 'x3',
          range: [-0.5, nRows - 0.5],
          showticklabels: false,
          showgrid: false,
          zeroline: false,
        }
      }

      if (this.hasGroupBar) {
        layout.yaxis4 = {
          domain: [heatmapTop + GAP, heatmapTop + GAP + GROUP_BAR_HEIGHT],
          anchor: 'x',
          showticklabels: false,
          showgrid: false,
          zeroline: false,
        }
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
      const buttons = this.multiSelectEnabled ? [clearSelectionButton(() => this.clearSelection())] : []
      return { ...this.getPlotConfig(buttons), scrollZoom: false }
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
