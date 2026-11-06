<template>
  <div
class="d-flex justify-center align-center rounded-lg" :class="proteinTerminalCellClasses"
    :style="proteinTerminalCellStyles" @click.stop @contextmenu.prevent="toggleMenuOpen">
    <div :class="['terminal-text', { truncated: truncated }]">
      {{ proteinTerminalText }}
    </div>
    <div v-if="!determined" class="undetermined">??</div>
    <v-menu
v-model="menuOpen" activator="parent" location="end" :open-on-click="false" :close-on-content-click="false"
      :width="hasLibrary ? '360px' : '200px'">
      <v-list>
        <v-list-item>
          <ModificationPicker
            v-if="hasLibrary"
            :site="proteinTerminal"
            :options="modificationsForSelect"
            :suggested="variableModData.suggested"
            :selected="selectedModification"
            @pick="updateSelectedModification"
          />
          <v-select
            v-else
            v-model="selectedModification"
            clearable
            label="Modification"
            density="compact"
            :items="modificationsForSelect"
            item-title="title"
            item-value="value"
            @update:model-value="updateSelectedModification"
          />
        </v-list-item>
        <v-list-item v-if="customSelected">
          <v-form @submit.prevent>
            <v-text-field v-model="customModMass" hide-details label="Monoisotopic mass in Da" type="number" />
            <v-btn type="submit" block class="mt-2" @click="updateCustomModification">Submit</v-btn>
          </v-form>
        </v-list-item>
      </v-list>
    </v-menu>
    <v-tooltip activator="parent">
      {{ proteinTerminalText }}
    </v-tooltip>
  </div>
</template>

<script lang="ts">
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useModificationStore } from '@/stores/variable-modification'
import type { Theme } from 'streamlit-component-lib'
import type { PropType } from 'vue'
import { defineComponent } from 'vue'
import { modificationOptions, type ModificationOption } from '@/components/sequence/modification'
import ModificationPicker from './ModificationPicker.vue'

export default defineComponent({
  name: 'ProteinTerminalCell',
  components: { ModificationPicker },
  props: {
    proteinTerminal: {
      type: String as PropType<'N-term' | 'C-term'>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
    truncated: {
      type: Boolean,
      required: false,
      default: false,
    },
    determined: {
      type: Boolean,
      required: false,
      default: true,
    },
    disableVariableModificationSelection: {
      type: Boolean,
      default: false,
    },
    fontSize: {
      type: Number,
      default: 12,
    },
  },
  setup() {
    const streamlitData = useStreamlitDataStore()
    const variableModData = useModificationStore()
    return { streamlitData, variableModData }
  },
  data() {
    return {
      menuOpen: false,
      selectedModification: undefined as string | undefined,
      customSelected: false,
      customModMass: '0' as string,
    }
  },
  computed: {
    id(): string {
      return `${this.proteinTerminal}${this.index}`
    },
    theme(): Theme | undefined {
      return this.streamlitData.theme
    },
    proteinTerminalText(): string {
      return this.proteinTerminal.charAt(0)
    },
    hasVariableModification(): boolean {
      return this.variableModData.variableModifications[this.index] !== undefined
        && this.variableModData.variableModifications[this.index] !== 0
    },
    modificationsForSelect(): ModificationOption[] {
      return modificationOptions(this.proteinTerminal, this.variableModData.library)
    },
    hasLibrary(): boolean {
      return this.variableModData.library !== null
    },
    // This residue's entry in the store (0 or undefined: unmodified)
    storedModificationMass(): number | undefined {
      return this.variableModData.variableModifications[this.index]
    },
    proteinTerminalCellStyles(): Record<string, string> {
      return {
        '--protein-terminal-cell-color': this.theme?.textColor ?? '#fff',
        '--protein-terminal-cell-hover-color': '#fff',
        '--protein-terminal-cell-hover-bg-color': this.theme?.secondaryBackgroundColor ?? '#000',
        '--amino-acid-font-size': `${this.fontSize}px`,
      }
    },
    proteinTerminalCellClasses(): Record<string, boolean> {
      return {
        'protein-terminal': this.selectedModification === undefined && !this.hasVariableModification,
        'protein-terminal-modified': this.selectedModification !== undefined || this.hasVariableModification,
      }
    },
  },
  watch: {
    // Removed elsewhere (the list of applied modifications)
    storedModificationMass(mass: number | undefined) {
      if (!mass) {
        this.selectedModification = undefined
        this.customSelected = false
        this.customModMass = '0'
      }
    },
  },
  methods: {
    toggleMenuOpen(): void {
      if (this.disableVariableModificationSelection) {
        return
      }
      this.menuOpen = !this.menuOpen
    },
    optionMass(value: string | undefined): number {
      return this.modificationsForSelect.find((o) => o.value === value)?.mass ?? 0
    },
    updateSelectedModification(modification: string | null) {
      if (modification === 'Custom') {
        this.customSelected = true
        return
      }
      this.selectedModification =
        modification === null || modification === 'None' ? undefined : modification
      this.toggleMenuOpen()
      this.customSelected = false
      this.customModMass = '0'
      this.variableModData.updateVariableModifications(
        this.index,
        this.optionMass(this.selectedModification),
        this.selectedModification
      )
    },
    updateCustomModification() {
      this.selectedModification = undefined
      this.variableModData.updateVariableModifications(
        this.index,
        parseFloat(this.customModMass),
        'Custom'
      )
      this.toggleMenuOpen()
    },
  },
})
</script>

<style scoped lang="scss">

.undetermined {
  position: relative;
  top: -20%;
  font-size: 0.7em;
  font-weight: 1000;
  color: red;
  z-index: 1100;
}

.protein-terminal {
  &:hover {
    background-color: var(--protein-terminal-cell-hover-bg-color);
    color: var(--protein-terminal-cell-hover-color);
  }
}

.terminal-text {
  font-weight: 1000;
  font-size: var(--amino-acid-font-size, 12px);
  &.truncated {
    color: rgba(128, 128, 128, 0.4);
    outline: rgba(128, 128, 128, 0.4);
  }
}

.protein-terminal-modified {
  @extend .protein-terminal;
  background-color: #9c1e1e;
  color: var(--amino-acid-cell-color);

  &:hover {
    background-color: #ff1e1e;
  }
}
</style>

