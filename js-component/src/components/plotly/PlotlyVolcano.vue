<template>
  <div class="volcano-plot">
    <div v-if="multiSelectEnabled && args.selectionPresets" class="volcano-select-bar">
      <span class="volcano-select-label">Select</span>
      <button type="button" class="volcano-select-button" :disabled="!presetCounts.changed" @click="selectPreset('changed')">
        {{ presetLabel('changed') }} ({{ presetCounts.changed }})
      </button>
      <button type="button" class="volcano-select-button" :disabled="!presetCounts.up" @click="selectPreset('up')">
        <span class="volcano-swatch" :style="{ background: args.upColor || '#E74C3C' }"></span>
        {{ presetLabel('up') }} ({{ presetCounts.up }})
      </button>
      <button type="button" class="volcano-select-button" :disabled="!presetCounts.down" @click="selectPreset('down')">
        <span class="volcano-swatch" :style="{ background: args.downColor || '#3498DB' }"></span>
        {{ presetLabel('down') }} ({{ presetCounts.down }})
      </button>
      <button type="button" class="volcano-select-button" :disabled="!selectedCount" @click="clearSelection">
        {{ presetLabel('clear') }}
      </button>
      <span v-if="selectedCount" class="volcano-select-hint">{{ selectedCount }} selected</span>
    </div>
    <!-- As tall as the plot: a relayout that autosizes (Plotly does one when a
         box or lasso selection ends) measures this element -->
    <div class="volcano-plot-area">
      <PlotToolbar :plot-id="id" :tools="toolbarTools" />
      <div :id="id" class="volcano-container" :style="{ minHeight: `${plotHeight}px` }"></div>
      <MeasureHint v-if="args.measure" :measure="measure" />
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, computed, type PropType } from 'vue'
import Plotly from '@/plotly/gl2d'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { usePlotlyScatter } from '@/composables/usePlotlyScatter'
import { clearSelectionTool, selectionOverlay, SELECTION_LAYOUT, useMultiSelect } from '@/composables/useMultiSelect'
import type { VolcanoPlotComponentArgs, VolcanoData } from '@/types/component'
import { useMeasure, type MeasureOverlay, type MeasureSpec } from '@/composables/useMeasure'
import { axisQuantity, pointsKey } from '@/utils/measure'
import MeasureHint from './MeasureHint.vue'
import { TOOLBAR_HEIGHT, type PlotTool } from '@/utils/plotTools'
import PlotToolbar from './PlotToolbar.vue'
import { useZoomState, withZoom, type ZoomValue } from '@/composables/useZoomState'

/**
 * Compute significance category for a point.
 * Up-regulated: p < pThreshold AND log2fc >= fcThreshold
 * Down-regulated: p < pThreshold AND log2fc <= -fcThreshold
 * Not significant: otherwise
 */
function computeSignificance(
  log2fc: number,
  pvalue: number,
  fcThreshold: number,
  pThreshold: number
): 'up' | 'down' | 'ns' {
  if (pvalue >= pThreshold) return 'ns'
  if (log2fc >= fcThreshold) return 'up'
  if (log2fc <= -fcThreshold) return 'down'
  return 'ns'
}

export default defineComponent({
  name: 'PlotlyVolcano',
  components: { MeasureHint, PlotToolbar },
  props: {
    args: {
      type: Object as PropType<VolcanoPlotComponentArgs>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
  },
  setup(props) {
    const streamlitDataStore = useStreamlitDataStore()

    // Measuring: two points, labelled with their fold change and p-value differences
    const measure = useMeasure(() => !!props.args.measure)
    const measureSpec = computed<MeasureSpec>(() => ({
      kind: 'points',
      xQuantity: axisQuantity(props.args.xLabel, 'log2 Fold Change'),
      yQuantity: axisQuantity(props.args.yLabel, '-log10(p-value)'),
    }))

    // Use shared Plotly scatter composable
    const plotlyScatter = usePlotlyScatter({
      id: computed(() => `volcano-${props.index}`),
      onPointClick: (point) => measure.pick({ x: Number(point.x), y: Number(point.y) }, measureSpec.value),
      interactivity: computed(() => props.args.interactivity || {}),
      getData: () => {
        const data = streamlitDataStore.allDataForDrawing?.volcanoData
        return (data as VolcanoData[]) || []
      },
      title: computed(() => props.args.title),
      imageFormat: computed(() => props.args.imageFormat),
    })

    const zoom = useZoomState(() => props.args.zoomIdentifier)
    const multi = useMultiSelect(computed(() => props.args.multiSelect))

    return {
      streamlitDataStore,
      ...plotlyScatter,
      measure,
      multiSelectEnabled: multi.enabled,
      selectedCount: multi.selectedCount,
      multiSelectionKey: multi.selectionKey,
      isRowSelected: multi.isRowSelected,
      applySelectedRows: multi.applyRows,
      clearSelection: multi.clear,
      zoom,
      zoomStamp: zoom.stamp,
    }
  },
  data() {
    return {
      isInitialized: false as boolean,
      // The zoom the plot shows, kept across redraws (Plotly.newPlot resets it)
      nativeZoom: null as ZoomValue | null,
      // Box or lasso select when several points can be selected, else zoom;
      // kept across re-renders when the user switches in the mode bar
      dragmode: (this.args.multiSelect && Object.keys(this.args.multiSelect).length > 0
        ? 'select'
        : 'zoom') as string,
      shiftHeld: false as boolean,
    }
  },
  computed: {
    /** Height of the plot below its toolbar; the frame keeps args.height. */
    plotHeight(): number {
      return (this.args.height || 400) - TOOLBAR_HEIGHT
    },

    toolbarTools(): PlotTool[] {
      return [
        ...(this.multiSelectEnabled ? [clearSelectionTool(() => this.clearSelection(), this.selectedCount)] : []),
        ...this.measure.tools(),
        this.downloadTool(),
      ]
    },

    id(): string {
      return `volcano-${this.index}`
    },

    /**
     * Get volcano data from Python.
     */
    volcanoData(): VolcanoData[] {
      const data = this.streamlitDataStore.allDataForDrawing?.volcanoData
      return (data as VolcanoData[]) || []
    },

    /**
     * Check if data is ready for rendering.
     */
    isDataReady(): boolean {
      return Array.isArray(this.volcanoData) && this.volcanoData.length > 0
    },

    /**
     * Threshold values from args.
     */
    fcThreshold(): number {
      return this.args.fcThreshold ?? 1.0
    },

    pThreshold(): number {
      return this.args.pThreshold ?? 0.05
    },

    /**
     * -log10(pThreshold) for threshold line.
     */
    neglog10PThreshold(): number {
      return this.pThreshold > 0 ? -Math.log10(this.pThreshold) : 0
    },

    /**
     * Categorize points by significance.
     */
    categorizedData(): {
      up: { x: number[]; y: number[]; text: string[]; indices: number[] }
      down: { x: number[]; y: number[]; text: string[]; indices: number[] }
      ns: { x: number[]; y: number[]; text: string[]; indices: number[] }
    } {
      const up = { x: [] as number[], y: [] as number[], text: [] as string[], indices: [] as number[] }
      const down = { x: [] as number[], y: [] as number[], text: [] as string[], indices: [] as number[] }
      const ns = { x: [] as number[], y: [] as number[], text: [] as string[], indices: [] as number[] }

      const log2fcCol = this.args.log2fcColumn
      const neglog10pCol = this.args.neglog10pColumn
      const pvalueCol = this.args.pvalueColumn
      const labelCol = this.args.labelColumn

      this.volcanoData.forEach((row, idx) => {
        const log2fc = Number(row[log2fcCol]) || 0
        const neglog10p = Number(row[neglog10pCol]) || 0
        const pvalue = Number(row[pvalueCol]) || 1
        const label = labelCol ? String(row[labelCol] || '') : ''

        const hoverText = labelCol
          ? `${label}<br>log2FC: ${log2fc.toFixed(3)}<br>p-value: ${pvalue.toExponential(2)}`
          : `log2FC: ${log2fc.toFixed(3)}<br>p-value: ${pvalue.toExponential(2)}`

        const category = computeSignificance(log2fc, pvalue, this.fcThreshold, this.pThreshold)

        if (category === 'up') {
          up.x.push(log2fc)
          up.y.push(neglog10p)
          up.text.push(hoverText)
          up.indices.push(idx)
        } else if (category === 'down') {
          down.x.push(log2fc)
          down.y.push(neglog10p)
          down.text.push(hoverText)
          down.indices.push(idx)
        } else {
          ns.x.push(log2fc)
          ns.y.push(neglog10p)
          ns.text.push(hoverText)
          ns.indices.push(idx)
        }
      })

      return { up, down, ns }
    },

    /** Number of points each selection button selects. */
    presetCounts(): { changed: number; up: number; down: number } {
      const { up, down } = this.categorizedData
      return { changed: up.x.length + down.x.length, up: up.x.length, down: down.x.length }
    },

    /** Row indices of the selected points (empty when nothing is selected). */
    selectedRowIndices(): Set<number> {
      const selected = new Set<number>()
      if (!this.multiSelectEnabled) return selected
      // Depend on the selection itself, not only on the data
      void this.multiSelectionKey
      this.volcanoData.forEach((row, idx) => {
        if (this.isRowSelected(row as Record<string, unknown>)) selected.add(idx)
      })
      return selected
    },

    /**
     * Build Plotly data traces.
     */
    plotData(): Plotly.Data[] {
      if (!this.isDataReady) {
        return this.getFallbackData()
      }

      const { up, down, ns } = this.categorizedData

      const traces: Plotly.Data[] = []

      // Not significant points (render first, behind)
      if (ns.x.length > 0) {
        traces.push({
          type: 'scattergl',
          name: 'Not significant',
          x: ns.x,
          y: ns.y,
          mode: 'markers',
          marker: {
            color: this.args.nsColor || '#95A5A6',
            size: 6,
            opacity: 0.6,
          },
          text: ns.text,
          hoverinfo: 'text',
          customdata: ns.indices,
          ...this.selectionStyle(ns.indices),
        })
      }

      // Down-regulated points
      if (down.x.length > 0) {
        traces.push({
          type: 'scattergl',
          name: 'Down-regulated',
          x: down.x,
          y: down.y,
          mode: 'markers',
          marker: {
            color: this.args.downColor || '#3498DB',
            size: 8,
          },
          text: down.text,
          hoverinfo: 'text',
          customdata: down.indices,
          ...this.selectionStyle(down.indices),
        })
      }

      // Up-regulated points (render last, on top)
      if (up.x.length > 0) {
        traces.push({
          type: 'scattergl',
          name: 'Up-regulated',
          x: up.x,
          y: up.y,
          mode: 'markers',
          marker: {
            color: this.args.upColor || '#E74C3C',
            size: 8,
          },
          text: up.text,
          hoverinfo: 'text',
          customdata: up.indices,
          ...this.selectionStyle(up.indices),
        })
      }

      if (this.multiSelectEnabled && this.selectedRowIndices.size > 0) {
        const x: number[] = []
        const y: number[] = []
        for (const group of [ns, down, up]) {
          group.indices.forEach((rowIndex, i) => {
            if (this.selectedRowIndices.has(rowIndex)) {
              x.push(group.x[i])
              y.push(group.y[i])
            }
          })
        }
        traces.push(...selectionOverlay(x, y, 8))
      }

      return traces
    },

    /**
     * Build threshold lines (shapes).
     */
    thresholdShapes(): Partial<Plotly.Shape>[] {
      if (!this.args.showThresholdLines) return []

      const lineStyle = this.args.thresholdLineStyle || 'dash'
      const shapes: Partial<Plotly.Shape>[] = []

      // Horizontal line at -log10(pThreshold)
      shapes.push({
        type: 'line',
        xref: 'paper',
        yref: 'y',
        x0: 0,
        x1: 1,
        y0: this.neglog10PThreshold,
        y1: this.neglog10PThreshold,
        line: {
          color: 'rgba(100, 100, 100, 0.5)',
          width: 1.5,
          dash: lineStyle as Plotly.Dash,
        },
      })

      // Vertical line at +fcThreshold
      shapes.push({
        type: 'line',
        xref: 'x',
        yref: 'paper',
        x0: this.fcThreshold,
        x1: this.fcThreshold,
        y0: 0,
        y1: 1,
        line: {
          color: 'rgba(100, 100, 100, 0.5)',
          width: 1.5,
          dash: lineStyle as Plotly.Dash,
        },
      })

      // Vertical line at -fcThreshold
      shapes.push({
        type: 'line',
        xref: 'x',
        yref: 'paper',
        x0: -this.fcThreshold,
        x1: -this.fcThreshold,
        y0: 0,
        y1: 1,
        line: {
          color: 'rgba(100, 100, 100, 0.5)',
          width: 1.5,
          dash: lineStyle as Plotly.Dash,
        },
      })

      return shapes
    },

    /**
     * Build annotations for top significant points.
     */
    pointAnnotations(): Partial<Plotly.Annotations>[] {
      if (!this.args.labelColumn) return []

      const maxLabels = this.args.maxLabels ?? 10
      if (maxLabels <= 0) return []

      const labelCol = this.args.labelColumn
      const log2fcCol = this.args.log2fcColumn
      const neglog10pCol = this.args.neglog10pColumn
      const pvalueCol = this.args.pvalueColumn

      // Get significant points and sort by -log10(p) descending
      const significantPoints: Array<{
        label: string
        log2fc: number
        neglog10p: number
      }> = []

      this.volcanoData.forEach((row) => {
        const log2fc = Number(row[log2fcCol]) || 0
        const pvalue = Number(row[pvalueCol]) || 1
        const neglog10p = Number(row[neglog10pCol]) || 0
        const label = String(row[labelCol] || '')

        const category = computeSignificance(log2fc, pvalue, this.fcThreshold, this.pThreshold)
        if (category !== 'ns' && label) {
          significantPoints.push({ label, log2fc, neglog10p })
        }
      })

      // Sort by significance (most significant first)
      significantPoints.sort((a, b) => b.neglog10p - a.neglog10p)

      // Take top N
      const topPoints = significantPoints.slice(0, maxLabels)

      return topPoints.map((point) => ({
        x: point.log2fc,
        y: point.neglog10p,
        text: point.label,
        showarrow: true,
        arrowhead: 0,
        arrowsize: 0.5,
        arrowwidth: 1,
        arrowcolor: 'rgba(100, 100, 100, 0.5)',
        ax: 0,
        ay: -25,
        font: {
          size: 10,
          color: this.theme?.textColor || 'black',
        },
        bgcolor: this.theme?.base === 'dark' ? 'rgba(14, 17, 23, 0.8)' : 'rgba(255, 255, 255, 0.8)',
        borderpad: 2,
      }))
    },

    /** Identity of the plotted points: other data drops the measurements. */
    measureKey(): string {
      const x = this.args.log2fcColumn
      const y = this.args.neglog10pColumn
      return pointsKey(
        this.volcanoData.map((row) => row[x]),
        this.volcanoData.map((row) => row[y]),
      )
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
        height: this.plotHeight,
        dragmode: this.dragmode as Plotly.Layout['dragmode'],
        ...SELECTION_LAYOUT,
        xaxis: {
          title: { text: this.args.xLabel || 'log2 Fold Change' },
          zeroline: true,
          zerolinecolor: 'rgba(150, 150, 150, 0.3)',
          zerolinewidth: 1,
        },
        yaxis: {
          title: { text: this.args.yLabel || '-log10(p-value)' },
          rangemode: 'tozero',
        },
        shapes: [...this.thresholdShapes, ...this.measureOverlay.shapes],
        annotations: [...this.pointAnnotations, ...this.measureOverlay.annotations],
        margin: {
          l: 60,
          r: 20,
          t: this.args.title ? 80 : 40,
          b: 60,
        },
      }
    },
  },

  watch: {
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

    'streamlitDataStore.allDataForDrawing.volcanoData': {
      handler() {
        if (this.isInitialized) {
          this.renderPlot()
        }
      },
      deep: true,
    },

    // Re-render when thresholds change
    fcThreshold() {
      if (this.isInitialized && this.isDataReady) {
        this.renderPlot()
      }
    },

    pThreshold() {
      if (this.isInitialized && this.isDataReady) {
        this.renderPlot()
      }
    },

    // The selected set changed (here or in another component)
    multiSelectionKey() {
      if (this.isInitialized && this.isDataReady) {
        this.renderPlot()
      }
    },
  },

  mounted() {
    this.isInitialized = true
    this.nativeZoom = this.zoom.incoming() ?? null
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
          console.warn(`PlotlyVolcano: DOM element with id '${this.id}' not found`)
          return
        }

        await Plotly.newPlot(
          this.id, this.plotData, withZoom(this.layout, this.nativeZoom),
          this.getPlotConfig(),
        )
        this.setupClickHandler()
        this.setupSelectHandlers()
        this.zoom.bindNative(element as Plotly.PlotlyHTMLElement, (z) => { this.nativeZoom = z })
        this.measure.bindLabelClicks(element)

        // Update Streamlit iframe height after plot is rendered
        this.$nextTick(() => {
          this.updateFrameHeight()
        })
      } catch (error) {
        console.error('PlotlyVolcano: Error rendering plot:', error)
        this.renderFallback()
      }
    },

    /** Plotly's selection styling for a trace whose points are rows `indices`. */
    selectionStyle(indices: number[]): Record<string, unknown> {
      const selected = this.selectedRowIndices
      if (!this.multiSelectEnabled || selected.size === 0) return {}
      const points: number[] = []
      indices.forEach((rowIndex, pointIndex) => {
        if (selected.has(rowIndex)) points.push(pointIndex)
      })
      return {
        selectedpoints: points,
        selected: { marker: { opacity: 1 } },
        unselected: { marker: { opacity: 0.15 } },
      }
    },

    presetLabel(name: string): string {
      const defaults: Record<string, string> = {
        changed: 'All changed', up: 'Up', down: 'Down', clear: 'Clear',
      }
      return this.args.presetLabels?.[name] || defaults[name] || name
    },

    /** Select every significant (changed), up- or down-regulated point. */
    selectPreset(preset: 'changed' | 'up' | 'down'): void {
      const { up, down } = this.categorizedData
      const indices = preset === 'up' ? up.indices : preset === 'down' ? down.indices : [...up.indices, ...down.indices]
      const rows = indices.map((i) => this.volcanoData[i] as Record<string, unknown>)
      this.applySelectedRows(rows, 'replace')
    },

    setupSelectHandlers(): void {
      if (!this.multiSelectEnabled) return
      const element = document.getElementById(this.id) as Plotly.PlotlyHTMLElement | null
      if (!element) return
      // Whether Shift was held while dragging: then the points are added
      if (!element.dataset.shiftListener) {
        element.dataset.shiftListener = '1'
        element.addEventListener('mousedown', (e: MouseEvent) => {
          this.shiftHeld = e.shiftKey
        }, true)
      }
      element.on('plotly_relayout', (eventData: Plotly.PlotRelayoutEvent) => {
        const mode = (eventData as Record<string, unknown>).dragmode
        if (typeof mode === 'string') this.dragmode = mode
      })
      element.on('plotly_selected', (eventData: Plotly.PlotSelectionEvent | undefined) => {
        // A click without dragging also ends in plotly_selected, without points
        if (!eventData || !eventData.points) return
        const rows: Record<string, unknown>[] = []
        for (const point of eventData.points) {
          const rowIndex = (point as unknown as { customdata?: unknown }).customdata
          if (typeof rowIndex === 'number' && this.volcanoData[rowIndex]) {
            rows.push(this.volcanoData[rowIndex] as Record<string, unknown>)
          }
        }
        if (rows.length === 0 && !this.shiftHeld) {
          this.clearSelection()
          return
        }
        this.applySelectedRows(rows, this.shiftHeld ? 'add' : 'replace')
      })
      element.on('plotly_deselect', () => {
        this.clearSelection()
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
          xaxis: { title: { text: 'log2 Fold Change' } },
          yaxis: { title: { text: '-log10(p-value)' } },
        }

        await Plotly.newPlot(this.id, this.getFallbackData(), fallbackLayout, {
          staticPlot: true,
        })
      } catch (error) {
        console.error('PlotlyVolcano: Failed to render fallback:', error)
      }
    },
  },
})
</script>

<style scoped>
.volcano-plot-area {
  position: relative;
}

.volcano-select-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 4px 4px 2px;
  font-size: 13px;
}
.volcano-select-label {
  font-weight: 600;
  opacity: 0.8;
}
.volcano-select-button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 10px;
  font: inherit;
  color: inherit;
  background: transparent;
  border: 1px solid rgba(128, 128, 128, 0.5);
  border-radius: 12px;
  cursor: pointer;
}
.volcano-select-button:hover:not(:disabled) {
  border-color: rgba(128, 128, 128, 0.9);
  background: rgba(128, 128, 128, 0.12);
}
.volcano-select-button:disabled {
  opacity: 0.45;
  cursor: default;
}
.volcano-swatch {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
.volcano-select-hint {
  opacity: 0.65;
  font-size: 12px;
}
.volcano-container {
  position: relative;
  width: 100%;
  min-height: 100px;
}
</style>
