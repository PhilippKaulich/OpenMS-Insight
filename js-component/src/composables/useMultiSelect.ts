/**
 * Selecting several entries at once (`multi_select` on the Python side).
 *
 * Each identifier of `multiSelect` holds the sorted distinct values of its
 * column over the selected entries, or null when nothing is selected. Every
 * component with the same identifier reads and writes the same set.
 */

import { computed, type ComputedRef } from 'vue'
import type Plotly from 'plotly.js-dist-min'
import { ICONS, type PlotTool } from '@/utils/plotTools'
import { useSelectionStore } from '@/stores/selection'

export type MultiSelectMode = 'replace' | 'add' | 'remove'

function sortValues(values: unknown[]): unknown[] {
  const distinct = Array.from(new Set(values.filter((v) => v !== null && v !== undefined)))
  return distinct.sort((a, b) => {
    if (typeof a === 'number' && typeof b === 'number') return a - b
    const sa = String(a)
    const sb = String(b)
    return sa < sb ? -1 : sa > sb ? 1 : 0
  })
}

/** The new set: `picked` replacing, added to or removed from `current`. */
export function combineSelection(
  current: unknown,
  picked: unknown[],
  mode: MultiSelectMode,
): unknown[] | null {
  const existing = Array.isArray(current) ? current : []
  let values: unknown[]
  if (mode === 'add') values = [...existing, ...picked]
  else if (mode === 'remove') {
    const removed = new Set(picked)
    values = existing.filter((v) => !removed.has(v))
  } else values = picked
  const sorted = sortValues(values)
  return sorted.length > 0 ? sorted : null
}

export function useMultiSelect(multiSelect: ComputedRef<Record<string, string> | undefined>) {
  const selectionStore = useSelectionStore()

  const enabled = computed(() => Object.keys(multiSelect.value || {}).length > 0)

  /** Selected values per identifier, as Sets (empty when none). */
  const selectedSets = computed<Record<string, Set<unknown>>>(() => {
    const sets: Record<string, Set<unknown>> = {}
    for (const identifier of Object.keys(multiSelect.value || {})) {
      const value = selectionStore.$state[identifier]
      sets[identifier] = new Set(Array.isArray(value) ? value : [])
    }
    return sets
  })

  /** Number of entries selected (of the first identifier). */
  const selectedCount = computed(() => {
    const first = Object.keys(multiSelect.value || {})[0]
    return first ? selectedSets.value[first]?.size ?? 0 : 0
  })

  /** A key that changes whenever any of the sets changes, to watch. */
  const selectionKey = computed(() =>
    JSON.stringify(
      Object.keys(multiSelect.value || {}).map((identifier) => selectionStore.$state[identifier] ?? null),
    ),
  )

  /** Whether a row belongs to the selection (by the first identifier). */
  function isRowSelected(row: Record<string, unknown> | undefined): boolean {
    if (!row) return false
    for (const [identifier, column] of Object.entries(multiSelect.value || {})) {
      const value = row[column]
      if (value !== undefined && value !== null && selectedSets.value[identifier]?.has(value)) {
        return true
      }
    }
    return false
  }

  /** Apply the rows picked by the user to every identifier. */
  function applyRows(rows: Record<string, unknown>[], mode: MultiSelectMode): void {
    for (const [identifier, column] of Object.entries(multiSelect.value || {})) {
      const picked = rows.map((row) => row[column])
      const next = combineSelection(selectionStore.$state[identifier], picked, mode)
      const current = selectionStore.$state[identifier] ?? null
      if (JSON.stringify(current) !== JSON.stringify(next)) {
        selectionStore.updateSelection(identifier, next)
      }
    }
  }

  /** Clear every identifier. */
  function clear(): void {
    for (const identifier of Object.keys(multiSelect.value || {})) {
      if ((selectionStore.$state[identifier] ?? null) !== null) {
        selectionStore.updateSelection(identifier, null)
      }
    }
  }

  return { enabled, selectedSets, selectedCount, selectionKey, isRowSelected, applyRows, clear }
}

/**
 * The plot toolbar's Clear selection tool, next to Plotly's own box and lasso
 * select buttons; its badge counts the selected points.
 */
export function clearSelectionTool(onClick: () => void, count = 0): PlotTool {
  return {
    id: 'clear-selection',
    group: 'view',
    icon: ICONS.deselect,
    label: 'Clear selection',
    help: count > 0 ? `${count} selected` : 'nothing is selected',
    count,
    run: () => onClick(),
  }
}

/** Accent color of a multi-selection, shared by every component. */
export const SELECTION_ACCENT = '#1e88e5'
const SELECTION_GLOW = 'rgba(30, 136, 229, 0.25)'

/**
 * The selected points as accent dots with a white rim and a soft glow,
 * drawn over the plot.
 * `size` is the marker size of the points underneath.
 */
export function selectionOverlay(x: number[], y: number[], size = 8): Plotly.Data[] {
  if (x.length === 0) return []
  const common = { type: 'scattergl', x, y, mode: 'markers', hoverinfo: 'skip', showlegend: false }
  return [
    { ...common, name: 'selection glow', marker: { symbol: 'circle', size: size + 7, color: SELECTION_GLOW } },
    {
      ...common,
      name: 'in selection',
      marker: { symbol: 'circle', size: size + 1, color: SELECTION_ACCENT, line: { width: 1.5, color: '#ffffff' } },
    },
  ] as Plotly.Data[]
}

/** Layout of the box and lasso while dragging and after: the accent, dotted. */
export const SELECTION_LAYOUT = {
  newselection: { line: { color: SELECTION_ACCENT, width: 1.5, dash: 'dot' } },
  activeselection: { fillcolor: 'rgba(30, 136, 229, 0.10)', opacity: 1 },
}
