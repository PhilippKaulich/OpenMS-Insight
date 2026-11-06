<template>
  <div class="sequence-view-container" :style="containerStyle">
    <v-sheet class="pa-4 rounded-lg" :theme="theme?.base ?? 'light'" border>
      <!-- Header with mass information -->
      <div class="d-flex justify-center mb-2">
        <h4>Sequence View</h4>
      </div>

      <!-- Toolbar -->
      <div class="d-flex justify-end px-4 mb-4">
        <ImageScreenshot
          :element-id="gridId"
          :filename="args.svgFilename || args.title || 'sequence'"
          :format="args.imageFormat"
          :color="theme?.primaryColor ?? 'primary'"
          size="small"
        />
        <v-btn variant="text" icon size="small" :disabled="sequence.length === 0" @click="copySequence">
          <v-icon>mdi-content-copy</v-icon>
          <v-tooltip activator="parent" location="bottom">Copy sequence to clipboard</v-tooltip>
        </v-btn>

        <v-btn id="settings-btn" variant="text" icon size="small">
          <v-icon>mdi-cog</v-icon>
        </v-btn>
        <v-menu :close-on-content-click="false" activator="#settings-btn" location="bottom">
          <v-card min-width="300">
            <v-list>
              <v-list-item>
                <v-list-item-title># amino acids per row</v-list-item-title>
                <v-slider
                  v-model="rowWidth"
                  :ticks="{ 20: '20', 25: '25', 30: '30', 35: '35', 40: '40' }"
                  :min="20"
                  :max="40"
                  step="5"
                  show-ticks="always"
                  tick-size="4"
                ></v-slider>
              </v-list-item>
              <v-list-item>
                <v-list-item-title>Font Size</v-list-item-title>
                <v-slider
                  v-model="fontSize"
                  :ticks="{ 8: '8', 10: '10', 12: '12', 14: '14', 16: '16' }"
                  :min="8"
                  :max="16"
                  step="2"
                  show-ticks="always"
                  tick-size="4"
                ></v-slider>
              </v-list-item>
              <v-list-item>
                <v-list-item-title>Show Fragments</v-list-item-title>
                <v-checkbox v-model="showFragments" hide-details density="comfortable"></v-checkbox>
              </v-list-item>
              <v-list-item>
                <v-list-item-title>Fragment ion types</v-list-item-title>
                <div class="d-flex justify-space-evenly">
                  <v-checkbox
                    v-for="ion in ionTypes"
                    :key="ion.text"
                    v-model="ion.selected"
                    :label="ion.text"
                    :disabled="!showFragments"
                    hide-details
                    density="comfortable"
                  ></v-checkbox>
                </div>
                <div class="d-flex justify-space-evenly">
                  <v-checkbox
                    v-for="(_, extra) in ionTypesExtra"
                    :key="extra"
                    v-model="ionTypesExtra[extra as ExtraFragmentType]"
                    :label="extra"
                    :disabled="!showFragments"
                    hide-details
                    density="comfortable"
                  ></v-checkbox>
                </div>
              </v-list-item>
              <v-list-item>
                <v-list-item-title>Fragment mass tolerance</v-list-item-title>
                <div class="d-flex align-center ga-2">
                  <v-text-field
                    v-model.number="fragmentMassTolerance"
                    type="number"
                    hide-details="auto"
                    :disabled="!showFragments"
                    density="compact"
                    style="max-width: 100px"
                  ></v-text-field>
                  <v-btn-toggle v-model="toleranceIsPpm" mandatory density="compact" :disabled="!showFragments">
                    <v-btn :value="true" size="small">ppm</v-btn>
                    <v-btn :value="false" size="small">Da</v-btn>
                  </v-btn-toggle>
                </div>
              </v-list-item>
              <v-list-item v-if="hasExternalAnnotations">
                <v-list-item-title>Use search engine annotations</v-list-item-title>
                <v-checkbox
                  v-model="useExternalAnnotations"
                  :disabled="!showFragments"
                  hide-details
                  density="comfortable"
                ></v-checkbox>
                <v-list-item-subtitle class="text-caption">
                  {{ externalAnnotations.length }} annotations from idXML
                </v-list-item-subtitle>
              </v-list-item>
            </v-list>
          </v-card>
        </v-menu>
      </div>

      <!-- Sequence grid -->
      <div :id="gridId" class="px-2 pb-4" :class="gridClasses" style="width: 100%; max-width: 100%">
        <template v-for="(aaObj, aaIndex) in sequenceObjects" :key="aaIndex">
          <!-- Row number (left) -->
          <div
            v-if="aaIndex !== 0 && aaIndex % rowWidth === 0"
            class="d-flex justify-center align-center row-number"
          >
            {{ aaIndex + 1 }}
          </div>

          <!-- N-terminal marker -->
          <div v-if="aaIndex === 0" class="d-flex justify-center align-center terminal-cell">N</div>

          <!-- Amino acid cell -->
          <AminoAcidCell
            :sequence-object="aaObj"
            :index="aaIndex"
            :sequence-length="sequence.length"
            :fixed-modification="isFixedModification(aaObj.aminoAcid)"
            :show-fragments="showFragments"
            :font-size="fontSize"
            :is-highlighted="selectedAAIndex === aaIndex"
            :modification="modifications[aaIndex] ?? null"
            @selected="onAminoAcidSelected"
          />

          <!-- Row number (right) -->
          <div
            v-if="aaIndex % rowWidth === rowWidth - 1 && aaIndex !== sequence.length - 1"
            class="d-flex justify-center align-center row-number"
          >
            {{ aaIndex + 1 }}
          </div>

          <!-- C-terminal marker -->
          <div
            v-if="aaIndex === sequence.length - 1"
            class="d-flex justify-center align-center terminal-cell"
          >
            C
          </div>
        </template>
      </div>

      <!-- Fragment table -->
      <div v-if="showFragments && fragmentTableData.length > 0" class="mt-4">
        <v-divider class="mb-4"></v-divider>
        <div class="d-flex justify-space-between align-center mb-2">
          <h5>Matching Fragments ({{ fragmentTableData.length }})</h5>
          <span class="text-caption">Residue cleavage: {{ residueCleavagePercentage.toFixed(1) }}%</span>
        </div>
        <v-data-table
          :headers="fragmentTableHeaders"
          :items="fragmentTableData"
          :items-per-page="10"
          density="compact"
          class="elevation-1"
          :row-props="getRowProps"
          @click:row="onFragmentTableRowClick"
        ></v-data-table>
      </div>
    </v-sheet>

    <!-- Copy snackbar -->
    <v-snackbar v-model="copySnackbar" :timeout="2000" location="bottom">
      {{ copySnackbarText }}
    </v-snackbar>
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import type { SequenceData, SequenceObject, FragmentTableRow, ExternalAnnotation } from '@/types/sequence-data'
import AminoAcidCell from './AminoAcidCell.vue'
import ImageScreenshot from '@/components/protein/ImageScreenshot.vue'
import { extraFragmentTypeObject, type ExtraFragmentType } from './modification'

// Proton mass for m/z calculations
const PROTON_MASS = 1.007276

// Superscript characters for charge display
const SUPERSCRIPT_DIGITS: Record<string, string> = {
  '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
  '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'
}

function toSuperscript(n: number): string {
  return String(n).split('').map(d => SUPERSCRIPT_DIGITS[d] || d).join('')
}

export default defineComponent({
  name: 'SequenceView',
  components: {
    AminoAcidCell,
    ImageScreenshot,
  },
  props: {
    args: {
      type: Object,
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
      rowWidth: 35,
      fontSize: 12,
      autoZoomApplied: false,
      showFragments: true,
      ionTypes: [
        { text: 'a', selected: false },
        { text: 'b', selected: true },
        { text: 'c', selected: false },
        { text: 'x', selected: false },
        { text: 'y', selected: true },
        { text: 'z', selected: false },
      ],
      ionTypesExtra: {
        'water loss': false,
        'ammonium loss': false,
        'proton loss/addition': false,
      } as Record<ExtraFragmentType, boolean>,
      fragmentMassTolerance: 10,
      toleranceIsPpm: true,
      // Track if settings have been initialized from Python defaults.
      // Once initialized, user adjustments persist across filter changes.
      settingsInitialized: false,
      useExternalAnnotations: true,
      sequenceObjects: [] as SequenceObject[],
      fragmentTableData: [] as FragmentTableRow[],
      selectedAAIndex: undefined as number | undefined,
      selectedFragmentRowIndex: undefined as number | undefined,
      copySnackbar: false,
      copySnackbarText: '',
    }
  },
  computed: {
    /** Element saved by the image download: the sequence grid */
    gridId(): string {
      return `sequence-view-grid-${this.index}`
    },
    containerStyle(): Record<string, string> {
      return {
        height: `${this.args.height || 400}px`,
        overflowY: 'auto'
      }
    },
    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },
    sequenceData(): SequenceData | undefined {
      return this.streamlitDataStore.allDataForDrawing.sequenceData as SequenceData | undefined
    },
    observedMasses(): number[] {
      return (this.streamlitDataStore.allDataForDrawing.observedMasses as number[]) ?? []
    },
    /** Peak IDs corresponding to observed masses (for interactivity linking) */
    peakIds(): number[] | undefined {
      return this.streamlitDataStore.allDataForDrawing.peakIds as number[] | undefined
    },
    precursorMass(): number {
      return (this.streamlitDataStore.allDataForDrawing.precursorMass as number) ?? 0
    },
    /** Interactivity mapping from component args */
    interactivity(): Record<string, string> {
      return (this.args.interactivity as Record<string, string>) ?? {}
    },
    /** Whether data is deconvolved (neutral masses) or not (m/z values) */
    deconvolved(): boolean {
      return (this.args.deconvolved as boolean) ?? true
    },
    /** Maximum charge state to consider for fragment matching */
    maxCharge(): number {
      return (this.streamlitDataStore.allDataForDrawing?.precursorCharge as number) ?? 1
    },
    sequence(): string[] {
      return this.sequenceData?.sequence ?? []
    },
    modifications(): (number | null)[] {
      return this.sequenceData?.modifications ?? []
    },
    theoreticalMass(): number {
      return this.sequenceData?.theoretical_mass ?? 0
    },
    fixedModificationSites(): string[] {
      return this.sequenceData?.fixed_modifications ?? []
    },
    /** External annotations from search engine if available */
    externalAnnotations(): ExternalAnnotation[] {
      return this.sequenceData?.external_annotations ?? []
    },
    /** Whether external annotations are available */
    hasExternalAnnotations(): boolean {
      return this.externalAnnotations.length > 0
    },
    /** Default tolerance from search parameters */
    defaultTolerance(): number {
      return this.sequenceData?.fragment_tolerance ?? 10
    },
    /** Default tolerance type from search parameters */
    defaultToleranceIsPpm(): boolean {
      return this.sequenceData?.fragment_tolerance_ppm ?? true
    },
    gridClasses(): Record<string, boolean> {
      return {
        'sequence-grid': true,
        [`grid-width-${this.rowWidth}`]: true,
      }
    },
    residueCleavagePercentage(): number {
      if (this.sequenceObjects.length <= 1) return 0

      let explainedCleavage = 0
      for (let i = 0; i < this.sequenceObjects.length - 1; i++) {
        const preAA = this.sequenceObjects[i]
        const postAA = this.sequenceObjects[i + 1]
        if (preAA.aIon || preAA.bIon || preAA.cIon || postAA.xIon || postAA.yIon || postAA.zIon) {
          explainedCleavage++
        }
      }
      return (explainedCleavage / (this.sequence.length - 1)) * 100
    },
    fragmentTableHeaders() {
      const headers = [
        { title: 'Name', key: 'Name', sortable: true },
        { title: 'Ion Type', key: 'IonType', sortable: true },
        { title: 'Ion #', key: 'IonNumber', sortable: true },
      ]
      // Add Charge column for non-deconvolved data
      if (!this.deconvolved) {
        headers.push({ title: 'z', key: 'Charge', sortable: true })
      }
      headers.push(
        { title: this.deconvolved ? 'Theo. Mass' : 'Theo. m/z', key: 'TheoreticalMass', sortable: true },
        { title: this.deconvolved ? 'Obs. Mass' : 'Obs. m/z', key: 'ObservedMass', sortable: true },
        { title: 'Δ Da', key: 'MassDiffDa', sortable: true },
        { title: 'Δ ppm', key: 'MassDiffPpm', sortable: true },
      )
      return headers
    },
  },
  watch: {
    'args.height'() {
      this.$nextTick(() => Streamlit.setFrameHeight())
    },
    sequenceData: {
      handler(newData, oldData) {
        // Reset auto-zoom flag when sequence changes
        const newSeq = newData?.sequence?.join('') ?? ''
        const oldSeq = oldData?.sequence?.join('') ?? ''
        if (newSeq !== oldSeq) {
          this.autoZoomApplied = false
        }

        this.initializeSequenceObjects()

        // Apply auto-zoom for short sequences
        this.applyAutoZoom()

        // Initialize settings from Python defaults ONLY on first load.
        // Once initialized, user adjustments persist across filter changes.
        if (!this.settingsInitialized) {
          if (this.sequenceData?.fragment_tolerance !== undefined) {
            this.fragmentMassTolerance = this.sequenceData.fragment_tolerance
          }
          if (this.sequenceData?.fragment_tolerance_ppm !== undefined) {
            this.toleranceIsPpm = this.sequenceData.fragment_tolerance_ppm
          }
          if (this.sequenceData?.neutral_losses !== undefined) {
            this.ionTypesExtra['water loss'] = this.sequenceData.neutral_losses
            this.ionTypesExtra['ammonium loss'] = this.sequenceData.neutral_losses
          }
          if (this.sequenceData?.proton_loss_addition !== undefined) {
            this.ionTypesExtra['proton loss/addition'] = this.sequenceData.proton_loss_addition
          }
          this.settingsInitialized = true
        }
        this.matchFragments()
      },
      immediate: true,
      deep: true,
    },
    observedMasses: {
      handler() {
        this.matchFragments()
      },
      deep: true,
    },
    ionTypes: {
      handler() {
        this.resetFragmentMarkers()
        this.matchFragments()
      },
      deep: true,
    },
    ionTypesExtra: {
      handler() {
        this.resetFragmentMarkers()
        this.matchFragments()
      },
      deep: true,
    },
    fragmentMassTolerance() {
      this.resetFragmentMarkers()
      this.matchFragments()
    },
    toleranceIsPpm() {
      this.resetFragmentMarkers()
      this.matchFragments()
    },
    useExternalAnnotations() {
      this.resetFragmentMarkers()
      this.matchFragments()
    },
  },
  mounted() {
    // The view has a fixed height; the frame does not follow it by itself
    this.$nextTick(() => Streamlit.setFrameHeight())
  },
  methods: {
    initializeSequenceObjects(): void {
      this.sequenceObjects = []
      for (const aa of this.sequence) {
        this.sequenceObjects.push({
          aminoAcid: aa,
          aIon: false,
          bIon: false,
          cIon: false,
          xIon: false,
          yIon: false,
          zIon: false,
          extraTypes: [],
        })
      }
    },
    /**
     * Apply auto-zoom for short sequences.
     * If the sequence fits on one line at minimum rowWidth (20),
     * set rowWidth to minimum and fontSize to maximum for maximum zoom.
     * Only applies once per sequence to avoid overriding user preferences.
     */
    applyAutoZoom(): void {
      if (this.autoZoomApplied) return

      const minRowWidth = 20
      const maxFontSize = 16

      // If sequence fits on one line at minimum row width, apply max zoom
      // (minimum AAs per row = maximum zoom level)
      if (this.sequence.length > 0 && this.sequence.length <= minRowWidth) {
        this.rowWidth = minRowWidth
        this.fontSize = maxFontSize
      }

      this.autoZoomApplied = true
    },
    resetFragmentMarkers(): void {
      for (const obj of this.sequenceObjects) {
        obj.aIon = false
        obj.bIon = false
        obj.cIon = false
        obj.xIon = false
        obj.yIon = false
        obj.zIon = false
        obj.extraTypes = []
      }
    },
    getFragmentMasses(ionType: string): number[][] {
      if (!this.sequenceData) return []
      const key = `fragment_masses_${ionType}` as keyof SequenceData
      return (this.sequenceData[key] as number[][]) ?? []
    },
    /** Check if mass difference is within tolerance */
    isWithinTolerance(massDiffDa: number, theoreticalValue: number): boolean {
      if (this.toleranceIsPpm) {
        const massDiffPpm = Math.abs((massDiffDa / theoreticalValue) * 1e6)
        return massDiffPpm <= this.fragmentMassTolerance
      } else {
        return Math.abs(massDiffDa) <= this.fragmentMassTolerance
      }
    },
    /** Mark amino acid position with matched ion */
    markAminoAcidPosition(ionType: string, ionNumber: number, typeName: string): void {
      const sequenceLength = this.sequence.length
      const isPrefixIon = ['a', 'b', 'c'].includes(ionType)
      const aaIndex = isPrefixIon ? ionNumber - 1 : sequenceLength - ionNumber

      if (aaIndex >= 0 && aaIndex < this.sequenceObjects.length) {
        const aaObj = this.sequenceObjects[aaIndex]
        const ionKey = `${ionType}Ion` as keyof SequenceObject
        ;(aaObj[ionKey] as boolean) = true

        if (typeName) {
          aaObj.extraTypes.push(`${ionType}${typeName}`)
        }
      }
    },
    /** Use external annotations from search engine */
    matchFragmentsExternal(): FragmentTableRow[] {
      const matchingFragments: FragmentTableRow[] = []

      for (const ann of this.externalAnnotations) {
        // Find closest observed peak and track its index for PeakId lookup
        let bestObserved: number | null = null
        let bestObservedIndex = -1
        let bestDiff = Infinity

        for (let obsIdx = 0; obsIdx < this.observedMasses.length; obsIdx++) {
          const observedValue = this.observedMasses[obsIdx]
          const diff = Math.abs(observedValue - ann.mz)
          if (diff < bestDiff) {
            bestDiff = diff
            bestObserved = observedValue
            bestObservedIndex = obsIdx
          }
        }

        if (bestObserved === null) continue

        const massDiffDa = bestObserved - ann.mz
        const massDiffPpm = (massDiffDa / ann.mz) * 1e6

        // Check if within tolerance
        if (!this.isWithinTolerance(massDiffDa, ann.mz)) continue

        // Parse ion number from annotation (e.g., "b5" -> 5)
        let ionNumber = 0
        const numMatch = ann.annotation.match(/[a-z](\d+)/i)
        if (numMatch) {
          ionNumber = parseInt(numMatch[1], 10)
        }

        const fragmentRow: FragmentTableRow = {
          Name: ann.annotation,
          IonType: ann.ion_type,
          IonNumber: ionNumber,
          TheoreticalMass: ann.mz.toFixed(3),
          ObservedMass: bestObserved,
          MassDiffDa: massDiffDa.toFixed(3),
          MassDiffPpm: massDiffPpm.toFixed(3),
        }

        if (ann.charge > 1) {
          fragmentRow.Charge = ann.charge
        }

        // Add PeakId for interactivity linking
        if (this.peakIds && bestObservedIndex >= 0 && this.peakIds[bestObservedIndex] !== undefined) {
          fragmentRow.PeakId = this.peakIds[bestObservedIndex]
        }

        matchingFragments.push(fragmentRow)

        // Mark amino acid position
        if (ionNumber > 0 && ann.ion_type !== 'unknown') {
          this.markAminoAcidPosition(ann.ion_type, ionNumber, '')
        }
      }

      return matchingFragments
    },
    /** Match fragments using theoretical masses */
    matchFragmentsTheoretical(): FragmentTableRow[] {
      const matchingFragments: FragmentTableRow[] = []
      const sequenceLength = this.sequence.length

      // Get active extra fragment types
      const extraFragments = Object.entries(extraFragmentTypeObject)
        .filter(
          ([type]) => this.ionTypesExtra[type as ExtraFragmentType] || type === 'default'
        )
        .map(([_, fragments]) => fragments)
        .flat()

      // Determine charge states to check
      const chargeStates = this.deconvolved ? [1] : Array.from({ length: this.maxCharge }, (_, i) => i + 1)

      // Process each selected ion type
      for (const ionType of this.ionTypes.filter((t) => t.selected)) {
        const theoreticalFrags = this.getFragmentMasses(ionType.text)

        for (let theoIndex = 0; theoIndex < theoreticalFrags.length; theoIndex++) {
          for (const theoreticalMass of theoreticalFrags[theoIndex]) {
            // Try each extra fragment type
            for (const { typeName, typeMass } of extraFragments) {
              const adjustedNeutralMass = theoreticalMass + typeMass

              // Try each charge state
              for (const charge of chargeStates) {
                // Calculate theoretical m/z (or use neutral mass for deconvolved)
                const theoreticalValue = this.deconvolved
                  ? adjustedNeutralMass
                  : (adjustedNeutralMass + charge * PROTON_MASS) / charge

                // Match against observed masses/m/z values (track index for PeakId lookup)
                for (let obsIdx = 0; obsIdx < this.observedMasses.length; obsIdx++) {
                  const observedValue = this.observedMasses[obsIdx]
                  const massDiffDa = observedValue - theoreticalValue

                  if (this.isWithinTolerance(massDiffDa, theoreticalValue)) {
                    const massDiffPpm = (massDiffDa / theoreticalValue) * 1e6

                    // Found a match - report all matches (multiple charge states)
                    // Include neutral loss/addition in name (e.g., "y5-H2O²⁺")
                    const baseIonName = `${ionType.text}${theoIndex + 1}${typeName}`
                    const ionName = this.deconvolved
                      ? baseIonName
                      : `${baseIonName}${toSuperscript(charge)}⁺`

                    const fragmentRow: FragmentTableRow = {
                      Name: ionName,
                      IonType: `${ionType.text}${typeName}`,
                      IonNumber: theoIndex + 1,
                      TheoreticalMass: theoreticalValue.toFixed(3),
                      ObservedMass: observedValue,
                      MassDiffDa: massDiffDa.toFixed(3),
                      MassDiffPpm: massDiffPpm.toFixed(3),
                    }

                    // Add charge for non-deconvolved data
                    if (!this.deconvolved) {
                      fragmentRow.Charge = charge
                    }

                    // Add PeakId for interactivity linking
                    if (this.peakIds && this.peakIds[obsIdx] !== undefined) {
                      fragmentRow.PeakId = this.peakIds[obsIdx]
                    }

                    matchingFragments.push(fragmentRow)

                    // Mark the amino acid position
                    this.markAminoAcidPosition(ionType.text, theoIndex + 1, typeName)
                  }
                }
              }
            }
          }
        }
      }

      return matchingFragments
    },
    matchFragments(): void {
      if (this.sequence.length === 0 || this.observedMasses.length === 0) {
        this.fragmentTableData = []
        // Clear annotations when no data
        this.streamlitDataStore.setAnnotations(null)
        return
      }

      // Use external annotations if available and enabled
      if (this.useExternalAnnotations && this.hasExternalAnnotations) {
        this.fragmentTableData = this.matchFragmentsExternal()
      } else {
        this.fragmentTableData = this.matchFragmentsTheoretical()
      }

      // Convert fragment table data to annotations for cross-component sharing
      // This enables LinePlot to display fragment annotations
      const peakIds: number[] = []
      const highlightColors: string[] = []
      const annotations: string[] = []

      for (const row of this.fragmentTableData) {
        if (row.PeakId !== undefined) {
          peakIds.push(row.PeakId)
          // Color based on ion type (a/b/c = red-ish, x/y/z = blue-ish)
          const ionType = row.IonType.charAt(0).toLowerCase()
          const color = ['a', 'b', 'c'].includes(ionType) ? '#E4572E' : '#1f77b4'
          highlightColors.push(color)
          annotations.push(row.Name)
        }
      }

      // Update store with annotations (triggers rerun in Python via state change)
      // Also increment selection counter to ensure state is sent reliably
      const prevAnnotations = this.streamlitDataStore.annotations
      const prevPeakIds = prevAnnotations?.peak_id ?? []
      const annotationsChanged = peakIds.length !== prevPeakIds.length ||
        peakIds.some((id, i) => id !== prevPeakIds[i])

      if (peakIds.length > 0) {
        this.streamlitDataStore.setAnnotations({
          peak_id: peakIds,
          highlight_color: highlightColors,
          annotation: annotations,
        })
      } else {
        this.streamlitDataStore.setAnnotations(null)
      }

      // Force counter increment when annotations change to ensure state is sent
      if (annotationsChanged) {
        this.selectionStore.$patch({ counter: (this.selectionStore.$state.counter || 0) + 1 })
      }
    },
    isFixedModification(aminoAcid: string): boolean {
      return this.fixedModificationSites.includes(aminoAcid)
    },
    onAminoAcidSelected(aaIndex: number): void {
      this.selectedAAIndex = aaIndex

      // Find corresponding fragment in table
      const aaObj = this.sequenceObjects[aaIndex]
      let ionName = ''

      if (aaObj.bIon) ionName = `b${aaIndex + 1}`
      else if (aaObj.aIon) ionName = `a${aaIndex + 1}`
      else if (aaObj.cIon) ionName = `c${aaIndex + 1}`
      else if (aaObj.yIon) ionName = `y${this.sequence.length - aaIndex}`
      else if (aaObj.xIon) ionName = `x${this.sequence.length - aaIndex}`
      else if (aaObj.zIon) ionName = `z${this.sequence.length - aaIndex}`

      if (ionName) {
        const rowIndex = this.fragmentTableData.findIndex((row) => row.Name === ionName)
        if (rowIndex >= 0) {
          this.selectedFragmentRowIndex = rowIndex
        }
      }
    },
    onFragmentTableRowClick(_event: Event, { item }: { item: FragmentTableRow }): void {
      // Find the amino acid index from the fragment
      const ionType = item.IonType.charAt(0)
      const ionNumber = item.IonNumber
      const isPrefixIon = ['a', 'b', 'c'].includes(ionType)

      const aaIndex = isPrefixIon ? ionNumber - 1 : this.sequence.length - ionNumber
      if (aaIndex >= 0 && aaIndex < this.sequenceObjects.length) {
        this.selectedAAIndex = aaIndex
      }

      // Handle interactivity: update selection for each mapped identifier
      // Uses the same pattern as other components (LinePlot, Table)
      if (item.PeakId !== undefined && Object.keys(this.interactivity).length > 0) {
        for (const [identifier, _columnName] of Object.entries(this.interactivity)) {
          // For SequenceView, the interactivity maps to peak_id
          // The column name tells us what field in the data this maps to
          this.selectionStore.updateSelection(identifier, item.PeakId)
        }
      }
    },
    getRowProps({ index }: { index: number }) {
      return {
        class: index === this.selectedFragmentRowIndex ? 'bg-amber-lighten-4' : '',
      }
    },
    async copySequence(): Promise<void> {
      try {
        const sequenceStr = this.sequence.join('')
        await navigator.clipboard.writeText(sequenceStr)
        this.copySnackbarText = 'Sequence copied to clipboard!'
        this.copySnackbar = true
      } catch (error) {
        this.copySnackbarText = 'Failed to copy sequence'
        this.copySnackbar = true
        console.error('Copy failed:', error)
      }
    },
  },
})
</script>

<style scoped>
.sequence-view-container {
  width: 100%;
}

.sequence-grid {
  display: grid;
  grid-template-rows: auto;
  gap: 4px;
}

.grid-width-20 {
  grid-template-columns: repeat(22, 1fr);
}

.grid-width-25 {
  grid-template-columns: repeat(27, 1fr);
}

.grid-width-30 {
  grid-template-columns: repeat(32, 1fr);
}

.grid-width-35 {
  grid-template-columns: repeat(37, 1fr);
}

.grid-width-40 {
  grid-template-columns: repeat(42, 1fr);
}

.row-number {
  font-size: 10px;
  opacity: 0.6;
}

.terminal-cell {
  font-weight: bold;
  font-size: 12px;
  background-color: rgba(128, 128, 128, 0.2);
  border-radius: 4px;
  aspect-ratio: 1;
}
</style>
