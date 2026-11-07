<template>
  <div v-if="labels.draft && position" class="peak-label-editor" :style="boxStyle">
    <input
      ref="input"
      v-model="text"
      type="text"
      class="peak-label-input"
      :maxlength="maxLength"
      placeholder="Label (Enter keeps, Esc closes)"
      aria-label="Peak label"
      @keydown.enter.prevent="commit"
      @keydown.esc.prevent="labels.cancel()"
      @keydown.stop
    />
  </div>
</template>

<script lang="ts">
/**
 * The text box for a peak label (see composables/usePeakLabels.ts), shown
 * just above the peak while a label is written or changed. Plain HTML over
 * the plot: it is not part of the image download. The parent must be
 * positioned (position: relative) and pass the peak's pixel position within
 * itself.
 */
import { defineComponent, type PropType } from 'vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { MAX_LABEL_LENGTH, type PeakLabelState } from '@/composables/usePeakLabels'

export default defineComponent({
  name: 'PeakLabelEditor',
  props: {
    labels: {
      type: Object as PropType<PeakLabelState>,
      required: true,
    },
    /** The peak's position in pixels within the parent, or null when unknown. */
    position: {
      type: Object as PropType<{ left: number; top: number } | null>,
      default: null,
    },
  },
  setup() {
    return { streamlitDataStore: useStreamlitDataStore() }
  },
  data() {
    return { text: '', maxLength: MAX_LABEL_LENGTH }
  },
  computed: {
    boxStyle(): Record<string, string> {
      const theme = this.streamlitDataStore.theme
      const left = Math.max(0, (this.position?.left ?? 0) - 90)
      const top = Math.max(0, (this.position?.top ?? 0) - 44)
      return {
        left: `${left}px`,
        top: `${top}px`,
        '--label-text': theme?.textColor || '#262730',
        '--label-background': theme?.backgroundColor || 'white',
        '--label-font': theme?.font || 'sans-serif',
      }
    },
  },
  watch: {
    // A new draft: start from its text and put the cursor in the box
    'labels.draft': {
      handler(draft: { text: string } | null) {
        if (!draft) return
        this.text = draft.text
        this.$nextTick(() => {
          const input = this.$refs.input as HTMLInputElement | undefined
          input?.focus()
          input?.select()
        })
      },
      immediate: true,
    },
  },
  methods: {
    commit(): void {
      this.labels.commit(this.text)
    },
  },
})
</script>

<style scoped>
.peak-label-editor {
  position: absolute;
  z-index: 11;
}

.peak-label-input {
  width: 180px;
  box-sizing: border-box;
  padding: 2px 6px;
  font-family: var(--label-font);
  font-size: 12px;
  color: var(--label-text);
  background: var(--label-background);
  border: 1px solid var(--label-text);
  border-radius: 3px;
  outline: none;
}
</style>
