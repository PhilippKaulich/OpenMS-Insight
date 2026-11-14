<template>
  <!-- Break line marking the residues a proteoform's terminus truncates:
       their protein positions and a flat wave over `cells` grid cells; the
       C-terminal one (end) runs wave first, positions last. In a single
       cell the positions stand above the wave -->
  <div
    :class="['truncated-residues', { 'truncated-residues-end': end, 'truncated-residues-narrow': cells < 2 }]"
    :aria-label="text"
  >
    <span class="truncated-label" aria-hidden="true">{{ range }}</span>
    <svg
      class="truncated-break" aria-hidden="true" preserveAspectRatio="none"
      :viewBox="`0 0 ${Math.max(cells, 1) * 20} 6`"
    >
      <path
        :d="path" fill="none" stroke="currentColor" stroke-width="1.2"
        stroke-linecap="round" vector-effect="non-scaling-stroke"
      />
    </svg>
    <v-tooltip activator="parent" location="bottom" max-width="480">
      <div class="truncated-range">{{ text }}</div>
      <div v-if="mass !== null" class="truncated-mass" :data-testid="`${testid}-mass`">{{ mass }}</div>
      <span class="truncated-sequence" :data-testid="`${testid}-sequence`">{{ residues }}</span>
    </v-tooltip>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'

export default defineComponent({
  name: 'TruncationBreak',
  props: {
    /** Protein positions, e.g. "1–21" */
    range: { type: String, required: true },
    /** Hover text and accessible label, e.g. "21 residues truncated (1–21)" */
    text: { type: String, required: true },
    /** Hover line on the residue mass; null leaves it out */
    mass: { type: String as PropType<string | null>, default: null },
    /** The truncated residues */
    residues: { type: String, required: true },
    /** Grid cells the line spans: sets the zig-zag's tooth count */
    cells: { type: Number, required: true },
    /** C-terminal: zig-zag first, positions on the right */
    end: { type: Boolean, default: false },
    testid: { type: String, required: true },
  },
  computed: {
    /** A smooth wave, one period per cell, so it keeps its pitch at any
     *  width and never reads as a letter */
    path(): string {
      const n = Math.max(this.cells, 1) * 2
      let d = 'M0,3'
      for (let i = 0; i < n; i++) d += ` q5,${i % 2 ? 6 : -6} 10,0`
      return d
    },
  },
})
</script>

<style scoped>
.truncated-residues {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  line-height: 1;
  opacity: var(--v-medium-emphasis-opacity);
  cursor: help;
  aspect-ratio: auto;
  align-self: center;
  min-width: 0;
  overflow: hidden;
  padding: 0 4px;
}

.truncated-residues-end {
  flex-direction: row-reverse;
}

.truncated-label {
  white-space: nowrap;
}

.truncated-break {
  flex: 1;
  min-width: 0;
  height: 6px;
}

/* One cell: positions above the wave */
.truncated-residues-narrow {
  flex-direction: column;
  gap: 2px;
}

.truncated-residues-narrow .truncated-break {
  flex: none;
  width: 100%;
}

.truncated-range {
  font-weight: 600;
}

.truncated-mass {
  font-variant-numeric: tabular-nums;
}

.truncated-sequence {
  font-family: monospace;
  overflow-wrap: anywhere;
}
</style>
