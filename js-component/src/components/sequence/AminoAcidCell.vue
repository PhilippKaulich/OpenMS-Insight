<template>
  <div
    :id="id"
    class="d-flex justify-center align-center rounded-lg"
    :class="[aminoAcidCellClass, { highlighted: isHighlighted }, { 'fixed-mod': fixedModification }]"
    :style="cellStyles"
    @click="selectCell"
  >
    <!-- Fragment ion markers (N-terminal: a, b, c) -->
    <div v-if="showFragments && sequenceObject.aIon" class="frag-marker-container frag-marker-a">
      <svg viewBox="0 0 10 10">
        <path stroke="green" d="M7, 1 L9, 3 L9, 7 L9, 3 L7, 1 z" stroke-width="1.5" />
      </svg>
    </div>
    <div v-if="showFragments && sequenceObject.bIon" class="frag-marker-container frag-marker-b">
      <svg viewBox="0 0 10 10">
        <path stroke="blue" d="M10, 0 V5 M10, 0 H5 z" stroke-width="3" />
      </svg>
    </div>
    <div v-if="showFragments && sequenceObject.cIon" class="frag-marker-container frag-marker-c">
      <svg viewBox="0 0 10 10">
        <path stroke="red" d="M4, 1 L9, 3 L9, 7 L9, 3 L4, 1 z" stroke-width="1.5" />
      </svg>
    </div>

    <!-- Fragment ion markers (C-terminal: x, y, z) -->
    <div v-if="showFragments && sequenceObject.xIon" class="frag-marker-container frag-marker-x">
      <svg viewBox="0 0 10 10">
        <path stroke="green" d="M1, 3 L1, 7 L3, 9 L1, 7 L1, 3 z" stroke-width="1.5" />
      </svg>
    </div>
    <div v-if="showFragments && sequenceObject.yIon" class="frag-marker-container frag-marker-y">
      <svg viewBox="0 0 10 10">
        <path stroke="blue" d="M0, 10 V5 M0, 10 H5 z" stroke-width="3" />
      </svg>
    </div>
    <div v-if="showFragments && sequenceObject.zIon" class="frag-marker-container frag-marker-z">
      <svg viewBox="0 0 10 10">
        <path stroke="red" d="M1, 3 L1, 7 L6, 9 L1, 7 L1, 3 z" stroke-width="1.5" />
      </svg>
    </div>

    <!-- Modification marker with dotted pattern -->
    <div v-if="modification !== null" class="rounded-lg mod-marker mod-start"></div>
    <div v-if="modification !== null" class="rounded-lg mod-marker mod-end"></div>

    <!-- Modification mass badge -->
    <div v-if="modification !== null" class="rounded-lg mod-mass">
      {{ modificationDisplay }}
      <v-tooltip activator="parent" class="foreground">
        Modification Mass: {{ modificationDisplay }} Da
      </v-tooltip>
    </div>

    <!-- Modification mass with fragment ion border coloring -->
    <div v-if="showFragments && modification !== null && sequenceObject.aIon && !sequenceObject.bIon" class="rounded-lg mod-mass-a">{{ modificationDisplay }}</div>
    <div v-if="showFragments && modification !== null && sequenceObject.bIon" class="rounded-lg mod-mass-b">{{ modificationDisplay }}</div>
    <div v-if="showFragments && modification !== null && sequenceObject.cIon && !sequenceObject.bIon" class="rounded-lg mod-mass-c">{{ modificationDisplay }}</div>

    <!-- Extra fragment type indicator -->
    <div v-if="hasExtraFragTypes" class="frag-marker-extra-type">
      <svg viewBox="0 0 10 10">
        <circle cx="5" cy="5" r="0.5" class="extra-frag-circle" stroke-width="0.3" fill="gold" />
      </svg>
    </div>

    <!-- Amino acid letter -->
    <div class="aa-text">{{ aminoAcid }}</div>

    <!-- Tooltip -->
    <v-tooltip activator="parent">
      <div>Position: {{ index + 1 }}</div>
      <div v-if="prefix !== undefined">Prefix: {{ prefix }}</div>
      <div v-if="suffix !== undefined">Suffix: {{ suffix }}</div>
      <div v-if="hasExtraFragTypes">{{ sequenceObject.extraTypes.join(', ') }}</div>
    </v-tooltip>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { SequenceObject } from '@/types/sequence-data'
import type { Theme } from 'streamlit-component-lib'

export default defineComponent({
  name: 'AminoAcidCell',
  props: {
    sequenceObject: {
      type: Object as PropType<SequenceObject>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
    sequenceLength: {
      type: Number,
      required: true,
    },
    fixedModification: {
      type: Boolean,
      default: false,
    },
    showFragments: {
      type: Boolean,
      default: true,
    },
    fontSize: {
      type: Number,
      default: 12,
    },
    isHighlighted: {
      type: Boolean,
      default: false,
    },
    modification: {
      type: Number as PropType<number | null>,
      default: null,
    },
  },
  emits: ['selected'],
  setup() {
    const streamlitData = useStreamlitDataStore()
    return { streamlitData }
  },
  computed: {
    id(): string {
      return `aa-${this.aminoAcid}-${this.index}`
    },
    theme(): Theme | undefined {
      return this.streamlitData.theme
    },
    aminoAcid(): string {
      return this.sequenceObject.aminoAcid
    },
    prefix(): number | undefined {
      return this.index + 1
    },
    suffix(): number | undefined {
      return this.sequenceLength - this.index
    },
    hasExtraFragTypes(): boolean {
      return this.sequenceObject.extraTypes.length > 0
    },
    hasMatchingFragments(): boolean {
      return (
        this.sequenceObject.aIon ||
        this.sequenceObject.bIon ||
        this.sequenceObject.cIon ||
        this.sequenceObject.xIon ||
        this.sequenceObject.yIon ||
        this.sequenceObject.zIon
      )
    },
    aminoAcidCellClass(): Record<string, boolean> {
      return {
        'sequence-amino-acid': !this.fixedModification,
        'sequence-amino-acid-highlighted': this.fixedModification,
      }
    },
    cellStyles(): Record<string, string> {
      const isDark = this.theme?.base === 'dark'
      return {
        '--amino-acid-cell-color': this.theme?.textColor ?? '#000',
        '--amino-acid-cell-bg-color': this.theme?.secondaryBackgroundColor ?? '#f0f0f0',
        '--amino-acid-cell-hover-color': this.theme?.textColor ?? '#000',
        '--amino-acid-cell-hover-bg-color': this.theme?.backgroundColor ?? '#fff',
        '--amino-acid-font-size': `${this.fontSize}px`,
        '--mod-mass-bg-color': isDark ? '#e0e0e0' : '#fff',
        '--mod-mass-text-color': '#000',
        '--mod-mass-border-color': isDark ? '#666' : '#a79c91',
        '--mod-marker-dot-color': isDark ? 'rgba(150, 150, 220, 0.8)' : '#676a9c',
        '--mod-marker-bg-color': isDark ? 'rgba(180, 180, 220, 0.3)' : '#e5e5f7',
        '--extra-frag-stroke': isDark ? 'rgba(255, 255, 255, 0.5)' : 'black',
        position: 'relative',
      }
    },
    modificationDisplay(): string {
      if (this.modification === null) return ''
      const mod = this.modification
      if (mod >= 0) {
        return `+${mod.toFixed(2)}`
      }
      return mod.toFixed(2)
    },
  },
  methods: {
    selectCell(): void {
      if (this.hasMatchingFragments) {
        this.$emit('selected', this.index)
      }
    },
  },
})
</script>

<style scoped>
.foreground {
  position: relative;
  z-index: 1000;
}

.sequence-amino-acid-highlighted,
.sequence-amino-acid.highlighted {
  background-color: #f3a712;
  color: #000000;
  outline: 3px solid #29335c;
  font-weight: bold;
}

.sequence-amino-acid {
  background-color: var(--amino-acid-cell-bg-color);
  color: var(--amino-acid-cell-color);
  cursor: pointer;
  aspect-ratio: 1;
}

.sequence-amino-acid:hover {
  background-color: var(--amino-acid-cell-hover-bg-color);
  color: var(--amino-acid-cell-hover-color);
}

.sequence-amino-acid-highlighted {
  background-color: var(--amino-acid-cell-bg-color);
  color: #f3a712;
}

.sequence-amino-acid-highlighted:hover {
  background-color: var(--amino-acid-cell-hover-bg-color);
}

.fixed-mod {
  color: #f3a712;
}

/* Fragment marker base container */
.frag-marker-container {
  width: 100%;
  height: 100%;
  position: absolute;
  z-index: 1000;
}

.frag-marker-a {
  top: -28%;
  left: 15%;
}

.frag-marker-b {
  top: -8%;
  left: 13%;
}

.frag-marker-c {
  top: -28%;
  left: 15%;
}

.frag-marker-x {
  bottom: -32%;
  left: -10%;
}

.frag-marker-y {
  bottom: -8%;
  left: -10%;
}

.frag-marker-z {
  bottom: -32%;
  left: -10%;
}

.frag-marker-extra-type {
  width: 100%;
  height: 100%;
  position: absolute;
  top: -30%;
  z-index: 1000;
}

.aa-text {
  position: absolute;
  font-size: var(--amino-acid-font-size, 12px);
  font-weight: 500;
}

/* Modification marker with dotted pattern background */
.mod-marker {
  position: absolute;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: right;
  background-image: radial-gradient(var(--mod-marker-dot-color, #676a9c) 0.5px, transparent 0.5px),
    radial-gradient(#444cf7 0.5px, var(--mod-marker-bg-color, #e5e5f7) 0.5px);
  background-size: 15px 15px;
  background-position: 0 0, 10px 10px;
  background-repeat: repeat;
}

.mod-start {
  clip-path: inset(0 50% 0 0);
}

.mod-end {
  clip-path: inset(0 0 0 50%);
}

/* Modification mass badge */
.mod-mass {
  background-color: var(--mod-mass-bg-color, white);
  color: var(--mod-mass-text-color, inherit);
  display: inline-block;
  position: absolute;
  top: -15%;
  right: -25%;
  display: flex;
  align-items: center;
  justify-content: right;
  border: 0.1em solid var(--mod-mass-border-color, #a79c91);
  font-size: 0.7em;
  padding: 0em 0.2em;
  z-index: 1100;
}

/* Extra fragment circle stroke */
.extra-frag-circle {
  stroke: var(--extra-frag-stroke, black);
}

/* Modification mass with fragment ion colored borders */
.mod-mass-a {
  display: inline-block;
  position: absolute;
  top: -15%;
  right: -25%;
  display: flex;
  align-items: center;
  border-top: 0.2em solid green;
  border-right: 0.2em solid green;
  border-bottom: 0.2em solid green;
  border-radius: 0.5rem;
  padding: 0em 0.2em;
  z-index: 1200;
  font-size: 0.7em;
  color: rgba(0, 0, 0, 0);
}

.mod-mass-b {
  display: inline-block;
  position: absolute;
  top: -15%;
  right: -25%;
  display: flex;
  align-items: center;
  border-top: 0.2em solid blue;
  border-right: 0.2em solid blue;
  border-bottom: 0.2em solid blue;
  border-radius: 0.5rem;
  z-index: 1200;
  padding: 0em 0.2em;
  font-size: 0.7em;
  color: rgba(0, 0, 0, 0);
}

.mod-mass-c {
  display: inline-block;
  position: absolute;
  top: -15%;
  right: -25%;
  display: flex;
  align-items: center;
  border-top: 0.2em solid red;
  border-right: 0.2em solid red;
  border-bottom: 0.2em solid red;
  border-radius: 0.5rem;
  z-index: 1200;
  font-size: 0.7em;
  padding: 0em 0.2em;
  color: rgba(0, 0, 0, 0);
}
</style>
