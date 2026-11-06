<template>
  <div v-if="measure.mode && measure.hint" class="measure-hint" :style="cssCustomProperties">
    {{ measure.hint }}
  </div>
</template>

<script lang="ts">
/**
 * A small note over the plot's top-left corner while measure mode is on (the
 * Measure button sits in Plotly's mode bar, which is hidden until hovered).
 * Plain HTML over the plot: it takes no height and is not part of the SVG
 * download. The parent must be positioned (position: relative).
 */
import { defineComponent, type PropType } from 'vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { MeasureState } from '@/composables/useMeasure'

export default defineComponent({
  name: 'MeasureHint',
  props: {
    measure: {
      type: Object as PropType<MeasureState>,
      required: true,
    },
  },
  setup() {
    return { streamlitDataStore: useStreamlitDataStore() }
  },
  computed: {
    cssCustomProperties(): Record<string, string> {
      const theme = this.streamlitDataStore.theme
      return {
        '--measure-text': theme?.textColor || '#262730',
        '--measure-background': theme?.backgroundColor || 'white',
        '--measure-font': theme?.font || 'sans-serif',
      }
    },
  },
})
</script>

<style scoped>
.measure-hint {
  position: absolute;
  top: 4px;
  left: 8px;
  z-index: 10;
  pointer-events: none;
  padding: 1px 6px;
  border-radius: 3px;
  font-family: var(--measure-font);
  font-size: 12px;
  color: var(--measure-text);
  background: color-mix(in srgb, var(--measure-background) 85%, transparent);
  opacity: 0.85;
}
</style>
