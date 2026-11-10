<template>
  <div ref="root" class="colorbar-legend" :style="cssCustomProperties">
    <button
      v-for="item in items"
      :key="item.id"
      type="button"
      class="colorbar-legend-item"
      :class="{ open: openId === item.id }"
      :title="item.editable === false ? item.label : `${item.label}: click to change the colors`"
      :disabled="item.editable === false"
      :aria-expanded="openId === item.id"
      @click="toggle(item)"
    >
      <span class="colorbar-legend-label">{{ item.label }}</span>
      <span class="colorbar-legend-tick">{{ item.low }}</span>
      <span class="colorbar-legend-bar" :style="{ background: gradient(item.stops) }"></span>
      <span class="colorbar-legend-tick">{{ item.high }}</span>
    </button>

    <div v-if="openItem && draft" ref="editor" class="colorbar-editor" role="dialog" :aria-label="`Colors of ${openItem.label}`">
      <div class="editor-heading">Colors</div>
      <div class="editor-segments" role="radiogroup" aria-label="Number of colors">
        <button
          v-for="n in [1, 2, 3]"
          :key="n"
          type="button"
          role="radio"
          :aria-checked="draft.mode === n"
          :class="{ on: draft.mode === n }"
          @click="setMode(n as 1 | 2 | 3)"
        >
          {{ n }} {{ n === 1 ? 'color' : 'colors' }}
        </button>
      </div>
      <div class="editor-stops">
        <label v-for="(name, i) in stopNames" :key="name" class="editor-stop">
          <input type="color" :value="draft.colors[i]" :aria-label="`${name} color`" @input="setColor(i, $event)" />
          <span>{{ name }}</span>
        </label>
        <span class="editor-preview" :style="{ background: gradient(draftStops) }"></span>
      </div>
      <label v-if="draft.mode === 3" class="editor-mid">
        <span>Middle at</span>
        <input type="range" min="0.1" max="0.9" step="0.05" :value="draft.mid" @input="setMid($event)" />
        <span class="editor-mid-value">{{ Math.round(draft.mid * 100) }}%</span>
      </label>
      <div class="editor-heading">Presets</div>
      <div class="editor-presets">
        <button
          v-for="(preset, i) in presets"
          :key="i"
          type="button"
          class="editor-preset"
          :aria-label="`Preset ${preset.join(' to ')}`"
          :style="{ background: gradient(presetStops(preset)) }"
          @click="usePreset(preset)"
        ></button>
      </div>
      <div class="editor-actions">
        <button type="button" :disabled="draft.mode === 1" @click="reverse">Reverse</button>
        <button type="button" @click="reset">Reset</button>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
/**
 * Small colorbars below a plot, one per colorscale it uses. A click on one
 * opens an editor: one, two or three colors, the position of the middle color,
 * presets, reverse and reset. Every change is emitted at once (`change` with
 * the item's id and the new spec, or null for the plot's own scale).
 */
import { defineComponent, type PropType } from 'vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import {
  PRESETS,
  cssGradient,
  specFromStops,
  specToStops,
  withMode,
  type ColorStops,
  type ColorbarSpec,
} from '@/utils/colorscale'

export interface ColorbarLegendItem {
  id: string
  label: string
  /** The scale as drawn now. */
  stops: ColorStops
  /** The spec the user chose, if any. */
  spec?: ColorbarSpec | null
  low: string
  high: string
  editable?: boolean
}

export default defineComponent({
  name: 'ColorbarLegend',
  props: {
    items: { type: Array as PropType<ColorbarLegendItem[]>, required: true },
  },
  emits: ['change'],
  setup() {
    return { streamlitDataStore: useStreamlitDataStore() }
  },
  data() {
    return {
      openId: null as string | null,
      draft: null as ColorbarSpec | null,
    }
  },
  computed: {
    openItem(): ColorbarLegendItem | null {
      return this.items.find((item) => item.id === this.openId) ?? null
    },
    background(): string {
      return this.streamlitDataStore.theme?.backgroundColor || '#ffffff'
    },
    neutral(): string {
      return this.streamlitDataStore.theme?.base === 'dark' ? '#383835' : '#f0efec'
    },
    draftStops(): ColorStops {
      return this.draft ? specToStops(this.draft, this.background) : []
    },
    stopNames(): string[] {
      const mode = this.draft?.mode ?? 2
      return mode === 1 ? ['Color'] : mode === 2 ? ['Low', 'High'] : ['Low', 'Middle', 'High']
    },
    presets(): string[][] {
      return PRESETS[this.draft?.mode ?? 2]
    },
    cssCustomProperties(): Record<string, string> {
      const theme = this.streamlitDataStore.theme
      return {
        '--cb-text': theme?.textColor || '#262730',
        '--cb-background': theme?.backgroundColor || '#ffffff',
        '--cb-accent': theme?.primaryColor || '#1436b8',
        '--cb-font': theme?.font || 'sans-serif',
      }
    },
  },
  watch: {
    items() {
      if (this.openId && !this.openItem) this.close()
    },
  },
  mounted() {
    document.addEventListener('pointerdown', this.onPointerDown, true)
    document.addEventListener('keydown', this.onKeyDown)
  },
  beforeUnmount() {
    document.removeEventListener('pointerdown', this.onPointerDown, true)
    document.removeEventListener('keydown', this.onKeyDown)
  },
  methods: {
    gradient(stops: ColorStops): string {
      return cssGradient(stops)
    },
    presetStops(colors: string[]): ColorStops {
      const mode = (this.draft?.mode ?? 2) as 1 | 2 | 3
      return specToStops({ mode, colors: [...colors, ...colors], mid: 0.5 }, this.background)
    },
    toggle(item: ColorbarLegendItem): void {
      if (this.openId === item.id) return this.close()
      this.openId = item.id
      const spec = item.spec ?? specFromStops(item.stops)
      this.draft = { ...spec, colors: [...spec.colors] }
    },
    close(): void {
      this.openId = null
      this.draft = null
    },
    emitDraft(): void {
      if (this.draft && this.openId) this.$emit('change', this.openId, { ...this.draft, colors: [...this.draft.colors] })
    },
    setMode(mode: 1 | 2 | 3): void {
      if (!this.draft) return
      this.draft = withMode(this.draft, mode, this.neutral)
      this.emitDraft()
    },
    setColor(index: number, event: Event): void {
      if (!this.draft) return
      const colors = [...this.draft.colors]
      colors[index] = (event.target as HTMLInputElement).value
      this.draft = { ...this.draft, colors }
      this.emitDraft()
    },
    setMid(event: Event): void {
      if (!this.draft) return
      this.draft = { ...this.draft, mid: Number((event.target as HTMLInputElement).value) }
      this.emitDraft()
    },
    usePreset(colors: string[]): void {
      if (!this.draft) return
      const next = [...this.draft.colors]
      colors.forEach((c, i) => (next[i] = c))
      this.draft = { ...this.draft, colors: next, mid: 0.5 }
      this.emitDraft()
    },
    reverse(): void {
      if (!this.draft || this.draft.mode === 1) return
      const [a, b, c] = this.draft.colors
      this.draft =
        this.draft.mode === 2
          ? { ...this.draft, colors: [b, a, c] }
          : { ...this.draft, colors: [c, b, a], mid: 1 - this.draft.mid }
      this.emitDraft()
    },
    reset(): void {
      const id = this.openId
      if (!id) return
      this.$emit('change', id, null)
      this.$nextTick(() => {
        const item = this.openItem
        if (item) this.draft = specFromStops(item.stops)
      })
    },
    onPointerDown(event: Event): void {
      if (!this.openId) return
      const root = this.$refs.root as HTMLElement | undefined
      if (root?.contains(event.target as Node)) return
      this.close()
    },
    onKeyDown(event: KeyboardEvent): void {
      if (event.key === 'Escape' && this.openId) this.close()
    },
  },
})
</script>

<style scoped>
.colorbar-legend {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  min-height: 26px;
  padding: 2px 4px 4px;
  font-family: var(--cb-font);
  font-size: 11px;
  color: var(--cb-text);
  --cb-muted: color-mix(in srgb, var(--cb-text) 62%, transparent);
  --cb-border: color-mix(in srgb, var(--cb-text) 16%, transparent);
  --cb-hover: color-mix(in srgb, var(--cb-text) 7%, var(--cb-background));
}
.colorbar-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: var(--cb-muted);
  font: inherit;
  cursor: pointer;
}
.colorbar-legend-item:hover:not(:disabled),
.colorbar-legend-item.open {
  border-color: var(--cb-border);
  background: var(--cb-hover);
  color: var(--cb-text);
}
.colorbar-legend-item:disabled {
  cursor: default;
}
.colorbar-legend-item:focus-visible {
  outline: 2px solid var(--cb-accent);
  outline-offset: 1px;
}
.colorbar-legend-label {
  font-weight: 600;
}
.colorbar-legend-tick {
  font-variant-numeric: tabular-nums;
}
.colorbar-legend-bar {
  width: 96px;
  height: 8px;
  border-radius: 2px;
  box-shadow: inset 0 0 0 1px var(--cb-border);
}
.colorbar-editor {
  position: absolute;
  right: 4px;
  bottom: calc(100% + 4px);
  z-index: 30;
  width: 264px;
  padding: 6px 8px 8px;
  border: 1px solid var(--cb-border);
  border-radius: 10px;
  background: var(--cb-background);
  box-shadow: 0 6px 20px color-mix(in srgb, var(--cb-text) 18%, transparent);
  font-size: 12px;
}
.editor-heading {
  padding: 4px 2px 3px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--cb-muted);
}
.editor-segments {
  display: inline-flex;
  border: 1px solid var(--cb-border);
  border-radius: 7px;
  overflow: hidden;
}
.editor-segments button {
  padding: 3px 10px;
  border: none;
  background: transparent;
  color: var(--cb-muted);
  font: inherit;
  cursor: pointer;
}
.editor-segments button.on {
  background: color-mix(in srgb, var(--cb-accent) 13%, var(--cb-background));
  color: var(--cb-accent);
  font-weight: 600;
}
.editor-stops {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  margin-top: 8px;
}
.editor-stop {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  font-size: 10.5px;
  color: var(--cb-muted);
}
.editor-stop input {
  width: 30px;
  height: 24px;
  padding: 0;
  border: 1px solid var(--cb-border);
  border-radius: 5px;
  background: none;
  cursor: pointer;
}
.editor-preview {
  flex: 1;
  height: 14px;
  margin-bottom: 15px;
  border-radius: 3px;
  box-shadow: inset 0 0 0 1px var(--cb-border);
}
.editor-mid {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  color: var(--cb-muted);
}
.editor-mid input {
  flex: 1;
  accent-color: var(--cb-accent);
}
.editor-mid-value {
  min-width: 30px;
  text-align: right;
  color: var(--cb-text);
}
.editor-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.editor-preset {
  width: 42px;
  height: 12px;
  padding: 0;
  border: 1px solid var(--cb-border);
  border-radius: 3px;
  cursor: pointer;
}
.editor-actions {
  display: flex;
  gap: 6px;
  margin-top: 10px;
}
.editor-actions button {
  padding: 3px 10px;
  border: 1px solid var(--cb-border);
  border-radius: 999px;
  background: transparent;
  color: var(--cb-text);
  font: inherit;
  cursor: pointer;
}
.editor-actions button:disabled {
  opacity: 0.45;
  cursor: default;
}
</style>
