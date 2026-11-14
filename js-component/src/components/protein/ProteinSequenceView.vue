<template>
  <!-- The header wraps whole label and value pairs, the residue grid puts
       fewer residues in a row, and the fragment table scrolls inside itself:
       the view fits a narrow frame instead of scrolling it sideways -->
  <!-- The Change sequence dialog is drawn inside this frame, which fits the
       view: while it is open, the view is at least as tall as the dialog and
       the fixed-modification list below its field -->
  <div
    class="sequence-view-row"
    :style="sequenceDialog ? { minHeight: `${SEQUENCE_DIALOG_HEIGHT + (args.uniprotLookup ? UNIPROT_ROW_HEIGHT : 0)}px` } : undefined"
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
        <v-chip v-if="isEdited" size="small" color="warning" variant="tonal" class="summary-pair">
          Edited
          <v-tooltip activator="parent" location="bottom">
            Sequence and modifications differ from the search result
          </v-tooltip>
        </v-chip>
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
            v-if="canStartEdit"
            variant="text"
            icon="mdi-pencil"
            size="large"
            @click="startEdit"
          >
            <v-icon>mdi-pencil</v-icon>
            <v-tooltip activator="parent" location="bottom">
              Edit sequence and modifications
            </v-tooltip>
          </v-btn>
          <v-btn
            v-if="isEdited"
            variant="text"
            icon="mdi-restore"
            size="large"
            @click="resetEdit"
          >
            <v-icon>mdi-restore</v-icon>
            <v-tooltip activator="parent" location="bottom">
              Reset to the search result
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
                      v-for="category in shownExtraFragmentTypes"
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
                <v-list-item v-if="isotopeErrorsEnabled && !usesAnnotator">
                  <v-list-item-title>Isotope errors</v-list-item-title>
                  <v-switch
                    v-model="isotopeMatching"
                    color="primary"
                    density="compact"
                    hide-details
                    label="Match isotope errors"
                    :disabled="!showFragments"
                  ></v-switch>
                  <v-text-field
                    v-if="isotopeMatching"
                    style="min-width: 0"
                    :model-value="isotopeErrors"
                    type="number"
                    step="1"
                    min="1"
                    max="5"
                    hide-details="auto"
                    label="up to ± isotopes"
                    :hint="`Also match masses off by whole isotopes (± n × ${isotopeSpacing} Da)`"
                    persistent-hint
                    :disabled="!showFragments"
                    @change="updateIsotopeErrors"
                  ></v-text-field>
                </v-list-item>
              </v-list>
            </v-card>
          </v-menu>
        </div>
      </div>
      <!-- A ProForma the app gave that the view cannot read -->
      <v-alert
        v-if="proformaSyncError"
        type="error"
        variant="tonal"
        density="compact"
        class="mx-4 mb-2"
      >
        {{ proformaSyncError }}
      </v-alert>
      <!-- No sequence yet: one button opens the Change sequence dialog -->
      <div
        v-if="sequence.length === 0 && shouldShowSequenceChangeButton && !isEdited"
        class="d-flex flex-column align-center text-center py-6 px-4"
      >
        <v-btn
          :color="accentColor"
          variant="tonal"
          size="large"
          prepend-icon="mdi-dna"
          class="text-none"
          @click="openSequenceDialog"
        >
          {{ args.uniprotLookup ? 'Enter a sequence or UniProt accession' : 'Enter a sequence' }}
        </v-btn>
        <div class="text-body-2 text-medium-emphasis mt-2">
          One-letter codes{{ args.proformaInput ? ', or ProForma with modifications' : '' }}{{ args.uniprotLookup ? ', or the sequence of a UniProt entry' : '' }}
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
          <!-- With truncations hidden, a break line one cell per truncated
               residue (at most a row) stands for the residues outside the
               proteoform. The first row runs: an empty row-number cell, the
               break line (positions, then zig-zag), N, the sequence; the last:
               the sequence, C, the break line (zig-zag, then positions), on a
               row of its own when the rest of C's row is too short for it. -->
          <div
            v-if="aa_index === sequence_start && truncatedBefore > 0"
            class="truncated-gap"
          ></div>
          <TruncationBreak
            :range="truncatedRange(1, truncatedBefore)" :text="truncatedText(truncatedBefore, 1, truncatedBefore)"
            :mass="truncatedMassText(0, truncatedBefore)" :residues="truncatedResidues(0, truncatedBefore)"
            testid="truncated-n-term" data-testid="truncated-n-term"
            v-if="aa_index === sequence_start && truncatedBefore > 0 && nBreakCells > 0"
            :cells="nBreakCells" :style="{ gridColumn: `span ${nBreakCells}` }"
          />
          <ProteinTerminalCell
            v-if="(aa_index === 0 && truncatedBefore === 0) || (aa_index === sequence_start && truncatedBefore > 0)"
            protein-terminal="N-term" :truncated=n_truncation :index="-1"
            :disable-variable-modification-selection="disableVariableModifications" :determined="n_determined" :font-size="fontSize"
          />
          <div
            v-if="(showTruncations && (aa_index !== 0) && (aa_index % perRow === 0)) || (!showTruncations && (aa_index >= sequence_start) && (aa_index <= sequence_end) && (gridCell(aa_index) === 0) && (aa_index > sequence_start || truncatedBefore > 0))"
            class="row-number row-number-start"
            :style="showTruncations ? undefined : { gridColumn: '1' }"
          >
          {{ aa_index + 1 }}
          </div>
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
            v-if="(showTruncations && (aa_index % perRow === perRow - 1 && aa_index !== sequence.length - 1)) || (!showTruncations && (gridCell(aa_index) === perRow - 1) && (aa_index < sequence_end) && (aa_index >= sequence_start))"
            class="row-number row-number-end"
          >
            {{ aa_index + 1 }}
          </div>
          <ProteinTerminalCell
            v-if="aa_index === sequence.length - 1"
            protein-terminal="C-term" :truncated=c_truncation
            :index="sequence.length"
            :disable-variable-modification-selection="disableVariableModifications"
            :determined="c_determined"
            :font-size="fontSize"
          />
          <TruncationBreak
            :range="truncatedRange(sequence_end + 2, sequence.length)" :text="truncatedText(truncatedAfter, sequence_end + 2, sequence.length)"
            :mass="truncatedMassText(sequence_end + 1, sequence.length)" :residues="truncatedResidues(sequence_end + 1, sequence.length)"
            end testid="truncated-c-term" data-testid="truncated-c-term"
            v-if="aa_index === sequence.length - 1 && truncatedAfter > 0 && cBreakInline"
            :cells="cBreakCells" :style="{ gridColumn: `span ${cBreakCells}` }"
          />
          <TruncationBreak
            :range="truncatedRange(sequence_end + 2, sequence.length)" :text="truncatedText(truncatedAfter, sequence_end + 2, sequence.length)"
            :mass="truncatedMassText(sequence_end + 1, sequence.length)" :residues="truncatedResidues(sequence_end + 1, sequence.length)"
            end testid="truncated-c-term" data-testid="truncated-c-term"
            v-if="aa_index === sequence.length - 1 && truncatedAfter > 0 && !cBreakInline"
            :cells="cBreakCells" :style="{ gridColumn: `2 / span ${cBreakCells}` }"
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
      <!-- What the matched fragments say about each modification range -->
      <div
        v-for="note in spanNotes"
        :key="`span-${note.index}`"
        class="d-flex align-center flex-wrap px-4 mb-2 text-body-2"
        :class="note.warning ? 'text-warning' : ''"
      >
        <v-icon size="small" class="mr-1">{{ note.warning ? 'mdi-alert-outline' : 'mdi-target' }}</v-icon>
        <span>{{ note.text }}</span>
        <v-btn
          v-if="note.narrow && args.proformaIdentifier"
          size="x-small"
          variant="tonal"
          class="ml-2 text-none"
          @click="narrowSpan(note.index)"
        >
          Narrow to {{ note.narrow }}
        </v-btn>
      </div>
      <!-- Variable modifications set on residues, with the library only -->
      <div
        v-if="(variableModData.library !== null || isEdited || hasLocalizationNotes) && appliedVariableModifications.length > 0"
        class="d-flex flex-wrap align-center px-2 pb-2 variable-modification-list"
      >
        <span class="text-body-2 mr-2">{{ isEdited ? 'Modifications:' : 'Variable modifications:' }}</span>
        <v-chip
          v-for="mod in appliedVariableModifications"
          :key="mod.index"
          size="small"
          class="mr-1 mb-1"
          :color="mod.note ? 'warning' : undefined"
          :prepend-icon="mod.note ? 'mdi-help-circle-outline' : undefined"
          closable
          @click:close="variableModData.updateVariableModifications(mod.index, 0)"
        >
          {{ mod.text }}
          <v-tooltip v-if="mod.note" activator="parent" location="bottom">
            Ambiguous: {{ mod.note }}
          </v-tooltip>
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
          :table-data="fragmentRows"
          :column-definitions="usesAnnotator ? annotatorTableColumnDefinitions : fragmentColumns"
          :index="index"
          :selected-row-index-from-listening="selectedFragTableRowIndex"
          :go-to-fields="['Name']"
          :filter-presets="fragmentFilterPresets"
          table-layout-param="fitColumns"
          @row-selected="onFragmentTableRowSelected"
          @preset-changed="onFragmentPresetChanged"
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
        <!-- A UniProt accession fills the field below with its sequence -->
        <div v-if="args.uniprotLookup" class="mb-4">
          <div class="d-flex align-start" style="gap: 8px">
            <v-text-field
              v-model="uniprotAccession"
              label="UniProt accession (optional)"
              placeholder="e.g. P0ACF0"
              density="compact"
              clearable
              :error-messages="uniprotError"
              :hint="uniprotEntry ? undefined : 'Gets the sequence of the entry; edit it or add modifications below'"
              :persistent-hint="!uniprotEntry"
              @keydown.enter.prevent="lookUpUniProt"
            >
              <template #prepend-inner>
                <v-icon>mdi-database-search</v-icon>
              </template>
            </v-text-field>
            <v-btn
              :color="accentColor"
              variant="tonal"
              :loading="uniprotLoading"
              :disabled="!uniprotAccession || !uniprotAccession.trim()"
              style="margin-top: 2px"
              @click="lookUpUniProt"
            >
              Get sequence
            </v-btn>
          </div>
          <div v-if="uniprotEntry" class="text-caption" style="margin-top: -14px">
            <a :href="uniprotEntry.url" target="_blank" rel="noopener">{{ uniprotEntry.accession }}</a>
            · {{ uniprotEntry.entryName }} · {{ uniprotEntry.proteinName }}
            <template v-if="uniprotEntry.organism"> · <i>{{ uniprotEntry.organism }}</i></template>
            · {{ uniprotEntry.sequence.length }} residues
          </div>
        </div>
        <!-- The example shows only while typing, under the raised label -->
        <v-textarea
          v-model="customSequenceInput"
          :label="args.proformaInput ? 'Protein sequence or ProForma' : 'Protein Sequence'"
          :placeholder="sequenceInputFocused ? (args.proformaInput ? 'e.g. MKFLVNVALVF... or <[Carbamidomethyl]@C>[Acetyl]-MK[Acetyl]S[+79.9663]...' : 'Enter amino acid sequence (e.g., MKFLVNVALVF...)') : undefined"
          @update:focused="sequenceInputFocused = $event"
          :error-messages="sequenceInputError"
          :rows="modificationItems.length > 0 ? 3 : 6"
          auto-grow
          counter
          :hint="args.proformaInput ? 'Single-letter codes, or ProForma with fixed, terminal and residue modifications' : 'Enter single-letter amino acid codes only'"
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
import type { FragmentMatches, MatchedFragmentIon, ProteinSequenceViewComponentArgs } from '@/types/component'
import type {
  AnnotatedFragment,
  AnnotationSummary,
  FragmentSettings,
  ModificationData,
  FragmentSelection,
  IdentificationEdit,
  MatchedSpectrum,
  SequenceTag,
  SequenceData,
} from '@/types/protein-sequence-data'
import type { SequenceObject } from '@/types/protein-sequence-object'
import type { ColumnDefinition } from 'tabulator-tables'
import FragmentTable from './FragmentTable.vue'
import type { FilterPreset } from '../filterPresets'
import AminoAcidCell from './ProteinAminoAcidCell.vue'
import ProteinTerminalCell from './ProteinTerminalCell.vue'
import ImageScreenshot from './ImageScreenshot.vue'
import SequenceViewInformation from './SequenceViewInformation.vue'
import InternalFragmentTrack from './InternalFragmentTrack.vue'
import TruncationBreak from './TruncationBreak.vue'
import { STANDARD_RESIDUE_MASSES } from '@/utils/measure'
import { builtInLibrary, extraFragmentTypeObject, type ExtraFragmentType } from '@/components/sequence/modification'
import {
  describeLocalization,
  localizeModifications,
  type ModificationLocalization,
} from './modification-localization'
import {
  findLibraryId,
  fixedFromId,
  formatMass,
  parseProForma,
  ProFormaError,
  toProForma,
  type ProFormaModification,
} from './proforma'
import { fetchUniProtEntry, type UniProtEntry } from './uniprot'
import type { ProFormaLink, ProFormaRead } from '@/types/protein-sequence-data'
import {
  CUSTOM_METHOD,
  FRAGMENTATION_METHODS,
  ION_VARIANTS,
  canonicalIonName,
  ionSeries,
  isPrefixIon,
  isSuffixIon,
  hydrogenShiftExpected,
  methodForIons,
  methodIons,
  formatIsotopeOffset,
  isotopeOffsets,
  matchIsotopeOffset,
  ISOTOPE_SPACING,
  toleranceDa,
  toleranceUnit,
  type IonSeries,
  type ToleranceUnit,
} from './fragment-ions'

// Fixed decimals for long numbers in the fragment tables
// Height (px) the Change sequence dialog needs: title, the sequence field,
// the fixed-modification picker with its open list, and the buttons
const SEQUENCE_DIALOG_HEIGHT = 640
// Extra height of the UniProt accession row above the sequence field
const UNIPROT_ROW_HEIGHT = 90

// The modifications over several residues, as a key to compare entries by
function spanKey(mods: { start: number; end: number; mass: number }[]): string {
  return mods
    .filter((m) => m.start !== m.end)
    .map((m) => `${m.start}:${m.end}:${m.mass.toFixed(3)}`)
    .sort()
    .join(',')
}

// A modification range and the window its matched fragments leave
// (lo..hi; lo > hi: they disagree), and whether any carries its shift
type SpanLocalization = {
  start: number; end: number; mass: number; lo: number; hi: number
  // any fragment cut in the range matched with the shift; how many agree with
  // lo..hi (negative: as many say the shift is not there, they disagree)
  support: boolean; agree: number; total: number
}

// Where a range's shift sits, by the fragments cut inside it: a prefix ion
// ending at `edge` carries the shift when it sits at or before edge, a suffix
// ion starting at `edge` when it sits at or after it. Every residue of the
// range is scored by the fragments that agree with it; the best scored ones
// are the window. Votes, not hard bounds: a large fragment matching by chance
// (near the precursor, with an isotope error) does not empty the window.
function localizeSpan(
  m: { start: number; end: number; mass_diff: number },
  evidence: { prefix: boolean; edge: number; carries: boolean }[],
): SpanLocalization {
  const base = { start: m.start, end: m.end, mass: m.mass_diff, total: evidence.length }
  const support = evidence.some((e) => e.carries)
  if (!support) return { ...base, lo: m.start, hi: m.end, support, agree: evidence.length }
  let best = -1
  let lo = m.start
  let hi = m.end
  for (let p = m.start; p <= m.end; p++) {
    const agree = evidence.filter((e) => e.carries === (e.prefix ? p <= e.edge : p >= e.edge)).length
    if (agree > best) {
      best = agree
      lo = p
      hi = p
    } else if (agree === best) {
      hi = p
    }
  }
  // The shift not in the range at all: every fragment without it agrees.
  // When that explains the fragments as well as any residue, they do not
  // support the shift there
  const without = evidence.filter((e) => !e.carries).length
  if (without > best) return { ...base, lo: m.start, hi: m.end, support: false, agree: without }
  // As many say "not here" as agree on any residue: they disagree
  if (without === best) return { ...base, lo: m.start, hi: m.end, support: true, agree: -without }
  return { ...base, lo, hi, support, agree: best }
}
type SpanNote = { index: number; text: string; warning: boolean; narrow: string | null }

// ProForma name of a residue menu label: a library id such as
// 'Acetyl (N-term)' gives 'Acetyl'; a custom mass or a sum has none
function proFormaName(label: string | undefined): string | undefined {
  if (!label || label === 'Custom' || label.includes(' + ')) return undefined
  if (/^[+-]?\d/.test(label)) return undefined
  return label.replace(/\s*\([^)]*\)$/, '')
}

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

// Same residues and masses (labels aside), for localized modifications
function sameModifications(a: ModificationData[], b: ModificationData[]): boolean {
  const key = (list: ModificationData[]) =>
    list
      .filter((m) => m.start === m.end && m.mass_diff)
      .map((m) => `${m.start}:${m.mass_diff.toFixed(6)}`)
      .sort()
      .join('|')
  return key(a) === key(b)
}

export default defineComponent({
  name: 'ProteinSequenceView',
  components: {
    SequenceViewInformation,
    FragmentTable,
    AminoAcidCell,
    ProteinTerminalCell,
    ImageScreenshot,
    InternalFragmentTrack,
    TruncationBreak,
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
      // Isotope errors tried in matching while isotopeMatching is on
      isotopeErrors: 1 as number,
      // The settings switch: match isotope errors at all
      isotopeMatching: false,
      isotopeSpacing: ISOTOPE_SPACING,
      visibilityOptions: [
        { text: 'Fragments', selected: true },
        { text: 'Modifications', selected: true },
        { text: 'Ambiguous fragments', selected: true },
      ] as { text: string; selected: boolean }[],
      // Per modification range: where the matched fragments place its shift
      spanLocalizations: [] as SpanLocalization[],
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
      // Observed masses no selected fragment ion matches (unmatchedMasses):
      // rows appended to the fragment table while the filter is off
      unmatchedTableData: [] as Record<string, unknown>[],
      unmatchedTableTitle: '' as string,
      unmatchedTableTooltip: '' as string,
      // Mirrors the 'Hide unmatched masses' preset of the fragment table
      showUnmatched: false as boolean,
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
      UNIPROT_ROW_HEIGHT,
      // UniProt lookup in the change-sequence dialog
      uniprotAccession: '' as string | null,
      uniprotError: '' as string,
      uniprotLoading: false as boolean,
      uniprotEntry: null as UniProtEntry | null,
      // Two-way ProForma link with the app (args.proformaIdentifier): the
      // residues a ProForma from the app asked for, until the view shows them
      pendingProFormaSequence: null as string | null,
      // ... and the spans of several residues the app's entry then has
      pendingProFormaSpans: null as string | null,
      // A ProForma from the app whose pyOpenMS reading has not come yet
      waitingProForma: null as string | null,
      // Number of the app's (or the dialog's) request the view shows
      appliedProFormaN: 0,
      proformaSyncError: '' as string,
      // Modification ids picked in the change-sequence dialog
      customModifications: [] as string[],
      // Where the matched fragments place each modification set on a residue
      localizations: [] as ModificationLocalization[],
      customSequenceInput: '' as string,
      sequenceInputError: '' as string,
      sequenceInputFocused: false,
    }
  },
  computed: {
    // The shown proteoform as ProForma, for the app's identifier
    proFormaText(): string {
      return this.args.proformaIdentifier ? this.proForma() : ''
    },
    // The app's ProForma as pyOpenMS read it (Python side), when it can
    proformaRead(): ProFormaRead | undefined {
      return (this.streamlitDataStore.allDataForDrawing.proformaRead as ProFormaRead | null) ?? undefined
    },
    // What is in the ProForma identifier: {text, by, n}. 'app' and 'dialog'
    // are requests, numbered; 'view' is what the view shows, with the number
    // of the request it answers. A plain string counts as a request.
    proformaLink(): ProFormaLink | null {
      const id = this.args.proformaIdentifier
      if (!id) return null
      const value = this.selectionStore.$state[id] as unknown
      if (typeof value === 'string') return { text: value, by: 'app', n: 0 }
      if (value && typeof value === 'object' && typeof (value as ProFormaLink).text === 'string') {
        return value as ProFormaLink
      }
      return null
    },
    // The ProForma the app (or the dialog) asked for, null when none is new
    externalProForma(): string | null {
      const link = this.proformaLink
      if (!link || link.by === 'view') return null
      return link.text
    },
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
    // method_ion_options: proton loss/addition only where a hydrogen moves
    // between the fragments (electron-based or photo fragmentation)
    protonShiftAllowed(): boolean {
      return !this.args.methodIonOptions || hydrogenShiftExpected(this.selectedIonSeries)
    },
    shownExtraFragmentTypes(): ExtraFragmentType[] {
      return (Object.keys(this.ionTypesExtra) as ExtraFragmentType[]).filter(
        (type) => type !== 'proton loss/addition' || this.protonShiftAllowed,
      )
    },
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
    // isotope_errors given: show the setting, the Isotope column and the
    // precursor's ppm and isotope reading
    isotopeErrorsEnabled(): boolean {
      return typeof this.args.isotopeErrors === 'number'
    },
    // Isotope errors matching uses: 0 while the switch is off
    activeIsotopeErrors(): number {
      return this.isotopeErrorsEnabled && this.isotopeMatching ? this.isotopeErrors : 0
    },
    // Modifications over several residues (an ambiguous range or an
    // unlocalized shift): the shift sits on one residue in the range
    spanModifications(): ModificationData[] {
      if (this.isEdited) return []
      const n = this.sequence.length
      return this.modifications.filter((m) => m.start !== m.end && m.start >= 0 && m.end < n && !!m.mass_diff)
    },
    showAmbiguousFragments(): boolean {
      return this.visibilityOptions.find((o) => o.text === 'Ambiguous fragments')?.selected ?? true
    },
    // What the matched fragments say about each range, as a line under the sequence
    spanNotes(): SpanNote[] {
      if (this.usesAnnotator || this.spectrum === undefined) return []
      const residue = (i: number) => `${this.sequence[i]}${i + 1}`
      const range = (a: number, b: number) => (a === b ? residue(a) : `${residue(a)}–${residue(b)}`)
      return this.spanLocalizations.flatMap((span, index): SpanNote[] => {
        const shift = formatMass(span.mass)
        const where = span.start === this.sequence_start && span.end === this.sequence_end
          ? 'anywhere in the sequence'
          : `in ${range(span.start, span.end)}`
        if (span.total === 0) return []
        if (!span.support) {
          const said = span.agree === span.total
            ? `None of the ${span.total} fragments cut ${where} matched with the ${shift} shift`
            : `${span.agree} of the ${span.total} fragments cut ${where} matched without the ${shift} shift`
          return [{ index, warning: true, narrow: null,
            text: `${said}: they do not support it there` }]
        }
        if (span.agree < 0) {
          const without = -span.agree
          return [{ index, warning: true, narrow: null,
            text: `The ${span.total} fragments cut ${where} disagree on the ${shift} shift (${span.total - without} with it, ${without} without)` }]
        }
        const votes = `${span.agree} of ${span.total} fragments cut in the range agree`
        if (span.lo === span.start && span.hi === span.end) {
          return [{ index, warning: span.agree < span.total, narrow: null,
            text: `The fragments do not narrow down the ${shift} shift ${where} (${votes})` }]
        }
        return [{ index, warning: span.agree < span.total, narrow: range(span.lo, span.hi),
          text: `The fragments place the ${shift} shift at ${range(span.lo, span.hi)} (${votes})` }]
      })
    },
    unmatchedAvailable(): boolean {
      return this.args.unmatchedMasses === true && !this.usesAnnotator &&
        this.unmatchedTableTitle !== ''
    },
    // The fragment table's rows: the matched fragments, then the unmatched
    // masses, which the table's 'Hide unmatched masses' preset hides by default
    fragmentRows(): Record<string, unknown>[] {
      if (!this.unmatchedAvailable) return this.fragmentTableData
      return [...this.fragmentTableData, ...this.unmatchedTableData]
    },
    fragmentFilterPresets(): FilterPreset[] {
      if (!this.unmatchedAvailable) return []
      return [{
        id: 'hide-unmatched',
        label: `Hide ${this.unmatchedTableTitle}`,
        help: this.unmatchedTableTooltip,
        filters: [{ column: 'Unmatched', op: '!=', value: true }],
        default: true,
      }]
    },
    fragmentColumns(): ColumnDefinition[] {
      const columns = this.columnsWithIsotope
      if (!this.unmatchedAvailable) return columns
      const at = columns.findIndex((column) => column.field === 'Name') + 1
      return [
        ...columns.slice(0, at),
        {
          title: 'Nearest ion', field: 'Nearest',
          headerTooltip: 'For an unmatched mass: the theoretical fragment ion (of the selected types) closest to it. The theoretical mass and the mass differences of that row are to this ion, outside the tolerance.',
        } as unknown as ColumnDefinition,
        ...columns.slice(at),
      ]
    },
    columnsWithIsotope(): ColumnDefinition[] {
      // a Shift column while a modification spans several residues
      const columns = this.spanModifications.length === 0
        ? this.fragmentTableColumnDefinitions
        : [
            ...this.fragmentTableColumnDefinitions,
            {
              title: 'Shift', field: 'Shift',
              headerTooltip: 'For a fragment cut inside a modification range: whether it matched with or without that shift. Such a fragment is ambiguous, since the shift may sit on either side of the cut; it narrows the range down but is not counted as a match.',
            } as unknown as ColumnDefinition,
          ]
      if (this.activeIsotopeErrors === 0) return columns
      const at = columns.findIndex((column) => column.field === 'ObservedMass') + 1
      return [
        ...columns.slice(0, at),
        {
          title: 'Isotope', field: 'Isotope', sorter: 'number',
          formatter: (cell: { getValue: () => unknown }) => {
            const value = cell.getValue()
            return typeof value === 'number' ? formatIsotopeOffset(value) : ''
          },
          headerTooltip: `Whole isotopes the observed mass is off from the theoretical one (× ${ISOTOPE_SPACING} Da); the mass differences are to the theoretical mass shifted by them.`,
        } as unknown as ColumnDefinition,
        ...columns.slice(at),
      ]
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
    /** Cells of the N-terminal break line: one per truncated residue, at
     *  most a row beside N */
    nBreakCells(): number {
      return Math.min(this.truncatedBefore, Math.max(this.perRow - 1, 0))
    },
    /** Cells before the first residue of the proteoform in the grid's first
     *  row: the break line and N (truncations hidden) */
    gridOffset(): number {
      return this.truncatedBefore > 0 ? this.nBreakCells + 1 : 0
    },
    /** Cells of the C-terminal break line: one per truncated residue, at
     *  most a row */
    cBreakCells(): number {
      return Math.min(this.truncatedAfter, this.perRow)
    },
    /** The C-terminal break line fits in the cells left after C in the last
     *  row; C takes the row-number column when the last residue ends a row */
    cBreakInline(): boolean {
      const last = this.gridCell(this.sequence_end)
      const free = last === this.perRow - 1 ? 0 : this.perRow - 2 - last
      return this.cBreakCells <= free
    },
    /** Residues before the proteoform truncated from the grid (truncations hidden) */
    truncatedBefore(): number {
      return this.showIdentification && !this.showTruncations ? this.sequence_start : 0
    },
    /** Residues after the proteoform truncated from the grid (truncations hidden) */
    truncatedAfter(): number {
      return this.showIdentification && !this.showTruncations
        ? Math.max(0, this.sequence.length - 1 - this.sequence_end)
        : 0
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
      // An identification's modifications are its search's, until it is edited
      if (this.showIdentification && !this.isEdited) {
        return true
      }
      return false
    },
    // The entry was edited in this view (the app returns it with edited: true)
    isEdited(): boolean {
      return this.showIdentification && !!this.args.editIdentifier && this.entry?.edited === true
    },
    canStartEdit(): boolean {
      return this.showIdentification && !!this.args.editIdentifier && !this.isEdited
        && this.sequence.length > 0
    },
    hasLocalizationNotes(): boolean {
      return this.localizations.some((l) => describeLocalization(l, this.sequence) !== '')
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
    appliedVariableModifications(): { index: number; text: string; note: string }[] {
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
          const loc = this.localizations.find((l) => l.index === index)
          const note = loc && (loc.ambiguous || loc.misplaced || loc.conflict) ? describeLocalization(loc, this.sequence) : ''
          return { index, text: `${site} ${name ? name + ' ' : ''}${shift} Da`, note }
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
      return (!this.showIdentification && !!this.args.sequenceIdentifier) || this.isEdited
    },
    // The edited identification's modifications as the store holds them
    storeModifications(): ModificationData[] {
      const masses = this.variableModData.variableModifications ?? {}
      const labels = this.variableModData.variableModLabels ?? {}
      return Object.entries(masses)
        .map(([key, mass]) => ({ index: Number(key), mass }))
        .filter((m) => m.mass && !Number.isNaN(m.mass))
        .sort((a, b) => a.index - b.index)
        .map(({ index, mass }) => ({ start: index, end: index, mass_diff: mass, labels: labels[index] ?? '' }))
    },
  },
  watch: {
    // The view's proteoform changed (sequence, fixed or variable modifications)
    proFormaText() {
      this.publishProForma()
    },
    // The app gave a new ProForma
    externalProForma(value: string | null) {
      const link = this.proformaLink
      if (value === null || !link) return
      if (link.n !== 0 && link.n <= this.appliedProFormaN) return
      this.appliedProFormaN = link.n
      if (value === this.proFormaText) {
        this.publishProForma()
        return
      }
      this.applyExternalProForma(value)
    },
    // pyOpenMS's reading of it can come a render later
    proformaRead(read: ProFormaRead | undefined) {
      const value = this.externalProForma
      if (!read || value === null || read.text !== value) return
      if (value === this.proFormaText) {
        this.waitingProForma = null
        return
      }
      this.applyExternalProForma(value)
    },
    protonShiftAllowed(allowed: boolean) {
      if (!allowed) this.ionTypesExtra['proton loss/addition'] = false
    },
    // An error about the input goes once the input changes
    customSequenceInput() {
      this.sequenceInputError = ''
    },
    uniprotAccession() {
      this.uniprotError = ''
    },
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
      this.syncStoreFromEntry()
      this.recomputeFragments()
      this.updateSettings()
    },
    // A modification set or removed on an edited identification: the app
    // keeps the edit, so it outlasts a rerun and a reload
    'variableModData.variableMod'() {
      if (!this.isEdited) return
      if (sameModifications(this.storeModifications, this.entry?.modifications ?? [])) return
      this.writeEdit({
        action: 'update',
        sequence: this.sequence.join(''),
        start_position: this.sequence_start_reported,
        end_position: this.sequence_end_reported,
        modifications: this.storeModifications,
      })
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
    // Ambiguous fragments shown or left out
    showAmbiguousFragments() {
      this.recomputeFragments()
    },
    toleranceUnit() {
      this.recomputeFragments()
    },
    activeIsotopeErrors() {
      this.recomputeFragments()
    },
    'args.isotopeErrors'(value) {
      this.applyIsotopeErrorsArg(value)
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
    this.syncStoreFromEntry()
    this.updateSettings()
    // A ProForma the app gave before the view existed, else the view's own
    if (this.externalProForma !== null && this.externalProForma !== this.proFormaText) {
      this.appliedProFormaN = this.proformaLink?.n ?? 0
      this.applyExternalProForma(this.externalProForma)
    } else {
      this.publishProForma()
    }
    if (typeof this.args.isotopeErrors === 'number') {
      this.applyIsotopeErrorsArg(this.args.isotopeErrors)
    }
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
    updateIsotopeErrors(event: Event) {
      const value = Number.parseInt((event.target as any).value as string, 10)
      if (Number.isFinite(value) && value >= 1) {
        this.isotopeErrors = Math.min(value, 5)
      }
    },
    // isotope_errors n: the switch starts on for n > 0 (off for 0), the
    // field at n (1 while off)
    applyIsotopeErrorsArg(value: unknown) {
      const n = typeof value === 'number' ? Math.max(0, Math.floor(value)) : 0
      this.isotopeMatching = n > 0
      this.isotopeErrors = Math.min(Math.max(n, 1), 5)
    },
    // Δ in ppm and the isotope reading of a precursor (or entry) mass
    precursorIsotopeRows(theoretical: number, observed: number): SummaryItem[] {
      if (!this.isotopeErrorsEnabled || !(theoretical > 0) || !(observed > 0)) return []
      const delta = observed - theoretical
      const rows: SummaryItem[] = [
        { label: 'Δ Mass (ppm)', value: ((delta / theoretical) * 1e6).toFixed(1) },
      ]
      const k = matchIsotopeOffset(
        observed, theoretical, isotopeOffsets(this.activeIsotopeErrors),
        this.fragmentMassTolerance, this.toleranceUnit
      )
      let reading = this.activeIsotopeErrors > 0 ? `none within ±${this.activeIsotopeErrors}` : 'not checked'
      if (k === 0) reading = '0'
      else if (k !== undefined) {
        const shifted = theoretical + k * ISOTOPE_SPACING
        reading = `${formatIsotopeOffset(k)} (then ${(((observed - shifted) / shifted) * 1e6).toFixed(1)} ppm)`
      }
      rows.push({ label: 'Isotope error', value: reading })
      return rows
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
    /** "1–23": protein positions (1-based) of truncated residues, the
     *  label of the break line marking a truncated terminus */
    truncatedRange(first: number, last: number): string {
      return first === last ? `${first}` : `${first}–${last}`
    },
    /** "23 residues truncated (1–23)": hover text and accessible label
     *  of the break line */
    truncatedText(count: number, first: number, last: number): string {
      return `${count} ${count === 1 ? 'residue' : 'residues'} truncated (${this.truncatedRange(first, last)})`
    },
    /** Cell (0-based column of the residue cells) of residue `index` in
     *  the grid with truncations hidden */
    gridCell(index: number): number {
      return (this.gridOffset + index - this.sequence_start) % this.perRow
    },
    /** Summed monoisotopic residue masses (Da) of the truncated residues
     *  (0-based, end exclusive); null when one of them is not a standard
     *  residue */
    truncatedMass(start: number, end: number): number | null {
      let mass = 0
      for (const aa of this.sequence.slice(start, end)) {
        const m = STANDARD_RESIDUE_MASSES[aa === 'I' || aa === 'L' ? 'I/L' : aa]
        if (m === undefined) return null
        mass += m
      }
      return mass
    },
    /** "Residue mass 2,156.21 Da": hover text of the break line */
    truncatedMassText(start: number, end: number): string | null {
      const mass = this.truncatedMass(start, end)
      if (mass === null) return null
      return `Residue mass ${mass.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Da`
    },
    /** The truncated residues themselves (0-based, end exclusive), shown on hover */
    truncatedResidues(start: number, end: number): string {
      return this.sequence.slice(start, end).join('')
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
    // An extra fragment type is matched when ticked and, for proton
    // loss/addition, allowed by the selected series (method_ion_options)
    extraTypeActive(type: ExtraFragmentType): boolean {
      if (type === 'proton loss/addition' && !this.protonShiftAllowed) return false
      return this.ionTypesExtra[type] ?? false
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
        // An edited entry's mass is that of its unmodified sequence: add the
        // modifications set in the view
        let theoretical = this.theoreticalMass
        if (this.isEdited) {
          Object.values(this.variableModifications).forEach((m) => {
            if (m && !Number.isNaN(m)) theoretical += m
          })
        }
        if (this.entryObservedMass > 0) {
          observed_mass = this.entryObservedMass.toFixed(2)
          delta_mass = Math.abs(theoretical - this.entryObservedMass).toFixed(2)
        }


        this.massData = [
          { label: this.isEdited ? 'Theoretical mass' : 'Theoretical protein mass', value: theoretical.toFixed(2) },
          { label: this.args.observedMassLabel ?? 'Observed mass', value: observed_mass },
          { label: 'Δ Mass (Da)', value: delta_mass },
          ...this.precursorIsotopeRows(theoretical, this.entryObservedMass),
        ]
        if (this.spectrumFragmentation) {
          this.massData.push({ label: 'Fragmentation', value: this.spectrumFragmentation })
        }

        // Ensures this is only executed once
        if (!this.visibilityOptions.some(option => option.text === 'Tags')) {
          // settings.show_truncations === false starts with the truncated
          // termini summarized instead of drawn
          this.visibilityOptions.push({ text: 'Truncations', selected: this.settings?.show_truncations !== false })
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
      let theoreticalMass = this.theoreticalMass
      // if variable modification is added, update theoretical mass accordingly
      if (!this.variableModData.isEmpty) {
        this.variableModifications.valueOf()
        Object.values(this.variableModifications).forEach((varMass) => {
          theoreticalMass += varMass
        })
      }
      this.massTitle = 'Precursor'
      this.massData = []
      // Without a sequence there is no theoretical mass to show
      if (this.sequence.length > 0) {
        this.massData.push({ label: 'Theoretical mass', value: theoreticalMass.toFixed(2) })
      }
      // Without a precursor mass: no observed mass to compare with
      if (observedMass > 0) {
        const deltaMassDa = Math.abs(theoreticalMass - observedMass)
        this.massData.push(
          { label: 'Observed mass', value: observedMass.toFixed(2) },
          ...(this.sequence.length > 0
            ? [
                { label: 'Δ Mass (Da)', value: deltaMassDa.toFixed(2) },
                ...this.precursorIsotopeRows(theoreticalMass, observedMass),
              ]
            : []),
        )
      }
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
      this.unmatchedTableData = []
      this.unmatchedTableTitle = ''
      this.unmatchedTableTooltip = ''

      if (this.sequence.length <= 0) {
        this.fragmentTableTitle = '' // if no sequence is selected, nothing to show
        this.publishFragmentMatches(null)
        return
      }

      if (this.spectrum === undefined) {
        this.fragmentTableTitle = '' // if no scan is selected, nothing to show
        this.publishFragmentMatches(null)
        return
      }

      // get the observed mass table info
      // Plain values: the loops below run peaks x fragments times, and a read
      // through Vue's reactive proxies there cost about a second per spectrum
      const observed_masses: number[] = toRaw(this.spectrum.masses ?? [])
      const tolerance = this.fragmentMassTolerance
      const unit = this.toleranceUnit
      const offsets = isotopeOffsets(this.activeIsotopeErrors)
      const extraFragments = Object.entries(extraFragmentTypeObject)
        .filter(
          ([extraFragmentType]) =>
            this.extraTypeActive(extraFragmentType as ExtraFragmentType) ||
            extraFragmentType === 'default'
        )
        .map(([_, extraFragment]) => extraFragment)
        .flat()

      // calculate matching masses
      let matching_fragments: Record<string, unknown>[] = []
      const matchedIons: MatchedFragmentIon[] = []
      const sequence_size = this.sequence_end
      // Ranges of a modification: a fragment cut inside one may carry the
      // shift or not (its masses list both); the one that matched says on
      // which side of the cut the shift sits
      const spans = this.spanModifications
      const evidence: { prefix: boolean; edge: number; carries: boolean }[][] = spans.map(() => [])
      let ambiguousCount = 0
      // The theoretical fragment closest to each observed mass (unmatchedMasses)
      const trackNearest = this.args.unmatchedMasses === true
      const nearestName: string[] = new Array(observed_masses.length).fill('')
      const nearestDiff: number[] = new Array(observed_masses.length).fill(Infinity)
      
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

            theoretical_frags[theoIndex].forEach((theoretical_mass, altIndex) => {
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
                  if (parseInt(varIndex) >= sequence_size - theoIndex) {
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
                if (trackNearest) {
                  const diff = observed_masses[obsIndex] - thisTypeMass
                  if (Math.abs(diff) < Math.abs(nearestDiff[obsIndex])) {
                    nearestDiff[obsIndex] = diff
                    nearestName[obsIndex] = `${series.name}${theoIndex + 1}${typeName}`
                  }
                }
                // The smallest isotope offset (0 without isotope errors) that
                // brings the masses within the tolerance
                const isotope = matchIsotopeOffset(
                  observed_masses[obsIndex], thisTypeMass, offsets, tolerance, unit
                )
                if (isotope === undefined) return
                const shiftedMass = thisTypeMass + isotope * ISOTOPE_SPACING
                const massDiffDa = observed_masses[obsIndex] - shiftedMass
                const massDiffPpm = (massDiffDa / shiftedMass) * 1e6

                // A prefix ion ends at residue `edge`, a suffix ion starts there
                const prefix = isPrefixIon(iontype.text)
                const edge = prefix ? aaIndex : sequence_size - theoIndex
                let ambiguousShift: number | null = null
                spans.forEach((m, j) => {
                  const cut = prefix ? m.start <= edge && edge < m.end : m.start < edge && edge <= m.end
                  if (!cut) return
                  ambiguousShift = m.mass_diff
                  evidence[j].push({ prefix, edge, carries: altIndex > 0 })
                })
                const ambiguous = ambiguousShift !== null
                if (ambiguous && !this.showAmbiguousFragments) return
                if (ambiguous) ambiguousCount++

                const matched = {
                  Name: `${series.name}${theoIndex + 1}`,
                  IonType: `${series.name}${typeName}`,
                  IonNumber: theoIndex + 1,
                  TheoreticalMass: thisTypeMass.toFixed(3),
                  ObservedMass: observed_masses[obsIndex], // should not have "toFixed" to be used as comparison factor
                  MassDiffDa: massDiffDa.toFixed(3),
                  MassDiffPpm: massDiffPpm.toFixed(3),
                  ...(spans.length > 0
                    ? { Shift: ambiguous ? `${altIndex > 0 ? 'with' : 'without'} ${formatMass(ambiguousShift ?? 0)} (ambiguous)` : '' }
                    : {}),
                }
                matching_fragments.push(
                  this.isotopeErrorsEnabled ? { ...matched, Isotope: isotope } : matched
                )
                matchedIons.push({
                  name: matched.Name,
                  ion: matched.IonType,
                  kind: isPrefixIon(iontype.text) ? 'N' : 'C',
                  mass: observed_masses[obsIndex],
                  massIndex: obsIndex,
                })
                // setting the fragment mark for fragment map; an ambiguous
                // fragment is drawn faint and does not count as a cleavage
                let aa_index = aaIndex
                if (iontype.text === 'x' || iontype.text === 'y' || iontype.text === 'z') {
                  aa_index = sequence_size - theoIndex
                }
                if (ambiguous) {
                  const object = this.sequenceObjects[aa_index]
                  object.ambiguousIons = [...(object.ambiguousIons ?? []), iontype.text]
                } else {
                  this.sequenceObjects[aa_index][`${iontype.text}Ion`] = true
                }
                if (typeName || isVariant) {
                  this.sequenceObjects[aa_index]['extraTypes'].push(`${series.name}${typeName}`)
                }
              })
            }
          })
        }
        })
      this.spanLocalizations = spans.map((m, j) => localizeSpan(m, evidence[j]))
      this.residueCleavagePercentage = this.calculateCleavagePercentage
      this.fragmentTableData = matching_fragments
      this.fragmentTableTitle = ambiguousCount > 0
        ? `Matching fragments (# ${matching_fragments.length - ambiguousCount}, ${ambiguousCount} ambiguous)`
        : `Matching fragments (# ${matching_fragments.length})`
      if (trackNearest) {
        const matchedIndices = new Set(matchedIons.map((ion) => ion.massIndex))
        const rows: Record<string, unknown>[] = []
        observed_masses.forEach((mass, obsIndex) => {
          if (matchedIndices.has(obsIndex)) return
          const diff = nearestDiff[obsIndex]
          const known = Number.isFinite(diff)
          rows.push({
            Name: 'unmatched',
            IonType: '',
            Nearest: nearestName[obsIndex],
            TheoreticalMass: known ? (mass - diff).toFixed(3) : '',
            ObservedMass: mass,
            MassDiffDa: known ? diff.toFixed(3) : '',
            MassDiffPpm: known ? ((diff / (mass - diff)) * 1e6).toFixed(3) : '',
            Unmatched: true,
          })
        })
        this.unmatchedTableData = rows
        this.unmatchedTableTitle =
          `unmatched masses (${rows.length} of ${observed_masses.length})`
        this.unmatchedTableTooltip =
          'Observed masses no fragment ion of the selected types matches. Shown, each is listed as \'unmatched\' with the nearest fragment ion and the differences to it.'
      }
      this.publishFragmentMatches(matchedIons)
    },
    // Externally annotated fragment ions: the envelopes accepted on the raw
    // spectrum, no matching against the deconvolved masses here.
    prepareAnnotatedFragmentTable(): void {
      if (this.sequence.length <= 0) {
        this.fragmentTableTitle = ''
        this.publishFragmentMatches(null)
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
      this.publishFragmentMatches(
        source.map((fragment) => ({
          name: fragment.name,
          ion: fragment.ion_type,
          kind: fragment.kind,
          mass: fragment.observed_mass,
          massIndex: this.massIndexOf(fragment.observed_mass),
          charge: fragment.charge,
          mz: fragment.mz,
        }))
      )
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
    // Index of the spectrum's mass nearest `mass` within the link tolerance, or null
    massIndexOf(mass: number): number | null {
      const masses: number[] = toRaw(this.spectrum?.masses ?? [])
      const tolerance = this.massLinkTolerance(mass)
      let best: number | null = null
      for (let i = 0; i < masses.length; i++) {
        const diff = Math.abs(masses[i] - mass)
        if (diff <= tolerance && (best === null || diff < Math.abs(masses[best] - mass))) best = i
      }
      return best
    },
    // The matched ions, for spectra to mark (fragmentMatchesIdentifier); null
    // while no spectrum is matched
    publishFragmentMatches(fragments: MatchedFragmentIon[] | null) {
      const id = this.args.fragmentMatchesIdentifier
      if (!id) return
      const next: FragmentMatches | null =
        fragments === null
          ? null
          : {
              spectrum: this.spectrum?.key ?? null,
              tolerance: { value: this.fragmentMassTolerance, unit: this.toleranceUnit },
              fragments,
              ...(this.args.fragmentMatchesProteoform ? { proteoform: this.matchedProteoform() } : {}),
            }
      // Skip no-op writes: each write is a round trip to Python
      if (JSON.stringify(next) === JSON.stringify(this.selectionStore.$state[id] ?? null)) return
      this.selectionStore.updateSelection(id, next)
    },
    // The proteoform the fragments are matched against (fragmentMatchesProteoform)
    matchedProteoform(): NonNullable<FragmentMatches['proteoform']> {
      let theoreticalMass = this.theoreticalMass
      for (const mass of Object.values(this.variableModifications)) theoreticalMass += mass
      return {
        proforma: this.proForma(),
        sequence: this.sequence.join(''),
        length: this.sequence.length,
        theoreticalMass,
        cleavagePercentage: this.calculateCleavagePercentage,
      }
    },
    publishSelectedFragment(rowIndex?: number) {
      const id = this.args.fragmentIdentifier
      if (!id) return
      const next = this.fragmentSelectionOf(rowIndex)
      // Skip no-op writes: each write is a round trip to Python
      if (JSON.stringify(next) === JSON.stringify(this.selectionStore.$state[id] ?? null)) return
      this.selectionStore.updateSelection(id, next)
    },
    onFragmentPresetChanged(id: string, active: boolean) {
      if (id === 'hide-unmatched') this.showUnmatched = !active
    },
    onFragmentTableRowSelected(rowIndex?: number) {
      const row = rowIndex === undefined ? undefined : this.fragmentRows[rowIndex]
      // An unmatched mass is no fragment: only the mass table follows it
      this.publishSelectedFragment(row?.Unmatched ? undefined : rowIndex)
      if (rowIndex !== undefined && !row?.Unmatched && this.fragmentTableSource[rowIndex]) {
        this.selectedFragment = this.fragmentTableSource[rowIndex]
      }
      if (row) {
        this.updateMassTableFromFragmentMass(row.ObservedMass as number)
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
      
      for (let i = 0; i < this.fragmentRows.length; i++) {
        const fragmentRow = this.fragmentRows[i]
        // Hidden unmatched rows cannot be selected
        if (fragmentRow.Unmatched && !this.showUnmatched) continue
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
      // An edited entry's modifications are in the store, drawn per residue
      const fromData = this.isEdited ? [] : this.modifications
      fromData.forEach((modification) => {
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
      // The window the fragments leave for a range's shift
      for (const span of this.spanLocalizations) {
        if (!span.support || span.agree < 0) continue
        if (span.lo === span.start && span.hi === span.end) continue
        for (let i = span.lo; i <= span.hi; i++) {
          const o = this.sequenceObjects[i]
          if (!o) continue
          o.ambStart = o.ambStart || i === span.lo
          o.ambEnd = o.ambEnd || i === span.hi
          o.ambCenter = o.ambCenter || (i !== span.lo && i !== span.hi)
        }
      }
      this.prepareModificationLocalization()
    },
    // Narrow a range down to the window its fragments leave (through the app)
    narrowSpan(index: number): void {
      const id = this.args.proformaIdentifier
      const span = this.spanLocalizations[index]
      const target = this.spanModifications[index]
      if (!id || !span || !target) return
      const text = this.proForma({ target, start: span.lo, end: span.hi })
      this.selectionStore.updateSelection(id, {
        text,
        by: 'dialog',
        n: Math.max(this.appliedProFormaN, this.proformaLink?.n ?? 0) + 1,
      })
    },
    // Where the matched fragments place each modification set on a residue:
    // a window of several possible residues (or several modifications of the
    // same mass) is marked on the sequence and in the list of modifications
    prepareModificationLocalization(): void {
      this.localizations = []
      if (this.usesAnnotator || this.spectrum === undefined || this.sequence.length === 0) return
      if (this.variableModData.isEmpty) return
      if (this.sequenceObjects.length !== this.sequence.length) return
      const extraMasses = Object.entries(extraFragmentTypeObject)
        .filter(([type]) => this.extraTypeActive(type as ExtraFragmentType) || type === 'default')
        .flatMap(([, list]) => list.map((e) => e.typeMass))
      const series = this.selectedIonSeries.filter((s) => {
        if (isPrefixIon(s.base) && this.sequence_start_reported < 0) return false
        if (isSuffixIon(s.base) && this.sequence_end_reported < 0) return false
        return true
      })
      const reference = this.spectrum.precursorMass || this.entryObservedMass || this.theoreticalMass
      const localizations = localizeModifications({
        sequence: this.sequence,
        start: this.sequence_start,
        end: this.sequence_end,
        fragmentMasses: (base) => this.getFragmentMasses(base),
        series,
        extraMasses,
        observedMasses: toRaw(this.spectrum.masses ?? []),
        tolerance: this.fragmentMassTolerance,
        unit: this.toleranceUnit,
        modifications: toRaw(this.variableModifications),
        library: this.variableModData.library ?? builtInLibrary(),
        referenceMass: reference ?? 0,
      })
      for (const loc of localizations) {
        const note = describeLocalization(loc, this.sequence)
        const object = this.sequenceObjects[loc.index]
        if (object && (loc.ambiguous || loc.misplaced || loc.conflict) && note) {
          object.modNote = note
        }
        // The window the fragments allow, when it holds more than one candidate
        if (loc.conflict || loc.evidence === 0) continue
        if (!(loc.candidates.length > 1 || loc.misplaced)) continue
        for (let i = loc.lo; i <= loc.hi; i++) {
          const o = this.sequenceObjects[i]
          if (!o) continue
          o.ambStart = o.ambStart || i === loc.lo
          o.ambEnd = o.ambEnd || i === loc.hi
          o.ambCenter = o.ambCenter || (i !== loc.lo && i !== loc.hi)
        }
      }
      this.localizations = localizations
    },
    // In an editable identification, the store holds the shown entry's
    // modifications: the search's are only in the fragment masses
    syncStoreFromEntry(): void {
      if (!this.args.editIdentifier) return
      if (this.isEdited) {
        const masses: Record<number, number> = {}
        const labels: Record<number, string> = {}
        for (const m of this.modifications) {
          if (m.start !== m.end || !m.mass_diff) continue
          masses[m.start] = m.mass_diff
          if (m.labels) labels[m.start] = m.labels
        }
        if (!sameModifications(this.storeModifications, this.modifications)) {
          this.variableModData.setAll(masses, labels)
        }
      } else if (this.showIdentification && !this.variableModData.isEmpty) {
        this.variableModData.clear()
      }
    },
    writeEdit(edit: Omit<IdentificationEdit, 'nonce'>): void {
      const id = this.args.editIdentifier
      if (!id) return
      // A new nonce each time: the app applies every edit once
      this.selectionStore.updateSelection(id, { ...edit, nonce: Date.now() })
    },
    startEdit(): void {
      this.writeEdit({ action: 'edit' })
    },
    resetEdit(): void {
      this.writeEdit({ action: 'reset' })
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
    proForma(narrow?: { target: ModificationData; start: number; end: number }): string {
      // An edited identification carries its modifications in the residue
      // menus' store (below) only
      const searched = this.isEdited ? [] : this.modifications
      const modifications: ProFormaModification[] = searched.map((m) => {
        const name = proFormaName(m.labels ?? undefined)
        const at = narrow && m === narrow.target ? { start: narrow.start, end: narrow.end } : { start: m.start, end: m.end }
        return { ...at, mass: m.mass_diff, ...(name ? { name } : {}) }
      })
      const labels = this.variableModData.variableModLabels ?? {}
      for (const [index, mass] of Object.entries(this.variableModifications)) {
        if (!mass) continue
        const name = proFormaName(labels[Number(index)])
        modifications.push({ start: Number(index), end: Number(index), mass, ...(name ? { name } : {}) })
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
      // An edited identification starts from its own residues
      this.customSequenceInput = this.isEdited
        ? this.sequence.slice(this.sequence_start, this.sequence_end + 1).join('')
        : ''
      this.customModifications = [...(this.args.modifications ?? [])]
      this.sequenceInputError = ''
      this.uniprotAccession = ''
      this.uniprotError = ''
      this.uniprotEntry = null
      this.sequenceDialog = true
    },
    // The sequence of a UniProt entry goes into the sequence field
    async lookUpUniProt(): Promise<void> {
      const input = this.uniprotAccession ?? ''
      if (!input.trim() || this.uniprotLoading) return
      this.uniprotLoading = true
      this.uniprotError = ''
      try {
        const entry = await fetchUniProtEntry(input)
        this.uniprotEntry = entry
        this.customSequenceInput = entry.sequence
      } catch (error) {
        this.uniprotEntry = null
        this.uniprotError = error instanceof Error ? error.message : String(error)
      } finally {
        this.uniprotLoading = false
      }
    },
    // The edited residues become the whole sequence; a modification stays on
    // its residue while that residue is unchanged
    submitEditedSequence(residues: string): void {
      if (residues.length === 0) return
      const offset = this.sequence_start
      const old = this.sequence
      const modifications: ModificationData[] = []
      for (const m of this.storeModifications) {
        let index = m.start
        if (index < 0) index = -1
        else if (index >= old.length) index = residues.length
        else {
          index -= offset
          if (index < 0 || index >= residues.length || residues[index] !== old[m.start]) continue
        }
        modifications.push({ ...m, start: index, end: index })
      }
      this.writeEdit({
        action: 'update',
        sequence: residues,
        start_position: 0,
        end_position: residues.length - 1,
        modifications,
      })
    },
    // The shown proteoform goes to the app's ProForma identifier; held back
    // while the view still waits for residues the app asked for
    publishProForma(): void {
      const id = this.args.proformaIdentifier
      if (!id || this.isEdited) return
      // The app's text first, once its reading is there
      if (this.waitingProForma !== null) return
      if (this.pendingProFormaSequence !== null) {
        if (this.sequence.join('') !== this.pendingProFormaSequence) return
        const spans = spanKey(this.modifications.map((m) => ({ start: m.start, end: m.end, mass: m.mass_diff })))
        if (this.pendingProFormaSpans !== null && spans !== this.pendingProFormaSpans) return
        this.pendingProFormaSequence = null
        this.pendingProFormaSpans = null
      }
      const text = this.proFormaText
      // The same text is there already: nothing to tell the app
      if (this.proformaLink?.text === text) return
      this.selectionStore.updateSelection(id, { text, by: 'view', n: this.appliedProFormaN })
    },
    // A ProForma from the app becomes the view's sequence and modifications,
    // as if it was applied in the Change sequence dialog
    applyExternalProForma(text: string): void {
      this.proformaSyncError = ''
      if (this.isEdited) return
      let read
      const fromApp = this.proformaRead
      if (fromApp && fromApp.text === text) {
        this.waitingProForma = null
        // Read by pyOpenMS: residue and terminal modifications go to the
        // residue menus; spans of several residues are in the app's entry
        if (fromApp.error) {
          this.proformaSyncError = fromApp.error
          return
        }
        const masses: Record<number, number> = {}
        const labels: Record<number, string> = {}
        for (const m of fromApp.modifications ?? []) {
          if (m.start !== m.end) continue
          masses[m.start] = (masses[m.start] ?? 0) + m.mass
          labels[m.start] = labels[m.start] ? `${labels[m.start]} + ${m.label}` : m.label
        }
        read = { sequence: fromApp.sequence ?? '', fixedIds: fromApp.fixed_ids ?? [], masses, labels }
      } else if (this.args.proformaReader === 'pyopenms' && /[[\]<>(){}?-]/.test(text)) {
        // ProForma is read by pyOpenMS on the app's side: wait for it
        this.waitingProForma = text
        return
      } else {
        try {
          read = /[[\]<>(){}?-]/.test(text)
            ? this.readProForma(text)
            : { sequence: text.toUpperCase().replace(/\s+/g, ''), fixedIds: [] as string[], masses: {}, labels: {} }
        } catch (error) {
          // The app still sends pyOpenMS's reading of it
          if (this.args.proformaReader === 'pyopenms') {
            this.waitingProForma = text
            return
          }
          this.proformaSyncError = error instanceof Error ? error.message : String(error)
          return
        }
      }
      this.customModifications = [...read.fixedIds]
      if (this.args.modificationsIdentifier) {
        this.selectionStore.updateSelection(this.args.modificationsIdentifier, [...read.fixedIds])
      }
      this.pendingProFormaSequence = read.sequence
      this.pendingProFormaSpans = fromApp && fromApp.text === text
        ? spanKey(fromApp.modifications ?? [])
        : null
      if (this.args.sequenceIdentifier) {
        this.selectionStore.updateSelection(this.args.sequenceIdentifier, read.sequence)
      }
      this.variableModData.setAll(read.masses, read.labels)
      this.$nextTick(() => this.publishProForma())
    },
    // The view goes back to no sequence (an empty ProForma from the app): its
    // residues, fixed and variable modifications are cleared
    clearSequence(): void {
      this.variableModData.clear()
      this.customModifications = []
      if (this.args.modificationsIdentifier) {
        this.selectionStore.updateSelection(this.args.modificationsIdentifier, [])
      }
      if (this.args.sequenceIdentifier) {
        this.selectionStore.updateSelection(this.args.sequenceIdentifier, '')
      }
    },
    closeSequenceDialog(): void {
      this.sequenceDialog = false
      this.customSequenceInput = ''
      this.sequenceInputError = ''
    },
    // A ProForma input as the view's sequence, fixed modification ids and
    // per-residue masses; throws ProFormaError with a message for the dialog
    readProForma(text: string): {
      sequence: string
      fixedIds: string[]
      masses: Record<number, number>
      labels: Record<number, string>
    } {
      const parsed = parseProForma(text)
      const residues = parsed.sequence
      const fixedLibrary = this.args.modificationLibrary ?? []
      const variableLibrary = this.args.variableModificationLibrary ?? []
      const fixedIds: string[] = []
      for (const f of parsed.fixed) {
        const residue = f.site === 'N-term' ? residues[0] : f.site === 'C-term' ? residues[residues.length - 1] : undefined
        const id = findLibraryId(f.name, f.site, fixedLibrary.map((m) => m.id), residue)
        if (!id || !this.args.modificationsIdentifier) {
          throw new ProFormaError(`Unknown fixed modification ${f.name} on ${f.site}`)
        }
        if (!fixedIds.includes(id)) fixedIds.push(id)
      }
      const masses: Record<number, number> = {}
      const labels: Record<number, string> = {}
      for (const m of parsed.modifications) {
        const site = m.index < 0 ? 'N-term' : m.index >= residues.length ? 'C-term' : residues[m.index]
        const where = m.index < 0 ? 'the N-terminus' : m.index >= residues.length ? 'the C-terminus' : `${site}${m.index + 1}`
        let mass = m.mass
        let label = m.name
        if (m.name) {
          const residue = m.index < 0 ? residues[0] : residues[residues.length - 1]
          for (const library of [variableLibrary, fixedLibrary]) {
            const id = findLibraryId(m.name, site, library.map((e) => e.id), residue)
            const entry = id ? library.find((e) => e.id === id) : undefined
            if (entry) {
              mass ??= entry.mass
              label = entry.id
              break
            }
          }
        }
        if (mass === undefined) {
          throw new ProFormaError(`Unknown modification ${m.name} on ${where}: give its mass, e.g. [+42.0106]`)
        }
        masses[m.index] = (masses[m.index] ?? 0) + mass
        const text = label ?? formatMass(mass)
        labels[m.index] = labels[m.index] ? `${labels[m.index]} + ${text}` : text
      }
      return { sequence: residues, fixedIds, masses, labels }
    },
    submitCustomSequence(): void {
      const input = this.customSequenceInput
      // Linked with the app and read by pyOpenMS there: the app takes it
      if (
        this.args.proformaIdentifier && this.args.proformaReader === 'pyopenms' &&
        !this.isEdited && /[[\]<>(){}?-]/.test(input)
      ) {
        this.proformaSyncError = ''
        this.selectionStore.updateSelection(this.args.proformaIdentifier, {
          text: input.trim(),
          by: 'dialog',
          n: Math.max(this.appliedProFormaN, this.proformaLink?.n ?? 0) + 1,
        })
        this.sequenceDialog = false
        this.customSequenceInput = ''
        this.sequenceInputError = ''
        return
      }
      if (this.args.proformaInput && /[[\]<>(){}?-]/.test(input)) {
        let read
        try {
          read = this.readProForma(input)
        } catch (error) {
          this.sequenceInputError = error instanceof Error ? error.message : String(error)
          return
        }
        if (this.isEdited) {
          if (read.fixedIds.length > 0) {
            this.sequenceInputError = 'Fixed modifications cannot be set on an identification'
            return
          }
          this.writeEdit({
            action: 'update',
            sequence: read.sequence,
            start_position: 0,
            end_position: read.sequence.length - 1,
            modifications: Object.entries(read.masses).map(([index, mass]) => ({
              start: Number(index),
              end: Number(index),
              mass_diff: mass,
              labels: read.labels[Number(index)] ?? '',
            })),
          })
        } else {
          if (read.fixedIds.length > 0 && this.args.modificationsIdentifier) {
            this.customModifications = [...new Set([...this.customModifications, ...read.fixedIds])]
            this.selectionStore.updateSelection(this.args.modificationsIdentifier, [...this.customModifications])
          }
          if (this.args.sequenceIdentifier) {
            this.selectionStore.updateSelection(this.args.sequenceIdentifier, read.sequence)
          }
          this.variableModData.setAll(read.masses, read.labels)
        }
        this.sequenceDialog = false
        this.customSequenceInput = ''
        this.sequenceInputError = ''
        return
      }
      if (this.isEdited) {
        this.submitEditedSequence(this.customSequenceInput.toUpperCase().replace(/\s+/g, ''))
        this.sequenceDialog = false
        this.customSequenceInput = ''
        this.sequenceInputError = ''
        return
      }
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

.sequence-grid > .truncated-gap {
  aspect-ratio: auto;
  grid-column: 1;
}

.sequence-grid > .truncated-residues {
  aspect-ratio: auto;
  align-self: center;
  min-width: 0;
  overflow: hidden;
  padding: 0 4px;
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