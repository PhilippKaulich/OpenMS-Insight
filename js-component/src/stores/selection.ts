/**
 * Generic selection store for cross-component state.
 *
 * Supports any identifier-based selection using dynamic keys.
 * Uses separate counters for selection and pagination state to prevent
 * rapid pagination clicks from causing legitimate selection updates to be rejected.
 */

import { defineStore } from 'pinia'

export interface SelectionState {
  // Session identifier for resetting on new session
  id?: number

  // Separate counters for conflict resolution
  selection_counter?: number
  pagination_counter?: number

  // Legacy counter for backwards compatibility
  counter?: number

  // Dynamic selection values keyed by identifier name
  [key: string]: unknown
}

/**
 * Check if identifier is for pagination state (ends with '_page').
 */
function isPaginationIdentifier(identifier: string): boolean {
  return identifier.endsWith('_page')
}

/** JSON with sorted keys: the same value from Python and from Vue compares equal. */
function stableJson(value: unknown): string {
  return JSON.stringify(value, (_key, v) =>
    v && typeof v === 'object' && !Array.isArray(v)
      ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, v[k]]))
      : v
  )
}

export const useSelectionStore = defineStore('selection', {
  state: (): SelectionState => ({
    id: undefined,
    selection_counter: undefined,
    pagination_counter: undefined,
    counter: undefined,
  }),

  actions: {
    /**
     * Update a selection value.
     *
     * @param identifier - The identifier name (e.g., 'spectrum', 'mass')
     * @param value - The selected value
     */
    updateSelection(identifier: string, value: unknown) {
      const isPagination = isPaginationIdentifier(identifier)
      console.log('[SelectionStore] ===== updateSelection =====', {
        timestamp: Date.now(),
        identifier,
        value,
        isPagination,
        currentSelectionCounter: this.$state.selection_counter,
        currentPaginationCounter: this.$state.pagination_counter,
      })
      // A table that loads the page it already shows sends the same
      // pagination again: moving the counter for it costs Python a rerun
      if (isPagination && stableJson(this.$state[identifier]) === stableJson(value)) {
        return
      }
      this.$patch((state) => {
        state[identifier] = value
        // Increment appropriate counter based on identifier type
        if (isPagination) {
          state.pagination_counter = (state.pagination_counter || 0) + 1
        } else {
          state.selection_counter = (state.selection_counter || 0) + 1
        }
        // Update legacy counter for backwards compatibility
        // IMPORTANT: Always increment counter so App.vue watcher sees every change
        // Using Math.max() would miss selection changes when pagination_counter is higher
        state.counter = (state.counter || 0) + 1
      })
      console.log('[SelectionStore] updateSelection DONE', {
        selectionCounter: this.$state.selection_counter,
        paginationCounter: this.$state.pagination_counter,
      })
    },
  },
})
