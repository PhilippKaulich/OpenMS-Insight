<template>
  <div class="plot-wrapper" :style="cssCustomProperties">
    <PlotToolbar :plot-id="id" :tools="toolbarTools" :stepper="args.stepper" />
    <div :id="id" class="plot-container"></div>
    <MeasureHint v-if="args.measure" :measure="measure" />
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
 *
 * With fragmentMatchesIdentifier, the fragment ions a ProteinSequenceView
 * matched are coloured and labelled in every mode (see utils/fragmentIons).
 */
import { defineComponent, type PropType } from 'vue'
import Plotly from '@/plotly/basic'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { DeconvolvedSpectrumComponentArgs, FragmentMatches } from '@/types/component'
import {
  fragmentMarks,
  matchesSpectrum,
  visibleLabels,
  type FragmentKind,
  type FragmentLabel,
  type FragmentMarks,
} from '@/utils/fragmentIons'
import { useMeasure, type MeasureOverlay, type MeasureSpec } from '@/composables/useMeasure'
import { usePinZoom } from '@/composables/usePinZoom'
import { useZoomState } from '@/composables/useZoomState'
import { MEASURE_CHARGES, pointsKey } from '@/utils/measure'
import MeasureHint from './MeasureHint.vue'
import { readableTextOn } from '@/utils/appTheme'
import { imageFormatOf } from '@/utils/imageExport'
import { downloadTool } from '@/utils/plotlyDownload'
import { TOOLBAR_HEIGHT, type PlotTool, type ToolIcon } from '@/utils/plotTools'
import PlotToolbar from './PlotToolbar.vue'

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
  // Circles of the theoretical isotope envelope (set_envelope)
  envelopeColor: '#D62728',
  isolationWindowColor: '#7F7F7F',
  // Fragment ions of the sequence view: N-terminal, C-terminal, internal
  nTermColor: '#1F5FBF',
  cTermColor: '#B5179E',
  internalColor: '#2E8B57',
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

/** A text label drawn by a scatter trace: unlike an annotation, it is clipped to the plot area. */
interface PlotLabel {
  x: number
  y: number
  text: string
  color: string
  family?: string
  hover?: string
}

/** One trace with the labels, cut off at the axes like the boxes behind them. */
function labelTrace(labels: PlotLabel[]): Plotly.Data | null {
  if (labels.length === 0) return null
  const hover = labels.some((label) => label.hover !== undefined)
  return {
    x: labels.map((label) => label.x),
    y: labels.map((label) => label.y),
    text: labels.map((label) => label.text),
    mode: 'text',
    type: 'scatter',
    cliponaxis: true,
    textposition: 'middle center',
    textfont: {
      size: 15,
      color: labels.map((label) => label.color),
      family: labels.map((label) => label.family ?? 'sans-serif'),
    },
    hoverinfo: hover ? 'text' : 'skip',
    hovertext: hover ? labels.map((label) => label.hover ?? '') : undefined,
    showlegend: false,
  } as unknown as Plotly.Data
}

/**
 * Label of a ladder step: its residues, shortened to the first and last two
 * with their number when the step spans more than four.
 */
export function ladderLabelText(residues: string): string {
  if (residues.length <= 4) return residues
  return `${residues.slice(0, 2)}…${residues.slice(-2)} (${residues.length})`
}

/** Residues broken into lines of 30 for a hover text. */
function wrapResidues(residues: string): string {
  const lines: string[] = []
  for (let i = 0; i < residues.length; i += 30) lines.push(residues.slice(i, i + 30))
  return lines.join('<br>')
}

/**
 * The part of a ladder arrow segment (tail to head) inside the x range, or null
 * when none of it is. A head cut off at the axis loses its arrowhead.
 */
export function clipArrow(
  tail: number,
  head: number,
  range: number[],
): { tail: number; head: number; headVisible: boolean } | null {
  if (range.length !== 2 || !(range[0] < range[1])) return { tail, head, headVisible: true }
  const [x0, x1] = range
  if (Math.max(tail, head) <= x0 || Math.min(tail, head) >= x1) return null
  const clamp = (x: number) => Math.min(Math.max(x, x0), x1)
  const clippedTail = clamp(tail)
  const clippedHead = clamp(head)
  if (clippedTail === clippedHead) return null
  return { tail: clippedTail, head: clippedHead, headVisible: clippedHead === head }
}
/** m/z distance between neighbouring isotopes at charge 1 (C13 - C12). */
const ISOTOPE_SPACING = 1.00235
/** Envelope circles show once neighbouring isotopes are this many pixels apart. */
const ENVELOPE_MIN_SPACING_PX = 8

const TOGGLE_ANNOTATIONS_ICON: ToolIcon = {
  viewBox: '0 0 1792 1792',
  markup: '<path d="M1664 960q-152-236-381-353 61 104 61 225 0 185-131.5 316.5t-316.5 131.5-316.5-131.5-131.5-316.5q0-121 61-225-229 117-381 353 133 205 333.5 326.5t434.5 121.5 434.5-121.5 333.5-326.5zm-720-384q0-20-14-34t-34-14q-125 0-214.5 89.5t-89.5 214.5q0 20 14 34t34 14 34-14 14-34q0-86 61-147t147-61q20 0 34-14t14-34zm848 384q0 34-20 69-140 230-376.5 368.5t-499.5 138.5-499.5-139-376.5-368q-20-35-20-69t20-69q140-229 376.5-368t499.5-139 499.5 139 376.5 368q20 35 20 69z"/>',
}
/** Fragment-ion labels closer than this (pixels) to a more intense one are left out. */
const FRAGMENT_LABEL_SPACING_PX = 14
const FRAGMENT_KINDS: FragmentKind[] = ['N', 'C', 'I']
const FRAGMENT_KIND_NAMES: Record<FragmentKind, string> = {
  N: 'N-terminal fragment ions',
  C: 'C-terminal fragment ions',
  I: 'Internal fragment ions',
}
// Square brackets: the ends of a sequence
const TOGGLE_FRAGMENTS_ICON: ToolIcon = {
  viewBox: '0 0 1000 1000',
  markup: '<path d="M150 100h300v100H250v600h200v100H150z M550 100h300v800H550V800h200V200H550z"/>',
}
const TOGGLE_PEAKS_ICON: ToolIcon = {
  viewBox: '0 0 1792 1792',
  markup: '<path d="M448 1024h896v128h-896v-128zm0-256h896v128h-896v-128zm0-256h896v128h-896v-128zm0-256h896v128h-896v-128zm-448 768h384v128h-384v-128zm0-256h384v128h-384v-128zm0-256h384v128h-384v-128zm0-256h384v128h-384v-128z"/>',
}

let plotIdCounter = 0

export default defineComponent({
  name: 'PlotlyDeconvolvedSpectrum',
  components: { MeasureHint, PlotToolbar },
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
  setup(props) {
    const streamlitDataStore = useStreamlitDataStore()
    const selectionStore = useSelectionStore()
    const measure = useMeasure(() => !!props.args.measure)
    const pinZoom = usePinZoom(() => !!props.args.keepZoom)
    const zoom = useZoomState(() => props.args.zoomIdentifier)
    return { streamlitDataStore, selectionStore, measure, pinZoom, zoom, zoomStamp: zoom.stamp, uniqueId: `deconv-spectrum-${++plotIdCounter}` }
  },
  data() {
    return {
      drawPending: false,
      manual: false,
      manualXRange: undefined as number[] | undefined,
      annotationsVisible: true,
      deconvolvedPeaksHighlightMode: false,
      // The fragment ions of the sequence view are marked (toolbar toggle)
      fragmentIonsVisible: true,
      // Drilled down from the ladder view into the raw peaks of a mass
      drilledDown: false,
    }
  },
  computed: {
    toolbarTools(): PlotTool[] {
      const tools: PlotTool[] = [
        ...this.pinZoom.tools(),
        ...this.measure.tools(this.measureTitle),
        {
          id: 'annotations',
          group: 'show',
          icon: TOGGLE_ANNOTATIONS_ICON,
          label: 'Annotations',
          short: 'Annotations',
          active: this.annotationsVisible,
          run: () => {
            this.annotationsVisible = !this.annotationsVisible
          },
        },
      ]
      if (this.hasFragmentMatches) {
        tools.push({
          id: 'fragment-ions',
          group: 'show',
          icon: TOGGLE_FRAGMENTS_ICON,
          label: 'Fragment ions',
          short: 'Fragments',
          active: this.fragmentIonsVisible,
          run: () => {
            this.fragmentIonsVisible = !this.fragmentIonsVisible
          },
        })
      }
      if (this.isMzMode) {
        tools.push({
          id: 'deconvolved-peaks',
          group: 'show',
          icon: TOGGLE_PEAKS_ICON,
          label: 'Deconvolved peaks',
          short: 'Deconvolved',
          active: this.deconvolvedPeaksHighlightMode,
          run: () => {
            this.deconvolvedPeaksHighlightMode = !this.deconvolvedPeaksHighlightMode
          },
        })
      }
      tools.push(
        downloadTool({
          plotId: this.id,
          format: () => imageFormatOf(this.args.imageFormat),
          filename: () => this.args.svgFilename || 'spectrum',
        }),
      )
      return tools
    },
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

    /** The fragment ions the sequence view matched on this spectrum, or null */
    fragmentMatches(): FragmentMatches | null {
      const id = this.args.fragmentMatchesIdentifier
      if (!id) return null
      const matches = this.selectionStore.$state[id] as FragmentMatches | null | undefined
      const keyColumn = this.args.spectrumKeyColumn
      const key = keyColumn ? this.row[keyColumn] : undefined
      return matchesSpectrum(matches, key) ? (matches as FragmentMatches) : null
    },
    fragmentMatchesJson(): string {
      return JSON.stringify(this.fragmentMatches)
    },
    hasFragmentMatches(): boolean {
      return (this.fragmentMatches?.fragments.length ?? 0) > 0
    },
    /** Masses and raw peaks the fragment ions explain */
    fragmentMarks(): FragmentMarks | null {
      const matches = this.fragmentMatches
      if (!matches || matches.fragments.length === 0) return null
      const intensities = this.row[this.args.massIntensityColumn]
      const peakIntensities = this.args.peakIntensityColumn ? this.row[this.args.peakIntensityColumn] : undefined
      return fragmentMarks(
        matches,
        this.MassValues,
        Array.isArray(intensities) ? (intensities as number[]) : [],
        this.MZValues,
        Array.isArray(peakIntensities) ? (peakIntensities as number[]) : [],
        this.mzSignals,
      )
    },
    /** Kind of fragment ion per drawn mass or peak, while they are shown */
    fragmentKindPos(): (FragmentKind | undefined)[] {
      const marks = this.fragmentMarks
      if (!marks || !this.fragmentIonsVisible || !this.annotationsVisible) return []
      return this.isMzMode ? marks.peakKinds : marks.massKinds
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
    envelopeJson(): string {
      return JSON.stringify(this.args.envelope ?? null)
    },
    /** Theoretical isotope envelope of the selected mass as open circles on
     * its raw peaks; drawn only while the mass it was computed for is selected. */
    envelopeTrace(): Plotly.Data | null {
      const envelope = this.args.envelope
      if (!envelope || !this.isMzMode || !this.annotationsVisible) return null
      if (envelope.massIndex !== this.selectedMassIndex) return null
      const n = Math.min(envelope.mzs.length, envelope.intensities.length)
      if (n === 0) return null
      // Circles only where the zoom puts neighbouring isotopes far enough apart
      // to tell them apart; zoomed out they would merge into one red smear.
      const [x0, x1] = this.xRange
      const pixelsPerMz = this.xAxisPixelLength() / Math.max(x1 - x0, 1e-9)
      const spacing = this.envelopeIsotopeSpacing(envelope.mzs.slice(0, n), envelope.charges)
      const x: number[] = []
      const y: number[] = []
      const hover: string[] = []
      for (let i = 0; i < n; i++) {
        if (spacing[i] * pixelsPerMz < ENVELOPE_MIN_SPACING_PX) continue
        const charge = envelope.charges?.[i]
        const isotope = envelope.isotopes?.[i]
        x.push(envelope.mzs[i])
        y.push(envelope.intensities[i])
        hover.push(
          `Theoretical m/z ${envelope.mzs[i].toFixed(4)}` +
            (charge !== undefined ? `<br>z=${charge}` : '') +
            (isotope !== undefined ? `, isotope ${isotope}` : ''),
        )
      }
      if (x.length === 0) return null
      return {
        x,
        y,
        mode: 'markers',
        type: 'scatter',
        name: 'Theoretical envelope',
        marker: {
          symbol: 'circle-open',
          size: 9,
          color: this.styling.envelopeColor,
          line: { width: 1.5, color: this.styling.envelopeColor },
        },
        hoverinfo: 'text',
        hovertext: hover,
      } as Plotly.Data
    },
    isolationWindowJson(): string {
      return JSON.stringify(this.args.isolationWindow ?? null)
    },
    /** The isolation window, in the m/z views only */
    isolationWindow(): { lower: number; upper: number; target?: number } | null {
      const window = this.args.isolationWindow
      if (!window || !this.isMzMode) return null
      if (!Number.isFinite(window.lower) || !Number.isFinite(window.upper)) return null
      return window
    },
    isolationWindowShapes(): Partial<Plotly.Shape>[] {
      const window = this.isolationWindow
      if (!window) return []
      const color = this.styling.isolationWindowColor
      const shapes: Partial<Plotly.Shape>[] = [
        {
          type: 'rect',
          xref: 'x',
          yref: 'paper',
          x0: window.lower,
          x1: window.upper,
          y0: 0,
          y1: 1,
          fillcolor: color,
          opacity: 0.25,
          line: { width: 0 },
          layer: 'below',
        },
      ]
      if (window.target !== undefined && Number.isFinite(window.target)) {
        shapes.push({
          type: 'line',
          xref: 'x',
          yref: 'paper',
          x0: window.target,
          x1: window.target,
          y0: 0,
          y1: 1,
          line: { color, width: 1, dash: 'dash' },
          layer: 'below',
        })
      }
      return shapes
    },
    isolationWindowAnnotations(): Partial<Plotly.Annotations>[] {
      const window = this.isolationWindow
      if (!window) return []
      return [
        {
          x: (window.lower + window.upper) / 2,
          y: 1,
          xref: 'x',
          yref: 'paper',
          yanchor: 'bottom',
          text: `Isolation window ${window.lower.toFixed(2)}–${window.upper.toFixed(2)}`,
          showarrow: false,
          font: { size: 11, color: this.styling.isolationWindowColor },
        },
      ]
    },
    ladderKey(): unknown {
      return this.args.ladder ? this.args.ladder.key ?? JSON.stringify(this.args.ladder.masses) : null
    },
    /**
     * The residues of each gap of the tag (masses[i] to masses[i + 1]). The
     * Python side assigns them by mass (a gap may hold several residues); an
     * older one sends none, and the gaps then read the sequence backwards, one
     * residue each.
     */
    ladderLabels(): string[] {
      const ladder = this.args.ladder
      if (!ladder) return []
      if (Array.isArray(ladder.labels)) return ladder.labels
      const sequence = ladder.sequence ?? ''
      return ladder.masses.slice(1).map((_, i) => sequence[sequence.length - 1 - i] ?? '')
    },
    /** The gap of the tag holding the selected residue (index into ladderLabels). */
    selectedGap(): number | undefined {
      const ladder = this.args.ladder
      if (!ladder) return undefined
      if ('selectedGap' in ladder) return ladder.selectedGap ?? undefined
      if (ladder.selectedIndex === null || ladder.selectedIndex === undefined) return undefined
      return ladder.sequence.length - 1 - ladder.selectedIndex
    },
    /**
     * The tag's masses found in the spectrum: their position in MassValues and
     * in the tag. A tag mass missing from the spectrum joins its two gaps.
     */
    ladderMatches(): { position: number; tagIndex: number }[] {
      const matches: { position: number; tagIndex: number }[] = []
      const tagMasses = this.args.ladder?.masses ?? []
      tagMasses.forEach((v, tagIndex) => {
        for (let j = 0; j < this.MassValues.length; j++) {
          if (Math.abs(this.MassValues[j] - v) < 1e-5) {
            matches.push({ position: j, tagIndex })
            break
          }
        }
      })
      return matches
    },
    /**
     * Index (into the drawn tag masses) of the first mass of the drawn step
     * holding the selected residue, or undefined.
     */
    selectedStep(): number | undefined {
      const gap = this.selectedGap
      if (gap === undefined) return undefined
      const matches = this.ladderMatches
      for (let i = 0; i < matches.length - 1; i++) {
        if (matches[i].tagIndex <= gap && gap < matches[i + 1].tagIndex) return i
      }
      return undefined
    },
    /** Positions (into MassValues) of the two masses around the selected residue. */
    selectedStepPositions(): Set<number> {
      const step = this.selectedStep
      const matches = this.ladderMatches
      if (step === undefined || this.mode !== 'ladder') return new Set()
      return new Set([matches[step].position, matches[step + 1].position])
    },
    showBackButton(): boolean {
      return this.hasLadder && this.mode === 'ladder-annotated'
    },

    /** Positions (into MassValues) highlighted by the tag or the mass selection. */
    selectedMassPositions(): number[] {
      let positions: number[] = this.ladderMatches.map((match) => match.position)
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
        N_x: [] as number[],
        N_y: [] as number[],
        C_x: [] as number[],
        C_y: [] as number[],
        I_x: [] as number[],
        I_y: [] as number[],
      }
      const mask = this.isMzMode ? this.highlightedMzPos : this.highlightedMassPos
      const selectedPositions = this.selectedStepPositions
      const fragmentKinds = this.fragmentKindPos
      for (let i = 0; i < this.xValues.length; i++) {
        const peak = Math.floor(i / 3)
        const posHighlight = mask[peak]
        if (posHighlight === undefined) continue
        const fragmentKind = fragmentKinds[peak]
        if (posHighlight && selectedPositions.has(peak)) {
          result.selected_x.push(this.xValues[i])
          result.selected_y.push(this.yValues[i])
        } else if (posHighlight) {
          result.highlighted_x.push(this.xValues[i])
          result.highlighted_y.push(this.yValues[i])
        } else if (fragmentKind !== undefined) {
          result[`${fragmentKind}_x`].push(this.xValues[i])
          result[`${fragmentKind}_y`].push(this.yValues[i])
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

      // Raw peaks of the highlighted masses: all of them, and the isolation window
      if (this.isMzMode) {
        const window = this.isolationWindow
        if (window) values.push(window.lower, window.upper)
        return [Math.min(...values) * 0.98, Math.max(...values) * 1.02]
      }

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
        const chargeLabels: PlotLabel[] = []
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
            // Below the label traces, which draw the text
            layer: 'between' as 'below',
          })
          chargeLabels.push({
            x: center,
            y: ypos,
            text: 'z=' + charge,
            color: readableTextOn(this.styling.annotationColors.massButton),
          })
        })
        const chargeTrace = labelTrace(chargeLabels)
        if (chargeTrace) buttonTraces.push(chargeTrace)
        return { shapes: buttonShapes, annotations: buttonAnnotations, traces: buttonTraces }
      }

      // Mass buttons and, for a tag, the ladder arrows between them
      const arrowAnnotations: Partial<Plotly.Annotations>[] = []
      // In the ladder view the highlights are the tag's masses (ladderMatches)
      const isLadder = this.mode === 'ladder'
      const selectedStep = isLadder ? this.selectedStep : undefined
      const matches = this.ladderMatches
      const labels = this.ladderLabels
      const visibleMassBoxes = this.annotationBoxData.filter((box) => box.type === 'mass' && box.visible)
      const scaling = highlighted.length === 1 ? 2 : 1
      const massLabels: PlotLabel[] = []
      const residueLabels: PlotLabel[] = []

      for (let i = 0; i < highlighted.length; i++) {
        const mass = highlighted[i].mass
        if (!isFinite(mass)) continue
        if (!visibleMassBoxes.some((box) => box.index === i)) continue
        let fillcolor = this.styling.annotationColors.massButton
        let family = 'sans-serif'
        if (selectedStep !== undefined && (selectedStep === i || selectedStep === i - 1)) {
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
          layer: 'between' as 'below',
        })
        massLabels.push({ x: mass, y: ypos, text: mass.toFixed(2), color: readableTextOn(fillcolor), family })
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
        if (selectedStep !== undefined && selectedStep === i) {
          fillcolor = this.styling.annotationColors.selectedSequenceArrow
          family = 'Arial Black, Arial Bold, Arial, sans-serif'
        }
        let xStart = current.mass
        let xEnd = next.mass
        const xMid = (xStart + xEnd) / 2
        let xMidStart = xMid
        let xMidEnd = xMid
        const diff = Math.abs(xStart - xEnd) * 0.9
        let residues = ''
        let delta = 0
        if (isLadder && sequence !== undefined && sequence.length > 0 && i + 1 < matches.length) {
          // The residues of every tag gap between these two masses
          residues = labels.slice(matches[i].tagIndex, matches[i + 1].tagIndex).join('')
        }
        const AA = ladderLabelText(residues)
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
        // Annotations are not clipped to the plot: draw only the part of
        // each segment inside the x range
        const segments = [
          clipArrow(xMidStart, xStart, this.xRange),
          clipArrow(xMidEnd, xEnd, this.xRange),
        ]
        segments.forEach((segment, s) => {
          if (!segment) return
          arrowAnnotations.push({
            ax: segment.tail,
            ay: yPosArrow,
            xref: 'x',
            yref: 'y',
            x: segment.head,
            y: yPosArrow,
            axref: 'x',
            ayref: 'y',
            showarrow: true,
            arrowhead: s === 1 && segment.headVisible ? 2 : 0,
            arrowsize: 1,
            arrowwidth: 2,
            arrowcolor: fillcolor,
          })
        })
        residueLabels.push({
          x: xMid,
          y: yPosAA,
          text: AA,
          color: fillcolor,
          family,
          hover: (residues.length > 1 ? wrapResidues(residues) + '<br>' : '') + 'Δ=' + delta.toFixed(2) + ' Da',
        })
      }
      for (const trace of [labelTrace(massLabels), labelTrace(residueLabels)]) {
        if (trace) buttonTraces.push(trace)
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
        ...this.fragmentTraces,
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
      if (this.envelopeTrace) traces.push(this.envelopeTrace)
      if (this.annotationsVisible) traces.push(...this.annotationData.traces)
      return traces
    },
    fragmentColors(): Record<FragmentKind, string> {
      return {
        N: this.styling.nTermColor,
        C: this.styling.cTermColor,
        I: this.styling.internalColor,
      }
    },
    /** Sticks of the fragment ions, one trace per kind, with the ion names on hover */
    fragmentTraces(): Plotly.Data[] {
      const marks = this.fragmentMarks
      if (!marks || this.fragmentKindPos.length === 0) return []
      const traces: Plotly.Data[] = []
      for (const kind of FRAGMENT_KINDS) {
        const x = this.plotData[`${kind}_x`]
        const y = this.plotData[`${kind}_y`]
        if (x.length === 0) continue
        traces.push({
          x,
          y,
          mode: 'lines',
          type: 'scatter',
          name: FRAGMENT_KIND_NAMES[kind],
          line: { color: this.fragmentColors[kind], width: 1.5 },
          hoverinfo: 'skip',
        } as Plotly.Data)
      }
      // Hover: the names of the ions at each marked mass or peak
      const hover = this.isMzMode ? marks.peakHover : marks.massHover
      const xs = this.xColumnValues
      const ys = this.yColumnValues
      const hx: number[] = []
      const hy: number[] = []
      const ht: string[] = []
      const kinds = this.fragmentKindPos
      hover.forEach((text, i) => {
        if (text === undefined || kinds[i] === undefined) return
        hx.push(xs[i])
        hy.push(ys[i])
        ht.push(`${text}<br>${this.isMzMode ? 'm/z' : 'Mass'} ${xs[i]?.toFixed(4)}`)
      })
      if (hx.length > 0) {
        traces.push({
          x: hx,
          y: hy,
          mode: 'markers',
          type: 'scatter',
          marker: { size: 8, opacity: 0 },
          hoverinfo: 'text',
          hovertext: ht,
          showlegend: false,
        } as Plotly.Data)
      }
      return traces
    },
    /** Ion names above their peaks, as many as fit */
    fragmentLabelAnnotations(): Partial<Plotly.Annotations>[] {
      const marks = this.fragmentMarks
      if (!marks || this.fragmentKindPos.length === 0) return []
      const labels: FragmentLabel[] = this.isMzMode ? marks.peakLabels : marks.massLabels
      const [x0, x1] = this.xRange
      const pixelsPerX = this.xAxisPixelLength() / Math.max(x1 - x0, 1e-9)
      // The selected mass carries its own label
      const selected = this.selectedMassIndex
      const skip =
        !this.isMzMode && selected !== undefined && selected < this.MassValues.length
          ? this.MassValues[selected]
          : undefined
      return visibleLabels(
        labels.filter((label) => label.x !== skip),
        this.xRange,
        pixelsPerX,
        FRAGMENT_LABEL_SPACING_PX,
      ).map((label) => ({
        x: label.x,
        y: label.y,
        xref: 'x',
        yref: 'y',
        yanchor: 'bottom',
        yshift: 2,
        textangle: '-90',
        text: label.text,
        showarrow: false,
        font: { size: 11, color: this.fragmentColors[label.kind] },
      }))
    },
    layout(): Partial<Plotly.Layout> {
      return {
        title: { text: `<b>${this.currentTitle}</b>` },
        showlegend: false,
        height: (this.args.height || 400) - TOOLBAR_HEIGHT,
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
        shapes: [
          ...this.isolationWindowShapes,
          ...this.annotationData.shapes,
          ...this.measureOverlay.shapes,
        ],
        annotations: [
          ...this.isolationWindowAnnotations,
          ...this.fragmentLabelAnnotations,
          ...this.annotationData.annotations,
          ...this.measureOverlay.annotations,
        ],
      }
    },
    /**
     * Differences between masses are neutral: matched to residue masses as
     * they are (1+). Between raw peaks they are m/z: matched at 1+ and 2+.
     */
    measureSpec(): MeasureSpec {
      return {
        kind: 'span',
        xQuantity: this.isMzMode ? 'm/z' : 'mass',
        charges: this.isMzMode ? MEASURE_CHARGES : [1],
        tolerance: this.args.measureTolerance,
        residues: this.args.measureResidues,
      }
    },
    measureTitle(): string {
      return this.isMzMode
        ? 'click two peaks for their m/z difference (Esc cancels)'
        : 'click two masses for their difference (Esc cancels)'
    },
    /** Identity of the plotted masses or peaks: others drop the measurements. */
    measureKey(): string {
      return `${this.isMzMode ? 'mz' : 'mass'}|${pointsKey(this.xColumnValues, this.yColumnValues)}`
    },
    /** Brackets of the measurements, spaced by the tallest visible peak. */
    measureOverlay(): MeasureOverlay {
      return this.measure.overlay({
        color: this.theme?.textColor || '#262730',
        background: this.theme?.backgroundColor || 'white',
        yScale: this.yRange[1] / 1.8,
      })
    },
    cssCustomProperties(): Record<string, string> {
      return {
        '--annotation-background': this.styling.annotationColors.background,
        '--button-hover-color': this.styling.annotationColors.buttonHover,
      }
    },
  },
  watch: {
    // A zoom set from Python (a saved view opened)
    zoomStamp() {
      if (this.applyIncomingZoom()) this.requestGraph()
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
      if (!this.isDataReady) return
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
        // A new spectrum: forget the zoom of the previous one, unless pinned
        // or a zoom came with it (a saved view opened)
        if (!this.applyIncomingZoom() && !this.pinZoom.pinned) {
          if (this.manual) this.zoom.report(null)
          this.manual = false
          this.manualXRange = undefined
        }
        this.requestGraph()
      },
      deep: true,
    },
    ladderKey(newKey: unknown, oldKey: unknown) {
      if (newKey !== oldKey) {
        // A pinned zoom outlives the reset of the drill-down state
        const { manual, manualXRange } = this
        this.resetManualState()
        if (this.pinZoom.pinned) {
          this.manual = manual
          this.manualXRange = manualXRange
        }
        this.applyIncomingZoom()
        this.requestGraph()
      }
    },
    // By value: the arguments arrive as a new object on every rerun
    ladderJson() {
      this.requestGraph()
    },
    envelopeJson() {
      this.requestGraph()
    },
    isolationWindowJson() {
      this.requestGraph()
    },
    // By value: the selection store gets a new object on every rerun
    fragmentMatchesJson() {
      this.requestGraph()
    },
    fragmentIonsVisible() {
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
    this.applyIncomingZoom()
    this.requestGraph()
  },
  methods: {
    /** Show a zoom set from outside; false if none came. */
    applyIncomingZoom(): boolean {
      const incoming = this.zoom.incoming()
      if (incoming === undefined) return false
      this.manual = !!incoming?.x
      this.manualXRange = incoming?.x
      return true
    },
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
    /** Width in pixels of the x axis: the plot area without the margins. */
    xAxisPixelLength(): number {
      const element = document.getElementById(this.id) as
        | (HTMLElement & { _fullLayout?: { xaxis?: { _length?: number } } })
        | null
      const length = element?._fullLayout?.xaxis?._length
      if (length && length > 0) return length
      const width = this.plotWidth()
      return width > 0 ? Math.max(width - 160, 100) : 1000
    },
    /** m/z distance from each envelope peak to the next isotope of its charge:
     * the isotope spacing over the charge, or, without charges, the distance to
     * the nearest other peak. */
    envelopeIsotopeSpacing(mzs: number[], charges?: number[]): number[] {
      if (charges && charges.length >= mzs.length) {
        return mzs.map((_, i) => (charges[i] > 0 ? ISOTOPE_SPACING / charges[i] : Infinity))
      }
      const order = mzs.map((_, i) => i).sort((a, b) => mzs[a] - mzs[b])
      const spacing = new Array<number>(mzs.length).fill(Infinity)
      for (let k = 0; k < order.length; k++) {
        const here = mzs[order[k]]
        const before = k > 0 ? here - mzs[order[k - 1]] : Infinity
        const after = k < order.length - 1 ? mzs[order[k + 1]] - here : Infinity
        spacing[order[k]] = Math.min(before, after)
      }
      return spacing
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
      // In measure mode a click picks the nearest mass or peak, not a selection
      if (this.measure.active) {
        const x = eventData.points?.[0]?.x
        const xs = this.xColumnValues
        const ys = this.yColumnValues
        if (typeof x !== 'number' || xs.length === 0) return
        let nearest = 0
        for (let i = 1; i < xs.length; i++) {
          if (Math.abs(xs[i] - x) < Math.abs(xs[nearest] - x)) nearest = i
        }
        this.measure.pick({ x: xs[nearest], y: ys[nearest] }, this.measureSpec)
        return
      }
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
        this.zoom.report({ x: newXRange as [number, number] })
        this.requestGraph()
      } else if (eventData['xaxis.autorange'] === true) {
        const xValues = this.xValues
        if (xValues.length === 0) return
        this.manual = true
        this.manualXRange = [Math.min(...xValues), Math.max(...xValues)]
        this.zoom.report(null)
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
      const plot = (await Plotly.newPlot(element, this.traces, this.layout, {
        modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
        displaylogo: false,
        scrollZoom: true,
      })) as unknown as { on: (event: string, handler: (data: never) => void) => void }
      plot.on('plotly_relayout', (eventData: Record<string, unknown>) => this.onRelayout(eventData))
      plot.on('plotly_click', (eventData: { points?: Array<{ x: number }> }) => this.onPlotClick(eventData))
      this.measure.bindLabelClicks(element)
      this.pinZoom.bind(element)
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
          height: (this.args.height || 400) - TOOLBAR_HEIGHT,
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
  top: calc(var(--toolbar-height, 36px) + 14%);
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
