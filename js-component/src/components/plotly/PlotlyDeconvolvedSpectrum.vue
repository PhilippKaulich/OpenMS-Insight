<template>
  <div class="plot-wrapper" :style="cssCustomProperties">
    <div :id="id" class="plot-container"></div>
    <button v-if="showBackButton" class="back-button" title="Back to the deconvolved spectrum" @click="backButton">
      ↩
    </button>
  </div>
</template>

<script lang="ts">
/**
 * Deconvolved spectrum plot (masses, raw peaks and sequence tag ladders).
 *
 * Modes:
 *  - deconvolved: masses as sticks, selected mass highlighted and labelled
 *  - annotated: raw peaks, signal peaks of the selected mass highlighted, z=N labels
 *  - ladder: masses with a sequence tag ladder; clicking a ladder mass drills
 *    down to its raw peaks ('ladder-annotated'), the back button returns
 */
import { defineComponent, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { DeconvolvedSpectrumComponentArgs } from '@/types/component'

type Mode = 'deconvolved' | 'annotated' | 'ladder' | 'ladder-annotated'

interface HighlightData {
  mass: number
  mzs: number[]
  intensity: number[]
  charges: number[]
}

interface AnnotationBox {
  x: number
  y: number
  width: number
  height: number
  type: 'mass' | 'charge'
  index: number
  visible: boolean
}

const DEFAULT_CONFIG = {
  xPosScalingFactor: 27.5,
  xPosScalingThreshold: 30,
}

const DEFAULT_STYLING = {
  highlightColor: '#E4572E',
  selectedColor: '#F3A712',
  unhighlightedColor: 'lightblue',
  highlightHiddenColor: '#1f77b4',
  annotationColors: {
    massButton: '#E4572E',
    selectedMassButton: '#F3A712',
    sequenceArrow: '#E4572E',
    selectedSequenceArrow: '#F3A712',
    background: '#f0f0f0',
    buttonHover: '#e0e0e0',
  },
}

// Stick plots draw each peak as x,x,x / floor,y,floor
const STICK_FLOOR = -10000000

const TOGGLE_ANNOTATIONS_ICON = {
  width: 1792,
  height: 1792,
  path: 'M1664 960q-152-236-381-353 61 104 61 225 0 185-131.5 316.5t-316.5 131.5-316.5-131.5-131.5-316.5q0-121 61-225-229 117-381 353 133 205 333.5 326.5t434.5 121.5 434.5-121.5 333.5-326.5zm-720-384q0-20-14-34t-34-14q-125 0-214.5 89.5t-89.5 214.5q0 20 14 34t34 14 34-14 14-34q0-86 61-147t147-61q20 0 34-14t14-34zm848 384q0 34-20 69-140 230-376.5 368.5t-499.5 138.5-499.5-139-376.5-368q-20-35-20-69t20-69q140-229 376.5-368t499.5-139 499.5 139 376.5 368q20 35 20 69z',
}
const TOGGLE_PEAKS_ICON = {
  width: 1792,
  height: 1792,
  path: 'M448 1024h896v128h-896v-128zm0-256h896v128h-896v-128zm0-256h896v128h-896v-128zm0-256h896v128h-896v-128zm-448 768h384v128h-384v-128zm0-256h384v128h-384v-128zm0-256h384v128h-384v-128zm0-256h384v128h-384v-128z',
}
const SVG_ICON = {
  width: 1792,
  height: 1792,
  path: 'M1152 1376v-160q0-14-9-23t-23-9h-96v-512q0-14-9-23t-23-9h-320q-14 0-23 9t-9 23v160q0 14 9 23t23 9h96v320h-96q-14 0-23 9t-9 23v160q0 14 9 23t23 9h320q14 0 23-9t9-23zm-128-896v-160q0-14-9-23t-23-9h-192q-14 0-23 9t-9 23v160q0 14 9 23t23 9h192q14 0 23-9t9-23zm640 416q0 209-103 385.5t-279.5 279.5-385.5 103-385.5-103-279.5-279.5-103-385.5 103-385.5 279.5-279.5 385.5-103 385.5 103 279.5 279.5 103 385.5z',
}

let plotIdCounter = 0

export default defineComponent({
  name: 'PlotlyDeconvolvedSpectrum',
  props: {
    args: {
      type: Object as PropType<DeconvolvedSpectrumComponentArgs>,
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
    return { streamlitDataStore, selectionStore, uniqueId: `deconv-spectrum-${++plotIdCounter}` }
  },
  data() {
    return {
      drawPending: false,
      manual: false,
      manualXRange: undefined as number[] | undefined,
      annotationsVisible: true,
      deconvolvedPeaksHighlightMode: false,
      // Drilled down from the ladder view into the raw peaks of a mass
      drilledDown: false,
    }
  },
  computed: {
    id(): string {
      return this.uniqueId
    },
    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },
    config(): typeof DEFAULT_CONFIG {
      return { ...DEFAULT_CONFIG, ...(this.args.config || {}) }
    },
    styling(): typeof DEFAULT_STYLING {
      return {
        ...DEFAULT_STYLING,
        ...(this.args.styling || {}),
        annotationColors: {
          ...DEFAULT_STYLING.annotationColors,
          ...(this.args.styling?.annotationColors || {}),
        },
      }
    },
    mode(): Mode {
      if (this.args.view === 'ladder') {
        return this.drilledDown ? 'ladder-annotated' : 'ladder'
      }
      return this.args.view
    },
    /** Raw peaks (m/z) are drawn, rather than masses */
    isMzMode(): boolean {
      return this.mode === 'annotated' || this.mode === 'ladder-annotated'
    },
    currentTitle(): string {
      return this.mode === 'ladder-annotated'
        ? this.args.drilldownTitle ?? 'Annotated Spectrum'
        : this.args.title
    },
    xAxisLabel(): string {
      return this.isMzMode ? 'm/z' : 'Monoisotopic Mass'
    },

    /** Column arrays of the (single) spectrum row sent by Python. */
    row(): Record<string, unknown> {
      const columns = this.streamlitDataStore.allDataForDrawing?.plotData as Record<string, unknown[]> | undefined
      const row: Record<string, unknown> = {}
      if (!columns) return row
      for (const [name, values] of Object.entries(columns)) {
        row[name] = values?.[0]
      }
      return row
    },
    MassValues(): number[] {
      const values = this.row[this.args.massColumn]
      return Array.isArray(values) ? (values as number[]) : []
    },
    MZValues(): number[] {
      const values = this.args.peakMzColumn ? this.row[this.args.peakMzColumn] : undefined
      return Array.isArray(values) ? (values as number[]) : []
    },
    mzSignals(): number[][][] {
      const values = this.args.signalColumn ? this.row[this.args.signalColumn] : undefined
      return Array.isArray(values) ? (values as number[][][]) : []
    },
    xColumnValues(): number[] {
      const column = this.isMzMode ? this.args.peakMzColumn : this.args.massColumn
      const values = column ? this.row[column] : undefined
      return Array.isArray(values) ? (values as number[]) : []
    },
    yColumnValues(): number[] {
      const column = this.isMzMode ? this.args.peakIntensityColumn : this.args.massIntensityColumn
      const values = column ? this.row[column] : undefined
      return Array.isArray(values) ? (values as number[]) : []
    },
    xValues(): number[] {
      const xValues: number[] = []
      for (const num of this.xColumnValues) {
        if (typeof num === 'number' && !isNaN(num)) xValues.push(num, num, num)
      }
      return xValues
    },
    yValues(): number[] {
      const yValues: number[] = []
      for (const num of this.yColumnValues) {
        if (typeof num === 'number' && !isNaN(num)) yValues.push(STICK_FLOOR, num, STICK_FLOOR)
      }
      return yValues
    },
    isDataReady(): boolean {
      return this.xColumnValues.length > 0 && this.yColumnValues.length > 0
    },

    selectedMassIndex(): number | undefined {
      if (!this.args.massIdentifier) return undefined
      const value = this.selectionStore.$state[this.args.massIdentifier]
      return typeof value === 'number' ? value : undefined
    },
    hasLadder(): boolean {
      return !!this.args.ladder
    },
    ladderJson(): string {
      return JSON.stringify(this.args.ladder ?? null)
    },
    ladderKey(): unknown {
      return this.args.ladder ? this.args.ladder.key ?? JSON.stringify(this.args.ladder.masses) : null
    },
    /**
     * A tag's masses arrive in descending order, so the rendered tag letters use a
     * reversed index (sequence.length - 1 - i). The selected residue is reversed
     * into that same space so the highlight lands on the residue the user selected.
     */
    reversedSelectedAA(): number | undefined {
      const ladder = this.args.ladder
      if (!ladder || ladder.selectedIndex === null || ladder.selectedIndex === undefined) return undefined
      return ladder.sequence.length - 1 - ladder.selectedIndex
    },
    showBackButton(): boolean {
      return this.hasLadder && this.mode === 'ladder-annotated'
    },

    /** Positions (into MassValues) highlighted by the tag or the mass selection. */
    selectedMassPositions(): number[] {
      let positions: number[] = []
      const tagMasses = this.args.ladder?.masses ?? []
      for (const v of tagMasses) {
        for (let j = 0; j < this.MassValues.length; j++) {
          if (Math.abs(this.MassValues[j] - v) < 1e-5) {
            positions.push(j)
            break
          }
        }
      }
      const selected = this.selectedMassIndex
      if (
        selected !== undefined &&
        selected >= 0 &&
        selected < this.MassValues.length &&
        this.mode !== 'ladder'
      ) {
        positions = [selected]
      }
      return positions
    },
    highlightedValues(): HighlightData[] {
      const massValues = this.MassValues
      if (massValues.length === 0) return []
      const highlightValues: HighlightData[] = []
      const highlightedIndices = new Set<number>()
      for (const posIndex of this.selectedMassPositions) {
        if (posIndex >= massValues.length) continue
        highlightedIndices.add(posIndex)
        highlightValues.push(this.highlightFor(posIndex))
      }
      if (this.deconvolvedPeaksHighlightMode) {
        for (let i = 0; i < massValues.length; i++) {
          if (highlightedIndices.has(i)) continue
          highlightValues.push(this.highlightFor(i))
        }
      }
      return highlightValues
    },
    /** Same as highlightedValues, without the show-all-peaks toggle (labels follow the selection only). */
    annotationHighlights(): HighlightData[] {
      return this.selectedMassPositions
        .filter((posIndex) => posIndex < this.MassValues.length)
        .map((posIndex) => this.highlightFor(posIndex))
    },
    highlightedMassPos(): boolean[] {
      const highlightedMasses = new Set(this.highlightedValues.map((h) => h.mass))
      return this.MassValues.map((mass) => highlightedMasses.has(mass))
    },
    highlightedMzPos(): boolean[] {
      const highlightedMzs = new Set(this.highlightedValues.flatMap((h) => h.mzs))
      return this.MZValues.map((mz) => highlightedMzs.has(mz))
    },
    plotData(): Record<string, number[]> {
      const result = {
        unhighlighted_x: [] as number[],
        unhighlighted_y: [] as number[],
        highlighted_x: [] as number[],
        highlighted_y: [] as number[],
        selected_x: [] as number[],
        selected_y: [] as number[],
      }
      const mask = this.isMzMode ? this.highlightedMzPos : this.highlightedMassPos
      const reversedSelectedAA = this.reversedSelectedAA
      for (let i = 0; i < this.xValues.length; i++) {
        const peak = Math.floor(i / 3)
        const posHighlight = mask[peak]
        if (posHighlight === undefined) continue
        if (posHighlight && (reversedSelectedAA === peak || reversedSelectedAA === peak - 1)) {
          result.selected_x.push(this.xValues[i])
          result.selected_y.push(this.yValues[i])
        } else if (posHighlight) {
          result.highlighted_x.push(this.xValues[i])
          result.highlighted_y.push(this.yValues[i])
        } else {
          result.unhighlighted_x.push(this.xValues[i])
          result.unhighlighted_y.push(this.yValues[i])
        }
      }
      return result
    },
    maxAnnotationRange(): number {
      return this.config.xPosScalingFactor * this.config.xPosScalingThreshold
    },
    xRange(): number[] {
      const xValues = this.xValues
      if (xValues.length === 0) return [0, 1]
      const fullRange = () => [Math.min(...xValues) * 0.98, Math.max(...xValues) * 1.02]

      // Showing every deconvolved peak: the whole spectrum
      if (this.deconvolvedPeaksHighlightMode) return fullRange()
      if (!this.annotationsVisible && !this.manual) return fullRange()
      if (this.manual && this.manualXRange !== undefined) return this.manualXRange

      const highlighted = this.highlightedValues
      if (highlighted.length === 0) return fullRange()

      const values = this.isMzMode
        ? highlighted.flatMap((a) => a.mzs).filter((m) => Number.isFinite(m))
        : highlighted.map((a) => a.mass).filter((m) => !isNaN(m))
      if (values.length === 0) return [0, 1]

      // Raw peaks of the highlighted masses: all of them
      if (this.isMzMode) return [Math.min(...values) * 0.98, Math.max(...values) * 1.02]

      // Masses: centre on them, then narrow until their labels stop overlapping
      const xcenter = values.reduce((sum, mass) => sum + mass, 0) / values.length
      const offset = 0.5 * 0.9 * this.maxAnnotationRange
      return this.calculateOptimalXRange([xcenter - offset, xcenter + offset])
    },
    yRange(): number[] {
      return this.computeYRange(this.xRange)
    },
    annotationBoxData(): AnnotationBox[] {
      return this.computeAnnotationBoxes(this.xRange, this.yRange)
    },
    annotationData(): { shapes: Partial<Plotly.Shape>[]; annotations: Partial<Plotly.Annotations>[]; traces: Plotly.Data[] } {
      const empty = { shapes: [], annotations: [], traces: [] }
      if (!this.annotationsVisible) return empty
      const highlighted = this.annotationHighlights
      if (highlighted.length === 0) return empty
      const positioning = this.annotationPositioning(this.xRange, this.yRange)
      if (!positioning) return empty
      const { ypos_low, ypos, ypos_high, xpos_scaling } = positioning

      const buttonTraces: Plotly.Data[] = []
      const buttonShapes: Partial<Plotly.Shape>[] = []
      const buttonAnnotations: Partial<Plotly.Annotations>[] = []

      if (this.isMzMode) {
        if (this.selectedMassIndex === undefined || this.selectedMassIndex >= this.MassValues.length) return empty
        // Only one mass is supported for raw spectra
        const groups = this.chargeGroups(highlighted[0])
        if (groups.length === 0) return empty
        const visibleChargeBoxes = this.annotationBoxData.filter((box) => box.type === 'charge' && box.visible)
        groups.forEach(({ charge, center }, chargeIndex) => {
          if (!visibleChargeBoxes.some((box) => box.index === chargeIndex)) return
          buttonShapes.push({
            type: 'rect',
            x0: center - 0.5 * xpos_scaling,
            y0: ypos_low,
            x1: center + 0.5 * xpos_scaling,
            y1: ypos_high,
            fillcolor: this.styling.annotationColors.massButton,
            line: { width: 0 },
          })
          buttonAnnotations.push({
            x: center,
            y: ypos,
            xref: 'x',
            yref: 'y',
            text: 'z=' + charge,
            showarrow: false,
            font: { size: 15 },
          })
        })
        return { shapes: buttonShapes, annotations: buttonAnnotations, traces: buttonTraces }
      }

      // Mass buttons and, for a tag, the ladder arrows between them
      const arrowAnnotations: Partial<Plotly.Annotations>[] = []
      const reversedSelectedAA = this.reversedSelectedAA
      const visibleMassBoxes = this.annotationBoxData.filter((box) => box.type === 'mass' && box.visible)
      const scaling = highlighted.length === 1 ? 2 : 1

      for (let i = 0; i < highlighted.length; i++) {
        const mass = highlighted[i].mass
        if (!isFinite(mass)) continue
        if (!visibleMassBoxes.some((box) => box.index === i)) continue
        let fillcolor = this.styling.annotationColors.massButton
        let family = 'sans-serif'
        if (reversedSelectedAA === i || reversedSelectedAA === i - 1) {
          fillcolor = this.styling.annotationColors.selectedMassButton
          family = 'Arial Black, Arial Bold, Arial, sans-serif'
        }
        // Invisible marker so hovering the label shows the mass
        buttonTraces.push({
          x: [mass],
          y: [ypos],
          mode: 'markers',
          marker: { size: 20, opacity: 0 },
          hoverinfo: 'text',
          hovertext: String(mass.toFixed(2)),
          type: 'scatter',
        } as Plotly.Data)
        buttonShapes.push({
          type: 'rect',
          x0: mass - scaling * xpos_scaling,
          y0: ypos_low,
          x1: mass + scaling * xpos_scaling,
          y1: ypos_high,
          fillcolor,
          line: { width: 0 },
        })
        buttonAnnotations.push({
          x: mass,
          y: ypos,
          xref: 'x',
          yref: 'y',
          text: mass.toFixed(2),
          showarrow: false,
          font: { size: 15, family },
        })
      }

      const yPosArrow = ypos * 0.5
      const yPosAA = ypos * 0.6
      const sequence = this.args.ladder?.sequence
      for (let i = 0; i < highlighted.length - 1; i++) {
        const current = highlighted[i]
        const next = highlighted[i + 1]
        if (!isFinite(current.mass) || !isFinite(next.mass)) continue
        const currentVisible = visibleMassBoxes.some((box) => box.index === i)
        const nextVisible = visibleMassBoxes.some((box) => box.index === i + 1)
        if (!currentVisible || !nextVisible) continue

        let fillcolor = this.styling.annotationColors.sequenceArrow
        let family = 'sans-serif'
        if (reversedSelectedAA === i) {
          fillcolor = this.styling.annotationColors.selectedSequenceArrow
          family = 'Arial Black, Arial Bold, Arial, sans-serif'
        }
        let xStart = current.mass
        let xEnd = next.mass
        const xMid = (xStart + xEnd) / 2
        let xMidStart = xMid
        let xMidEnd = xMid
        const diff = Math.abs(xStart - xEnd) * 0.9
        let AA = ''
        let delta = 0
        if (sequence !== undefined && sequence.length > 0) {
          const reverseIndex = sequence.length - 1 - i
          if (reverseIndex >= 0 && reverseIndex < sequence.length) AA = sequence[reverseIndex]
        }
        if (xStart > xEnd) {
          delta = xStart - xEnd
          xStart -= diff
          xMidStart += diff * 0.1
          xEnd += diff
          xMidEnd -= diff * 0.1
        } else {
          delta = xEnd - xStart
          xStart += diff
          xMidStart -= diff * 0.1
          xEnd -= diff
          xMidEnd += diff * 0.1
        }
        arrowAnnotations.push({
          ax: xMidStart,
          ay: yPosArrow,
          xref: 'x',
          yref: 'y',
          x: xStart,
          y: yPosArrow,
          axref: 'x',
          ayref: 'y',
          showarrow: true,
          arrowhead: 0,
          arrowsize: 1,
          arrowwidth: 2,
          arrowcolor: fillcolor,
        })
        arrowAnnotations.push({
          ax: xMidEnd,
          ay: yPosArrow,
          xref: 'x',
          yref: 'y',
          x: xEnd,
          y: yPosArrow,
          axref: 'x',
          ayref: 'y',
          showarrow: true,
          arrowhead: 2,
          arrowsize: 1,
          arrowwidth: 2,
          arrowcolor: fillcolor,
        })
        arrowAnnotations.push({
          x: xMid,
          y: yPosAA,
          xref: 'x',
          yref: 'y',
          text: AA,
          hovertext: 'Δ=' + delta.toFixed(2) + ' Da',
          showarrow: false,
          font: { size: 15, color: fillcolor, family },
        })
      }
      return {
        shapes: buttonShapes,
        annotations: [...buttonAnnotations, ...arrowAnnotations],
        traces: buttonTraces,
      }
    },
    traces(): Plotly.Data[] {
      // Annotations hidden and not showing all peaks: one plain colour
      if (!this.annotationsVisible && !this.deconvolvedPeaksHighlightMode) {
        return [
          {
            x: this.xValues,
            y: this.yValues,
            mode: 'lines',
            type: 'scatter',
            connectgaps: false,
            marker: { color: this.styling.highlightHiddenColor },
          } as Plotly.Data,
        ]
      }
      const traces: Plotly.Data[] = [
        {
          x: this.plotData.unhighlighted_x,
          y: this.plotData.unhighlighted_y,
          mode: 'lines',
          type: 'scatter',
          marker: { color: this.styling.unhighlightedColor },
        } as Plotly.Data,
        {
          x: this.plotData.highlighted_x,
          y: this.plotData.highlighted_y,
          mode: 'lines',
          type: 'scatter',
          marker: { color: this.styling.highlightColor },
        } as Plotly.Data,
        {
          x: this.plotData.selected_x,
          y: this.plotData.selected_y,
          mode: 'lines',
          type: 'scatter',
          marker: { color: this.styling.selectedColor },
        } as Plotly.Data,
      ]
      if (this.annotationsVisible) traces.push(...this.annotationData.traces)
      return traces
    },
    layout(): Partial<Plotly.Layout> {
      return {
        title: { text: `<b>${this.currentTitle}</b>` },
        showlegend: false,
        height: this.args.height || 400,
        xaxis: {
          title: { text: this.xAxisLabel },
          showgrid: false,
          showline: true,
          linecolor: 'grey',
          linewidth: 1,
          range: this.xRange,
        },
        yaxis: {
          title: { text: 'Intensity' },
          showgrid: true,
          gridcolor: this.theme?.secondaryBackgroundColor,
          rangemode: 'nonnegative',
          fixedrange: false,
          showline: true,
          linecolor: 'grey',
          linewidth: 1,
          range: this.yRange,
        },
        paper_bgcolor: this.theme?.backgroundColor,
        plot_bgcolor: this.theme?.backgroundColor,
        font: {
          color: this.theme?.textColor,
          family: this.theme?.font,
        },
        shapes: this.annotationData.shapes,
        annotations: this.annotationData.annotations,
      }
    },
    cssCustomProperties(): Record<string, string> {
      return {
        '--annotation-background': this.styling.annotationColors.background,
        '--button-hover-color': this.styling.annotationColors.buttonHover,
      }
    },
  },
  watch: {
    'streamlitDataStore.allDataForDrawing.plotData': {
      handler() {
        // A new spectrum: forget the zoom of the previous one
        this.manual = false
        this.manualXRange = undefined
        this.requestGraph()
      },
      deep: true,
    },
    ladderKey(newKey: unknown, oldKey: unknown) {
      if (newKey !== oldKey) {
        this.resetManualState()
        this.requestGraph()
      }
    },
    // By value: the arguments arrive as a new object on every rerun
    ladderJson() {
      this.requestGraph()
    },
    selectedMassIndex() {
      this.manual = false
      this.requestGraph()
    },
    annotationsVisible() {
      this.requestGraph()
    },
    deconvolvedPeaksHighlightMode() {
      this.requestGraph()
    },
    drilledDown() {
      this.requestGraph()
    },
  },
  mounted() {
    this.requestGraph()
  },
  methods: {
    /** Draw once per tick: one update often changes several watched values
     * (the data and the selection), and each drawing costs a full Plotly render. */
    requestGraph(): void {
      if (this.drawPending) return
      this.drawPending = true
      this.$nextTick(() => {
        this.drawPending = false
        this.safeGraph()
      })
    },
    highlightFor(posIndex: number): HighlightData {
      const highlight: HighlightData = { mass: this.MassValues[posIndex], mzs: [], charges: [], intensity: [] }
      // Deconvolved-only spectrum: no raw peaks to point at
      if (this.mzSignals.length === 0) return highlight
      const signalGroup = this.mzSignals[posIndex]
      if (Array.isArray(signalGroup)) {
        for (const signal of signalGroup) {
          if (Array.isArray(signal) && signal.length >= 4) {
            highlight.mzs.push(signal[1])
            highlight.intensity.push(signal[2])
            highlight.charges.push(signal[3])
          }
        }
      }
      return highlight
    },
    /** Signal peaks of one mass grouped by charge, with their intensity weighted mean m/z. */
    chargeGroups(highlight: HighlightData | undefined): Array<{ charge: number; center: number }> {
      if (!highlight || highlight.mzs.length === 0) return []
      const grouped = new Map<number, Array<{ mz: number; intensity: number }>>()
      for (let i = 0; i < highlight.mzs.length; i++) {
        const charge = highlight.charges[i]
        if (!grouped.has(charge)) grouped.set(charge, [])
        grouped.get(charge)!.push({ mz: highlight.mzs[i], intensity: highlight.intensity[i] })
      }
      const groups: Array<{ charge: number; center: number }> = []
      grouped.forEach((peaks, charge) => {
        const summedIntensity = peaks.reduce((sum, val) => sum + val.intensity, 0)
        const center = peaks.reduce((sum, val) => sum + (val.intensity / summedIntensity) * val.mz, 0)
        groups.push({ charge, center })
      })
      return groups
    },
    plotWidth(): number {
      const element = document.getElementById(this.id)
      if (element) {
        const rect = element.getBoundingClientRect()
        if (rect.width > 0) return rect.width
      }
      return -1
    },
    computeXposScalingFactor(xRange: number): number {
      const actualWidth = this.plotWidth()
      if (actualWidth < 0) return 0
      return ((1200 / actualWidth) * xRange) / this.config.xPosScalingFactor
    },
    annotationPositioning(
      xRange: number[],
      yRange: number[]
    ): { ypos_low: number; ypos: number; ypos_high: number; xpos_scaling: number } | null {
      if (yRange.length < 2 || yRange[1] <= 0 || xRange.length < 2) return null
      const ymax = yRange[1] / 1.8
      return {
        ypos_low: ymax * 1.18,
        ypos: ymax * 1.25,
        ypos_high: ymax * 1.32,
        xpos_scaling: this.computeXposScalingFactor(xRange[1] - xRange[0]),
      }
    },
    computeAnnotationBoxes(xRange: number[], yRange: number[]): AnnotationBox[] {
      const highlighted = this.highlightedValues
      if (highlighted.length === 0) return []
      const positioning = this.annotationPositioning(xRange, yRange)
      if (!positioning) return []
      const { ypos_low, ypos_high, xpos_scaling } = positioning
      const boxes: AnnotationBox[] = []

      if (this.isMzMode) {
        if (this.selectedMassIndex === undefined || this.selectedMassIndex >= this.MassValues.length) return boxes
        this.chargeGroups(highlighted[0]).forEach(({ center }, chargeIndex) => {
          boxes.push({
            x: center,
            y: (ypos_low + ypos_high) / 2,
            width: xpos_scaling,
            height: ypos_high - ypos_low,
            type: 'charge',
            index: chargeIndex,
            visible: true,
          })
        })
      } else {
        const scaling = highlighted.length === 1 ? 2 : 1
        for (let i = 0; i < highlighted.length; i++) {
          const mass = highlighted[i].mass
          if (!isFinite(mass)) continue
          boxes.push({
            x: mass,
            y: (ypos_low + ypos_high) / 2,
            width: scaling * xpos_scaling * 2,
            height: ypos_high - ypos_low,
            type: 'mass',
            index: i,
            visible: true,
          })
        }
      }

      // Any two labels overlapping hides all of them
      if (boxes.length > 1) {
        let hasOverlap = false
        for (let i = 0; i < boxes.length && !hasOverlap; i++) {
          for (let j = i + 1; j < boxes.length; j++) {
            if (this.boxesOverlap(boxes[i], boxes[j], xRange)) {
              hasOverlap = true
              break
            }
          }
        }
        if (hasOverlap) boxes.forEach((box) => (box.visible = false))
      }
      return boxes
    },
    boxesOverlap(box1: AnnotationBox, box2: AnnotationBox, xRange: number[]): boolean {
      if (xRange.length !== 2 || xRange[1] <= xRange[0]) return false
      const xPadding = (xRange[1] - xRange[0]) * 0.01
      const yPadding = box1.height * 0.1
      const left1 = box1.x - box1.width / 2 - xPadding
      const right1 = box1.x + box1.width / 2 + xPadding
      const top1 = box1.y - box1.height / 2 - yPadding
      const bottom1 = box1.y + box1.height / 2 + yPadding
      const left2 = box2.x - box2.width / 2 - xPadding
      const right2 = box2.x + box2.width / 2 + xPadding
      const top2 = box2.y - box2.height / 2 - yPadding
      const bottom2 = box2.y + box2.height / 2 + yPadding
      return !(right1 < left2 || right2 < left1 || bottom1 < top2 || bottom2 < top1)
    },
    /** Narrow the range around its centre (up to 10 times by 0.8) until labels are visible. */
    calculateOptimalXRange(initialRange: number[]): number[] {
      let currentRange = [...initialRange]
      for (let iteration = 0; iteration < 10; iteration++) {
        const boxes = this.computeAnnotationBoxes(currentRange, this.computeYRange(currentRange))
        if (boxes.some((box) => box.visible)) return currentRange
        const center = (currentRange[0] + currentRange[1]) / 2
        const halfWidth = ((currentRange[1] - currentRange[0]) / 2) * 0.8
        currentRange = [center - halfWidth, center + halfWidth]
        if (currentRange[1] - currentRange[0] < 0.1) break
      }
      return currentRange
    },
    computeYRange(xRange: number[]): number[] {
      const yValues = this.yValues
      const xValues = this.xValues
      if (yValues.length === 0 || xValues.length === 0) return [0, 1]
      if (xRange.length !== 2 || xRange[0] >= xRange[1]) return [0, 1]
      let max = 0
      for (let i = 0; i < Math.min(xValues.length, yValues.length); i++) {
        const xval = xValues[i]
        const yval = yValues[i]
        if (!isFinite(xval) || !isFinite(yval)) continue
        if (xval <= xRange[0] || xval >= xRange[1]) continue
        if (yval > max) max = yval
      }
      return max === 0 ? [0, 1] : [0, max * 1.8]
    },
    setSelectedMass(index: number | undefined): void {
      const identifier = this.args.massIdentifier
      if (!identifier) return
      const current = this.selectionStore.$state[identifier]
      const next = index === undefined ? null : index
      if (current === next || (current === undefined && next === null)) return
      this.selectionStore.updateSelection(identifier, next)
    },
    resetManualState(): void {
      this.manual = false
      this.manualXRange = undefined
      if (this.drilledDown) this.drilledDown = false
      if (this.args.view === 'ladder') this.setSelectedMass(undefined)
    },
    backButton(): void {
      this.resetManualState()
      this.requestGraph()
    },
    onPlotClick(eventData: { points?: Array<{ x: number }> }): void {
      if (!eventData.points || eventData.points.length === 0 || !this.args.massIdentifier) return
      const x = eventData.points[0].x
      for (let i = 0; i < this.MassValues.length; i++) {
        if (x === this.MassValues[i]) {
          if (this.mode === 'ladder') {
            // Only the tag's masses lead on to their raw peaks
            if (!this.highlightedMassPos[i]) break
            this.drilledDown = true
          }
          this.manual = false
          this.setSelectedMass(i)
          this.requestGraph()
          break
        }
      }
    },
    onRelayout(eventData: Record<string, unknown>): void {
      if (eventData['xaxis.range[0]'] !== undefined && eventData['xaxis.range[1]'] !== undefined) {
        const newXRange = [eventData['xaxis.range[0]'] as number, eventData['xaxis.range[1]'] as number]
        if (newXRange[0] < 0) newXRange[0] = 0
        this.manual = true
        this.manualXRange = newXRange
        this.requestGraph()
      } else if (eventData['xaxis.autorange'] === true) {
        const xValues = this.xValues
        if (xValues.length === 0) return
        this.manual = true
        this.manualXRange = [Math.min(...xValues), Math.max(...xValues)]
        this.requestGraph()
      }
    },
    async safeGraph(): Promise<void> {
      try {
        if (!this.isDataReady) {
          await this.renderEmpty()
          return
        }
        await this.graph()
      } catch (error) {
        console.error('PlotlyDeconvolvedSpectrum: render failed', error)
        await this.renderEmpty()
      }
    },
    async graph(): Promise<void> {
      const element = document.getElementById(this.id)
      if (!element) return
      const modeBarButtons: Array<Record<string, unknown>> = [
        {
          title: this.annotationsVisible ? 'Hide Annotations' : 'Show Annotations',
          name: 'toggleAnnotations',
          icon: TOGGLE_ANNOTATIONS_ICON,
          click: () => {
            this.annotationsVisible = !this.annotationsVisible
          },
        },
      ]
      if (this.isMzMode) {
        modeBarButtons.push({
          title: this.deconvolvedPeaksHighlightMode ? 'Hide Deconvolved Peaks' : 'Show Deconvolved Peaks',
          name: 'toggleDeconvolvedPeaks',
          icon: TOGGLE_PEAKS_ICON,
          click: () => {
            this.deconvolvedPeaksHighlightMode = !this.deconvolvedPeaksHighlightMode
          },
        })
      }
      modeBarButtons.push({
        title: 'Download as SVG',
        name: 'toImageSvg',
        icon: SVG_ICON,
        click: () => {
          const plotElement = document.getElementById(this.id)
          if (plotElement) {
            Plotly.downloadImage(plotElement, {
              filename: this.args.svgFilename || 'spectrum',
              height: 400,
              width: 1200,
              format: 'svg',
            })
          }
        },
      })
      const plot = (await Plotly.newPlot(element, this.traces, this.layout, {
        modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
        modeBarButtonsToAdd: modeBarButtons as unknown as Plotly.ModeBarButton[],
        scrollZoom: true,
      })) as unknown as { on: (event: string, handler: (data: never) => void) => void }
      plot.on('plotly_relayout', (eventData: Record<string, unknown>) => this.onRelayout(eventData))
      plot.on('plotly_click', (eventData: { points?: Array<{ x: number }> }) => this.onPlotClick(eventData))
      this.$nextTick(() => Streamlit.setFrameHeight())
    },
    async renderEmpty(): Promise<void> {
      const element = document.getElementById(this.id)
      if (!element) return
      await Plotly.newPlot(
        element,
        [{ x: [0, 1], y: [0, 0], mode: 'lines', type: 'scatter', marker: { color: this.styling.unhighlightedColor } }],
        {
          title: { text: `<b>${this.currentTitle}</b>` },
          showlegend: false,
          height: this.args.height || 400,
          xaxis: { title: { text: this.xAxisLabel }, showgrid: false },
          yaxis: { title: { text: 'Intensity' }, showgrid: true, rangemode: 'nonnegative' },
          paper_bgcolor: this.theme?.backgroundColor,
          plot_bgcolor: this.theme?.backgroundColor,
          font: { color: this.theme?.textColor, family: this.theme?.font },
        },
        { staticPlot: true }
      )
      this.$nextTick(() => Streamlit.setFrameHeight())
    },
  },
})
</script>

<style scoped>
.plot-wrapper {
  position: relative;
  width: 100%;
}

.plot-container {
  width: 100%;
}

.back-button {
  position: absolute;
  top: 17%;
  left: 6.5%;
  z-index: 1000;
  background-color: var(--annotation-background);
  border: none;
  border-radius: 50%;
  width: 30px;
  height: 30px;
  text-align: center;
  line-height: 230%;
  cursor: pointer;
}

.back-button:hover {
  background-color: var(--button-hover-color);
}
</style>
