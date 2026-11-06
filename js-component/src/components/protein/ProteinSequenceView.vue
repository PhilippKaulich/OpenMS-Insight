<template>
  <!-- The header wraps whole label and value pairs, the residue grid puts
       fewer residues in a row, and the fragment table scrolls inside itself:
       the view fits a narrow frame instead of scrolling it sideways -->
  <!-- The Change sequence dialog is drawn inside this frame, which fits the
       view: while it is open, the view is at least as tall as the dialog and
       the fixed-modification list below its field -->
  <div
    class="sequence-view-row"
    :style="sequenceDialog ? { minHeight: `${SEQUENCE_DIALOG_HEIGHT}px` } : undefined"
  >
  <div class="sequence-view-column">
  <div v-if="args.title" class="d-flex justify-center">
    <h4>{{ args.title }}</h4>
  </div>

  <v-sheet class="pa-4 rounded-lg" style="max-width: 97%" :theme="theme?.base ?? 'light'" border>
    <div class="sequence-and-scale">
    <div :id="sequencePartId" class="sequence-part">
      <!-- Label and value pairs wrap as whole pairs, never inside one -->
      <div v-if="massData.length != 0" class="summary-line">
        <h3 class="summary-title">{{ massTitle }}</h3>
        <span v-for="(item, p_index) in massData" :key="p_index" class="summary-pair">
          <span class="summary-label">{{ item.label }}</span>
          <span class="summary-value">{{ item.value }}</span>
        </span>
      </div>
      <div v-if="annotationSummaryItems.length > 0" class="summary-line summary-line-secondary text-body-2 mt-1">
        <span class="summary-title font-weight-bold">{{ args.annotationTitle ?? 'Fragment annotation' }}</span>
        <span v-for="(item, s_index) in annotationSummaryItems" :key="`s${s_index}`" class="summary-pair">
          <span class="summary-label">{{ item.label }}</span>
          <span class="summary-value">{{ item.value }}</span>
        </span>
      </div>
      <div class="d-flex justify-end px-4 mb-4">
        <div>
          <ImageScreenshot
            :element-id="sequencePartId"
            :filename="args.svgFilename"
            :format="args.imageFormat"
            :color="accentColor"
          />
          <SequenceViewInformation :color="accentColor" />
          <v-btn
            variant="text"
            icon="mdi-content-copy"
            size="large"
            :disabled="sequence.length === 0"
            @click="copySequence"
          >
            <v-icon>mdi-content-copy</v-icon>
            <v-tooltip activator="parent" location="bottom">
              Copy sequence to clipboard
            </v-tooltip>
          </v-btn>
          <v-btn
            v-if="args.proformaCopy"
            variant="text"
            icon="mdi-code-brackets"
            size="large"
            :disabled="sequence.length === 0"
            @click="copyProForma"
          >
            <v-icon>mdi-code-brackets</v-icon>
            <v-tooltip activator="parent" location="bottom">
              Copy as ProForma
            </v-tooltip>
          </v-btn>
          <v-btn
            v-if="shouldShowSequenceChangeButton"
            variant="text"
            icon="mdi-dna"
            size="large"
            @click="openSequenceDialog"
          >
            <v-icon>mdi-dna</v-icon>
            <v-tooltip activator="parent" location="bottom">
              Change sequence
            </v-tooltip>
          </v-btn>
          <v-btn
            variant="text"
            icon="mdi-magnify"
            size="large"
            :disabled="sequence.length === 0"
            @click="toggleRegexHighlight"
          >
            <v-icon>mdi-magnify</v-icon>
            <v-tooltip activator="parent" location="bottom">
              {{ showRegexHighlight ? 'Hide regex highlighting' : 'Show regex highlighting' }}
            </v-tooltip>
          </v-btn>
          <v-btn :id="settingsButtonId" variant="text" icon="mdi-cog" size="large"></v-btn>
          <v-menu :close-on-content-click="false" :activator="`#${settingsButtonId}`" location="bottom">
            <v-card min-width="300" class="sequence-controls">
              <v-list>
                <v-list-item>
                  <v-list-item-title># amino acids per row</v-list-item-title>
                  <v-list-item-subtitle v-if="perRow < rowWidth">
                    {{ perRow }} fit at this width
                  </v-list-item-subtitle>
                  <v-slider
                    v-model="rowWidth"
                    :ticks="tickLabels"
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
                    :ticks="fontSizeTickLabels"
                    :min="8"
                    :max="16"
                    step="2"
                    show-ticks="always"
                    tick-size="4"
                  ></v-slider>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Visibility</v-list-item-title>
                  <div class="d-flex justify-space-evenly">
                    <v-checkbox
                      v-for="visibilityOption in visibilityOptions"
                      :key="visibilityOption.text"
                      v-model="visibilityOption.selected"
                      hide-details
                      density="comfortable"
                      :label="visibilityOption.text"
                    ></v-checkbox>
                  </div>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Fragmentation method</v-list-item-title>
                  <v-select
                    v-model="fragmentationMethod"
                    :items="fragmentationMethodItems"
                    density="compact"
                    hide-details
                    :disabled="!showFragments"
                  ></v-select>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Fragment ion types</v-list-item-title>
                  <div class="d-flex justify-space-evenly">
                    <v-checkbox
                      v-for="(category, ionIndex) in ionTypes"
                      :key="category.text"
                      v-model="category.selected"
                      hide-details
                      density="comfortable"
                      :label="category.text"
                      :disabled="!showFragments"
                      @click="toggleIonTypeSelected(ionIndex)"
                    >
                    </v-checkbox>
                  </div>
                  <div v-if="!usesAnnotator" class="d-flex justify-space-evenly">
                    <v-checkbox
                      v-for="variant in ionTypeVariants"
                      :key="variant.text"
                      v-model="variant.selected"
                      hide-details
                      density="comfortable"
                      :label="variant.text"
                      :disabled="!showFragments"
                    >
                    </v-checkbox>
                  </div>
                  <div class="d-flex justify-space-evenly">
                    <v-checkbox
                      v-for="category in Object.keys(ionTypesExtra)"
                      :key="category"
                      v-model="ionTypesExtra[category as ExtraFragmentType]"
                      hide-details
                      density="comfortable"
                      :label="category"
                      :disabled="!showFragments"
                    >
                    </v-checkbox>
                  </div>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Fragment mass tolerance</v-list-item-title>
                  <div class="d-flex align-center ga-2">
                    <v-text-field
                      style="min-width: 0"
                      v-model="fragmentMassTolerance"
                      type="number"
                      :step="toleranceUnit === 'Da' ? 0.01 : 1"
                      min="0"
                      hide-details="auto"
                      :label="`mass tolerance in ${toleranceUnit}`"
                      :disabled="!showFragments"
                      @change="updateMassTolerance"
                    ></v-text-field>
                    <v-btn-toggle
                      v-model="toleranceUnit"
                      mandatory
                      class="flex-shrink-0"
                      density="compact"
                      variant="outlined"
                      divided
                      :disabled="!showFragments"
                    >
                      <v-btn value="ppm" size="small" class="text-none">ppm</v-btn>
                      <v-btn value="Da" size="small" class="text-none">Da</v-btn>
                    </v-btn-toggle>
                  </div>
                  <!-- TODO: add "required" -->
                </v-list-item>
              </v-list>
            </v-card>
          </v-menu>
        </div>
      </div>
      <!-- Regex highlighting input -->
      <div v-if="showRegexHighlight" class="pb-4 px-4">
        <v-card variant="outlined" class="pa-3">
          <v-row align="center">
            <v-col cols="12" md="8">
              <v-text-field
                v-model="regexPattern"
                class="sequence-regex-field"
                label="Regex pattern for highlighting"
                placeholder="e.g., A+, [KR], M.*L"
                :error-messages="regexError"
                hide-details="auto"
                density="compact"
                @input="onRegexInput"
              >
                <template #prepend-inner>
                  <v-icon>mdi-regex</v-icon>
                </template>
              </v-text-field>
            </v-col>
            <v-col cols="12" md="4">
              <div v-if="regexHighlightedIndices.size > 0" class="text-caption text-medium-emphasis">
                {{ regexHighlightedIndices.size }} cells highlighted
              </div>
              <div v-else-if="regexPattern && !regexError" class="text-caption text-medium-emphasis">
                No matches found
              </div>
            </v-col>
          </v-row>
        </v-card>
      </div>
      <div ref="sequenceGrid" class="pb-4 px-2 sequence-grid" :style="gridStyles">
        <template v-for="(aminoAcidObj, aa_index) in sequenceObjects" :key="aa_index">
          <div
            v-if="(showTruncations && (aa_index !== 0) && (aa_index % perRow === 0)) || (!showTruncations && ((aa_index - sequence_start) !== 0) && ((aa_index - sequence_start) % perRow === 0) && (aa_index < sequence_end) && (aa_index > sequence_start))"
            class="row-number row-number-start"
          >
          {{ showTruncations ? aa_index + 1 : aa_index - sequence_start + 1 }}
          </div>
          <ProteinTerminalCell v-if="aa_index === 0" protein-terminal="N-term" :truncated=n_truncation :index="-1" :disable-variable-modification-selection="disableVariableModifications" :determined="n_determined" :font-size="fontSize"/>
          <AminoAcidCell
            v-if="showTruncations || ((sequence_start <= aa_index) && (sequence_end >= aa_index))"
            :index="aa_index"
            :sequence-object="aminoAcidObj"
            :fixed-modification="fixedModification(aminoAcidObj.aminoAcid)"
            :disable-variable-modification-selection="disableVariableModifications"
            :show-tags="showTags"
            :show-fragments="showFragments"
            :show-modifications="showModifications"
            :font-size="fontSize"
            :is-regex-highlighted="regexHighlightedIndices.has(aa_index)"
            :show-internal="showInternal"
            :max-internal-depth="maxInternalDepth"
            :in-internal-span="inSelectedInternalSpan(aa_index)"
            @selected="aminoAcidSelected"
          />
          <div
            v-if="(showTruncations && (aa_index % perRow === perRow - 1 && aa_index !== sequence.length - 1)) || (!showTruncations && ((aa_index - sequence_start) % perRow === perRow - 1) && (aa_index < sequence_end) && (aa_index > sequence_start))"
            class="row-number row-number-end"
          >
            {{ showTruncations ? aa_index + 1 : aa_index - sequence_start + 1 }}
          </div>
          <ProteinTerminalCell
            v-if="aa_index === sequence.length - 1"
            protein-terminal="C-term" :truncated=c_truncation
            :index="sequence.length"
            :disable-variable-modification-selection="disableVariableModifications"
            :determined="c_determined"
            :font-size="fontSize"
          />
          </template>
      </div>
      <InternalFragmentTrack
        v-if="showInternal"
        :sequence="sequence"
        :range-start="showTruncations ? 0 : sequence_start"
        :range-end="showTruncations ? sequence.length - 1 : sequence_end"
        :fragments="annotatedFragments ?? []"
        :selected-fragment="selectedFragment"
        :highlight-residue="selectedResidue"
        :theme="theme"
        @select="onInternalFragmentSelected"
      />
      <!-- Variable modifications set on residues, with the library only -->
      <div
        v-if="variableModData.library !== null && appliedVariableModifications.length > 0"
        class="d-flex flex-wrap align-center px-2 pb-2 variable-modification-list"
      >
        <span class="text-body-2 mr-2">Variable modifications:</span>
        <v-chip
          v-for="mod in appliedVariableModifications"
          :key="mod.index"
          size="small"
          class="mr-1 mb-1"
          closable
          @click:close="variableModData.updateVariableModifications(mod.index, 0)"
        >
          {{ mod.text }}
        </v-chip>
        <span class="text-body-2 ml-1">{{ variableModificationTotal }}</span>
      </div>
    </div>
    <div v-if="(maxCoverage > 0) && showTags" class="scale-container" title="Sequence Tag Coverage">
      <div class="scale-text"> {{ maxCoverage + "x" }}</div>
      <div class="scale"></div>
      <div class="scale-text">1x</div>
    </div>
  </div>
    <div class="fit-width">
      <template v-if="(fragmentTableTitle !== '') && showFragments">
        <FragmentTable
          :key="usesAnnotator ? 'annotator' : 'matched'"
          :table-data="fragmentTableData"
          :column-definitions="usesAnnotator ? annotatorTableColumnDefinitions : fragmentTableColumnDefinitions"
          :index="index"
          :selected-row-index-from-listening="selectedFragTableRowIndex"
          :go-to-fields="['Name']"
          table-layout-param="fitColumns"
          @row-selected="onFragmentTableRowSelected"
        >
          <template #default>{{ fragmentTableTitle }}</template>
          <template #end-title-row
            >% Residue cleavage: {{ residueCleavagePercentage.toFixed(3) }}%</template
          >
        </FragmentTable>
      </template>
    </div>
  </v-sheet>
  </div>
  </div>
  
  <v-snackbar
    v-model="copySnackbar"
    :timeout="3000"
    location="bottom"
  >
    {{ copySnackbarText }}
    <template #actions>
      <v-btn
        color="blue"
        variant="text"
        @click="copySnackbar = false"
      >
        Close
      </v-btn>
    </template>
  </v-snackbar>

  <!-- Sequence Input Dialog -->
  <v-dialog v-model="sequenceDialog" max-width="600" persistent scrollable>
    <v-card>
      <v-card-title class="text-h6">
        Enter Custom Sequence
      </v-card-title>
      <v-card-text style="padding-bottom: 12px">
        <!-- The example shows only while typing, under the raised label -->
        <v-textarea
          v-model="customSequenceInput"
          label="Protein Sequence"
          :placeholder="sequenceInputFocused ? 'Enter amino acid sequence (e.g., MKFLVNVALVF...)' : undefined"
          @update:focused="sequenceInputFocused = $event"
          :error-messages="sequenceInputError"
          :rows="modificationItems.length > 0 ? 3 : 6"
          auto-grow
          counter
          hint="Enter single-letter amino acid codes only"
          persistent-hint
        >
          <template #prepend-inner>
            <v-icon>mdi-dna</v-icon>
          </template>
        </v-textarea>
        <v-autocomplete
          v-if="modificationItems.length > 0"
          v-model="customModifications"
          :items="modificationItems"
          item-title="title"
          item-value="value"
          label="Fixed modifications"
          placeholder="Search by name or mass, e.g. Carbamidomethyl or 57.02"
          hint="Each goes on every residue of its kind, or on the terminus"
          persistent-hint
          multiple
          chips
          closable-chips
          clearable
          class="mt-4"
        ></v-autocomplete>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn
          variant="text"
          @click="closeSequenceDialog"
        >
          Cancel
        </v-btn>
        <v-btn
          :color="accentColor"
          variant="elevated"
          @click="submitCustomSequence"
        >
          Apply Sequence
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script lang="ts">
import { defineComponent, toRaw, type PropType } from 'vue'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import { useModificationStore } from '@/stores/variable-modification'
import type { ProteinSequenceViewComponentArgs } from '@/types/component'
import type {
  AnnotatedFragment,
  AnnotationSummary,
  FragmentSettings,
  ModificationData,
  FragmentSelection,
  MatchedSpectrum,
  SequenceTag,
  SequenceData,
} from '@/types/protein-sequence-data'
import type { SequenceObject } from '@/types/protein-sequence-object'
import type { ColumnDefinition } from 'tabulator-tables'
import FragmentTable from './FragmentTable.vue'
import AminoAcidCell from './ProteinAminoAcidCell.vue'
import ProteinTerminalCell from './ProteinTerminalCell.vue'
import ImageScreenshot from './ImageScreenshot.vue'
import SequenceViewInformation from './SequenceViewInformation.vue'
import InternalFragmentTrack from './InternalFragmentTrack.vue'
import { extraFragmentTypeObject, type ExtraFragmentType } from '@/components/sequence/modification'
import { fixedFromId, toProForma, type ProFormaModification } from './proforma'
import {
  CUSTOM_METHOD,
  FRAGMENTATION_METHODS,
  ION_VARIANTS,
  canonicalIonName,
  ionSeries,
  isPrefixIon,
  isSuffixIon,
  methodForIons,
  methodIons,
  toleranceDa,
  toleranceUnit,
  type IonSeries,
  type ToleranceUnit,
} from './fragment-ions'

// Fixed decimals for long numbers in the fragment tables
// Height (px) the Change sequence dialog needs: title, the sequence field,
// the fixed-modification picker with its open list, and the buttons
const SEQUENCE_DIALOG_HEIGHT = 640

// One label and value of the summary lines above the sequence
type SummaryItem = { label: string; value: string }

// Residues per row the view falls back to, in steps of 5, when the chosen
// number does not fit: a residue cell stays at least this many font sizes wide
const MIN_CELL_FONT_SIZES = 2
const MIN_CELL_PX = 20
const MIN_ROW_WIDTH = 10

const toFixedFormatter = (decimalPlaces?: number) => (cell: { getValue: () => unknown }) => {
  const value = cell.getValue()
  if (value === null || value === undefined) return ''
  return String(value).length > 4 ? (value as number).toFixed(decimalPlaces ?? 4) : value
}

let viewIdCounter = 0

export default defineComponent({
  name: 'ProteinSequenceView',
  components: {
    SequenceViewInformation,
    FragmentTable,
    AminoAcidCell,
    ProteinTerminalCell,
    ImageScreenshot,
    InternalFragmentTrack,
  },
  props: {
    args: {
      type: Object as PropType<ProteinSequenceViewComponentArgs>,
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
    const variableModData = useModificationStore()
    const uid = ++viewIdCounter
    return {
      streamlitDataStore,
      selectionStore,
      variableModData,
      sequencePartId: `sequence-part-${uid}`,
      resizeObserver: undefined as ResizeObserver | undefined,
      settingsButtonId: `sequence-settings-${uid}`,
    }
  },
  provide() {
    // Residue cells read the entry and the residue selection through this
    return {
      sequenceView: {
        entry: () => this.entry,
        selectedAA: () => this.selectedAA,
        setSelectedAA: (position?: number) => this.setSelectedAA(position),
      },
    }
  },
  data() {
    return {
      rowWidth: 35 as number,
      fontSize: 12 as number,
      massData: [] as SummaryItem[],
      gridWidth: 0 as number,
      gridResizeObserver: undefined as ResizeObserver | undefined,
      massTitle: "" as string,
      ionTypes: [
        { text: 'a', selected: false },
        { text: 'b', selected: true },
        { text: 'c', selected: false },
        { text: 'x', selected: false },
        { text: 'y', selected: true },
        { text: 'z', selected: false },
      ] as { text: string; selected: boolean }[],
      ionTypesExtra: {
        'water loss': false,
        'ammonium loss': false,
        'proton loss/addition': false,
      } as Record<ExtraFragmentType, boolean>,
      // Radical / hydrogen-shifted series (ETD/ECD, UVPD): offsets of a base series
      ionTypeVariants: ION_VARIANTS.map((variant) => ({ text: variant.name, selected: false })) as {
        text: string
        selected: boolean
      }[],
      fragmentMassTolerance: 10 as number,
      toleranceUnit: 'ppm' as ToleranceUnit,
      visibilityOptions: [
        { text: 'Fragments', selected: true },
        { text: 'Modifications', selected: true },
      ] as { text: string; selected: boolean }[],
      fragmentTableColumnDefinitions: [
        {
          title: 'Name', field: 'Name',
            headerTooltip: 'The name of the fragment ion, represented in Biemann notation.'
        },
        {
          title: 'Ion type', field: 'IonType',
          headerTooltip: 'The type of fragment ion identified in the spectrum.'
        },
        {
          title: 'Ion number', field: 'IonNumber', sorter: 'number',
          headerTooltip: 'The position of the fragment ion within the sequence.'
        },
        {
          title: 'Theoretical mass', field: 'TheoreticalMass', sorter: 'number',
          headerTooltip: 'The expected mass of the fragment ion.'
        },
        {
          title: 'Observed mass', field: 'ObservedMass', formatter: toFixedFormatter(), sorter: 'number',
          headerTooltip: 'The mass of the fragment ion as observed in the spectrum.'
        },
        {
          title: 'Mass difference (Da)', field: 'MassDiffDa', sorter: 'number',
          headerTooltip: 'The difference between the observed and theoretical masses of the fragment ion, in Daltons.'
        },
        {
          title: 'Mass difference (ppm)', field: 'MassDiffPpm', sorter: 'number',
          headerTooltip: 'The difference between the observed and theoretical masses of the fragment ion, in parts per million (ppm).'
        },
      ] as ColumnDefinition[],
      // Fragment table of externally annotated envelopes (one row per envelope)
      annotatorTableColumnDefinitions: [
        {
          title: 'Name', field: 'Name',
          headerTooltip: 'Terminal fragments in Biemann notation; internal fragments as type[first-last residue of the identified sequence].'
        },
        {
          title: 'Ion type', field: 'IonType',
          headerTooltip: 'Terminal ion type, or N-end/C-end type of an internal fragment.'
        },
        {
          title: 'Charge', field: 'Charge', sorter: 'number',
          headerTooltip: 'Charge of the matched isotope envelope.'
        },
        {
          title: 'Theoretical mass', field: 'TheoreticalMass', sorter: 'number',
          headerTooltip: 'Monoisotopic neutral mass of the fragment.'
        },
        {
          title: 'm/z', field: 'Mz', sorter: 'number',
          headerTooltip: 'Theoretical m/z of the most abundant isotope peak.'
        },
        {
          title: 'Mass difference (ppm)', field: 'MassDiffPpm', sorter: 'number',
          headerTooltip: 'Error of the most abundant peak after calibration.'
        },
        {
          title: 'Cosine', field: 'Cosine', sorter: 'number',
          headerTooltip: 'Cosine similarity of the observed and theoretical isotope envelopes.'
        },
        {
          title: 'Peaks', field: 'Peaks',
          headerTooltip: 'Matched / predicted isotope peaks.'
        },
        {
          title: 'Intensity', field: 'Intensity', sorter: 'number', formatter: toFixedFormatter(0),
          headerTooltip: 'Summed intensity of the matched peaks.'
        },
      ] as ColumnDefinition[],
      fragmentTableData: [] as Record<string, unknown>[],
      // Annotated fragment behind each fragmentTableData row
      fragmentTableSource: [] as AnnotatedFragment[],
      selectedFragment: undefined as AnnotatedFragment | undefined,
      selectedResidue: undefined as number | undefined,
      fragmentTableTitle: '' as string,
      residueCleavagePercentage: 0 as number,
      sequenceObjects: [] as SequenceObject[],
      selectedFragTableRowIndex: undefined as number | undefined,
      copySnackbar: false as boolean,
      copySnackbarText: '' as string,
      _updatingFromMass: false as boolean,
      _updatingFromFragment: false as boolean,
      showRegexHighlight: false as boolean,
      regexPattern: '' as string,
      regexError: '' as string,
      regexHighlightedIndices: new Set<number>(),
      // Sequence change dialog properties
      sequenceDialog: false as boolean,
      SEQUENCE_DIALOG_HEIGHT,
      // Modification ids picked in the change-sequence dialog
      customModifications: [] as string[],
      customSequenceInput: '' as string,
      sequenceInputError: '' as string,
      sequenceInputFocused: false,
    }
  },
  computed: {
    fragmentationMethodItems(): string[] {
      return [...FRAGMENTATION_METHODS.map((m) => m.name), CUSTOM_METHOD]
    },
    // The method whose ion series are the selected ones ('Custom' otherwise);
    // picking a method selects its series
    fragmentationMethod: {
      get(): string {
        return methodForIons(this.selectedIonSeries.map((series) => series.name))
      },
      set(method: string) {
        const ions = methodIons(method)
        if (ions === undefined) return
        this.selectIons(ions)
      },
    },
    // Selected ion series: the base types and, without an annotation, the variants
    selectedIonSeries(): IonSeries[] {
      const names = this.ionTypes.filter((t) => t.selected).map((t) => t.text)
      if (!this.usesAnnotator) {
        this.ionTypeVariants.filter((t) => t.selected).forEach((t) => names.push(t.text))
      }
      return names.map((name) => ionSeries(name)).filter((series): series is IonSeries => series !== undefined)
    },
    accentColor(): string {
      return this.args.accentColor ?? 'primary'
    },
    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },
    entry(): SequenceData | undefined {
      return (this.streamlitDataStore.allDataForDrawing.sequenceData as SequenceData | null) ?? undefined
    },
    spectrum(): MatchedSpectrum | undefined {
      return (this.streamlitDataStore.allDataForDrawing.spectrumData as MatchedSpectrum | null) ?? undefined
    },
    spectrumFragmentation(): string | undefined {
      return this.spectrum?.fragmentation ?? undefined
    },
    settings(): FragmentSettings | undefined {
      return this.args.settings ?? undefined
    },
    selectedTagKey(): string {
      return JSON.stringify(this.selectedTag ?? null)
    },
    selectedTag(): SequenceTag | undefined {
      return this.args.tag ?? undefined
    },
    selectedAA(): number | undefined {
      const id = this.args.aaIdentifier
      if (!id) return undefined
      const value = this.selectionStore.$state[id]
      return typeof value === 'number' ? value : undefined
    },
    selectedMassIndex(): number | undefined {
      const id = this.args.massIdentifier
      if (!id) return undefined
      const value = this.selectionStore.$state[id]
      return typeof value === 'number' ? value : undefined
    },
    sequence(): string[] {
      return this.entry?.sequence ?? []
    },
    /** Identifies the entry shown. Data arriving again after a rerun builds
     * new objects for the same entry, which must not reset the view. */
    entryKey(): string {
      const entry = this.entry
      if (!entry) return ''
      return JSON.stringify([
        entry.sequence, entry.start_position, entry.end_position, entry.theoretical_mass,
        entry.observed_mass, entry.fixed_modifications, entry.modifications,
      ])
    },
    sequence_start_reported(): number {
      return this.entry?.start_position ?? 0
    },
    sequence_start(): number {
      if (this.sequence_start_reported < 0)
      {
        return 0
      }
      return this.sequence_start_reported
    },
    n_truncation(): boolean {
      return this.sequence_start > 0
    },
    n_determined(): boolean {
      return this.sequence_start_reported >= 0
    },
    sequence_end_reported(): number {
      return this.entry?.end_position ?? this.sequence.length-1
    },
    sequence_end(): number {
      if (this.sequence_end_reported < 0) {
        return this.sequence.length-1
      }
      return this.sequence_end_reported
    },
    c_truncation(): boolean {
      return this.sequence_end < (this.sequence.length - 1)
    },
    c_determined(): boolean {
      return this.sequence_end_reported >= 0
    },
    modifications(): ModificationData[] {
      return this.entry?.modifications ?? []
    },
    // null/undefined: no annotated fragments -> fragments are matched here
    annotatedFragments(): AnnotatedFragment[] | undefined {
      return this.entry?.annotated_fragments ?? undefined
    },
    usesAnnotator(): boolean {
      return this.annotatedFragments !== undefined
    },
    annotationSummary(): AnnotationSummary | undefined {
      return this.entry?.annotation_summary ?? undefined
    },
    annotationSummaryItems(): SummaryItem[] {
      const s = this.annotationSummary
      if (s === undefined || !this.showFragments) return []
      const items: SummaryItem[] = []
      if (s.score !== null) items.push({ label: 'Score', value: s.score.toFixed(2) })
      if (s.coverage !== null) items.push({ label: 'Bond coverage', value: `${s.coverage.toFixed(1)}%` })
      if (s.coverage_with_internal !== null) items.push({ label: 'With internal', value: `${s.coverage_with_internal.toFixed(1)}%` })
      if (s.internal_matched !== null && s.internal_hypotheses !== null) {
        items.push({ label: 'Internal pieces', value: `${s.internal_matched} / ${s.internal_hypotheses}` })
      }
      if (s.calibration_ppm !== null) items.push({ label: 'Calibration', value: `${s.calibration_ppm.toFixed(2)} ppm` })
      return items
    },
    hasInternalFragments(): boolean {
      return (this.annotatedFragments ?? []).some((f) => f.kind === 'I')
    },
    showInternal(): boolean {
      if (!this.hasInternalFragments) {
        return false
      }
      return this.visibilityOptions.find(option => option.text === 'Internal fragments')?.selected ?? false
    },
    maxInternalDepth(): number {
      return this.sequenceObjects.reduce((m, o) => Math.max(m, o.internalDepth ?? 0), 0)
    },
    coverage(): number[] {
      return this.entry?.coverage ?? []
    },
    maxCoverage() : number {
      return this.entry?.maxCoverage ?? -1
    },
    theoreticalMass(): number {
      return this.entry?.theoretical_mass ?? 0
    },
    entryObservedMass(): number | undefined {
      return this.entry?.observed_mass
    },
    fixedModificationSites(): string[] {
      return this.entry?.fixed_modifications ?? []
    },
    variableModifications(): Record<number, number> {
      // return {}
      return this.variableModData.variableModifications ?? {}
    },
    tickLabels(): Record<number, string> {
      return {
        20: '20',
        25: '25',
        30: '30',
        35: '35',
        40: '40',
      }
    },
    fontSizeTickLabels(): Record<number, string> {
      return {
        8: '8',
        10: '10',
        12: '12',
        14: '14',
        16: '16',
      }
    },
    // Residues per row: the chosen number, or fewer where its cells would be
    // too small to read at this width
    perRow(): number {
      if (this.gridWidth <= 0) return this.rowWidth
      const minCell = Math.max(MIN_CELL_PX, this.fontSize * MIN_CELL_FONT_SIZES)
      // Two row-number columns of up to four digits, the gaps and the padding
      const numbers = 2 * (4 * 0.65 * this.fontSize + 8)
      for (let n = this.rowWidth; n > MIN_ROW_WIDTH; n -= 5) {
        if ((this.gridWidth - numbers - 16) / n - 4 >= minCell) return n
      }
      return MIN_ROW_WIDTH
    },
    // Row numbers get columns of their own, as wide as the widest number,
    // so they never run into the first or last residue of a row
    gridStyles(): Record<string, string> {
      return {
        width: '100%',
        maxWidth: '100%',
        gridTemplateColumns: `max-content repeat(${this.perRow}, minmax(0, 1fr)) max-content`,
        '--row-number-font-size': `${this.fontSize}px`,
      }
    },
    proteinTerminalCellStyles(): Record<string, string> {
      return {
        '--amino-acid-cell-hover-color': '#fff',
        '--amino-acid-cell-hover-bg-color': this.theme?.secondaryBackgroundColor ?? '#000',
      }
    },
    calculateCleavagePercentage(): number {
      let explained_cleavage = 0
      for (let i = 0, end_site = this.sequenceObjects.length - 1; i < end_site; ++i) {
        const preAA = this.sequenceObjects[i]
        const postAA = this.sequenceObjects[i + 1]
        if (preAA.aIon || preAA.bIon || preAA.cIon || postAA.xIon || postAA.yIon || postAA.zIon) {
          ++explained_cleavage
        }
      }
      return (explained_cleavage / (this.sequence_end - this.sequence_start)) * 100
    },
    disableVariableModifications(): boolean {
      if (this.showIdentification) {
        return true
      }
      return false
    },
    showIdentification(): boolean {
      if (this.entryObservedMass !== undefined) {
        return true
      }
      return false
    },
    showTags(): boolean {
      if (!this.showIdentification) {
        return false
      }
      if (this.visibilityOptions.find(option => option.text === 'Tags')?.selected) {
        return true
      }
      return false
    },
    showTruncations(): boolean {
      if (!this.showIdentification) {
        return false
      }
      if (this.visibilityOptions.find(option => option.text === 'Truncations')?.selected) {
        return true
      }
      return false
    },
    showModifications(): boolean {
      if (this.visibilityOptions.find(option => option.text === 'Modifications')?.selected) {
        return true
      }
      return false
    },
    showFragments(): boolean {
      if (this.visibilityOptions.find(option => option.text === 'Fragments')?.selected) {
        return true
      }
      return false
    },
    // Sequence change button computed properties
    // Applied variable modifications, in sequence order: site, name, mass
    appliedVariableModifications(): { index: number; text: string }[] {
      const masses = this.variableModData.variableModifications ?? {}
      const labels = this.variableModData.variableModLabels ?? {}
      return Object.entries(masses)
        .map(([key, mass]) => ({ index: Number(key), mass }))
        .filter((m) => m.mass !== undefined && m.mass !== 0 && !Number.isNaN(m.mass))
        .sort((a, b) => a.index - b.index)
        .map(({ index, mass }) => {
          let site: string
          if (index < 0) site = 'N-term'
          else if (index >= this.sequence.length) site = 'C-term'
          else site = `${this.sequence[index]}${index + 1}`
          const name = labels[index] ?? ''
          const shift = mass.toLocaleString('en-US', { signDisplay: 'always', maximumFractionDigits: 4 })
          return { index, text: `${site} ${name ? name + ' ' : ''}${shift} Da` }
        })
    },
    variableModificationTotal(): string {
      const total = Object.values(this.variableModData.variableModifications ?? {})
        .filter((m) => m && !Number.isNaN(m))
        .reduce((a, b) => a + b, 0)
      return `Total ${total.toLocaleString('en-US', { signDisplay: 'always', maximumFractionDigits: 4 })} Da`
    },
    modificationItems(): { title: string; value: string }[] {
      return (this.args.modificationLibrary ?? []).map((m) => {
        const sign = m.mass >= 0 ? '+' : ''
        return { title: `${m.id}  ${sign}${m.mass.toFixed(4)} Da`, value: m.id }
      })
    },
    shouldShowSequenceChangeButton(): boolean {
      return !this.showIdentification && !!this.args.sequenceIdentifier
    },
  },
  watch: {
    // The residue menus read the variable-modification library from the store
    'args.variableModificationLibrary': {
      handler(library) {
        this.variableModData.setLibrary(library, this.args.variableModificationSuggestions)
      },
      immediate: true,
    },
    'args.variableModificationSuggestions'(suggested) {
      this.variableModData.setLibrary(this.args.variableModificationLibrary, suggested)
    },
    // A new spectrum (or entry) arrives: rematch the fragments
    spectrum() {
      this.recomputeFragments()
    },
    // The selected spectrum's fragmentation method (fragmentation_column):
    // a spectrum acquired with another method selects that method's series
    spectrumFragmentation() {
      this.applySpectrumFragmentation()
    },
    // A new entry (another identification, or a user-given sequence): clears the
    // stale residue selection and re-reads the settings.
    entryKey() {
      this.setSelectedAA(undefined)
      this.recomputeFragments()
      this.updateSettings()
    },
    // Selected sequence tag; cleared when the app resets it on a new entry.
    // By value: the arguments arrive as a new object on every rerun
    selectedTagKey() {
      this.updateTagPosition()
    },
    // Re-match fragments on a tolerance change (local state, no round-trip).
    fragmentMassTolerance() {
      this.recomputeFragments()
    },
    toleranceUnit() {
      this.recomputeFragments()
    },
    // Radical / hydrogen-shifted series toggles. deep required (nested .selected).
    ionTypeVariants: {
      handler() {
        this.recomputeFragments()
      },
      deep: true,
    },
    // Rows selected from the sequence (residue click, internal track, mass table)
    selectedFragTableRowIndex(rowIndex?: number) {
      this.publishSelectedFragment(rowIndex)
    },
    // Ion-type a/b/c/x/y/z toggles. deep required (nested .selected).
    ionTypes: {
      handler() {
        this.initializeSequenceObjects()
        this.prepareFragmentTable()
        this.prepareAmbigiousModifications()
      },
      deep: true,
    },
    // Extra fragment-type toggles. deep required (nested key).
    ionTypesExtra: {
      handler() {
        this.initializeSequenceObjects()
        this.prepareFragmentTable()
        this.prepareAmbigiousModifications()
      },
      deep: true,
    },
    // Internal fragments toggled in the visibility menu: their residue marks
    // and table rows are built in prepareAnnotatedFragmentTable.
    showInternal() {
      this.recomputeFragments()
    },
    // Variable modifications set on residues (only without an identification).
    variableModifications() {
      this.recomputeFragments()
    },
    // KEPT — mass-table selection -> highlight the matching fragment row (loop-guarded).
    selectedMassIndex: {
      handler(newMassIndex: number | undefined) {
        if (newMassIndex !== undefined) {
          this.updateFragmentTableFromMassSelection(newMassIndex);
        }
      },
      immediate: false
    }
  },
  mounted() {
    this.setSelectedAA(undefined)
    this.updateSettings()
    this.recomputeFragments()
    // The view grows and shrinks with the sequence and the fragment table:
    // keep the frame fitted to it
    this.resizeObserver = new ResizeObserver(() => Streamlit.setFrameHeight())
    this.resizeObserver.observe(document.body)
    const grid = this.$refs.sequenceGrid as HTMLElement | undefined
    if (grid) {
      this.gridResizeObserver = new ResizeObserver((entries) => {
        this.gridWidth = entries[0]?.contentRect.width ?? grid.clientWidth
      })
      this.gridResizeObserver.observe(grid)
    }
  },
  beforeUnmount() {
    this.resizeObserver?.disconnect()
    this.gridResizeObserver?.disconnect()
  },
  methods: {
    // Full recompute of the sequence view: precursor info, per-residue objects,
    // fragment-ion matching, and ambiguous-modification marks. Shared by the
    // per_scan_data / sequence / fragmentMassTolerance / variableModifications
    // watchers and mounted() so the prepare* order stays consistent.
    recomputeFragments(): void {
      this.preparePrecursorInfo()
      this.initializeSequenceObjects()
      this.prepareFragmentTable()
      this.prepareAmbigiousModifications()
    },
    getFragmentMasses(iontype: string): number[][] {
      return (this.entry?.[`fragment_masses_${iontype}` as keyof SequenceData] as number[][] | undefined) ?? []
    },
    updateMassTolerance(event: Event) {
      const value = Number.parseFloat((event.target as any).value as string)
      if (Number.isFinite(value) && value >= 0) {
        this.fragmentMassTolerance = value
      }
    },
    // Select exactly these ion series (base types and variants)
    selectIons(names: string[]) {
      const selected = new Set(names.map(canonicalIonName))
      if (this.usesAnnotator) {
        // Annotated fragments are drawn by their base type (z+1, z+2 as z)
        names.forEach((name) => {
          const base = ionSeries(name)?.base ?? name.charAt(0)
          selected.add(base)
        })
      }
      this.ionTypes.forEach((item) => {
        item.selected = selected.has(item.text)
      })
      this.ionTypeVariants.forEach((item) => {
        item.selected = selected.has(item.text)
      })
    },
    updateSettings() {
      const settings = this.settings
      if (settings?.ion_types !== undefined && settings.ion_types !== null) {
        this.selectIons(settings.ion_types)
      } else {
        const ions = methodIons(settings?.fragmentation)
        if (ions !== undefined) this.selectIons(ions)
      }
      if (settings?.tolerance !== undefined && settings.tolerance !== null) {
        this.fragmentMassTolerance = settings.tolerance
      }
      if (settings?.tolerance_unit !== undefined && settings.tolerance_unit !== null) {
        this.toleranceUnit = toleranceUnit(settings.tolerance_unit)
      }
      this.applySpectrumFragmentation()
    },
    // Select the ion series of the spectrum's own fragmentation method. Not with
    // annotated fragments: those were annotated for the search's ion types.
    applySpectrumFragmentation() {
      if (this.usesAnnotator) return
      const ions = methodIons(this.spectrumFragmentation)
      if (ions !== undefined) this.selectIons(ions)
    },
    toggleIonTypeSelected(index: number) {
      this.ionTypes[index].selected = !this.ionTypes[index].selected
    },
    preparePrecursorInfo(): void {
      if (this.spectrum === undefined) {
        this.massData = [] // if no scan is selected, nothing to show
        return
      }

      if (this.entryObservedMass !== undefined) {

        this.massTitle = this.args.entryTitle ?? 'Identification'
        let observed_mass = '-'
        let delta_mass = '-'
        if (this.entryObservedMass > 0) {
          observed_mass = this.entryObservedMass.toFixed(2)
          delta_mass = Math.abs(this.theoreticalMass - this.entryObservedMass).toFixed(2)
        }


        this.massData = [
          { label: 'Theoretical protein mass', value: this.theoreticalMass.toFixed(2) },
          { label: this.args.observedMassLabel ?? 'Observed mass', value: observed_mass },
          { label: 'Δ Mass (Da)', value: delta_mass },
        ]
        if (this.spectrumFragmentation) {
          this.massData.push({ label: 'Fragmentation', value: this.spectrumFragmentation })
        }

        // Ensures this is only executed once
        if (!this.visibilityOptions.some(option => option.text === 'Tags')) {
          this.visibilityOptions.push({ text: 'Truncations', selected: true })
          this.visibilityOptions.push({ text: 'Tags', selected: true })
          this.visibilityOptions.push({ text: 'Internal fragments', selected: true })
          this.updateSettings()
          
        }

        this.ionTypesExtra['ammonium loss'] = false
        this.ionTypesExtra['water loss'] = false
        this.ionTypesExtra['proton loss/addition'] = false
        return

      }

      const observedMass = this.spectrum.precursorMass ?? 0
      if (observedMass === 0) {
        // if selected scan is not eligible for this view
        this.massData = []
        return
      }

      let theoreticalMass = this.theoreticalMass
      // if variable modification is added, update theoretical mass accordingly
      if (!this.variableModData.isEmpty) {
        this.variableModifications.valueOf()
        Object.values(this.variableModifications).forEach((varMass) => {
          theoreticalMass += varMass
        })
      }
      const deltaMassDa = Math.abs(theoreticalMass - observedMass)
      this.massTitle = 'Precursor'
      this.massData = [
        { label: 'Theoretical mass', value: theoreticalMass.toFixed(2) },
        { label: 'Observed mass', value: observedMass.toFixed(2) },
        { label: 'Δ Mass (Da)', value: deltaMassDa.toFixed(2) },
      ]
      if (this.spectrumFragmentation) {
        this.massData.push({ label: 'Fragmentation', value: this.spectrumFragmentation })
      }
    },
    prepareFragmentTable(): void {
      this.selectedFragment = undefined
      this.selectedResidue = undefined
      this.publishSelectedFragment(undefined)
      if (this.usesAnnotator) {
        this.prepareAnnotatedFragmentTable()
        return
      }
      this.fragmentTableSource = []

      if (this.sequence.length <= 0) {
        this.fragmentTableTitle = '' // if no sequence is selected, nothing to show
        return
      }

      if (this.spectrum === undefined) {
        this.fragmentTableTitle = '' // if no scan is selected, nothing to show
        return
      }

      // get the observed mass table info
      // Plain values: the loops below run peaks x fragments times, and a read
      // through Vue's reactive proxies there cost about a second per spectrum
      const observed_masses: number[] = toRaw(this.spectrum.masses ?? [])
      const tolerance = this.fragmentMassTolerance
      const unit = this.toleranceUnit
      const extraFragments = Object.entries(extraFragmentTypeObject)
        .filter(
          ([extraFragmentType]) =>
            this.ionTypesExtra[extraFragmentType as ExtraFragmentType] ||
            extraFragmentType === 'default'
        )
        .map(([_, extraFragment]) => extraFragment)
        .flat()

      // calculate matching masses
      let matching_fragments: Record<string, unknown>[] = []
      const sequence_size = this.sequence_end
      
      this.selectedIonSeries
        .forEach((series) => {
          // The base series' flags and masses; a variant shifts the masses
          const iontype = { text: series.base }
          const isVariant = series.name !== series.base

          // Dont match fragments of an identification whose end is undetermined
          if (isPrefixIon(iontype.text) && (this.sequence_start_reported < 0))
            return
          if (isSuffixIon(iontype.text) && (this.sequence_end_reported < 0))
            return

          const theoretical_frags = this.getFragmentMasses(iontype.text)
          
          for (
            let theoIndex = 0, FragSize = theoretical_frags.length;
            theoIndex < FragSize;
            ++theoIndex
          ) {
            const aaIndex = theoIndex + this.sequence_start

            theoretical_frags[theoIndex].forEach((theoretical_mass) => {
              // if any variable modifications are given, change the theoretical mass accordingly
            if (!this.variableModData.isEmpty) {
              if (iontype.text === 'a' || iontype.text === 'b' || iontype.text === 'c')
                // if this is prefix, add modification mass starting from the theoretical index
                Object.entries(this.variableModifications).forEach(([varIndex, varMass]) => {
                  if (parseInt(varIndex) <= aaIndex) {
                    theoretical_mass += varMass
                  }
                })
              if (iontype.text === 'x' || iontype.text === 'y' || iontype.text === 'z')
                // if this is suffix, add modification mass string from the theoretical index (reverse)
                Object.entries(this.variableModifications).forEach(([varIndex, varMass]) => {
                  if (sequence_size - parseInt(varIndex) <= aaIndex) {
                    theoretical_mass += varMass
                  }
                })
            }
            for (
              let obsIndex = 0, obsSize = observed_masses.length;
              obsIndex < obsSize;
              ++obsIndex
            ) {
              extraFragments.forEach(({ typeName, typeMass }) => {
                // Mass difference = (observed-theoretical)/theoretical*1e6
                const thisTypeMass = theoretical_mass + series.offset + typeMass
                const massDiffDa = observed_masses[obsIndex] - thisTypeMass
                const massDiffPpm = (massDiffDa / thisTypeMass) * 1e6
                if (Math.abs(massDiffDa) > toleranceDa(thisTypeMass, tolerance, unit)) {
                  // if mass difference is larger than tolerance, ignore
                  return
                }

                const matched = {
                  Name: `${series.name}${theoIndex + 1}`,
                  IonType: `${series.name}${typeName}`,
                  IonNumber: theoIndex + 1,
                  TheoreticalMass: thisTypeMass.toFixed(3),
                  ObservedMass: observed_masses[obsIndex], // should not have "toFixed" to be used as comparison factor
                  MassDiffDa: massDiffDa.toFixed(3),
                  MassDiffPpm: massDiffPpm.toFixed(3),
                }
                matching_fragments.push(matched)
                // setting the fragment mark for fragment map
                let aa_index = aaIndex
                if (iontype.text === 'a' || iontype.text === 'b' || iontype.text === 'c')
                  this.sequenceObjects[aa_index][`${iontype.text}Ion`] = true
                if (iontype.text === 'x' || iontype.text === 'y' || iontype.text === 'z') {
                  this.sequenceObjects[sequence_size - theoIndex][`${iontype.text}Ion`] = true
                  aa_index = sequence_size - theoIndex
                }
                if (typeName || isVariant) {
                  this.sequenceObjects[aa_index]['extraTypes'].push(`${series.name}${typeName}`)
                }
              })
            }
          })
        }
        })
      this.residueCleavagePercentage = this.calculateCleavagePercentage
      this.fragmentTableData = matching_fragments
      this.fragmentTableTitle = `Matching fragments (# ${matching_fragments.length})`
    },
    // Externally annotated fragment ions: the envelopes accepted on the raw
    // spectrum, no matching against the deconvolved masses here.
    prepareAnnotatedFragmentTable(): void {
      if (this.sequence.length <= 0) {
        this.fragmentTableTitle = ''
        return
      }
      const selectedTypes = new Set(
        this.ionTypes.filter((iontype) => iontype.selected).map((iontype) => iontype.text)
      )
      const rows: Record<string, unknown>[] = []
      const source: AnnotatedFragment[] = []
      let terminalCount = 0
      let internalCount = 0
      ;(this.annotatedFragments ?? []).forEach((fragment) => {
        const objects = this.sequenceObjects
        if (fragment.start < 0 || fragment.end >= objects.length) {
          return
        }
        if (fragment.kind === 'I') {
          if (!this.showInternal) return
          for (let r = fragment.start; r <= fragment.end; r++) {
            objects[r].internalDepth = (objects[r].internalDepth ?? 0) + 1
          }
          objects[fragment.start].internalStart = true
          objects[fragment.end].internalEnd = true
          internalCount++
        } else {
          // z+1 / z+2 are drawn as z
          const base = fragment.ion_type.charAt(0) as 'a' | 'b' | 'c' | 'x' | 'y' | 'z'
          if (!selectedTypes.has(base)) return
          const residue = fragment.kind === 'N' ? fragment.end : fragment.start
          objects[residue][`${base}Ion`] = true
          if (fragment.ion_type.length > 1) {
            objects[residue].extraTypes.push(fragment.ion_type)
          }
          terminalCount++
        }
        source.push(fragment)
        rows.push({
          Name: fragment.name,
          IonType: fragment.ion_type,
          Charge: fragment.charge,
          TheoreticalMass: fragment.mono_mass.toFixed(3),
          ObservedMass: fragment.observed_mass,
          Mz: fragment.mz.toFixed(4),
          MassDiffPpm: fragment.ppm_error.toFixed(2),
          Cosine: fragment.cosine.toFixed(3),
          Peaks: `${fragment.matched_peaks}/${fragment.predicted_peaks}`,
          Intensity: fragment.intensity,
        })
      })
      this.fragmentTableSource = source
      this.residueCleavagePercentage = this.calculateCleavagePercentage
      this.fragmentTableData = rows
      this.fragmentTableTitle = this.hasInternalFragments
        ? `Matched fragments (# ${terminalCount} terminal, ${internalCount} internal fragments)`
        : `Matched fragments (# ${terminalCount})`
    },
    inSelectedInternalSpan(aaIndex: number): boolean {
      const f = this.selectedFragment
      return f !== undefined && f.kind === 'I' && this.showInternal && f.start <= aaIndex && aaIndex <= f.end
    },
    onInternalFragmentSelected(fragment: AnnotatedFragment) {
      // the row of the most intense envelope of that piece (one row per charge)
      let best = -1
      this.fragmentTableSource.forEach((f, i) => {
        if (f.kind === fragment.kind && f.ion_type === fragment.ion_type && f.start === fragment.start && f.end === fragment.end) {
          if (best < 0 || f.intensity > this.fragmentTableSource[best].intensity) best = i
        }
      })
      this.selectedFragment = fragment
      if (best >= 0) {
        this.selectedFragTableRowIndex = best
      }
    },
    // Annotator masses are envelope masses, not the deconvolved masses: link
    // them to the mass table within the fragment tolerance
    massLinkTolerance(mass: number): number {
      if (this.usesAnnotator) {
        return toleranceDa(mass, this.fragmentMassTolerance, this.toleranceUnit)
      }
      return 0.001 // 0.001 Da tolerance for floating point precision
    },
    fixedModification(aminoAcid: string): boolean {
      return this.fixedModificationSites.includes(aminoAcid)
    },
    initializeSequenceObjects(): void {
      this.sequenceObjects = []
      this.sequence.forEach((aa, index) => {
        const cov = this.coverage[index]
        let truncated = false
        if ((this.sequence_start > index) || (this.sequence_end < index)) {
          truncated = true
        }
        
        this.sequenceObjects.push({
          aminoAcid: aa,
          coverage: cov,
          truncated: truncated,
          aIon: false,
          bIon: false,
          cIon: false,
          xIon: false,
          yIon: false,
          zIon: false,
          // The tag can arrive before a rebuild (e.g. with a new entry)
          tagStart: this.selectedTag?.startPos == index,
          tagEnd : this.selectedTag?.endPos == index,
          modStart : false,
          modEnd : false,
          modCenter : false,
          modMass : '',
          modLabels : '',
          extraTypes: [],
          internalDepth: 0,
          internalStart: false,
          internalEnd: false,
        })
      })
    },
    aminoAcidSelected(aaIndex: number) {
      this.selectedResidue = aaIndex
      if (this.usesAnnotator) {
        // terminal fragment cleaving at this residue first, else the most
        // intense internal piece covering it
        const objects = this.sequenceObjects
        const terminal = this.fragmentTableSource.findIndex((f) =>
          (f.kind === 'N' && f.end === aaIndex) || (f.kind === 'C' && f.start === aaIndex))
        let row = terminal
        if (row < 0 || !(objects[aaIndex].aIon || objects[aaIndex].bIon || objects[aaIndex].cIon
          || objects[aaIndex].xIon || objects[aaIndex].yIon || objects[aaIndex].zIon)) {
          row = -1
          this.fragmentTableSource.forEach((f, i) => {
            if (f.kind === 'I' && f.start <= aaIndex && aaIndex <= f.end) {
              if (row < 0 || f.intensity > this.fragmentTableSource[row].intensity) row = i
            }
          })
        }
        if (row < 0) row = terminal
        if (row >= 0) {
          this.selectedFragment = this.fragmentTableSource[row]
          this.selectedFragTableRowIndex = row
          this.updateMassTableFromFragmentMass(this.fragmentTableSource[row].observed_mass)
        }
        return
      }
      let ionName = ''
      const this_seqObj = this.sequenceObjects[aaIndex]
      if (this_seqObj.aIon) {
        ionName = `a${aaIndex - this.sequence_start + 1}`
      } else if (this_seqObj.bIon) {
        ionName = `b${aaIndex - this.sequence_start + 1}`
      } else if (this_seqObj.cIon) {
        ionName = `c${aaIndex - this.sequence_start + 1}`
      } else if (this_seqObj.xIon) {
        ionName = `x${this.sequence_end - aaIndex + 1}`
      } else if (this_seqObj.yIon) {
        ionName = `y${this.sequence_end - aaIndex + 1}`
      } else {
        ionName = `z${this.sequence_end - aaIndex + 1}`
      }
      // find matching fragments from the table
      this.selectedFragTableRowIndex = this.fragmentTableData.findIndex((x) => x.Name === ionName)
      // update mass table selection using the observed mass
      if (this.selectedFragTableRowIndex >= 0) {
        this.updateMassTableFromFragmentMass(
          this.fragmentTableData[this.selectedFragTableRowIndex].ObservedMass as number
        )
      }
    },
    // Bounds of a fragment table row (database positions), for linked views
    fragmentSelectionOf(rowIndex?: number): FragmentSelection | null {
      if (rowIndex === undefined || rowIndex < 0) return null
      if (this.usesAnnotator) {
        const f = this.fragmentTableSource[rowIndex]
        return f === undefined ? null : { name: f.name, kind: f.kind, start: f.start, end: f.end }
      }
      const row = this.fragmentTableData[rowIndex]
      if (row === undefined) return null
      const ion = String(row.IonType).charAt(0)
      const n = row.IonNumber as number
      if (['a', 'b', 'c'].includes(ion)) {
        return { name: row.Name as string, kind: 'N', start: this.sequence_start, end: this.sequence_start + n - 1 }
      }
      return { name: row.Name as string, kind: 'C', start: this.sequence_end - n + 1, end: this.sequence_end }
    },
    publishSelectedFragment(rowIndex?: number) {
      const id = this.args.fragmentIdentifier
      if (!id) return
      const next = this.fragmentSelectionOf(rowIndex)
      // Skip no-op writes: each write is a round trip to Python
      if (JSON.stringify(next) === JSON.stringify(this.selectionStore.$state[id] ?? null)) return
      this.selectionStore.updateSelection(id, next)
    },
    onFragmentTableRowSelected(rowIndex?: number) {
      this.publishSelectedFragment(rowIndex)
      if (rowIndex !== undefined && this.fragmentTableSource[rowIndex]) {
        this.selectedFragment = this.fragmentTableSource[rowIndex]
      }
      if (rowIndex !== undefined && this.fragmentTableData[rowIndex]) {
        const observedMass = this.fragmentTableData[rowIndex].ObservedMass as number
        this.updateMassTableFromFragmentMass(observedMass)
      }
    },
    updateMassTableFromFragmentMass(observedMass: number) {
      // Prevent circular updates
      if (this._updatingFromMass) {
        return
      }
      
      this._updatingFromFragment = true
      
      const massArray: number[] | undefined = this.spectrum?.masses
      
      if (!massArray || massArray.length === 0) {
        this._updatingFromFragment = false
        return
      }

      // Try exact match first
      let massIndex = massArray.findIndex((mass) => mass === observedMass)
      
      // If no exact match, find the closest match within tolerance (floating point precision issue)
      if (massIndex < 0) {
        const tolerance = this.massLinkTolerance(observedMass)
        const closeMatches = massArray.map((mass, index) => ({
          index,
          mass,
          diff: Math.abs(mass - observedMass)
        })).filter(item => item.diff < tolerance).sort((a, b) => a.diff - b.diff)
        
        if (closeMatches.length > 0) {
          massIndex = closeMatches[0].index
        }
      }
      
      // Skip no-op writes: they advance this frame's selection counter without
      // a round trip, and its stale state would then win over the next click
      if (
        massIndex >= 0 && this.args.massIdentifier &&
        this.selectionStore.$state[this.args.massIdentifier] !== massIndex
      ) {
        this.selectionStore.updateSelection(this.args.massIdentifier, massIndex)
      }
      
      this._updatingFromFragment = false
    },
    updateFragmentTableFromMassSelection(massIndex: number) {
      // Prevent circular updates
      if (this._updatingFromFragment) {
        return
      }
      
      this._updatingFromMass = true
      
      // Get the mass value from the mass data at the given index
      let selectedMass: number | undefined = undefined
      
      const massArray: number[] | undefined = this.spectrum?.masses
      
      if (!massArray || massIndex >= massArray.length || massIndex < 0) {
        this._updatingFromMass = false
        return
      }
      
      selectedMass = massArray[massIndex]
      
      if (!selectedMass) {
        this._updatingFromMass = false
        return
      }
      
      // Find matching fragment in the fragment table data using tolerance-based matching
      const tolerance = this.massLinkTolerance(selectedMass)
      let bestMatch: { index: number; diff: number } | null = null
      
      for (let i = 0; i < this.fragmentTableData.length; i++) {
        const fragmentRow = this.fragmentTableData[i]
        const observedMass = fragmentRow.ObservedMass as number
        
        if (observedMass !== undefined) {
          const massDiff = Math.abs(observedMass - selectedMass)
          
          if (massDiff < tolerance) {
            if (!bestMatch || massDiff < bestMatch.diff) {
              bestMatch = { index: i, diff: massDiff }
            }
          }
        }
      }
      
      if (bestMatch) {
        if (this.selectedFragTableRowIndex !== bestMatch.index) {
          this.selectedFragTableRowIndex = bestMatch.index
        }
      } else {
        this.selectedFragTableRowIndex = undefined
      }
      
      this._updatingFromMass = false
    },
    updateTagPosition() {
      // Protein without sequence selected
      if (this.sequence.length <= 0) {
        return
      }
      // No sequences in data
      if (this.sequenceObjects.length !== this.sequence.length) {
        this.initializeSequenceObjects()
      }

      this.sequence.forEach((aa, index) => {
        const start = this.selectedTag?.startPos == index
        const end = this.selectedTag?.endPos == index
        this.sequenceObjects[index].tagStart = start
        this.sequenceObjects[index].tagEnd = end
      })
    },
    prepareAmbigiousModifications() {
      this.modifications.forEach((modification) => {
        const start = modification.start
        const end = modification.end
        const mass = modification.mass_diff.toFixed(2)
        const labels = modification.labels
        const mass_display = parseFloat(mass).toLocaleString('en-US', { signDisplay: 'always' })
        for (let index = start; index <= end; index++) {
          if (index == start) {
            this.sequenceObjects[index].modStart = true
          }
          if (index == end) {
            this.sequenceObjects[index].modEnd = true
            this.sequenceObjects[index].modMass = mass_display
            this.sequenceObjects[index].modLabels = labels
          }
          if ((index != start) && (index != end)) {
            this.sequenceObjects[index].modCenter = true
          }
        }
      })
    },
    setSelectedAA(position?: number): void {
      const id = this.args.aaIdentifier
      if (!id) return
      const value = position ?? null
      // Skip no-op writes: each write is a round trip to Python
      if ((this.selectionStore.$state[id] ?? null) === value) return
      this.selectionStore.updateSelection(id, value)
    },
    async copySequence(): Promise<void> {
      try {
        if (this.sequence.length === 0) {
          return
        }
        
        const sequenceToCopy = this.sequence.slice(this.sequence_start, this.sequence_end + 1).join('')
        
        if (!navigator.clipboard) {
          throw new Error('Clipboard API not available')
        }
        
        await navigator.clipboard.writeText(sequenceToCopy)
        this.copySnackbarText = 'Sequence copied to clipboard!'
        this.copySnackbar = true
      } catch (error) {
        this.copySnackbarText = 'Failed to copy sequence to clipboard'
        this.copySnackbar = true
        console.error('Copy failed:', error)
      }
    },
    proForma(): string {
      const modifications: ProFormaModification[] = this.modifications.map((m) => ({
        start: m.start,
        end: m.end,
        mass: m.mass_diff,
      }))
      for (const [index, mass] of Object.entries(this.variableModifications)) {
        if (mass) modifications.push({ start: Number(index), end: Number(index), mass })
      }
      return toProForma({
        sequence: this.sequence,
        start: this.sequence_start,
        end: this.sequence_end,
        fixed: (this.args.modifications ?? []).map(fixedFromId),
        modifications,
      })
    },
    async copyProForma(): Promise<void> {
      try {
        const text = this.proForma()
        if (!text) return
        if (!navigator.clipboard) {
          throw new Error('Clipboard API not available')
        }
        await navigator.clipboard.writeText(text)
        this.copySnackbarText = 'ProForma copied to clipboard!'
        this.copySnackbar = true
      } catch (error) {
        this.copySnackbarText = 'Failed to copy ProForma to clipboard'
        this.copySnackbar = true
        console.error('Copy failed:', error)
      }
    },
    toggleRegexHighlight(): void {
      this.showRegexHighlight = !this.showRegexHighlight
      if (!this.showRegexHighlight) {
        this.regexPattern = ''
        this.regexError = ''
        this.regexHighlightedIndices.clear()
      }
    },
    onRegexInput(): void {
      this.regexError = ''
      this.regexHighlightedIndices.clear()
      
      if (!this.regexPattern) {
        return
      }
      
      try {
        const regex = new RegExp(this.regexPattern, 'gi')
        const sequenceString = this.sequence.join('')
        
        let match
        while ((match = regex.exec(sequenceString)) !== null) {
          // Highlight all characters in the match
          for (let i = match.index; i < match.index + match[0].length; i++) {
            this.regexHighlightedIndices.add(i)
          }
          
          // Prevent infinite loop for zero-length matches
          if (match[0].length === 0) {
            break
          }
        }
      } catch (error) {
        this.regexError = 'Invalid regex pattern'
        console.warn('Regex error:', error)
      }
    },
    // Sequence change dialog methods
    openSequenceDialog(): void {
      this.customSequenceInput = ''
      this.customModifications = [...(this.args.modifications ?? [])]
      this.sequenceInputError = ''
      this.sequenceDialog = true
    },
    closeSequenceDialog(): void {
      this.sequenceDialog = false
      this.customSequenceInput = ''
      this.sequenceInputError = ''
    },
    submitCustomSequence(): void {
      // The picked modifications first, so the rebuild for the sequence uses them
      if (this.args.modificationsIdentifier && this.modificationItems.length > 0) {
        this.selectionStore.updateSelection(
          this.args.modificationsIdentifier,
          [...this.customModifications]
        )
      }
      // Python rebuilds the view for the new sequence
      if (this.args.sequenceIdentifier) {
        this.selectionStore.updateSelection(
          this.args.sequenceIdentifier,
          this.customSequenceInput.toUpperCase()
        )
      }
      
      // Close dialog
      this.sequenceDialog = false
      this.customSequenceInput = ''
      this.sequenceInputError = ''
    },
  },
})
</script>

<style lang="scss">
/* Option labels at medium emphasis and the regex field's height, as in the
   view's first release (dialogs and menus render outside the component) */
.sequence-controls .v-selection-control .v-label {
  opacity: var(--v-medium-emphasis-opacity);
}
.sequence-regex-field .v-field__input {
  padding-top: 19px;
  padding-bottom: 4px;
}
</style>

<style scoped lang="scss">
.sequence-view-row {
  display: flex;
}

.sequence-view-column {
  flex: 0 1 100%;
}

.sequence-grid {
  display: grid;
  grid-template-rows: auto;
  gap: 4px 4px;

  > div {
    aspect-ratio: 1;
  }
}

.protein-terminal {
  &:hover {
    background-color: var(--amino-acid-cell-hover-bg-color);
    color: var(--amino-acid-cell-hover-color);
  }
}

/* Residue columns may shrink below their content (minmax(0, 1fr)): with
   plain 1fr a long residue label widened the grid past its container, so the
   last column ran under the coverage scale */
.sequence-grid > .row-number {
  aspect-ratio: auto;
  display: flex;
  align-items: center;
  padding: 0 4px;
  font-size: var(--row-number-font-size, 12px);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  opacity: var(--v-medium-emphasis-opacity);
}

.row-number-start {
  justify-content: flex-end;
}

.row-number-end {
  justify-content: flex-start;
}

/* Label and value pairs above the sequence: whole pairs wrap to the next
   line, a label never splits from its value */
.summary-line {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: baseline;
  column-gap: 24px;
  row-gap: 2px;
}

.summary-title {
  margin-right: 4px;
}

/* Drawn at the width it is given: the table's columns (and the internal
   fragment track's SVG) keep the width of their last layout, so without
   this a frame that narrowed would stay as wide as before */
.fit-width,
.sequence-part :deep(.internal-track) {
  contain: inline-size;
}

.summary-pair {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  white-space: nowrap;
}

.summary-label {
  opacity: var(--v-medium-emphasis-opacity);
}

.summary-value {
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.sequence-and-scale {
    display: flex;
    align-items: center;
  }

  /* Never narrower than its scale, and clear of the row numbers */
  .scale-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    flex-shrink: 0;
    margin-left: 8px;
  }

  .sequence-part {
    flex-grow: 1;
    min-width: 0;
  }

  .scale {
    width: 60px;
    height: 100px; /* Adjust the width as needed */
    background: linear-gradient(
      to top, 
      rgba(228, 87, 46, 0.1),
      rgba(228, 87, 46, 0.2) 10%,
      rgba(228, 87, 46, 0.4) 20%,
      rgba(228, 87, 46, 0.6) 40%,
      rgba(228, 87, 46, 0.8) 70%,
      rgba(228, 87, 46, 1) 100%
    );
  }

  .scale-text {
    text-align: center;
    font-size: 14pt;
    font-weight: bold;
  }
</style>
@/types/sequence-data