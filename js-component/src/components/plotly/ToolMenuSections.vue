<template>
  <div class="tool-menu-sections">
    <template v-for="(section, index) in sections" :key="index">
      <div v-if="index" class="menu-separator"></div>
      <div class="menu-heading">{{ section.label }}</div>

      <template v-if="section.kind === 'choice'">
        <button
          v-for="option in section.options"
          :key="option.value"
          type="button"
          class="menu-item"
          role="menuitemradio"
          :aria-checked="option.value === section.value"
          @click="section.select(option.value)"
        >
          <span class="menu-label">{{ option.label }}</span>
          <svg v-if="option.value === section.value" class="menu-check" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
            <path :d="ICONS.check" />
          </svg>
        </button>
      </template>

      <template v-else-if="section.kind === 'toggles'">
        <button
          v-for="item in section.items"
          :key="item.value"
          type="button"
          class="menu-item"
          role="menuitemcheckbox"
          :aria-checked="item.active"
          :disabled="item.disabled"
          :title="item.disabled ? 'At least one stays shown' : undefined"
          @click="section.toggle(item.value)"
        >
          <span v-if="item.color" class="menu-swatch" :style="{ background: item.color }"></span>
          <span class="menu-label">{{ item.label }}</span>
          <svg v-if="item.active" class="menu-check" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
            <path :d="ICONS.check" />
          </svg>
        </button>
      </template>

      <label v-else-if="section.kind === 'range'" class="menu-range">
        <input
          type="range"
          :min="section.min"
          :max="section.max"
          :step="section.step"
          :value="section.value"
          :aria-label="section.label"
          @input="section.input(Number(($event.target as HTMLInputElement).value))"
        />
        <span class="menu-range-value">{{ section.format ? section.format(section.value) : section.value }}</span>
      </label>
    </template>
  </div>
</template>

<script lang="ts">
/** The choices of a toolbar button with a menu (see PlotTool.menu). */
import { defineComponent, type PropType } from 'vue'
import { ICONS, type ToolMenuSection } from '@/utils/plotTools'

export default defineComponent({
  name: 'ToolMenuSections',
  props: {
    sections: { type: Array as PropType<ToolMenuSection[]>, required: true },
  },
  setup() {
    return { ICONS }
  },
})
</script>

<style scoped>
.menu-heading {
  padding: 5px 9px 2px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--tb-muted);
}
.menu-separator {
  height: 1px;
  margin: 3px 6px;
  background: var(--tb-border);
}
.menu-item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  min-height: 26px;
  padding: 3px 9px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--tb-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.menu-item:hover:not(:disabled) {
  background: var(--tb-hover-bg);
}
.menu-item:disabled {
  cursor: default;
}
.menu-item:focus-visible {
  outline: 2px solid var(--tb-accent);
  outline-offset: 1px;
}
.menu-label {
  flex: 1;
}
.menu-check {
  flex: none;
  fill: var(--tb-accent);
}
.menu-swatch {
  flex: none;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.menu-range {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 9px 6px;
}
.menu-range input {
  flex: 1;
  accent-color: var(--tb-accent);
}
.menu-range-value {
  min-width: 42px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
