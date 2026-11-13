<template>
  <div ref="root" class="plot-toolbar" :style="cssCustomProperties">
    <!-- Every group in a row; also kept (hidden) while collapsed, to measure whether it fits again -->
    <div ref="full" class="toolbar-row" :class="{ measuring: collapsed }" :aria-hidden="collapsed">
      <div v-for="group in groups" :key="group.name" class="toolbar-group" role="group" :aria-label="group.label">
        <button
          v-for="tool in group.tools"
          :key="tool.id"
          :ref="tool.menu ? `menuButton-${tool.id}` : undefined"
          type="button"
          class="toolbar-button"
          :class="{ active: tool.active || openTool === tool.id, labelled: !!tool.short }"
          :title="titleOf(tool)"
          :aria-pressed="tool.menu || tool.active === undefined ? undefined : tool.active"
          :aria-haspopup="tool.menu ? 'menu' : undefined"
          :aria-expanded="tool.menu ? openTool === tool.id : undefined"
          :data-tool-menu="tool.menu ? tool.id : undefined"
          :tabindex="collapsed ? -1 : 0"
          @click="press(tool)"
        >
          <ToolIconSvg :icon="tool.icon" />
          <span v-if="tool.short" class="toolbar-label">{{ tool.short }}</span>
          <ToolIconSvg v-if="tool.menu" class="toolbar-caret" :icon="CARET" :size="12" />
          <span v-if="tool.count" class="toolbar-count">{{ tool.count }}</span>
          <span
            v-if="tool.clear && tool.count"
            class="toolbar-clear"
            role="button"
            :title="tool.clear.label"
            :aria-label="tool.clear.label"
            @click.stop="tool.clear.run()"
          >
            <ToolIconSvg :icon="ICONS.close" :size="12" />
          </span>
        </button>
      </div>
    </div>

    <!-- The choices of a tool with a menu, below the toolbar -->
    <div
      v-if="openMenuTool && !collapsed"
      ref="toolMenu"
      class="toolbar-menu"
      role="menu"
      :aria-label="openMenuTool.label"
      :style="{ maxHeight: `${menuMaxHeight}px` }"
    >
      <ToolMenuSections :sections="openMenuTool.menu || []" />
    </div>

    <!-- Narrow panel: the tools that are on, Reset, and a menu with everything -->
    <div v-if="collapsed" class="toolbar-row">
      <div v-if="pinned.length" class="toolbar-group">
        <button
          v-for="tool in pinned"
          :key="tool.id"
          type="button"
          class="toolbar-button"
          :class="{ active: tool.active, labelled: !!tool.short && tool.active }"
          :title="titleOf(tool)"
          @click="tool.run()"
        >
          <ToolIconSvg :icon="tool.icon" />
          <span v-if="tool.short && tool.active" class="toolbar-label">{{ tool.short }}</span>
          <span v-if="tool.count" class="toolbar-count">{{ tool.count }}</span>
          <span
            v-if="tool.clear && tool.count"
            class="toolbar-clear"
            role="button"
            :title="tool.clear.label"
            :aria-label="tool.clear.label"
            @click.stop="tool.clear.run()"
          >
            <ToolIconSvg :icon="ICONS.close" :size="12" />
          </span>
        </button>
      </div>
      <div class="toolbar-group">
        <button
          ref="moreButton"
          type="button"
          class="toolbar-button"
          :class="{ active: menuOpen }"
          title="All tools"
          aria-haspopup="menu"
          :aria-expanded="menuOpen"
          @click="menuOpen = !menuOpen"
        >
          <ToolIconSvg :icon="ICONS.more" />
        </button>
      </div>
      <div v-if="menuOpen" ref="menu" class="toolbar-menu" role="menu" :style="{ maxHeight: `${menuMaxHeight}px` }">
        <template v-for="(group, index) in groups" :key="group.name">
          <div v-if="index" class="menu-separator"></div>
          <div class="menu-heading">{{ group.label }}</div>
          <template v-for="tool in group.tools" :key="tool.id">
            <ToolMenuSections v-if="tool.menu" class="menu-nested" :sections="tool.menu" />
            <button v-else type="button" class="menu-item" role="menuitem" :title="titleOf(tool)" @click="choose(tool.run)">
              <ToolIconSvg :icon="tool.icon" />
              <span class="menu-label">{{ tool.label }}</span>
              <span v-if="tool.count" class="toolbar-count">{{ tool.count }}</span>
              <ToolIconSvg v-if="tool.active" class="menu-check" :icon="ICONS.check" />
            </button>
            <button
              v-if="tool.clear && tool.count"
              type="button"
              class="menu-item"
              role="menuitem"
              @click="choose(tool.clear.run)"
            >
              <ToolIconSvg :icon="ICONS.close" />
              <span class="menu-label">{{ tool.clear.label }}</span>
            </button>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
/**
 * The tools of a plot as labelled groups above it (view, annotate, show,
 * download). When the groups do not fit the panel's width, the toolbar keeps
 * the tools that are on (with their counts and clear buttons) and Reset, and
 * offers every tool in a menu behind ⋯.
 *
 * `tools` are the component's own tools (see utils/plotTools.ts). A
 * component given a `stepper` (core/stepper.py) gets its ‹ value › buttons
 * first in the View group, on a narrow toolbar too. Plotly's
 * navigation buttons (zoom, pan, select, reset) are read from the plot's mode
 * bar, which stays in the page but hidden, so they work exactly as before.
 */
import { defineComponent, h, type PropType } from 'vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import { stepperTools, type StepperArgs } from '@/utils/stepper'
import ToolMenuSections from './ToolMenuSections.vue'
import {
  GROUP_LABELS,
  GROUP_ORDER,
  ICONS,
  TOOLBAR_HEIGHT,
  plotlyTools,
  toolTitle,
  type PlotTool,
  type PlotlyTool,
  type ToolGroup,
  type ToolIcon,
} from '@/utils/plotTools'

const ToolIconSvg = defineComponent({
  name: 'ToolIconSvg',
  props: {
    icon: { type: [String, Object] as PropType<ToolIcon>, required: true },
    size: { type: Number, default: 16 },
  },
  setup(props) {
    return () => {
      const icon = props.icon
      const common = { width: props.size, height: props.size, 'aria-hidden': 'true', class: 'tool-icon' }
      if (typeof icon === 'string') {
        return h('svg', { ...common, viewBox: '0 0 24 24' }, [h('path', { d: icon })])
      }
      return h('svg', { ...common, viewBox: icon.viewBox, innerHTML: icon.markup })
    }
  },
})

/** Small chevron after the name of a tool that opens a menu. */
const CARET = 'M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z'

interface Group {
  name: ToolGroup
  label: string
  tools: PlotTool[]
}

export default defineComponent({
  name: 'PlotToolbar',
  components: { ToolIconSvg, ToolMenuSections },
  props: {
    /** Id of the element Plotly draws the plot in. */
    plotId: {
      type: String,
      required: true,
    },
    /** The component's own tools, in the order they appear within their group. */
    tools: {
      type: Array as PropType<PlotTool[]>,
      default: () => [],
    },
    /** The component's `stepper` argument: previous / next buttons for one filter. */
    stepper: {
      type: Object as PropType<StepperArgs | undefined>,
      default: undefined,
    },
  },
  setup() {
    return { streamlitDataStore: useStreamlitDataStore(), selectionStore: useSelectionStore(), ICONS, CARET }
  },
  data() {
    return {
      plotlyButtons: [] as PlotlyTool[],
      collapsed: false,
      menuOpen: false,
      /** Id of the tool whose menu is open below the toolbar. */
      openTool: null as string | null,
      menuMaxHeight: 320,
      observer: null as MutationObserver | null,
      resizeObserver: null as ResizeObserver | null,
      observedElement: null as HTMLElement | null,
      frame: 0,
    }
  },
  computed: {
    stepperTools(): PlotTool[] {
      const stepper = this.stepper
      if (!stepper) return []
      return stepperTools(stepper, this.selectionStore.$state[stepper.identifier], (identifier, value) =>
        this.selectionStore.updateSelection(identifier, value),
      )
    },
    /** The component's tools with the stepper's buttons first. */
    allTools(): PlotTool[] {
      return [...this.stepperTools, ...this.tools]
    },
    groups(): Group[] {
      const all: PlotTool[] = [...this.plotlyButtons, ...this.allTools]
      return GROUP_ORDER.map((name) => ({
        name,
        label: GROUP_LABELS[name],
        tools: all.filter((tool) => tool.group === name),
      })).filter((group) => group.tools.length > 0)
    },
    /** The tool whose menu is open, as it is now (its choices follow the plot). */
    openMenuTool(): PlotTool | null {
      return this.allTools.find((tool) => tool.id === this.openTool && tool.menu) ?? null
    },
    /** What a narrow toolbar keeps: tools that are on or hold something, and Reset. */
    pinned(): PlotTool[] {
      const keep = this.plotlyButtons.filter((tool) => tool.keep)
      const on = this.tools.filter((tool) => tool.active || (tool.count ?? 0) > 0)
      return [...this.stepperTools, ...on, ...keep]
    },
    cssCustomProperties(): Record<string, string> {
      const theme = this.streamlitDataStore.theme
      return {
        '--tb-text': theme?.textColor || '#262730',
        '--tb-background': theme?.backgroundColor || '#ffffff',
        '--tb-accent': theme?.primaryColor || '#1436b8',
        '--tb-font': theme?.font || 'sans-serif',
        '--tb-height': `${TOOLBAR_HEIGHT}px`,
      }
    },
  },
  watch: {
    plotId() {
      this.observePlot()
    },
    groups() {
      this.$nextTick(() => this.fit())
    },
  },
  mounted() {
    this.observePlot()
    this.resizeObserver = new ResizeObserver(() => this.fit())
    this.resizeObserver.observe(this.$refs.root as HTMLElement)
    document.addEventListener('pointerdown', this.onPointerDown, true)
    document.addEventListener('keydown', this.onKeyDown)
  },
  beforeUnmount() {
    this.observer?.disconnect()
    this.resizeObserver?.disconnect()
    cancelAnimationFrame(this.frame)
    document.removeEventListener('pointerdown', this.onPointerDown, true)
    document.removeEventListener('keydown', this.onKeyDown)
  },
  methods: {
    titleOf(tool: PlotTool): string {
      return toolTitle(tool)
    },
    /** Follow the plot's mode bar: Plotly adds it on each draw and marks the drag mode. */
    observePlot(): void {
      this.observer?.disconnect()
      this.observer = new MutationObserver(() => this.scheduleRead())
      // The plot element may be created after the toolbar; watch the parent too
      const parent = (this.$refs.root as HTMLElement | undefined)?.parentElement
      if (parent) {
        this.observer.observe(parent, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] })
      }
      this.scheduleRead()
    },
    scheduleRead(): void {
      if (this.frame) return
      this.frame = requestAnimationFrame(() => {
        this.frame = 0
        this.readPlotlyButtons()
      })
    },
    readPlotlyButtons(): void {
      const next = plotlyTools(document.getElementById(this.plotId))
      const same =
        next.length === this.plotlyButtons.length &&
        next.every((tool, i) => tool.id === this.plotlyButtons[i].id && tool.active === this.plotlyButtons[i].active)
      if (!same) this.plotlyButtons = next
    },
    /** Collapse when the groups need more width than the panel has. */
    fit(): void {
      const root = this.$refs.root as HTMLElement | undefined
      const full = this.$refs.full as HTMLElement | undefined
      if (!root || !full) return
      const needed = full.scrollWidth
      const collapsed = needed > root.clientWidth + 1
      if (collapsed !== this.collapsed) {
        this.collapsed = collapsed
        if (!collapsed) this.menuOpen = false
      }
      // The menu may cover the plot, but not run past the frame's bottom
      const frameHeight = document.documentElement.clientHeight || window.innerHeight
      const top = root.getBoundingClientRect().bottom
      this.menuMaxHeight = Math.max(160, frameHeight - top - 8)
    },
    choose(run: () => void): void {
      this.menuOpen = false
      run()
    },
    /** A tool with a menu opens or closes it; any other tool runs. */
    press(tool: PlotTool): void {
      if (!tool.menu) {
        this.openTool = null
        tool.run()
        return
      }
      this.openTool = this.openTool === tool.id ? null : tool.id
      if (this.openTool) this.$nextTick(() => this.fit())
    },
    menuButton(id: string): HTMLElement | undefined {
      const ref = this.$refs[`menuButton-${id}`] as HTMLElement | HTMLElement[] | undefined
      return Array.isArray(ref) ? ref[0] : ref
    },
    onPointerDown(event: Event): void {
      const target = event.target as Node
      if (this.openTool) {
        const panel = this.$refs.toolMenu as HTMLElement | undefined
        const button = this.menuButton(this.openTool)
        if (!panel?.contains(target) && !button?.contains(target)) this.openTool = null
      }
      if (!this.menuOpen) return
      const menu = this.$refs.menu as HTMLElement | undefined
      const more = this.$refs.moreButton as HTMLElement | undefined
      if (menu?.contains(target) || more?.contains(target)) return
      this.menuOpen = false
    },
    onKeyDown(event: KeyboardEvent): void {
      if (event.key !== 'Escape') return
      if (this.openTool) {
        const button = this.menuButton(this.openTool)
        this.openTool = null
        button?.focus()
      }
      if (this.menuOpen) {
        this.menuOpen = false
        ;(this.$refs.moreButton as HTMLElement | undefined)?.focus()
      }
    },
  },
})
</script>

<style scoped>
.plot-toolbar {
  position: relative;
  height: var(--tb-height);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  font-family: var(--tb-font);
  font-size: 12px;
  color: var(--tb-text);
  --tb-muted: color-mix(in srgb, var(--tb-text) 62%, transparent);
  --tb-border: color-mix(in srgb, var(--tb-text) 16%, transparent);
  --tb-active-bg: color-mix(in srgb, var(--tb-accent) 13%, var(--tb-background));
  --tb-hover-bg: color-mix(in srgb, var(--tb-text) 7%, var(--tb-background));
}
.toolbar-row {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.toolbar-row.measuring {
  position: absolute;
  right: 0;
  visibility: hidden;
  pointer-events: none;
}
.toolbar-group {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  padding: 2px;
  border: 1px solid var(--tb-border);
  border-radius: 999px;
  background: var(--tb-background);
}
.toolbar-button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  min-width: 26px;
  padding: 0 5px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--tb-muted);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.toolbar-button.labelled {
  padding: 0 9px 0 7px;
}
.toolbar-button:hover {
  background: var(--tb-hover-bg);
  color: var(--tb-text);
}
.toolbar-button:focus-visible,
.menu-item:focus-visible {
  outline: 2px solid var(--tb-accent);
  outline-offset: 1px;
}
.toolbar-button.active {
  background: var(--tb-active-bg);
  color: var(--tb-accent);
  box-shadow: inset 0 0 0 1px var(--tb-accent);
}
.tool-icon {
  flex: none;
  fill: currentColor;
}
.tool-icon :deep(path) {
  fill: currentColor;
}
.toolbar-count {
  min-width: 15px;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--tb-accent);
  color: var(--tb-background);
  font-size: 10px;
  line-height: 15px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.toolbar-clear {
  display: inline-flex;
  margin: 0 -4px 0 -1px;
  padding: 2px;
  border-radius: 50%;
  opacity: 0.75;
}
.toolbar-clear:hover {
  opacity: 1;
  background: var(--tb-hover-bg);
}
.toolbar-menu {
  position: absolute;
  top: calc(100% + 2px);
  right: 0;
  z-index: 30;
  min-width: 220px;
  padding: 4px;
  overflow-y: auto;
  border: 1px solid var(--tb-border);
  border-radius: 10px;
  background: var(--tb-background);
  box-shadow: 0 6px 20px color-mix(in srgb, var(--tb-text) 18%, transparent);
}
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
  padding: 3px 9px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--tb-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.menu-item .tool-icon {
  color: var(--tb-muted);
}
.menu-item:hover {
  background: var(--tb-hover-bg);
}
.menu-label {
  flex: 1;
}
.menu-item .menu-check {
  color: var(--tb-accent);
}
.toolbar-caret {
  margin-left: -3px;
  opacity: 0.7;
}
.menu-nested {
  margin: 0 0 2px;
}
</style>

<style>
/* Plotly's own mode bar stays in the page for the toolbar to click, but out of sight */
.plot-toolbar ~ * .modebar-container,
.plot-toolbar ~ .modebar-container {
  display: none !important;
}
</style>
