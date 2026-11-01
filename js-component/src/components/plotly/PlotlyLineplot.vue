<template>
  <div :id="id" class="plot-container" :style="cssCustomProperties"></div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { LinePlotComponentArgs, PlotData } from '@/types/component'

// Default styling configuration
const DEFAULT_STYLING = {
  highlightColor: '#E4572E',
  selectedColor: '#F3A712',
  unhighlightedColor: 'lightblue',
  highlightHiddenColor: '#1f77b4',
  annotationBackground: '#f8f8f8',
}

// Default config for annotation scaling
const DEFAULT_CONFIG = {
  xPosScalingFactor: 80,
  xPosScalingThreshold: 500,
  minAnnotationWidth: 40,
}

export default defineComponent({
  name: 'PlotlyLineplot',
  props: {
    args: {
      type: Object as PropType<LinePlotComponentArgs>,
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
    return { streamlitDataStore, selectionStore }
  },
  data() {
    return {
      isInitialized: false as boolean,
      manualXRange: undefined as number[] | undefined,
      lastAutoZoomedPeakIndex: undefined as number | undefined,
      textMeasureCanvas: null as HTMLCanvasElement | null,
    }
  },
  computed: {
    id(): string {
      return `plot-${this.index}`
    },

    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },

    styling() {
      return {
        ...DEFAULT_STYLING,
        ...this.args.styling,
      }
    },

    config() {
      return {
        ...DEFAULT_CONFIG,
        ...this.args.config,
      }
    },

    /**
     * Get actual plot width from DOM.
     */
    actualPlotWidth(): number {
      const element = document.getElementById(this.id)
      if (element) {
        const rect = element.getBoundingClientRect()
        if (rect.width > 0) {
          return rect.width
        }
      }
      return 800 // default
    },

    /**
     * Get plot config from Python (sent with data, may have dynamic column names).
     * When dynamic annotations are set, _plotConfig contains updated column names.
     */
    plotConfig(): Record<string, unknown> | undefined {
      return this.streamlitDataStore.allDataForDrawing?._plotConfig as Record<string, unknown> | undefined
    },

    /**
     * Get plot data from Python.
     * Data arrives as column arrays: {columnName: [values...], ...}
     * We map to the expected format using xColumn/yColumn from args.
     */
    plotData(): PlotData | undefined {
      const rawData = this.streamlitDataStore.allDataForDrawing?.plotData as
        | Record<string, unknown[]>
        | undefined
      if (!rawData) return undefined

      // Get column names from args (static) or plotConfig (dynamic, may be updated at runtime)
      const config = this.plotConfig
      const xCol = (config?.xColumn as string) || this.args.xColumn || 'x'
      const yCol = (config?.yColumn as string) || this.args.yColumn || 'y'

      // Map to expected PlotData format
      const result: PlotData = {
        x_values: (rawData[xCol] as number[]) || [],
        y_values: (rawData[yCol] as number[]) || [],
      }

      // Add highlight mask if present
      // Use plotConfig column name if available (for dynamic annotations), otherwise args
      const highlightCol = (config?.highlightColumn as string) || this.args.highlightColumn
      if (highlightCol && rawData[highlightCol]) {
        result.highlight_mask = rawData[highlightCol] as boolean[]
      }

      // Add annotations if present
      const annotationCol = (config?.annotationColumn as string) || this.args.annotationColumn
      if (annotationCol && rawData[annotationCol]) {
        result.annotations = rawData[annotationCol] as string[]
      }

      // Add interactivity column data for click handling
      // Columns are stored with their original names in rawData
      if (this.args.interactivity) {
        for (const [identifier, column] of Object.entries(this.args.interactivity)) {
          const colName = column as string
          if (rawData[colName]) {
            result[`interactivity_${colName}`] = rawData[colName]
          }
        }
      }

      return result
    },

    /**
     * Get interactivity mapping from args.
     * Maps identifier names to column names.
     */
    interactivity(): Record<string, string> {
      return this.args.interactivity || {}
    },

    /**
     * Find the index of the selected peak based on interactivity mapping.
     * Looks up the selection value and finds the matching index in the data.
     */
    selectedPeakIndex(): number | undefined {
      if (!this.isDataReady || !this.plotData) {
        return undefined
      }

      // For each identifier in interactivity, check if there's a selection
      for (const [identifier, column] of Object.entries(this.interactivity)) {
        const selectedValue = this.selectionStore.$state[identifier]
        if (selectedValue === undefined || selectedValue === null) {
          continue
        }

        // Look for the interactivity column data (e.g., interactivity_peak_id)
        const columnKey = `interactivity_${column}`
        const columnValues = this.plotData[columnKey] as unknown[] | undefined

        if (columnValues && Array.isArray(columnValues)) {
          // Find the index with matching value
          for (let i = 0; i < columnValues.length; i++) {
            if (columnValues[i] === selectedValue) {
              return i
            }
          }
        } else if (column === this.args.xColumn) {
          // Fallback: if no interactivity column data, try matching x values
          const xValues = this.plotData.x_values
          for (let i = 0; i < xValues.length; i++) {
            if (xValues[i] === selectedValue) {
              return i
            }
          }
        }
      }
      return undefined
    },

    /**
     * Check if data is ready for rendering.
     */
    isDataReady(): boolean {
      if (!this.plotData) return false
      return (
        Array.isArray(this.plotData.x_values) &&
        Array.isArray(this.plotData.y_values) &&
        this.plotData.x_values.length > 0
      )
    },

    /**
     * Generate stick format x values from raw data.
     * Each data point (x) becomes triplet: [x, x, x]
     */
    xValuesStick(): number[] {
      if (!this.isDataReady || !this.plotData) return []
      const result: number[] = []
      for (const x of this.plotData.x_values) {
        result.push(x, x, x)
      }
      return result
    },

    /**
     * Generate stick format y values from raw data.
     * Each data point (y) becomes triplet: [-10000000, y, -10000000]
     * Using large negative value to avoid visual artifacts.
     */
    yValuesStick(): number[] {
      if (!this.isDataReady || !this.plotData) return []
      const result: number[] = []
      const baseline = -10000000
      for (const y of this.plotData.y_values) {
        result.push(baseline, y, baseline)
      }
      return result
    },

    /**
     * Compute x range for the plot.
     */
    xRange(): number[] {
      // Use manual range if set (from zoom)
      if (this.manualXRange) {
        return this.manualXRange
      }

      if (!this.isDataReady || !this.plotData) return [0, 1]

      const xValues = this.plotData.x_values
      const minX = Math.min(...xValues)
      const maxX = Math.max(...xValues)
      const padding = (maxX - minX) * 0.02

      return [minX - padding, maxX + padding]
    },

    /**
     * Compute y range for the plot based on visible x range.
     * Adds extra space at top for annotations.
     */
    yRange(): number[] {
      if (!this.isDataReady || !this.plotData) return [0, 1]

      const { x_values, y_values } = this.plotData
      const xRange = this.xRange

      // Find max y within the visible x range
      let maxY = 0
      for (let i = 0; i < x_values.length; i++) {
        const x = x_values[i]
        const y = y_values[i]
        if (x >= xRange[0] && x <= xRange[1] && y > maxY) {
          maxY = y
        }
      }

      if (maxY === 0) return [0, 1]

      // Add headroom for annotations (1.8x)
      return [0, maxY * 1.8]
    },

    /**
     * Compute x position scaling factor based on current zoom level.
     */
    xPosScalingFactor(): number {
      const xRange = this.xRange
      const rangeWidth = xRange[1] - xRange[0]
      const actualWidth = this.actualPlotWidth
      return (1200 / actualWidth) * rangeWidth / this.config.xPosScalingFactor
    },

    /**
     * Get annotation data: positions, labels, and visibility based on overlap.
     * Uses raw x_values/y_values (not stick format triplets).
     */
    annotatedPeaks(): Array<{
      x: number
      y: number
      label: string
      index: number
    }> {
      if (!this.isDataReady || !this.plotData) return []

      const { x_values, y_values, annotations, highlight_mask } = this.plotData
      if (!annotations) return []

      const peaks: Array<{ x: number; y: number; label: string; index: number }> = []

      for (let i = 0; i < annotations.length; i++) {
        const label = annotations[i]
        // Only include highlighted peaks with non-empty labels
        if (!label || label.length === 0) continue
        if (highlight_mask && !highlight_mask[i]) continue

        peaks.push({
          x: x_values[i],
          y: y_values[i],
          label: label,
          index: i,
        })
      }

      return peaks
    },

    /**
     * Compute annotation boxes with overlap detection.
     * Returns which annotations should be visible.
     * Uses greedy intensity-based resolution: highest intensity annotations
     * get priority, lower intensity ones are hidden if they would overlap.
     */
    annotationBoxData(): Array<{
      x: number
      y: number
      width: number
      height: number
      label: string
      visible: boolean
      index: number
    }> {
      const peaks = this.annotatedPeaks
      if (peaks.length === 0) return []

      const yRange = this.yRange
      const xRange = this.xRange

      if (yRange[1] <= 0 || xRange[1] <= xRange[0]) return []

      const ymax = yRange[1] / 1.8
      const ypos_low = ymax * 1.18
      const ypos_high = ymax * 1.32
      const boxHeight = ypos_high - ypos_low

      // Padding around text in pixels (8px on each side)
      const textPaddingPx = 16

      // Create boxes for each annotation with peak intensity preserved
      // Box width is calculated from actual text width + padding
      const boxes: Array<{
        x: number
        y: number
        width: number
        height: number
        label: string
        visible: boolean
        inVisibleRange: boolean
        index: number
        peakY: number  // Original peak intensity for sorting
      }> = []

      for (const peak of peaks) {
        const inVisibleRange = peak.x >= xRange[0] && peak.x <= xRange[1]
        // Measure text width and convert to data units
        const textWidthPx = this.measureTextWidth(peak.label)
        const boxWidthDataUnits = this.pixelWidthToDataUnits(textWidthPx + textPaddingPx)

        boxes.push({
          x: peak.x,
          y: (ypos_low + ypos_high) / 2,
          width: boxWidthDataUnits,
          height: boxHeight,
          label: peak.label,
          visible: false,  // Will be set by overlap resolution
          inVisibleRange: inVisibleRange,
          index: peak.index,
          peakY: peak.y,  // Preserve intensity for sorting
        })
      }

      // Filter to visible boxes and sort by intensity (descending)
      // Use x position as secondary sort for determinism when intensities are equal
      const visibleBoxes = boxes
        .filter((box) => box.inVisibleRange)
        .sort((a, b) => {
          if (b.peakY !== a.peakY) return b.peakY - a.peakY  // Highest intensity first
          return a.x - b.x  // Leftmost first as tiebreaker
        })

      // Greedy overlap resolution: show highest intensity, hide overlapping lower ones
      // Use a small gap between boxes (4px converted to data units)
      const gapDataUnits = this.pixelWidthToDataUnits(4)
      const committedBoxes: typeof visibleBoxes = []

      for (const box of visibleBoxes) {
        const boxLeft = box.x - box.width / 2 - gapDataUnits
        const boxRight = box.x + box.width / 2 + gapDataUnits

        // Check overlap with all committed (visible) boxes
        let hasOverlap = false
        for (const committed of committedBoxes) {
          const committedLeft = committed.x - committed.width / 2
          const committedRight = committed.x + committed.width / 2

          // Check x overlap (y is the same for all annotation boxes)
          if (!(boxRight < committedLeft || boxLeft > committedRight)) {
            hasOverlap = true
            break
          }
        }

        if (!hasOverlap) {
          box.visible = true
          committedBoxes.push(box)
        }
      }

      return boxes
    },

    /**
     * Build Plotly shapes for annotation background boxes.
     * Box color matches the peak: selectedColor if peak is selected, highlightColor otherwise.
     */
    annotationShapes(): Partial<Plotly.Shape>[] {
      const boxes = this.annotationBoxData
      const shapes: Partial<Plotly.Shape>[] = []

      const yRange = this.yRange
      if (yRange[1] <= 0) return shapes

      const ymax = yRange[1] / 1.8
      const ypos_low = ymax * 1.18
      const ypos_high = ymax * 1.32

      const selectedIndex = this.selectedPeakIndex

      for (const box of boxes) {
        if (!box.visible) continue

        // Use selected color if this annotation's peak is selected
        const isSelected = box.index === selectedIndex
        const boxColor = isSelected ? this.styling.selectedColor : this.styling.highlightColor

        shapes.push({
          type: 'rect',
          x0: box.x - box.width / 2,
          y0: ypos_low,
          x1: box.x + box.width / 2,
          y1: ypos_high,
          fillcolor: boxColor,
          line: { width: 0 },
        })
      }

      return shapes
    },

    /**
     * Build Plotly annotations for peak labels.
     */
    peakAnnotations(): Partial<Plotly.Annotations>[] {
      const boxes = this.annotationBoxData
      const annotations: Partial<Plotly.Annotations>[] = []

      const yRange = this.yRange
      if (yRange[1] <= 0) return annotations

      const ymax = yRange[1] / 1.8
      const ypos = ymax * 1.25

      for (const box of boxes) {
        if (!box.visible) continue

        annotations.push({
          x: box.x,
          y: ypos,
          xref: 'x',
          yref: 'y',
          text: box.label,
          showarrow: false,
          font: {
            size: 14,
            color: 'white',
          },
        })
      }

      return annotations
    },

    /**
     * Check if the selected peak is annotated but its annotation is currently hidden.
     */
    selectedAnnotationHidden(): boolean {
      const selectedIndex = this.selectedPeakIndex
      if (selectedIndex === undefined) return false

      const boxes = this.annotationBoxData
      const selectedBox = boxes.find(box => box.index === selectedIndex)

      // Not annotated = not hidden
      if (!selectedBox) return false

      // Return true if annotation exists but is not visible
      return !selectedBox.visible
    },

    /**
     * Build Plotly traces.
     * Uses stick format triplets generated from raw data.
     * Includes a separate gold trace for the selected peak.
     */
    traces(): Plotly.Data[] {
      if (!this.isDataReady || !this.plotData) {
        return this.getFallbackData()
      }

      const traces: Plotly.Data[] = []
      const { highlight_mask } = this.plotData
      const selectedIndex = this.selectedPeakIndex
      const baseline = -10000000

      // Split into unhighlighted, highlighted, and selected
      const unhighlighted_x: number[] = []
      const unhighlighted_y: number[] = []
      const highlighted_x: number[] = []
      const highlighted_y: number[] = []
      const selected_x: number[] = []
      const selected_y: number[] = []

      const numPoints = this.plotData.x_values.length

      for (let i = 0; i < numPoints; i++) {
        const x = this.plotData.x_values[i]
        const y = this.plotData.y_values[i]
        const isHighlighted = highlight_mask ? highlight_mask[i] : false
        const isSelected = selectedIndex !== undefined && i === selectedIndex

        if (isSelected) {
          // Selected peak goes in gold trace (drawn last, on top)
          selected_x.push(x, x, x)
          selected_y.push(baseline, y, baseline)
        } else if (isHighlighted) {
          // Highlighted peaks (annotated)
          highlighted_x.push(x, x, x)
          highlighted_y.push(baseline, y, baseline)
        } else {
          // Normal unhighlighted peaks
          unhighlighted_x.push(x, x, x)
          unhighlighted_y.push(baseline, y, baseline)
        }
      }

      // Unhighlighted trace (drawn first, bottom layer)
      if (unhighlighted_x.length > 0) {
        traces.push({
          x: unhighlighted_x,
          y: unhighlighted_y,
          mode: 'lines',
          type: 'scatter',
          connectgaps: false,
          marker: { color: this.styling.unhighlightedColor },
          hoverinfo: 'x+y',
        })
      }

      // Highlighted trace (middle layer)
      if (highlighted_x.length > 0) {
        traces.push({
          x: highlighted_x,
          y: highlighted_y,
          mode: 'lines',
          type: 'scatter',
          connectgaps: false,
          marker: { color: this.styling.highlightColor },
          hoverinfo: 'x+y',
        })
      }

      // Selected trace (top layer, gold color)
      if (selected_x.length > 0) {
        traces.push({
          x: selected_x,
          y: selected_y,
          mode: 'lines',
          type: 'scatter',
          connectgaps: false,
          marker: { color: this.styling.selectedColor },
          line: { width: 3 }, // Make selected peak slightly thicker
          hoverinfo: 'x+y',
        })
      }

      // If no data was added (no highlight mask and no selection), show all as default
      if (traces.length === 0) {
        traces.push({
          x: this.xValuesStick,
          y: this.yValuesStick,
          mode: 'lines',
          type: 'scatter',
          connectgaps: false,
          marker: { color: this.styling.highlightHiddenColor },
          hoverinfo: 'x+y',
        })
      }

      return traces
    },

    /**
     * Build Plotly layout.
     */
    layout(): Partial<Plotly.Layout> {
      return {
        title: this.args.title ? { text: `<b>${this.args.title}</b>` } : undefined,
        showlegend: false,
        height: this.args.height || 400,
        xaxis: {
          title: this.args.xLabel ? { text: this.args.xLabel } : undefined,
          showgrid: false,
          showline: true,
          linecolor: 'grey',
          linewidth: 1,
          range: this.xRange,
        },
        yaxis: {
          title: this.args.yLabel ? { text: this.args.yLabel } : undefined,
          showgrid: true,
          gridcolor: this.theme?.secondaryBackgroundColor || '#f0f0f0',
          rangemode: 'nonnegative',
          fixedrange: false,
          showline: true,
          linecolor: 'grey',
          linewidth: 1,
          range: this.yRange,
        },
        paper_bgcolor: this.theme?.backgroundColor || 'white',
        plot_bgcolor: this.theme?.backgroundColor || 'white',
        font: {
          color: this.theme?.textColor || 'black',
          family: this.theme?.font || 'Arial',
        },
        margin: {
          l: 60,
          r: 20,
          t: this.args.title ? 50 : 20,
          b: 50,
        },
        shapes: this.annotationShapes,
        annotations: this.peakAnnotations,
      }
    },

    cssCustomProperties(): Record<string, string> {
      return {
        '--highlight-color': this.styling.highlightColor,
        '--selected-color': this.styling.selectedColor,
        '--unhighlighted-color': this.styling.unhighlightedColor,
      }
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

    'streamlitDataStore.allDataForDrawing.plotData': {
      handler(newData, oldData) {
        console.log('[LinePlot] plotData changed', {
          newLength: newData?.x_values?.length,
          oldLength: oldData?.x_values?.length,
          newFirstX: newData?.x_values?.[0],
          oldFirstX: oldData?.x_values?.[0],
        })
        if (this.isInitialized) {
          // Reset zoom when data changes (e.g., switching spectra)
          this.manualXRange = undefined
          this.lastAutoZoomedPeakIndex = undefined
          this.renderPlot()
        }
      },
      deep: true,
    },

    // Re-render when plot config changes (e.g., dynamic annotations)
    'streamlitDataStore.allDataForDrawing._plotConfig': {
      handler() {
        if (this.isInitialized) {
          this.renderPlot()
        }
      },
      deep: true,
    },

    // Re-render when selection changes (to update gold highlighting)
    // Also auto-zoom if selected annotated peak's label is hidden
    'selectionStore.$state': {
      handler(newState) {
        console.log('[LinePlot] selection changed', newState)
        if (this.isDataReady && this.isInitialized) {
          this.autoZoomToSelectedAnnotation()
          this.renderPlot()
        }
      },
      deep: true,
    },
  },

  mounted() {
    this.isInitialized = true
    // Use nextTick to ensure DOM is fully ready
    this.$nextTick(() => {
      if (this.isDataReady) {
        this.renderPlot()
      }
    })
  },

  methods: {
    /**
     * Measure text width in pixels using Canvas API.
     * Caches the canvas context for performance.
     */
    measureTextWidth(text: string): number {
      if (!this.textMeasureCanvas) {
        this.textMeasureCanvas = document.createElement('canvas')
      }
      const ctx = this.textMeasureCanvas.getContext('2d')
      if (!ctx) return text.length * 8 // Fallback estimate
      ctx.font = '14px Arial'
      return ctx.measureText(text).width
    },

    /**
     * Convert pixel width to data units (x-axis scale).
     * Accounts for current zoom level and plot width.
     */
    pixelWidthToDataUnits(pixelWidth: number): number {
      const xRange = this.xRange
      const rangeWidth = xRange[1] - xRange[0]
      const plotWidth = this.actualPlotWidth
      // pixels / (pixels/dataUnit) = dataUnits
      return pixelWidth / (plotWidth / rangeWidth)
    },

    async renderPlot(): Promise<void> {
      try {
        const element = document.getElementById(this.id)
        if (!element) {
          console.warn(`PlotlyLineplot: DOM element with id '${this.id}' not found`)
          return
        }

        const modeBarButtons = [
          {
            title: 'Download as SVG',
            name: 'toImageSvg',
            icon: {
              width: 1792,
              height: 1792,
              path: 'M1152 1376v-160q0-14-9-23t-23-9h-96v-512q0-14-9-23t-23-9h-320q-14 0-23 9t-9 23v160q0 14 9 23t23 9h96v320h-96q-14 0-23 9t-9 23v160q0 14 9 23t23 9h320q14 0 23-9t9-23zm-128-896v-160q0-14-9-23t-23-9h-192q-14 0-23 9t-9 23v160q0 14 9 23t23 9h192q14 0 23-9t9-23zm640 416q0 209-103 385.5t-279.5 279.5-385.5 103-385.5-103-279.5-279.5-103-385.5 103-385.5 279.5-279.5 385.5-103 385.5 103 279.5 279.5 103 385.5z',
            },
            click: () => {
              const element = document.getElementById(this.id)
              if (element) {
                Plotly.downloadImage(element, {
                  filename: this.args.title || 'plot',
                  height: 400,
                  width: 1200,
                  format: 'svg',
                })
              }
            },
          },
        ]

        await Plotly.newPlot(this.id, this.traces, this.layout, {
          modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
          modeBarButtonsToAdd: modeBarButtons,
          scrollZoom: true,
          responsive: true,
        })

        // Update Streamlit iframe height after plot is rendered
        this.$nextTick(() => {
          if (this.args.height) {
            Streamlit.setFrameHeight(this.args.height)
          } else {
            Streamlit.setFrameHeight()
          }
        })

        // Add event listeners
        const plotElement = document.getElementById(this.id) as any
        if (plotElement) {
          plotElement.on('plotly_click', (eventData: any) => {
            this.onPlotClick(eventData)
          })

          plotElement.on('plotly_relayout', (eventData: any) => {
            this.onRelayout(eventData)
          })
        }
      } catch (error) {
        console.error('PlotlyLineplot: Error rendering plot:', error)
        this.renderFallback()
      }
    },

    onRelayout(eventData: any): void {
      // Handle zoom/pan events
      if (eventData['xaxis.range[0]'] !== undefined && eventData['xaxis.range[1]'] !== undefined) {
        const newXRange = [eventData['xaxis.range[0]'], eventData['xaxis.range[1]']]
        if (newXRange[0] < 0) {
          newXRange[0] = 0
        }
        this.manualXRange = newXRange
        // Reset auto-zoom tracking when user manually zooms
        this.lastAutoZoomedPeakIndex = undefined
        this.renderPlot()
      } else if (eventData['xaxis.autorange'] === true) {
        // Reset to auto range
        this.manualXRange = undefined
        this.lastAutoZoomedPeakIndex = undefined
        this.renderPlot()
      }
    },

    /**
     * Auto-zoom to show the selected peak's annotation if it's currently hidden.
     * Only triggers once per peak selection to allow manual zoom adjustments.
     */
    autoZoomToSelectedAnnotation(): void {
      const selectedIndex = this.selectedPeakIndex

      // Reset tracking if no selection
      if (selectedIndex === undefined) {
        this.lastAutoZoomedPeakIndex = undefined
        return
      }

      // Don't re-zoom for the same peak (allows user to manually adjust after auto-zoom)
      if (selectedIndex === this.lastAutoZoomedPeakIndex) {
        return
      }

      // Check if selected peak is annotated and its annotation is hidden
      if (!this.selectedAnnotationHidden) {
        return
      }

      // Calculate zoom range to show the annotation
      const newRange = this.calculateZoomForSelectedAnnotation()
      if (newRange) {
        this.manualXRange = newRange
        this.lastAutoZoomedPeakIndex = selectedIndex
      }
    },

    /**
     * Calculate a zoom range that would show the selected annotated peak's label
     * without overlapping with neighboring annotations.
     */
    calculateZoomForSelectedAnnotation(): number[] | undefined {
      const selectedIndex = this.selectedPeakIndex
      if (selectedIndex === undefined || !this.plotData) return undefined

      const peaks = this.annotatedPeaks
      const selectedPeak = peaks.find(p => p.index === selectedIndex)
      if (!selectedPeak) return undefined

      // Find distances to nearest annotated neighbors
      let leftNeighborDist = Infinity
      let rightNeighborDist = Infinity

      for (const peak of peaks) {
        if (peak.index === selectedIndex) continue
        const dist = peak.x - selectedPeak.x
        if (dist < 0 && -dist < leftNeighborDist) {
          leftNeighborDist = -dist
        } else if (dist > 0 && dist < rightNeighborDist) {
          rightNeighborDist = dist
        }
      }

      // Use the smaller distance to nearest neighbor for zoom calculation
      const minNeighborDist = Math.min(leftNeighborDist, rightNeighborDist)

      // Calculate range width that would prevent overlap
      // Box width formula: 2 * (1200 / actualWidth) * rangeWidth / scalingFactor
      // For no overlap: neighborDist > boxWidth + padding
      // Solving for rangeWidth that gives comfortable spacing
      const actualWidth = this.actualPlotWidth
      const scalingFactor = this.config.xPosScalingFactor

      let rangeWidth: number
      if (minNeighborDist < Infinity) {
        // Zoom aggressively to show just the selected peak and its immediate context
        // Use 2x the neighbor distance as the visible range
        rangeWidth = minNeighborDist * 2
      } else {
        // No annotated neighbors - zoom to show 20% of total data range
        const xValues = this.plotData.x_values
        const dataRange = Math.max(...xValues) - Math.min(...xValues)
        rangeWidth = dataRange * 0.2
      }

      // Center on selected peak, clamped to data bounds
      const xValues = this.plotData.x_values
      const minX = Math.min(...xValues)
      const maxX = Math.max(...xValues)

      let newLeft = selectedPeak.x - rangeWidth / 2
      let newRight = selectedPeak.x + rangeWidth / 2

      // Clamp to data bounds while maintaining range width
      if (newLeft < minX) {
        newLeft = minX
        newRight = Math.min(minX + rangeWidth, maxX)
      }
      if (newRight > maxX) {
        newRight = maxX
        newLeft = Math.max(maxX - rangeWidth, minX)
      }

      return [newLeft, newRight]
    },

    onPlotClick(eventData: any): void {
      // Only handle clicks if interactivity is configured
      if (!this.interactivity || Object.keys(this.interactivity).length === 0) {
        return
      }

      if (eventData.points && eventData.points.length > 0) {
        const point = eventData.points[0]
        const clickedX = point.x

        // Find the nearest peak to the clicked x position
        // Plotly click returns triplet index, we need to find the actual peak
        if (!this.plotData) return

        const xValues = this.plotData.x_values
        let nearestIndex = 0
        let nearestDistance = Infinity

        for (let i = 0; i < xValues.length; i++) {
          const distance = Math.abs(xValues[i] - clickedX)
          if (distance < nearestDistance) {
            nearestDistance = distance
            nearestIndex = i
          }
        }

        // Update selection store using the interactivity mapping
        for (const [identifier, column] of Object.entries(this.interactivity)) {
          // Look for the interactivity column data (e.g., interactivity_peak_id)
          const columnKey = `interactivity_${column}`
          const columnValues = this.plotData[columnKey] as unknown[] | undefined

          if (columnValues && Array.isArray(columnValues) && nearestIndex < columnValues.length) {
            // Use the value from the interactivity column
            this.selectionStore.updateSelection(identifier, columnValues[nearestIndex])
          } else if (column === this.args.xColumn) {
            // Fallback: use x value if no interactivity column data
            this.selectionStore.updateSelection(identifier, xValues[nearestIndex])
          }
        }
      }
    },

    getFallbackData(): Plotly.Data[] {
      return [
        {
          x: [0, 1],
          y: [0, 0],
          mode: 'lines',
          type: 'scatter',
          marker: { color: this.styling.unhighlightedColor },
          name: 'No Data',
        },
      ]
    },

    async renderFallback(): Promise<void> {
      try {
        const fallbackLayout: Partial<Plotly.Layout> = {
          title: { text: '<b>No Data Available</b>' },
          showlegend: false,
          height: 400,
          xaxis: { title: { text: 'X' }, showgrid: false },
          yaxis: { title: { text: 'Y' }, showgrid: true, rangemode: 'nonnegative' },
          paper_bgcolor: this.theme?.backgroundColor || 'white',
          plot_bgcolor: this.theme?.backgroundColor || 'white',
          font: {
            color: this.theme?.textColor || 'black',
            family: this.theme?.font || 'Arial',
          },
        }

        await Plotly.newPlot(this.id, this.getFallbackData(), fallbackLayout, {
          staticPlot: true,
        })
      } catch (error) {
        console.error('PlotlyLineplot: Failed to render fallback:', error)
      }
    },
  },
})
</script>

<style scoped>
.plot-container {
  position: relative;
  width: 100%;
  min-height: 100px;
}
</style>
