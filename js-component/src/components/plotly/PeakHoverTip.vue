<template>
  <div v-if="tip" class="peak-hover" aria-hidden="true">
    <div class="peak-hover-dot" :style="dotStyle"></div>
    <div class="peak-hover-box" :style="boxStyle">
      <div v-for="(line, i) in tip.lines" :key="i">{{ line }}</div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import type { PeakHoverTip } from '@/composables/usePeakHover'

/** The hover read-out of a stick spectrum: a dot on the peak top and its values. */
export default defineComponent({
  name: 'PeakHoverTip',
  props: {
    tip: { type: Object as PropType<PeakHoverTip | null>, default: null },
    color: { type: String, default: '#262730' },
    background: { type: String, default: 'white' },
  },
  computed: {
    dotStyle(): Record<string, string> {
      if (!this.tip) return {}
      return { left: `${this.tip.left}px`, top: `${this.tip.top}px`, borderColor: this.color }
    },
    boxStyle(): Record<string, string> {
      if (!this.tip) return {}
      return {
        left: `${this.tip.left + (this.tip.flip ? -8 : 8)}px`,
        transform: this.tip.flip ? 'translate(-100%, -100%)' : 'translateY(-100%)',
        top: `${this.tip.top}px`,
        color: this.color,
        background: this.background,
        borderColor: this.color,
      }
    },
  },
})
</script>

<style scoped>
.peak-hover {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 2;
}

.peak-hover-dot {
  position: absolute;
  width: 8px;
  height: 8px;
  margin: -5px 0 0 -5px;
  border: 1px solid;
  border-radius: 50%;
}

.peak-hover-box {
  position: absolute;
  padding: 2px 6px;
  border: 1px solid;
  border-radius: 3px;
  font-size: 12px;
  line-height: 1.35;
  white-space: nowrap;
  opacity: 0.92;
}
</style>
