<template>
  <!-- A table fitted to a few rows stays at least 200 px tall -->
  <div
    style="padding: 8px; width: 98%; box-sizing: border-box"
    :style="isServerSidePagination ? {} : { minHeight: '200px' }"
  >
    <div class="d-flex">
      <div class="table-toolbar">
        <div class="table-toolbar-buttons">
          <v-btn
            variant="text"
            size="small"
            icon="mdi-download"
            :loading="pendingDownloadId !== null"
            :title="isServerSidePagination ? 'Download all rows and columns as CSV' : undefined"
            @click="downloadTable"
          />
          <div style="position: relative; display: inline-flex">
            <v-btn
              variant="text"
              size="small"
              icon="mdi-filter"
              :title="activeFilterCount > 0 ? `Filters (${activeFilterCount} active)` : 'Filters'"
              @click="openFilterDialog"
            />
            <div v-if="activeFilterCount > 0" class="filter-badge">
              {{ activeFilterCount }}
            </div>
          </div>
          <v-btn v-if="args.columnMenu !== false" variant="text" size="small" icon="mdi-view-column" :title="columnMenuTitle">
            <v-icon>mdi-view-column</v-icon>
            <v-menu activator="parent" :close-on-content-click="false" location="bottom start">
              <v-card min-width="220">
                <div class="d-flex align-center justify-space-between px-3 pt-2">
                  <span class="text-subtitle-2">Columns</span>
                  <v-btn size="small" variant="text" @click="resetColumnVisibility">Reset</v-btn>
                </div>
                <div style="max-height: 260px; overflow-y: auto" class="px-2 pb-2">
                  <v-checkbox
                    v-for="col in columnNames"
                    :key="col.field"
                    :model-value="isColumnVisible(col.field)"
                    :label="col.title"
                    :disabled="isColumnVisible(col.field) && visibleColumnCount <= 1"
                    hide-details
                    density="compact"
                    @update:model-value="setColumnVisible(col.field, !!$event)"
                  />
                </div>
              </v-card>
            </v-menu>
          </v-btn>
          <v-btn
            v-if="args.goToFields && args.goToFields.length > 0"
            variant="text"
            size="small"
            icon="mdi-arrow-right-bold"
            @click="toggleGoTo"
            color="default"
          />
          <v-text-field
            v-if="args.search"
            :model-value="searchInput"
            density="compact"
            variant="outlined"
            hide-details
            single-line
            clearable
            prepend-inner-icon="mdi-magnify"
            :placeholder="args.searchPlaceholder || 'Search'"
            :title="searchTitle"
            class="table-search"
            @update:model-value="onSearchInput"
            @keyup.enter="commitSearch"
          />
        </div>
        <div class="table-toolbar-title">
          <h4 :title="args.title ?? undefined">{{ args.title ?? '' }}</h4>
          <v-btn
            v-if="multiSelectEnabled"
            variant="text"
            size="x-small"
            icon="mdi-checkbox-multiple-marked-outline"
            :class="['multi-select-toggle', { active: checkboxesShown }]"
            :title="checkboxesShown ? 'Hide the check boxes' : 'Tick rows to select several'"
            @click="toggleCheckboxes"
          />
        </div>
        <div class="table-toolbar-toggles">
          <v-checkbox
            v-for="toggle in toggleFilters"
            :key="toggle.column"
            :model-value="currentToggles[toggle.column]"
            :label="toggle.label"
            hide-details
            density="compact"
            :color="toggle.color || 'primary'"
            class="toggle-filter"
            @update:model-value="onToggleFilter(toggle.column, $event)"
          />
        </div>
      </div>
    </div>

    <!-- The filters in force, each removable -->
    <div v-if="activeFilterChips.length > 0" class="table-filter-chips">
      <v-chip
        v-for="chip in activeFilterChips"
        :key="chip.key"
        size="small"
        closable
        :title="chip.kind === 'search' ? searchTitle : 'Click to edit, × to remove'"
        @click="chip.kind !== 'search' && openFilterDialog()"
        @click:close="removeFilterChip(chip)"
      >
        {{ chip.label }}
      </v-chip>
      <v-btn
        v-if="activeFilterChips.length > 1"
        size="x-small"
        variant="text"
        color="primary"
        @click="clearAllFilters"
      >
        Clear all
      </v-btn>
    </div>

    <!-- Go To interface -->
    <div
      v-if="args.goToFields && args.goToFields.length > 0 && showGoTo"
      style="
        padding: 8px;
        margin-bottom: 8px;
        background-color: #f5f5f5;
        border-radius: 4px;
        border: 1px solid #e0e0e0;
      "
    >
      <div style="display: flex; gap: 8px; align-items: center; height: 32px">
        <span style="font-size: 14px; font-weight: 500; color: #333">Go to:</span>
        <select
          v-model="selectedGoToField"
          style="
            font-size: 12px;
            padding: 4px 8px;
            border: 1px solid #ccc;
            border-radius: 3px;
            background: white;
            height: 24px;
          "
        >
          <option v-for="field in args.goToFields" :key="field" :value="field">
            {{ getGoToFieldLabel(field) }}
          </option>
        </select>
        <input
          v-model="goToInputValue"
          @keyup.enter="performGoTo"
          :placeholder="getGoToPlaceholder()"
          style="
            width: 200px;
            font-size: 12px;
            padding: 4px 8px;
            border: 1px solid #ccc;
            border-radius: 3px;
            height: 24px;
          "
        />
        <button
          @click="performGoTo"
          :disabled="!goToInputValue.trim()"
          style="
            font-size: 12px;
            padding: 4px 12px;
            border: 1px solid #ccc;
            border-radius: 3px;
            cursor: pointer;
            height: 24px;
          "
          :style="{
            opacity: !goToInputValue.trim() ? 0.5 : 1,
            cursor: !goToInputValue.trim() ? 'not-allowed' : 'pointer',
          }"
        >
          Go
        </button>
      </div>
    </div>

    <div :id="id" :class="tableClasses" @keydown.capture="onTableKeydown"></div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import { TabulatorFull as Tabulator, type CellComponent, type ColumnDefinition, type Options } from 'tabulator-tables'
import { Streamlit } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type {
  TableComponentArgs,
  PaginationState,
  ColumnMetadata,
  ColumnFilter,
  NumericFilterConfig,
} from '@/types/component'
import { isCustomFormatter, getCustomFormatter } from './formatters'
import { combineSelection } from '@/composables/useMultiSelect'

// Global counter for unique table IDs
let tableIdCounter = 0

type NumericOp = 'between' | '>=' | '<='
type FilterValue = {
  categorical?: string[]
  // A bound left null is open
  numeric?: { op: NumericOp; min: number | null; max: number | null }
  text?: string
}
interface FilterChip {
  key: string
  kind: 'search' | 'categorical' | 'numeric' | 'text'
  field?: string
  label: string
}

/** A number as people write it: no exponent, at most 6 significant digits. */
function formatNumber(value: number): string {
  return value.toLocaleString('en-US', { maximumSignificantDigits: 6, useGrouping: false })
}

// How long typing in the search box waits before the table is searched
const SEARCH_DELAY_MS = 400
// A row reached with the keyboard is highlighted at once, and selected (sent to
// Python, so linked components follow) once no key has been pressed for this
// long: holding a key down reruns the app once, not once per row passed
const KEY_SELECT_DELAY_MS = 200
// A page asked for by the keyboard that has not arrived after this long is
// given up, so the keys work again
const KEY_PAGE_TIMEOUT_MS = 5000
// How often a page asked for by the keyboard is looked for: Tabulator may
// still be busy with the previous page and drop the request, which is then
// made again
const KEY_PAGE_CHECK_MS = 750

type KeyMove = 'up' | 'down' | 'pageUp' | 'pageDown' | 'home' | 'end'
const KEY_MOVES: Record<string, KeyMove> = {
  ArrowUp: 'up',
  ArrowDown: 'down',
  PageUp: 'pageUp',
  PageDown: 'pageDown',
  Home: 'home',
  End: 'end',
}

export default defineComponent({
  name: 'TabulatorTable',
  props: {
    args: {
      type: Object as PropType<TableComponentArgs>,
      required: true,
    },
  },
  emits: ['rowSelected'],
  setup() {
    const streamlitDataStore = useStreamlitDataStore()
    const selectionStore = useSelectionStore()
    // Generate unique ID on setup
    const uniqueId = `table-${Date.now()}-${++tableIdCounter}`
    return { streamlitDataStore, selectionStore, uniqueId }
  },
  data() {
    return {
      tabulator: undefined as Tabulator | undefined,
      // Request id of a full-table CSV export awaiting its payload from Python
      pendingDownloadId: null as number | null,
      // Columns the viewer showed or hid in the column menu (field -> visible)
      columnVisibility: {} as Record<string, boolean>,
      selectedColumns: [] as string[],
      filterValues: {} as Record<string, FilterValue>,
      filterTypes: {} as Record<string, 'categorical' | 'numeric' | 'text'>,
      columnAnalysis: {} as Record<
        string,
        {
          uniqueValues: (string | number)[]
          minValue?: number
          maxValue?: number
          dataType: 'categorical' | 'numeric' | 'text'
        }
      >,
      teleportDialog: false,
      teleportBackdrop: null as HTMLElement | null,
      teleportContainer: null as HTMLElement | null,
      parentDocument: null as Document | null,
      showGoTo: false,
      selectedGoToField: '',
      goToInputValue: '',
      // Pending selection: stores selection values that couldn't be applied
      // because the data wasn't ready yet. Applied when new data arrives.
      pendingSelection: null as Record<string, unknown> | null,
      // Track last data hash to avoid unnecessary redraws
      lastDataHash: '' as string,
      // Flag to skip redundant syncSelectionFromStore calls after manual selection
      skipNextSync: false as boolean,
      // reclick 'unhighlight': the selection whose row the user unhighlighted.
      // The row stays unhighlighted until the selection changes.
      unhighlightedSelection: null as Record<string, unknown> | null,
      rootResizeObserver: null as ResizeObserver | null,
      // Pending data request for server-side pagination (deferred promise)
      pendingDataRequest: null as { resolve: (data: any) => void; reject: (err: any) => void } | null,
      // Track if we're waiting for server response
      isLoadingServerData: false as boolean,
      // Track current server-side filter state sent to Python
      currentColumnFilters: [] as Array<{ field: string; type: string; value: unknown }>,
      // On/off state of the title-row toggle filters, keyed by column
      currentToggles: {} as Record<string, boolean>,
      // Text in the search box, and the search last sent to Python
      searchInput: '' as string,
      currentSearch: '' as string,
      searchTimer: null as ReturnType<typeof setTimeout> | null,
      // Track if table has fired tableBuilt event (DOM ready)
      isTableBuilt: false as boolean,
      // Track if we're in the middle of a user-initiated page navigation
      isNavigatingPages: false as boolean,
      // Pending target row index for selection after page navigation completes
      pendingTargetRowIndex: null as number | null,
      // Flag to track programmatic navigation via navigate_to_page (forces data injection)
      pendingPageNavigation: false as boolean,
      // Flag to prevent selectDefaultRow from updating selection during initial render
      // This prevents orphaned AJAX promises when Streamlit reruns before tableBuilt
      initialLoadComplete: false as boolean,
      // Track what page Vue requested (for detecting when Python adjusted the page)
      lastRequestedPage: null as number | null,
      // Track what sort the CLIENT requested (not server state)
      // These are local state that persists during the request-response cycle
      requestedSortColumn: '' as string,
      requestedSortDir: 'asc' as 'asc' | 'desc',
      // Track the counter value when AJAX request was made (for stale response detection)
      pendingRequestCounter: null as number | null,
      // multi_select: last check box toggled (for Shift ranges), and a check box
      // click, which must not also select the row
      lastCheckedPosition: null as number | null,
      checkboxClicked: false as boolean,
      // The check box column is shown once the user asks for it
      checkboxesShown: false as boolean,
      // Keyboard navigation: the row highlighted with the keys and not yet
      // selected (its index field value), and the timer that selects it
      keyboardRowId: null as unknown,
      // The last row the keys moved to: kept in view when its page is drawn again
      keyboardShownId: null as unknown,
      keySelectTimer: null as ReturnType<typeof setTimeout> | null,
      // Position (over all pages) of the row the keys moved to while its page
      // is being fetched, the page asked for and when
      keyNavTarget: null as number | null,
      keyNavRequestedPage: null as number | null,
      keyNavRequestedAt: 0,
      keyNavCheckTimer: null as ReturnType<typeof setTimeout> | null,
    }
  },
  computed: {
    // Buttons and chips in the table's dialogs take the app's primary colour
    accentColor(): string {
      return this.streamlitDataStore.theme?.primaryColor || '#1976d2'
    },
    accentHover(): string {
      return `color-mix(in srgb, ${this.accentColor} 82%, black)`
    },
    multiSelectEnabled(): boolean {
      return Object.keys(this.args.multiSelect || {}).length > 0
    },
    // Changes whenever a multi_select set changes
    multiSelectionKey(): string {
      return JSON.stringify(
        Object.keys(this.args.multiSelect || {}).map((identifier) => this.selectionStore.$state[identifier] ?? null),
      )
    },
    selectionScrollPosition(): 'top' | 'center' | 'bottom' | 'nearest' {
      return this.args.scrollPosition || 'center'
    },
    id(): string {
      return this.uniqueId
    },
    tableClasses(): Record<string, boolean> {
      return {
        'table-dark': this.streamlitDataStore.theme?.base === 'dark',
        'table-light': this.streamlitDataStore.theme?.base === 'light',
        'table-bordered': true,
        'table-sm': true,
      }
    },
    toggleFilters(): Array<{ label: string; column: string; default: boolean; color?: string }> {
      return this.args.toggleFilters || []
    },
    /**
     * Toggle state and search to merge into pagination requests (nothing for a
     * table that has neither, so its requests stay as they were).
     */
    viewFiltersPatch(): Record<string, unknown> {
      return {
        ...(this.toggleFilters.length > 0 ? { toggles: { ...this.currentToggles } } : {}),
        ...(this.args.search ? { search: this.currentSearch } : {}),
      }
    },
    numericFilterConfig(): Record<string, NumericFilterConfig> {
      return this.args.numericFilters || {}
    },
    searchTitle(): string {
      const titles = (this.args.searchColumns || []).map((field) => this.columnTitle(field))
      const where = titles.length > 0 ? ` in ${titles.join(', ')}` : ''
      return `Rows with every word${where}. Not case sensitive.`
    },
    /** One chip per filter in force: the search, then the dialog's filters. */
    activeFilterChips(): FilterChip[] {
      const chips: FilterChip[] = []
      if (this.currentSearch) {
        chips.push({ key: 'search', kind: 'search', label: `Search: ${this.currentSearch}` })
      }
      for (const field of this.selectedColumns) {
        const value = this.filterValues[field]
        if (!value || !this.isFilterActive(field)) continue
        const title = this.columnTitle(field)
        const type = this.filterTypes[field]
        if (type === 'numeric' && value.numeric) {
          const { op, min, max } = value.numeric
          let label: string
          if (op === '>=' || (op === 'between' && max === null)) label = `${title} ≥ ${formatNumber(min as number)}`
          else if (op === '<=' || min === null) label = `${title} ≤ ${formatNumber(max as number)}`
          else label = `${title} ${formatNumber(min)} – ${formatNumber(max as number)}`
          chips.push({ key: `n:${field}`, kind: 'numeric', field, label })
        } else if (type === 'categorical' && value.categorical) {
          const shown = value.categorical.slice(0, 3).join(', ')
          const more = value.categorical.length > 3 ? ` +${value.categorical.length - 3}` : ''
          chips.push({ key: `c:${field}`, kind: 'categorical', field, label: `${title}: ${shown}${more}` })
        } else if (type === 'text' && value.text) {
          chips.push({ key: `t:${field}`, kind: 'text', field, label: `${title} ~ ${value.text}` })
        }
      }
      return chips
    },
    tableData(): Record<string, unknown>[] {
      const data = this.streamlitDataStore.allDataForDrawing?.tableData
      return Array.isArray(data) ? data : []
    },
    columnNames(): { field: string; title: string }[] {
      return (this.args.columnDefinitions || [])
        .map((col) => ({
          field: col.field || '',
          title: (col.title as string) || col.field || '',
        }))
        .filter((col) => col.field !== '')
    },
    // Columns hidden until the viewer turns them on
    defaultHiddenColumns(): Set<string> {
      const hidden = new Set<string>(this.args.hiddenColumns || [])
      for (const col of this.args.columnDefinitions || []) {
        if (col.visible === false && col.field) hidden.add(col.field)
      }
      return hidden
    },
    visibleColumnCount(): number {
      return this.columnNames.filter((col) => this.isColumnVisible(col.field)).length
    },
    columnMenuTitle(): string {
      const hidden = this.columnNames.length - this.visibleColumnCount
      return hidden > 0 ? `Choose columns (${hidden} hidden)` : 'Choose columns'
    },
    // localStorage key for the viewer's column choice, one per table
    columnVisibilityKey(): string {
      return `openms-insight:columns:${this.args.paginationIdentifier || this.args.title || ''}`
    },
    activeFilterCount(): number {
      return this.selectedColumns.filter((field) => this.isFilterActive(field)).length
    },
    preparedTableData(): Record<string, unknown>[] {
      const indexField = this.args.tableIndexField || 'id'
      const interactivity = this.args.interactivity || {}
      const interactivityColumns = Object.values(interactivity) as string[]

      // Include all columns needed: visible columns, index field, and interactivity columns
      const allColumns = [
        ...(this.args.columnDefinitions || []).map((col) => col.field),
        indexField,
        ...interactivityColumns,
      ]
      // Deduplicate columns
      const columns = [...new Set(allColumns)]

      if (this.tableData.length > 0) {
        const result: Record<string, unknown>[] = []
        this.tableData.forEach((row, index) => {
          const filteredRow: Record<string, unknown> = {}
          columns.forEach((column) => {
            if (column !== undefined) {
              filteredRow[column] = row[column]
            }
          })
          if (this.tableData[0][indexField] === undefined) {
            result.push({ ...filteredRow, [indexField]: index })
          } else {
            result.push({ ...filteredRow })
          }
        })
        return result
      }
      return this.tableData
    },
    // Get current data hash from store for change detection
    currentDataHash(): string {
      return this.streamlitDataStore.hash || ''
    },
    // Server-side pagination state from Python
    paginationState(): PaginationState | null {
      const state = this.streamlitDataStore.allDataForDrawing?._pagination as PaginationState | null
      console.log(`[TabulatorTable ${this.args.title}] paginationState COMPUTED:`, {
        page: state?.page,
        totalRows: state?.total_rows,
        hasState: !!state,
      })
      return state
    },
    // Navigation hint from Python (when selection is on different page)
    navigateToPage(): number | null {
      const val = this.streamlitDataStore.allDataForDrawing?._navigate_to_page
      return typeof val === 'number' ? val : null
    },
    // Target row index within the page (for highlighting after navigation)
    targetRowIndex(): number | null {
      const val = this.streamlitDataStore.allDataForDrawing?._target_row_index
      return typeof val === 'number' ? val : null
    },
    // Full-table CSV export prepared by Python in answer to a download request
    downloadPayload(): { request_id: number; filename: string; csv: string } | null {
      const val = this.streamlitDataStore.allDataForDrawing?._download
      return val && typeof val === 'object' ? (val as { request_id: number; filename: string; csv: string }) : null
    },
    // Check if server-side pagination is enabled
    isServerSidePagination(): boolean {
      return this.args.pagination !== false && !!this.args.paginationIdentifier
    },
    // Server's confirmed sort state (from last response)
    serverSortColumn(): string {
      return this.paginationState?.sort_column || ''
    },
    // Server's confirmed sort direction (from last response)
    serverSortDir(): 'asc' | 'desc' {
      return this.paginationState?.sort_dir || 'asc'
    },
    // Get column metadata from Python for filter dialogs
    serverColumnMetadata(): Record<string, ColumnMetadata> {
      return this.args.columnMetadata || {}
    },
  },
  watch: {
    // The checked rows changed (here or in another component)
    multiSelectionKey() {
      this.refreshCheckboxes()
    },
    // Save the CSV once per request. The payload stays in the data store after
    // later merges, so only the id this table asked for is honoured.
    downloadPayload(payload) {
      if (!payload || payload.request_id !== this.pendingDownloadId) return
      this.pendingDownloadId = null
      const blob = new Blob([payload.csv], { type: 'text/csv;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = payload.filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    },
    // Watch data hash instead of tableData directly
    // This prevents unnecessary redraws when only selection changes (data unchanged)
    currentDataHash(newHash, oldHash) {
      console.log(`[TabulatorTable ${this.args.title}] ===== currentDataHash WATCHER FIRED =====`, {
        timestamp: Date.now(),
        newHash: newHash?.slice(0, 8),
        oldHash: oldHash?.slice(0, 8),
        lastDataHash: this.lastDataHash?.slice(0, 8),
        hasPendingRequest: !!this.pendingDataRequest,
        pendingTargetRowIndex: this.pendingTargetRowIndex,
      })

      // Skip if hash hasn't actually changed (e.g., on initial load or selection-only updates)
      if (newHash === this.lastDataHash) {
        // Note: Don't call syncSelectionFromStore here - the selection store watcher
        // already handles selection changes. Calling it here was causing double work.
        console.log(`[TabulatorTable ${this.args.title}] currentDataHash watcher: early return (hash unchanged)`)
        return
      }

      // Update our local hash tracker
      this.lastDataHash = newHash

      // Auto-clear invalid selections: when data changes, check if current selection
      // still exists in the new data. If not, clear it from the selection store.
      // This ensures that when upstream filters change (e.g., selecting a new spectrum),
      // any selection that's no longer valid (e.g., an identification from the old spectrum)
      // is automatically cleared.
      this.clearInvalidSelections()

      this.$nextTick(() => {
        // Use replaceData if table exists - preserves scroll position, sort, filters
        // Only full rebuild needed on initial render or if table was destroyed
        if (this.tabulator) {
          this.updateTableData()
        } else {
          this.drawTable()
        }
      })
    },
    // Watch for height changes in args
    'args.height'(newHeight: number | undefined) {
      if (this.tabulator && newHeight) {
        this.tabulator.setHeight(Math.max(this.tableMaxHeight(), 50))
      }
    },
    // The chip row takes room from the rows of a table of fixed height
    'activeFilterChips.length'(count: number, previous: number) {
      if ((count > 0) !== (previous > 0) && this.tabulator && this.isServerSidePagination) {
        this.tabulator.setHeight(Math.max(this.tableMaxHeight(), 150))
      }
    },
    // Another table drawn in this view: show its filters, not the last table's
    'args.paginationIdentifier'(identifier: string | undefined, previous: string | undefined) {
      if (identifier !== previous) {
        this.restoreFilters()
      }
    },
    selectedColumns: {
      handler(newColumns: string[]) {
        newColumns.forEach((columnField) => {
          this.initializeFilterValue(columnField)
        })
      },
      immediate: true,
    },
    // Watch selection store to update table selection when state changes
    'selectionStore.$state': {
      handler() {
        this.syncSelectionFromStore()
      },
      deep: true,
    },
    // Watch for navigation hints from Python (selection on different page)
    navigateToPage(newPage: number | null) {
      console.log(`[TabulatorTable ${this.args.title}] navigateToPage watcher:`, {
        newPage,
        targetRowIndex: this.targetRowIndex,
        isServerSidePagination: this.isServerSidePagination,
        hasTabulator: !!this.tabulator,
        isNavigatingPages: this.isNavigatingPages,
      })

      // Skip if Vue is already navigating pages (Vue-initiated navigation)
      // Python sends navigate hints even for Vue-initiated page changes, which
      // causes a feedback loop if we process them
      if (this.isNavigatingPages) {
        console.log(
          `[TabulatorTable ${this.args.title}] navigateToPage: SKIPPING (Vue-initiated navigation in progress)`,
        )
        return
      }

      if (newPage && this.tabulator && this.isServerSidePagination) {
        // Store target row index for selection after data injection
        // Do NOT attempt selection here - data hasn't arrived yet
        this.pendingTargetRowIndex = this.targetRowIndex
        // Mark that we're navigating programmatically (forces data injection even without AJAX request)
        this.pendingPageNavigation = true
        // Mark that we're navigating pages so applyFilters() is skipped in updateTableData()
        // This prevents applyFilters() from resetting page to 1 after Python-triggered navigation
        this.isNavigatingPages = true
        console.log(`[TabulatorTable ${this.args.title}] Set pendingTargetRowIndex:`, this.pendingTargetRowIndex)
        // Navigate to the page - selection will happen in paginationState watcher
        ;(this.tabulator as any).setPage(newPage).catch(() => {})
      }
    },
    // Watch pagination state to update table when server sends new data
    paginationState: {
      handler(newState: PaginationState | null, oldState: PaginationState | null) {
        console.log(`[TabulatorTable ${this.args.title}] ===== paginationState WATCHER FIRED =====`, {
          timestamp: Date.now(),
          newPage: newState?.page,
          oldPage: oldState?.page,
          newTotalRows: newState?.total_rows,
          pendingTargetRowIndex: this.pendingTargetRowIndex,
          hasPendingDataRequest: !!this.pendingDataRequest,
          pendingRequestCounter: this.pendingRequestCounter,
          isTableBuilt: this.isTableBuilt,
          isServerSidePagination: this.isServerSidePagination,
          preparedDataLength: this.preparedTableData.length,
          storeDataForDrawingKeys: Object.keys(this.streamlitDataStore.allDataForDrawing || {}),
        })

        if (!newState || !this.isServerSidePagination || !this.tabulator) {
          console.log(`[TabulatorTable ${this.args.title}] paginationState watcher: early return`)
          return
        }

        // Try to inject data if table is empty (handles case where tableBuilt fired before paginationState was available)
        // Pass newState directly to bypass Vue's computed property timing issue
        // (watchers receive new values before computed properties re-evaluate)
        this.injectServerSideData(newState)

        // ALWAYS update pagination limits when they change (not just on data injection)
        // This fixes the bug where filter changes update data but not the pagination UI
        // because injectServerSideData() returns early when table already has data
        const tab = this.tabulator as any
        if (
          tab.modules?.page &&
          (oldState?.total_rows !== newState.total_rows ||
            oldState?.total_pages !== newState.total_pages)
        ) {
          console.log(
            `[TabulatorTable ${this.args.title}] paginationState watcher: updating pagination limits`,
            {
              oldTotalRows: oldState?.total_rows,
              newTotalRows: newState.total_rows,
              oldTotalPages: oldState?.total_pages,
              newTotalPages: newState.total_pages,
            }
          )
          tab.modules.page.setMaxRows(newState.total_rows)
          tab.modules.page.setMaxPage(newState.total_pages)
          tab.redraw(true)
          // Trigger setPage to refresh pagination counter (Showing X of Y rows)
          // setMaxRows/setMaxPage update internal state but don't trigger _setPageCounter()
          tab.setPage(newState.page || 1).catch(() => {})
        }

        // Sync client's requested state with server's confirmed state
        // This ensures local state stays up-to-date after server response
        if (newState.sort_column !== undefined) {
          this.requestedSortColumn = newState.sort_column || ''
        }
        if (newState.sort_dir !== undefined) {
          this.requestedSortDir = newState.sort_dir || 'asc'
        }

        // After data injection, attempt pending row selection
        // This is the correct place to select because data is now available
        if (this.pendingTargetRowIndex !== null) {
          console.log(`[TabulatorTable ${this.args.title}] paginationState watcher: scheduling selectPendingTargetRow`)
          this.$nextTick(() => {
            this.selectPendingTargetRow()
          })
        }

        // Resolve any pending data request (if using ajaxRequestFunc)
        console.log(`[TabulatorTable ${this.args.title}] paginationState watcher: checking pendingDataRequest`, {
          hasPendingDataRequest: !!this.pendingDataRequest,
          pendingRequestCounter: this.pendingRequestCounter,
        })
        if (this.pendingDataRequest) {
          this.resolveDataRequest()
        } else {
          console.log(`[TabulatorTable ${this.args.title}] paginationState watcher: NO pendingDataRequest to resolve`)
        }

        // After successful data injection or AJAX resolution, mark initial load complete
        // Python pre-computes initial selections, so selectDefaultRow only highlights existing selection
        if (!this.initialLoadComplete && this.isTableBuilt) {
          this.$nextTick(() => {
            this.initialLoadComplete = true
            console.log(`[TabulatorTable ${this.args.title}] initialLoadComplete set to true`)
            // Call selectDefaultRow to highlight any pre-computed selection from Python
            this.selectDefaultRow()
          })
        }

        // Clear loading state
        this.isLoadingServerData = false
        // NOTE: Do NOT clear isNavigatingPages here - it must persist until
        // replaceData().then() completes in updateTableData()
      },
      deep: true,
    },
  },
  created() {
    // Toggle filters start from the state Python last saw, else their defaults
    const saved = this.paginationState?.toggles || {}
    for (const toggle of this.toggleFilters) {
      this.currentToggles[toggle.column] = saved[toggle.column] ?? toggle.default
    }
    // So do the search and the dialog's filters, e.g. when the page is opened again
    this.restoreFilters()
  },
  mounted() {
    // Initialize lastDataHash from store and draw table
    this.lastDataHash = this.currentDataHash
    this.loadColumnVisibility()
    this.drawTable()
    this.initializeTeleport()
    this.initializeGoTo()
    // A new selection of these identifiers starts the rows in the initial order
    for (const identifier of this.args.resetSortOn || []) {
      this.$watch(
        () => this.selectionStore.$state[identifier],
        () => {
          if (this.tabulator && !this.isServerSidePagination) {
            ;(this.tabulator as any).setSort(this.args.initialSort || [])
            ;(this.tabulator as any).rowManager.element.scrollTop = 0
          }
        }
      )
    }
    // A table fitted to its rows resizes with them: the frame follows it
    if (!this.isServerSidePagination) {
      this.rootResizeObserver = new ResizeObserver(() => {
        Streamlit.setFrameHeight((this.$el as HTMLElement).offsetHeight)
      })
      this.rootResizeObserver.observe(this.$el as HTMLElement)
    }
  },
  beforeUnmount() {
    if (this.searchTimer) clearTimeout(this.searchTimer)
    if (this.keySelectTimer) clearTimeout(this.keySelectTimer)
    if (this.keyNavCheckTimer) clearTimeout(this.keyNavCheckTimer)
    this.cleanupTeleport()
    this.rootResizeObserver?.disconnect()
  },
  methods: {
    /** Height left for the rows: the component's height less toolbar, go-to bar and filter chips. */
    tableMaxHeight(): number {
      const passedHeight = this.args.height
      const defaultHeight = this.args.title ? 320 : 310
      const baseHeight = passedHeight ? passedHeight - 56 : defaultHeight
      const goToHeight = this.showGoTo ? 58 : 0
      const chipsHeight = this.activeFilterChips.length > 0 ? 34 : 0
      return baseHeight - goToHeight - chipsHeight
    },

    columnTitle(field: string): string {
      const column = (this.args.columnDefinitions || []).find((col) => col.field === field)
      return (column?.title as string) || field
    },

    /** Whether the dialog's filter on this column restricts the rows. */
    isFilterActive(field: string): boolean {
      const value = this.filterValues[field]
      if (!value) return false
      switch (this.filterTypes[field]) {
        case 'categorical':
          return !!value.categorical && value.categorical.length > 0
        case 'numeric':
          return this.numericBounds(field).length > 0
        case 'text':
          return !!value.text && value.text.trim() !== ''
      }
      return false
    },

    /** The '>=' and '<=' bounds a numeric filter sets (none while open). */
    numericBounds(field: string): Array<{ type: '>=' | '<='; value: number }> {
      const numeric = this.filterValues[field]?.numeric
      if (!numeric) return []
      const bounds: Array<{ type: '>=' | '<='; value: number }> = []
      if (numeric.op !== '<=' && numeric.min !== null && Number.isFinite(numeric.min)) {
        bounds.push({ type: '>=', value: numeric.min })
      }
      if (numeric.op !== '>=' && numeric.max !== null && Number.isFinite(numeric.max)) {
        bounds.push({ type: '<=', value: numeric.max })
      }
      return bounds
    },

    /**
     * Take the search and the dialog's filters from the state Python echoes,
     * the filters in force for this table. Columns with a numeric filter
     * option are always offered in the dialog.
     */
    restoreFilters(): void {
      const state = this.paginationState
      const filters: ColumnFilter[] = Array.isArray(state?.column_filters) ? state!.column_filters! : []
      this.filterValues = {}
      this.filterTypes = {}
      this.columnAnalysis = {}
      const selected = new Set<string>(Object.keys(this.numericFilterConfig))
      for (const filter of filters) {
        if (!filter?.field) continue
        selected.add(filter.field)
        const value: FilterValue = this.filterValues[filter.field] || {}
        if (filter.type === 'in' && Array.isArray(filter.value)) {
          value.categorical = filter.value.map((v) => String(v))
          this.filterTypes[filter.field] = 'categorical'
        } else if ((filter.type === '>=' || filter.type === '<=') && typeof filter.value === 'number') {
          const numeric = value.numeric || { op: filter.type, min: null, max: null }
          if (filter.type === '>=') numeric.min = filter.value
          else numeric.max = filter.value
          numeric.op = numeric.min !== null && numeric.max !== null ? 'between' : filter.type
          value.numeric = numeric
          this.filterTypes[filter.field] = 'numeric'
        } else if (filter.type === 'regex' && typeof filter.value === 'string') {
          value.text = filter.value
          this.filterTypes[filter.field] = 'text'
        }
        this.filterValues[filter.field] = value
      }
      this.selectedColumns = this.columnNames.map((col) => col.field).filter((field) => selected.has(field))
      this.currentColumnFilters = filters.map((f) => ({ field: f.field, type: f.type, value: f.value }))
      this.currentSearch = typeof state?.search === 'string' ? state.search : ''
      this.searchInput = this.currentSearch
    },

    /** Ask Python for page 1 of the rows under the current filters and search. */
    requestFilteredRows(): void {
      const paginationIdentifier = this.args.paginationIdentifier
      if (!paginationIdentifier) return
      this.isLoadingServerData = true
      this.selectionStore.updateSelection(paginationIdentifier, {
        page: 1,
        page_size: this.paginationState?.page_size || this.args.pageSize || 100,
        sort_column: this.requestedSortColumn || undefined,
        sort_dir: this.requestedSortDir,
        column_filters: this.currentColumnFilters,
        ...this.viewFiltersPatch,
      })
    },

    onSearchInput(value: string | null): void {
      this.searchInput = value ?? ''
      if (this.searchTimer) clearTimeout(this.searchTimer)
      // Cleared with the × button: at once
      if (!this.searchInput) {
        this.commitSearch()
        return
      }
      this.searchTimer = setTimeout(() => this.commitSearch(), SEARCH_DELAY_MS)
    },

    /** Search the whole table (in Python) for the text in the search box. */
    commitSearch(): void {
      if (this.searchTimer) {
        clearTimeout(this.searchTimer)
        this.searchTimer = null
      }
      const text = this.searchInput.split(/\s+/).filter(Boolean).join(' ')
      if (text === this.currentSearch) return
      this.currentSearch = text
      this.requestFilteredRows()
    },

    removeFilterChip(chip: FilterChip): void {
      if (chip.kind === 'search') {
        this.searchInput = ''
        this.commitSearch()
        return
      }
      const value = chip.field ? this.filterValues[chip.field] : undefined
      if (!chip.field || !value) return
      if (chip.kind === 'numeric' && value.numeric) {
        value.numeric = { ...value.numeric, min: null, max: null }
      } else if (chip.kind === 'categorical') {
        value.categorical = []
      } else if (chip.kind === 'text') {
        value.text = ''
      }
      this.applyFilters()
      this.refreshTeleportDialog()
    },

    /** Remove the search and every filter of the dialog (not the title-row toggles). */
    clearAllFilters(): void {
      if (this.searchTimer) clearTimeout(this.searchTimer)
      this.searchInput = ''
      const hadSearch = this.currentSearch !== ''
      this.currentSearch = ''
      for (const field of Object.keys(this.filterValues)) {
        const value = this.filterValues[field]
        if (value.numeric) value.numeric = { ...value.numeric, min: null, max: null }
        if (value.categorical) value.categorical = []
        if (value.text) value.text = ''
      }
      // Server-side tables send the search along with the filters
      this.applyFilters()
      if (hadSearch && !this.isServerSidePagination) this.requestFilteredRows()
      this.refreshTeleportDialog()
    },

    /**
     * Tick or untick a title-row toggle filter. The filtering happens in Python,
     * so this requests page 1 of the re-filtered data.
     */
    onToggleFilter(column: string, value: boolean | null): void {
      this.currentToggles[column] = !!value
      const paginationIdentifier = this.args.paginationIdentifier
      if (!paginationIdentifier) return
      this.isLoadingServerData = true
      this.selectionStore.updateSelection(paginationIdentifier, {
        page: 1,
        page_size: this.paginationState?.page_size || this.args.pageSize || 100,
        sort_column: this.paginationState?.sort_column,
        sort_dir: this.paginationState?.sort_dir || 'asc',
        column_filters: this.currentColumnFilters,
        ...this.viewFiltersPatch,
      })
    },
    drawTable(): void {
      // Reset table built flag - new table being created
      this.isTableBuilt = false
      // Reset initial load flag - need to wait for data again
      this.initialLoadComplete = false

      // Destroy existing table if any
      if (this.tabulator) {
        this.tabulator.destroy()
        this.tabulator = undefined
      }

      const indexField = this.args.tableIndexField || 'id'
      // Use passed height if available, otherwise use default
      // Subtract space for title bar (~40px) and padding (~16px)
      const tableMaxHeight = this.tableMaxHeight()

      // Build Tabulator options
      // Note: For server-side pagination, we must NOT set the data option.
      // Tabulator only calls ajaxRequestFunc when data is undefined.
      // Setting data: [] makes Tabulator think it's initialized and skip AJAX.
      const tabulatorOptions: Options = {
        index: indexField,
        minHeight: 150,
        maxHeight: Math.max(tableMaxHeight, 150),
        height: Math.max(tableMaxHeight, 150),
        responsiveLayout: 'collapse',
        layout: this.args.tableLayoutParam || 'fitDataFill',
        selectable: 1,
        columnDefaults: {
          title: '',
          hozAlign: 'right',
        },
        columns: [...this.multiSelectColumns(), ...this.rowOverviewColumns(), ...(this.args.columnDefinitions || []).map((col) => {
          // Use a flexible type that allows both string and function formatters
          // Tabulator accepts function formatters but the TS types only declare string
          const colDef: Record<string, unknown> = { ...col }
          colDef.visible = this.isColumnVisible(col.field || '')
          if (colDef.headerTooltip === undefined) {
            colDef.headerTooltip = true
          }
          // A missing number arrives as NaN; the CSV leaves it empty
          if (colDef.accessorDownload === undefined) {
            colDef.accessorDownload = (value: unknown) =>
              typeof value === 'number' && Number.isNaN(value) ? '' : value
          }
          // Resolve custom formatter names to their implementations
          // Python sends formatter as a string (e.g., "scientific", "signed", "badge")
          // We replace it with the actual formatter function
          if (typeof colDef.formatter === 'string' && isCustomFormatter(colDef.formatter)) {
            const customFormatter = getCustomFormatter(colDef.formatter)
            if (customFormatter) {
              colDef.formatter = customFormatter
            }
          }
          return colDef as ColumnDefinition
        })],
        initialSort: this.args.initialSort,
      }

      // Enable pagination for large datasets (default: true)
      const usePagination = this.args.pagination !== false
      if (usePagination) {
        tabulatorOptions.pagination = true
        tabulatorOptions.paginationSize = this.paginationState?.page_size || this.args.pageSize || 100
        tabulatorOptions.paginationSizeSelector = [50, 100, 200, 500, 1000]
        tabulatorOptions.paginationCounter = 'rows'

        // Use remote pagination mode for server-side pagination
        // This makes Tabulator calculate button states from server-provided totals
        if (this.isServerSidePagination) {
          tabulatorOptions.paginationMode = 'remote'
          tabulatorOptions.sortMode = 'remote'
          tabulatorOptions.filterMode = 'remote'
          // Placeholder URL required by Tabulator for remote mode
          tabulatorOptions.ajaxURL = 'streamlit://data'
          // Custom request handler
          tabulatorOptions.ajaxRequestFunc = this.handleRemoteRequest.bind(this)
        } else {
          // For client-side pagination, set data directly
          tabulatorOptions.data = this.preparedTableData
        }
      } else {
        // For non-paginated tables, set data directly
        tabulatorOptions.data = this.preparedTableData
        if (this.args.fillHeight) {
          // Always the height it was given, so tables side by side line up
          tabulatorOptions.height = Math.max(tableMaxHeight, 50)
          tabulatorOptions.minHeight = Math.max(tableMaxHeight, 50)
          tabulatorOptions.maxHeight = Math.max(tableMaxHeight, 50)
        } else {
          // The table is as tall as its rows, up to the height it was given
          delete tabulatorOptions.height
          tabulatorOptions.minHeight = 50
          tabulatorOptions.maxHeight = Math.max(tableMaxHeight, 50)
        }
        // Only use virtual DOM if pagination is disabled and dataset is large
        const useVirtualDom = this.preparedTableData.length > 100
        tabulatorOptions.renderVertical = useVirtualDom ? 'virtual' : 'basic'
      }

      this.tabulator = new Tabulator(`#${this.id}`, tabulatorOptions)

      // Error handlers for data loading issues
      this.tabulator.on('dataLoadError', (error: any) => {
        console.error(`[TabulatorTable ${this.args.title}] Data load error:`, error)
      })
      this.tabulator.on('ajaxError', (error: any) => {
        console.error(`[TabulatorTable ${this.args.title}] AJAX error:`, error)
      })

      this.tabulator.on('tableBuilt', () => {
        // Mark table as fully initialized (DOM ready)
        this.isTableBuilt = true

        // Try to inject data (will succeed if paginationState is already available)
        this.injectServerSideData()

        // Only call selectDefaultRow for client-side pagination
        // For server-side, we call it after paginationState confirms data is ready (see paginationState watcher)
        // This prevents orphaned AJAX promises when selection update triggers Streamlit rerun
        if (!this.isServerSidePagination) {
          this.selectDefaultRow()
        }
        this.applyFilters()

        // Update Streamlit iframe height after table is rendered
        // Use specified height if provided, otherwise auto-calculate
        this.$nextTick(() => {
          if (this.args.height && this.isServerSidePagination) {
            Streamlit.setFrameHeight(this.args.height)
          } else if (!this.isServerSidePagination) {
            // The table's own height: while Tabulator lays out new rows, the
            // document is briefly taller than the table
            Streamlit.setFrameHeight((this.$el as HTMLElement).offsetHeight)
          } else {
            Streamlit.setFrameHeight()
          }
          // Force Tabulator to recalculate and render visible rows
          // This fixes issues where virtual rendering doesn't show rows until scroll
          setTimeout(() => {
            if (this.tabulator) {
              // Get the selected row and scroll to it to force virtual DOM render
              const selectedRows = this.tabulator.getSelectedRows()
              if (selectedRows.length > 0) {
                // scrollToRow forces virtual DOM to calculate and render visible rows
                // (rejects when the row is not rendered, e.g. on a collapsed table)
                this.tabulator.scrollToRow(selectedRows[0], this.selectionScrollPosition, false).catch(() => {})
              } else if (this.tabulator.getRows().length > 0) {
                // No selection - scroll to top to trigger render
                this.tabulator.scrollToRow(this.tabulator.getRows()[0], 'top', false).catch(() => {})
              }
            }
          }, 50)
        })
      })

      // Use Tabulator's rowClick event for reliable row selection handling
      this.tabulator.on('rowClick', (e: Event, row: any) => {
        this.onRowClick(row)
      })

      // Ensure visual selection matches selection state after render.
      // Only sync if no row is currently selected to avoid infinite loops
      // (selecting a row triggers render, which would trigger sync again).
      this.tabulator.on('renderComplete', () => {
        this.refreshCheckboxes()
        // A page the keys asked for has arrived
        this.applyKeyNavTarget()
        this.keepKeyboardRowInView()
        const selectedRows = this.tabulator?.getSelectedRows() || []
        if (selectedRows.length === 0 && !this.skipNextSync) {
          this.syncSelectionFromStore()
        }
      })

      // Handle remote sorting - Tabulator doesn't pass sorters to ajaxRequestFunc on header click
      // We need to manually trigger the remote request when sort changes
      if (this.isServerSidePagination) {
        this.tabulator.on('dataSorting', (sorters: Array<{ field: string; dir: string }>) => {
          console.log(`[TabulatorTable ${this.args.title}] dataSorting event:`, sorters)

          if (!sorters || sorters.length === 0) return

          const sortColumn = sorters[0].field
          const sortDir = sorters[0].dir as 'asc' | 'desc'

          // Check if sort actually changed
          const cachedSortCol = this.paginationState?.sort_column || ''
          const cachedSortDir = this.paginationState?.sort_dir || 'asc'

          if (sortColumn === cachedSortCol && sortDir === cachedSortDir) {
            console.log(`[TabulatorTable ${this.args.title}] dataSorting: sort unchanged, skipping`)
            return
          }

          console.log(`[TabulatorTable ${this.args.title}] dataSorting: requesting sorted data`, {
            from: { col: cachedSortCol, dir: cachedSortDir },
            to: { col: sortColumn, dir: sortDir },
          })

          // Track what we're requesting (client state)
          // This persists during the request-response cycle
          this.requestedSortColumn = sortColumn
          this.requestedSortDir = sortDir

          this.isLoadingServerData = true

          // Request sorted data from Python
          const paginationIdentifier = this.args.paginationIdentifier
          if (paginationIdentifier) {
            this.selectionStore.updateSelection(paginationIdentifier, {
              page: 1, // Reset to first page when sort changes
              page_size: this.paginationState?.page_size || this.args.pageSize || 100,
              sort_column: sortColumn,
              sort_dir: sortDir,
              column_filters: this.currentColumnFilters,
              ...this.viewFiltersPatch,
            })
          }
        })
      }
    },

    /**
     * Handle remote pagination/sort/filter requests from Tabulator.
     * Called by Tabulator when in remote pagination mode.
     *
     * Key insight: On initial load, Python has already sent data before Tabulator
     * calls this function. We detect this by comparing request params to current
     * paginationState and return existing data immediately if they match.
     * For subsequent page/sort/filter changes, we request new data from Python.
     */
    handleRemoteRequest(
      url: string,
      config: any,
      params: { page?: number; size?: number; sorters?: Array<{ field: string; dir: string }>; filter?: any[] }
    ): Promise<{ last_page: number; last_row: number; data: any[] }> {
      // Extract pagination parameters
      const page = params.page || 1
      const pageSize = params.size || this.args.pageSize || 100

      // Track what page we requested (for detecting when Python adjusts for selection)
      this.lastRequestedPage = page
      // Use requested state (client) for fallbacks, not server state
      // This preserves sort during page navigation before server responds
      const sortColumn = params.sorters?.[0]?.field ?? (this.requestedSortColumn || undefined)
      const sortDir = (params.sorters?.[0]?.dir ?? this.requestedSortDir ?? 'asc') as 'asc' | 'desc'

      console.log(`[TabulatorTable ${this.args.title}] ===== handleRemoteRequest START =====`, {
        timestamp: Date.now(),
        requestedPage: page,
        requestedSize: pageSize,
        requestedSortColumn: sortColumn,
        requestedSortDir: sortDir,
        rawSorters: params.sorters,
        paginationIdentifier: this.args.paginationIdentifier,
        currentPaginationState: this.paginationState,
        cachedSortColumn: this.paginationState?.sort_column,
        cachedSortDir: this.paginationState?.sort_dir,
        hasPendingRequest: !!this.pendingDataRequest,
      })

      // Check if we already have data for this request (initial load or same page/sort)
      // This happens when Python sends initial data before Tabulator calls ajaxRequestFunc
      const cachedSortCol = this.paginationState?.sort_column || ''
      const cachedSortDir = this.paginationState?.sort_dir || 'asc'
      const requestedSortCol = sortColumn || ''
      const sortMatch = cachedSortCol === requestedSortCol && cachedSortDir === sortDir

      console.log(`[TabulatorTable ${this.args.title}] handleRemoteRequest: SORT CHECK v2`, {
        cachedSortCol,
        cachedSortDir,
        requestedSortCol,
        requestedSortDir: sortDir,
        sortMatch,
      })

      if (
        this.paginationState &&
        this.paginationState.page === page &&
        this.paginationState.page_size === pageSize &&
        sortMatch &&
        // A filter that leaves no rows is an answer too: without it the page
        // counter kept the previous count
        (this.tableData.length > 0 || this.paginationState.total_rows === 0)
      ) {
        console.log(`[TabulatorTable ${this.args.title}] handleRemoteRequest: using cached data (page=${page}, sortCol=${cachedSortCol})`)

        // FIX: Update selection store even when using cached data
        // This keeps Vue's state in sync with what's displayed
        // Without this, Vue's selection store would have stale page number
        // (e.g., after Python navigates to page 38, Vue's store still had page 1)
        const paginationIdentifier = this.args.paginationIdentifier
        if (paginationIdentifier) {
          this.selectionStore.updateSelection(paginationIdentifier, {
            page,
            page_size: pageSize,
            sort_column: sortColumn,
            sort_dir: sortDir,
            column_filters: this.currentColumnFilters,
              ...this.viewFiltersPatch,
          })
        }

        // Use setTimeout(0) to delay resolution to next tick
        // This allows Tabulator's internal state machine to complete setup
        const responseData = {
          last_page: this.paginationState!.total_pages,
          last_row: this.paginationState!.total_rows,
          data: this.preparedTableData,
        }
        return new Promise((resolve) => {
          setTimeout(() => resolve(responseData), 0)
        })
      }

      this.isLoadingServerData = true

      // Mark that we're navigating pages (user-initiated, not filter change)
      this.isNavigatingPages = true

      // Request new data from Python via selection store
      const paginationIdentifier = this.args.paginationIdentifier
      if (paginationIdentifier) {
        console.log(`[TabulatorTable ${this.args.title}] handleRemoteRequest: requesting page ${page} via selectionStore`)
        this.selectionStore.updateSelection(paginationIdentifier, {
          page,
          page_size: pageSize,
          sort_column: sortColumn,
          sort_dir: sortDir,
          column_filters: this.currentColumnFilters,
              ...this.viewFiltersPatch,
        })
      }

      // Return promise that will be resolved when Python returns data
      // Track the counter value when request was made (for stale response detection)
      this.pendingRequestCounter = this.selectionStore.$state.pagination_counter || 0
      console.log(`[TabulatorTable ${this.args.title}] handleRemoteRequest: STORED pendingRequestCounter`, {
        pendingRequestCounter: this.pendingRequestCounter,
        selectionStorePaginationCounter: this.selectionStore.$state.pagination_counter,
      })

      return new Promise((resolve, reject) => {
        this.pendingDataRequest = { resolve, reject }
        console.log(`[TabulatorTable ${this.args.title}] handleRemoteRequest: pendingDataRequest SET`, {
          timestamp: Date.now(),
          requestCounter: this.pendingRequestCounter,
        })
        // Timeout after 30 seconds to prevent hanging
        setTimeout(() => {
          if (this.pendingDataRequest) {
            console.warn(`[TabulatorTable ${this.args.title}] Request timeout`)
            this.pendingDataRequest = null
            this.pendingRequestCounter = null
            this.isLoadingServerData = false
            reject(new Error('Request timeout'))
          }
        }, 30000)
      })
    },

    /**
     * Resolve pending data request when Python returns new data.
     * Called by the paginationState watcher.
     */
    resolveDataRequest(): void {
      const selectionStoreState = this.selectionStore.$state
      console.log(`[TabulatorTable ${this.args.title}] ===== resolveDataRequest CALLED =====`, {
        timestamp: Date.now(),
        hasPendingRequest: !!this.pendingDataRequest,
        pendingRequestCounter: this.pendingRequestCounter,
        paginationStatePage: this.paginationState?.page,
        preparedDataLength: this.preparedTableData.length,
        selectionStorePaginationCounter: selectionStoreState.pagination_counter,
        selectionStoreCounter: selectionStoreState.counter,
      })

      if (!this.pendingDataRequest || !this.paginationState) {
        console.log(`[TabulatorTable ${this.args.title}] resolveDataRequest: EARLY RETURN (missing data)`, {
          hasPendingRequest: !!this.pendingDataRequest,
          hasPaginationState: !!this.paginationState,
        })
        return
      }

      // Validate that this response matches what we requested
      // If counter advanced since we made the request, data is stale
      // (another page request was made while waiting for this response)
      const currentCounter = this.selectionStore.$state.pagination_counter || 0
      const isStale = this.pendingRequestCounter !== null && currentCounter > this.pendingRequestCounter + 1
      console.log(`[TabulatorTable ${this.args.title}] resolveDataRequest: STALE CHECK`, {
        pendingRequestCounter: this.pendingRequestCounter,
        currentCounter,
        threshold: this.pendingRequestCounter !== null ? this.pendingRequestCounter + 1 : 'N/A',
        isStale,
      })
      if (isStale) {
        console.log(`[TabulatorTable ${this.args.title}] resolveDataRequest: STALE RESPONSE DETECTED, rejecting promise`)
        // FIX: REJECT the promise instead of orphaning it
        // This allows Tabulator to clean up properly and not wait forever
        this.pendingDataRequest.reject(new Error('Stale response - newer request pending'))
        this.pendingDataRequest = null
        this.pendingRequestCounter = null
        this.isLoadingServerData = false
        return
      }

      console.log(`[TabulatorTable ${this.args.title}] resolveDataRequest: RESOLVING PROMISE`, {
        lastPage: this.paginationState.total_pages,
        lastRow: this.paginationState.total_rows,
        dataLength: this.preparedTableData.length,
      })

      // Resolve the promise with Tabulator's expected format
      this.pendingDataRequest.resolve({
        last_page: this.paginationState.total_pages,
        last_row: this.paginationState.total_rows,
        data: this.preparedTableData,
      })

      this.pendingDataRequest = null
      this.pendingRequestCounter = null
      this.isLoadingServerData = false
      console.log(`[TabulatorTable ${this.args.title}] resolveDataRequest: PROMISE RESOLVED`)
      // NOTE: Do NOT clear isNavigatingPages here - it must persist until
      // replaceData().then() completes in updateTableData() to prevent
      // selectDefaultRow() from resetting the page during navigation
    },

    /**
     * Manually inject data for server-side pagination when Tabulator doesn't
     * call ajaxRequestFunc (common in iframe environments like Streamlit).
     * Safe to call multiple times - only injects if table is empty.
     *
     * @param paginationStateOverride - Optional pagination state to use instead of computed property.
     *   This is needed because Vue watchers receive new values before computed properties update,
     *   so passing the watcher's newState directly bypasses this timing issue.
     */
    injectServerSideData(paginationStateOverride?: PaginationState | null): void {
      const paginationState = paginationStateOverride ?? this.paginationState

      console.log(`[TabulatorTable ${this.args.title}] ===== injectServerSideData CALLED =====`, {
        timestamp: Date.now(),
        hasPaginationState: !!paginationState,
        paginationPage: paginationState?.page,
        isTableBuilt: this.isTableBuilt,
        hasPendingRequest: !!this.pendingDataRequest,
        pendingPageNavigation: this.pendingPageNavigation,
        tabulatorRows: this.tabulator?.getRows().length,
        preparedDataLength: this.preparedTableData.length,
        isServerSidePagination: this.isServerSidePagination,
      })

      if (!this.tabulator || !this.isServerSidePagination || !paginationState || !this.isTableBuilt) {
        console.log(`[TabulatorTable ${this.args.title}] injectServerSideData: early return (preconditions)`)
        return
      }

      const hasPendingRequest = !!this.pendingDataRequest
      const tabulatorRows = this.tabulator.getRows().length

      // If there's a pending AJAX request, let resolveDataRequest handle it
      // Don't manually inject - Tabulator will handle data via Promise resolution
      if (hasPendingRequest) {
        console.log(`[TabulatorTable ${this.args.title}] injectServerSideData: skipping (AJAX pending)`)
        return
      }

      // Force injection only for programmatic navigation (no AJAX request)
      // This handles programmatic navigation via navigate_to_page where Tabulator doesn't
      // call ajaxRequestFunc (common in Streamlit iframe environments)
      const forceInject = this.pendingPageNavigation && this.preparedTableData.length > 0

      if (!forceInject && (tabulatorRows > 0 || this.preparedTableData.length === 0)) {
        console.log(`[TabulatorTable ${this.args.title}] injectServerSideData: early return (has data/no request)`)
        return
      }

      // Clear the navigation flag after injection
      if (this.pendingPageNavigation) {
        this.pendingPageNavigation = false
      }

      console.log(`[TabulatorTable ${this.args.title}] injectServerSideData: injecting data`)
      const tab = this.tabulator as any
      tab.rowManager.setData(this.preparedTableData, false, false)

      if (tab.modules?.page) {
        tab.modules.page.setMaxRows(paginationState.total_rows)
        tab.modules.page.setMaxPage(paginationState.total_pages)
      }

      tab.redraw(true)

      // Clear the loading overlay that setPage() shows when expecting AJAX response
      // In iframe environments, we manually inject data so we must clear the alert
      if (tab.clearAlert) {
        tab.clearAlert()
      }
    },

    selectPendingTargetRow(): void {
      const targetIndex = this.pendingTargetRowIndex
      this.pendingTargetRowIndex = null

      console.log(`[TabulatorTable ${this.args.title}] selectPendingTargetRow:`, {
        targetIndex,
        hasTabulator: !!this.tabulator,
        activeRowCount: this.tabulator?.getRows('active').length,
      })

      if (targetIndex === null || !this.tabulator) {
        console.log(`[TabulatorTable ${this.args.title}] selectPendingTargetRow: early return`)
        return
      }

      const rows = this.tabulator.getRows('active')
      console.log(`[TabulatorTable ${this.args.title}] selectPendingTargetRow: rows[${targetIndex}] exists:`, !!rows?.[targetIndex])

      if (rows && rows[targetIndex]) {
        this.tabulator.deselectRow()
        rows[targetIndex].select()
        rows[targetIndex].scrollTo(this.selectionScrollPosition, false).catch(() => {})
        console.log(`[TabulatorTable ${this.args.title}] selectPendingTargetRow: SUCCESS - selected row ${targetIndex}`)
      }
    },

    syncSelectionFromStore(): void {
      // Skip if we just manually selected a row (flag set in onRowClick)
      // This prevents redundant work since the visual selection is already done
      if (this.skipNextSync) {
        return
      }
      // The keys moved the highlight and the selection follows shortly: keep
      // the highlighted row rather than going back to the selected one
      if (this.keepKeyboardRow()) {
        return
      }

      // Sync table selection with selection store
      if (!this.tabulator) return

      const interactivity = this.args.interactivity || {}

      if (this.unhighlightedSelection) {
        const unchanged = Object.entries(this.unhighlightedSelection).every(
          ([identifier, value]) => this.selectionStore.$state[identifier] === value
        )
        if (unchanged) {
          this.tabulator.deselectRow()
          return
        }
        this.unhighlightedSelection = null
      }

      // For server-side pagination, Python handles navigation to the correct page
      // via the navigate_to_page hint. We only need to select the row if it's
      // on the current page.
      if (this.isServerSidePagination) {
        for (const [identifier, column] of Object.entries(interactivity)) {
          const selectedValue = this.selectionStore.$state[identifier]
          if (selectedValue !== undefined && selectedValue !== null) {
            // Check if the currently selected row already matches
            const currentlySelected = this.tabulator.getSelectedRows()[0]
            if (currentlySelected) {
              const currentData = currentlySelected.getData()
              if (currentData[column as string] === selectedValue) {
                return
              }
            }

            // Try to find and select the row on the current page
            const rowIndex = this.preparedTableData.findIndex(
              (row) => row[column as string] === selectedValue
            )
            if (rowIndex >= 0) {
              const indexField = this.args.tableIndexField || 'id'
              const rowId = this.preparedTableData[rowIndex][indexField]
              const row = this.tabulator.getRow(rowId)
              if (row) {
                this.tabulator.deselectRow()
                row.select()
                row.scrollTo(this.selectionScrollPosition, false).catch(() => {})
              }
            } else {
              // Store as pending - row may be on different page awaiting navigation
              this.pendingSelection = { [identifier]: selectedValue }
            }
            return
          }
        }
        this.highlightDefaultRow()
        return
      }

      // Client-side sync (for non-streaming tables)
      let anySelected = false
      for (const [identifier, column] of Object.entries(interactivity)) {
        const selectedValue = this.selectionStore.$state[identifier]
        if (selectedValue !== undefined && selectedValue !== null) {
          anySelected = true
          // Check if the currently selected row already matches
          const currentlySelected = this.tabulator.getSelectedRows()[0]
          if (currentlySelected) {
            const currentData = currentlySelected.getData()
            if (currentData[column as string] === selectedValue) {
              // Already selected the correct row, clear any pending selection
              this.pendingSelection = null
              return
            }
          }

          // Find and select the row with this value
          const rowIndex = this.preparedTableData.findIndex(
            (row) => row[column as string] === selectedValue
          )
          if (rowIndex >= 0) {
            const indexField = this.args.tableIndexField || 'id'
            const rowId = this.preparedTableData[rowIndex][indexField]
            // Use getRow(rowId) which works across all pages, not just current page
            const row = this.tabulator.getRow(rowId)
            if (row) {
              this.tabulator.deselectRow()
              row.select()
              // Use setPageToRow() for pagination (navigates to correct page), then scroll within page
              if (this.tabulator.options.pagination) {
                this.tabulator.setPageToRow(rowId as string | number).then(() => {
                  row.scrollTo(this.selectionScrollPosition, false).catch(() => {})
                }).catch(() => {})
              } else {
                row.scrollTo(this.selectionScrollPosition, false).catch(() => {})
              }
              // Successfully selected, clear any pending selection
              this.pendingSelection = null
            } else {
              // Row exists in data but not in tabulator yet - store as pending
              // This happens when data and selection change simultaneously
              this.pendingSelection = { [identifier]: selectedValue }
            }
          } else {
            // Row not found in current data - store as pending selection
            // This happens when selection changes before filtered data arrives
            this.pendingSelection = { [identifier]: selectedValue }
          }
          break
        }
      }
      if (!anySelected) this.highlightDefaultRow()
    },

    /** Nothing is selected: with highlightDefaultRow, mark the default row
     * without selecting it (the selection store is left as it is). */
    highlightDefaultRow(): void {
      if (!this.args.highlightDefaultRow || !this.tabulator) return
      const defaultRow = this.args.defaultRow ?? 0
      // In display order: after Tabulator's own sort
      const rows = this.tabulator.getRows('display')
      if (defaultRow < 0 || defaultRow >= rows.length) return
      if (this.tabulator.getSelectedRows()[0] === rows[defaultRow]) return
      this.tabulator.deselectRow()
      rows[defaultRow].select()
    },

    selectDefaultRow(): void {
      if (this.keepKeyboardRow()) {
        return
      }
      // Skip auto-selection during initial load for server-side pagination.
      // Wait for paginationState watcher to confirm data is ready.
      if (this.isServerSidePagination && !this.initialLoadComplete) {
        console.log(`[TabulatorTable ${this.args.title}] selectDefaultRow: SKIPPED (initial load not complete)`)
        return
      }

      // Skip auto-selection during user-initiated page navigation for server-side pagination
      // UNLESS Python sent a different page (meaning Python adjusted for selection tracking)
      if (this.isServerSidePagination && this.isNavigatingPages) {
        const pythonPage = this.paginationState?.page
        const requestedPage = this.lastRequestedPage
        // If Python sent the same page we requested, skip selection (user navigation)
        // If Python sent a different page, allow selection (Python tracking)
        if (pythonPage === requestedPage) {
          return
        }
      }

      const interactivity = this.args.interactivity || {}
      let selectedFromState = false

      // First, check for pending selection (from previous failed sync attempts)
      if (this.pendingSelection) {
        for (const [identifier, selectedValue] of Object.entries(this.pendingSelection)) {
          const column = interactivity[identifier]
          if (column && selectedValue !== undefined && selectedValue !== null) {
            const rowIndex = this.preparedTableData.findIndex(
              (row) => row[column as string] === selectedValue
            )
            if (rowIndex >= 0) {
              const indexField = this.args.tableIndexField || 'id'
              const rowId = this.preparedTableData[rowIndex][indexField]
              const rows = this.tabulator?.getRows() || []
              const row = rows.find(r => r.getData()[indexField] === rowId)
              if (row) {
                row.select()
                // Use setPageToRow() for pagination (navigates to correct page), then scroll within page
                if (this.tabulator?.options.pagination) {
                  this.tabulator.setPageToRow(rowId as string | number).then(() => {
                    row.scrollTo(this.selectionScrollPosition, false).catch(() => {})
                  }).catch(() => {})
                } else {
                  row.scrollTo(this.selectionScrollPosition, false).catch(() => {})
                }
                selectedFromState = true
                // Clear pending selection since we successfully applied it
                this.pendingSelection = null
                break
              }
            }
          }
        }
      }

      // Check current selection state - Python pre-computes initial selections,
      // so we only need to highlight the row (no store update needed)
      if (!selectedFromState) {
        for (const [identifier, column] of Object.entries(interactivity)) {
          const selectedValue = this.selectionStore.$state[identifier]
          if (selectedValue !== undefined && selectedValue !== null) {
            // Find the row with this value in the column
            const rowIndex = this.preparedTableData.findIndex(
              (row) => row[column as string] === selectedValue
            )
            if (rowIndex >= 0) {
              const indexField = this.args.tableIndexField || 'id'
              const rowId = this.preparedTableData[rowIndex][indexField]
              // Use getRows to avoid "Find Error" warnings during race conditions
              const rows = this.tabulator?.getRows() || []
              const row = rows.find(r => r.getData()[indexField] === rowId)
              if (row) {
                row.select()
                // Use setPageToRow() for pagination (navigates to correct page), then scroll within page
                if (this.tabulator?.options.pagination) {
                  this.tabulator.setPageToRow(rowId as string | number).then(() => {
                    row.scrollTo(this.selectionScrollPosition, false).catch(() => {})
                  }).catch(() => {})
                } else {
                  row.scrollTo(this.selectionScrollPosition, false).catch(() => {})
                }
                // KEY: Don't call updateSelection - Python already set it
                selectedFromState = true
                break
              }
            }
            // Count as selected even if row not on current page
            // Python handles page navigation via navigate_to_page
            selectedFromState = true
            break
          }
        }
      }

      // Python selects the default row (and sends the selection with the
      // data); without a selection only the highlight is left to do here
      if (!selectedFromState && !this.isServerSidePagination) {
        this.highlightDefaultRow()
      }
    },

    clearInvalidSelections(): void {
      // For server-side pagination, Python handles navigation to the correct page
      // when a selection doesn't exist on the current page, so we don't clear
      // selections here - they may be valid on a different page
      if (this.isServerSidePagination) {
        return
      }

      // Check if current selection values exist in the new data
      // If not, clear them from the selection store
      const interactivity = this.args.interactivity || {}

      for (const [identifier, column] of Object.entries(interactivity)) {
        const selectedValue = this.selectionStore.$state[identifier]

        // Skip if no selection
        if (selectedValue === undefined || selectedValue === null) {
          continue
        }

        // Check if selected value exists in current data
        const rowIndex = this.preparedTableData.findIndex(
          (row) => row[column as string] === selectedValue
        )

        if (rowIndex < 0) {
          // Selected value not found in new data - clear the selection
          this.selectionStore.updateSelection(identifier, null)
          // Clear any pending selection for this identifier as well
          if (this.pendingSelection && identifier in this.pendingSelection) {
            delete this.pendingSelection[identifier]
            if (Object.keys(this.pendingSelection).length === 0) {
              this.pendingSelection = null
            }
          }
        }
      }
    },

    onRowClick(row: any): void {
      // A click on a check box (multi_select) checks the row, nothing more
      if (this.checkboxClicked) {
        this.checkboxClicked = false
        return
      }
      // A click wins over a row the keys moved to and not yet selected
      this.cancelKeyboardSelection()
      // Get the row data directly from Tabulator's row object
      const rowData = row.getData()
      const rowIndex = row.getIndex()
      const interactivity = this.args.interactivity || {}

      // Clicking the highlighted row again only removes the highlight
      if (this.args.reclick === 'unhighlight' && row.isSelected()) {
        row.deselect()
        this.unhighlightedSelection = Object.fromEntries(
          Object.keys(interactivity).map((identifier) => [
            identifier,
            this.selectionStore.$state[identifier],
          ])
        )
        return
      }
      this.unhighlightedSelection = null

      // Clicking the selected row again clears its selections
      if (
        this.args.reclick === 'deselect' && rowData && Object.keys(interactivity).length > 0 &&
        Object.entries(interactivity).every(
          ([identifier, column]) => this.selectionStore.$state[identifier] === rowData[column as string]
        )
      ) {
        this.tabulator?.deselectRow()
        this.skipNextSync = true
        for (const identifier of Object.keys(interactivity)) {
          this.selectionStore.updateSelection(identifier, null)
        }
        this.$nextTick(() => {
          this.skipNextSync = false
        })
        return
      }

      // FIRST: Immediately select the row visually (before any async operations)
      // This ensures instant visual feedback regardless of Streamlit round-trip
      this.tabulator?.deselectRow()
      row.select()
      // A clicked row that is cut off is brought into view when the table
      // asks for a scroll position of its own
      if (this.args.scrollPosition) {
        row.scrollTo(this.args.scrollPosition, false).catch(() => {})
      }

      this.commitRowSelection(rowData, rowIndex)
    },

    /**
     * Select a row (already highlighted) as a click does: set the selections
     * of ``interactivity`` and ``on_select`` to it.
     */
    commitRowSelection(rowData: Record<string, unknown> | undefined, rowIndex: unknown): void {
      const interactivity = this.args.interactivity || {}
      this.$emit('rowSelected', rowIndex)

      // Set flag to skip the redundant syncSelectionFromStore call that will be
      // triggered by the selection store watcher when we update the store below.
      // The visual selection is already done - no need to redo it.
      this.skipNextSync = true

      // THEN: Update selection store (which triggers Streamlit.setComponentValue)
      // The visual selection is already done, so user sees instant feedback

      if (rowData) {
        // Side effects first, so a selection set by both on_select and
        // interactivity ends up with the clicked row's value
        const onSelect = this.args.onSelect || {}
        const selectionChanges = Object.entries(interactivity).some(
          ([identifier, column]) => this.selectionStore.$state[identifier] !== rowData[column as string]
        )
        if (selectionChanges) {
          for (const [identifier, value] of Object.entries(onSelect)) {
            if (!(identifier in interactivity) && this.selectionStore.$state[identifier] !== value) {
              this.selectionStore.updateSelection(identifier, value)
            }
          }
        }
        for (const [identifier, column] of Object.entries(interactivity)) {
          const value = rowData[column as string]
          this.selectionStore.updateSelection(identifier, value)
        }
      }

      // Clear flag after Vue's next tick (after watcher has fired)
      this.$nextTick(() => {
        this.skipNextSync = false
      })
    },

    /**
     * Arrow keys, Page Up/Down, Home and End step through the rows while the
     * rows have focus (a row was clicked, or the table tabbed to). Keys typed
     * in a field (search box, check box, editor) and keys with a modifier are
     * left alone. Handled in the capture phase so Tabulator's own Page Up/Down,
     * Home and End scrolling does not run as well.
     */
    onTableKeydown(event: KeyboardEvent): void {
      if (this.args.keyboardNavigation === false || !this.tabulator) return
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
      const move = KEY_MOVES[event.key]
      if (!move) return
      const holder = (this.tabulator as any).rowManager?.element as HTMLElement | undefined
      const target = event.target as HTMLElement | null
      if (!holder || !target || !holder.contains(target)) return
      if (target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"])')) return
      event.preventDefault()
      event.stopPropagation()
      this.stepSelection(move)
    },

    /** Rows that fit in the visible part of the table (Page Up/Down step). */
    visibleRowCount(rows: any[]): number {
      const holder = (this.tabulator as any)?.rowManager?.element as HTMLElement | undefined
      const sample = (this.tabulator?.getSelectedRows()[0] || rows[0]) as any
      const rowHeight = sample?.getElement?.()?.offsetHeight || 0
      if (!holder || rowHeight <= 0) return 10
      return Math.max(1, Math.floor(holder.clientHeight / rowHeight))
    },

    /**
     * Move the highlight one step. Positions count over every row passing the
     * filters, so with server-side pagination a step past the end of the page
     * goes on to the next page (fetched from Python) and Home/End reach the
     * first and last page.
     */
    stepSelection(move: KeyMove): void {
      if (!this.tabulator) return
      const rows = this.tabulator.getRows('active') as any[]
      const server = this.isServerSidePagination
      const state = this.paginationState
      const pageSize = server ? state?.page_size || this.args.pageSize || 100 : Math.max(rows.length, 1)
      const offset = server ? ((state?.page || 1) - 1) * pageSize : 0
      const total = server ? (state?.total_rows ?? rows.length) : rows.length
      if (total <= 0) return

      // While a page is on its way, keep counting from the position asked for
      let current: number | null = this.keyNavTarget
      if (current === null) {
        // By index: the row objects Tabulator hands out are not always the same
        const selected = this.tabulator.getSelectedRows()[0] as any
        const selectedId = selected ? selected.getIndex() : undefined
        const local = selected ? rows.findIndex((row) => row.getIndex() === selectedId) : -1
        current = local >= 0 ? offset + local : null
      }
      const pageStep = this.visibleRowCount(rows)
      let target: number
      if (move === 'home') target = 0
      else if (move === 'end') target = total - 1
      // Nothing highlighted yet: start at the first row on screen
      else if (current === null) target = offset
      else if (move === 'down') target = current + 1
      else if (move === 'up') target = current - 1
      else if (move === 'pageDown') target = current + pageStep
      else target = current - pageStep
      target = Math.max(0, Math.min(total - 1, target))
      this.moveKeyboardSelectionTo(target, rows, offset, pageSize)
    },

    /** Highlight the row at ``target`` (over all pages), fetching its page if need be. */
    moveKeyboardSelectionTo(target: number, rows: any[], offset: number, pageSize: number): void {
      const pageInFlight =
        this.keyNavRequestedPage !== null && Date.now() - this.keyNavRequestedAt < KEY_PAGE_TIMEOUT_MS
      if (pageInFlight) {
        // Decided when the page arrives
        this.keyNavTarget = target
        return
      }
      this.keyNavRequestedPage = null
      if (target >= offset && target < offset + rows.length) {
        this.keyNavTarget = null
        this.highlightKeyboardRow(rows[target - offset])
        return
      }
      if (!this.isServerSidePagination || !this.tabulator) return
      // On another page: ask Python for it and select the row once it is here.
      // The row selected so far stays selected until then.
      this.cancelKeyboardSelection()
      const page = Math.floor(target / pageSize) + 1
      this.keyNavTarget = target
      this.keyNavRequestedPage = page
      this.keyNavRequestedAt = Date.now()
      ;(this.tabulator as any).setPage(page).catch(() => {})
      this.scheduleKeyNavCheck()
    },

    /** Look for the page the keys asked for until it is here, asking again if it went astray. */
    scheduleKeyNavCheck(): void {
      if (this.keyNavCheckTimer) clearTimeout(this.keyNavCheckTimer)
      this.keyNavCheckTimer = setTimeout(() => {
        this.keyNavCheckTimer = null
        const page = this.keyNavRequestedPage
        if (page === null || !this.tabulator) return
        if (Date.now() - this.keyNavRequestedAt >= KEY_PAGE_TIMEOUT_MS) {
          this.keyNavRequestedPage = null
          this.keyNavTarget = null
          return
        }
        this.applyKeyNavTarget()
        if (this.keyNavRequestedPage === null) return
        if (this.paginationState?.page !== page) {
          if (!this.pendingDataRequest) {
            ;(this.tabulator as any).setPage(page).catch(() => {})
          } else if (this.args.paginationIdentifier) {
            // The request reached Python while it was busy and went unanswered:
            // send it again, for the request Tabulator is waiting on
            this.selectionStore.updateSelection(this.args.paginationIdentifier, {
              page,
              page_size: this.paginationState?.page_size || this.args.pageSize || 100,
              sort_column: this.requestedSortColumn || undefined,
              sort_dir: this.requestedSortDir,
              column_filters: this.currentColumnFilters,
              ...this.viewFiltersPatch,
            })
            this.pendingRequestCounter = this.selectionStore.$state.pagination_counter || 0
          }
        }
        this.scheduleKeyNavCheck()
      }, KEY_PAGE_CHECK_MS)
    },

    /** A page the keys asked for arrived: highlight the row they moved to. */
    applyKeyNavTarget(): void {
      if (this.keyNavRequestedPage === null || this.keyNavTarget === null || !this.tabulator) return
      const state = this.paginationState
      if (!state || state.page !== this.keyNavRequestedPage) return
      const rows = this.tabulator.getRows('active') as any[]
      const data = this.preparedTableData
      const indexField = this.args.tableIndexField || 'id'
      // Tabulator holds the rows Python sent for that page
      if (
        rows.length === 0 ||
        rows.length !== data.length ||
        rows[0].getData()[indexField] !== data[0][indexField]
      ) {
        return
      }
      const target = this.keyNavTarget
      const pageSize = state.page_size || this.args.pageSize || 100
      this.keyNavRequestedPage = null
      this.keyNavTarget = null
      this.moveKeyboardSelectionTo(target, rows, (state.page - 1) * pageSize, pageSize)
    },

    /** Highlight a row now and select it once the keys rest. */
    highlightKeyboardRow(row: any): void {
      if (!row || !this.tabulator) return
      this.unhighlightedSelection = null
      if (!row.isSelected()) {
        this.tabulator.deselectRow()
        row.select()
      }
      row.scrollTo('nearest', false).catch(() => {})
      this.keyboardRowId = row.getIndex()
      this.keyboardShownId = this.keyboardRowId
      if (this.keySelectTimer) clearTimeout(this.keySelectTimer)
      this.keySelectTimer = setTimeout(() => this.commitKeyboardRow(), KEY_SELECT_DELAY_MS)
    },

    /** The keys rested: select the highlighted row as a click would. */
    commitKeyboardRow(): void {
      this.keySelectTimer = null
      const id = this.keyboardRowId
      this.keyboardRowId = null
      if (id === null || id === undefined || !this.tabulator) return
      const row = this.tabulator.getRow(id as string | number) as any
      if (!row) return
      if (!row.isSelected()) {
        this.tabulator.deselectRow()
        row.select()
      }
      this.commitRowSelection(row.getData(), row.getIndex())
    },

    /** Forget a row the keys moved to and have not selected yet. */
    cancelKeyboardSelection(): void {
      if (this.keySelectTimer) clearTimeout(this.keySelectTimer)
      this.keySelectTimer = null
      this.keyboardRowId = null
      this.keyboardShownId = null
      this.keyNavTarget = null
      this.keyNavRequestedPage = null
    },

    /**
     * Loading a page again (as Tabulator does after a page change) scrolls it
     * back to the top: bring the row the keys moved to back into view.
     */
    keepKeyboardRowInView(): void {
      if (this.keyboardShownId === null || !this.tabulator) return
      const selected = this.tabulator.getSelectedRows()[0] as any
      if (!selected || selected.getIndex() !== this.keyboardShownId) {
        this.keyboardShownId = null
        return
      }
      selected.scrollTo('nearest', false).catch(() => {})
    },

    /**
     * While the keys are moving the highlight (its selection pending, or its
     * page on the way), the table keeps that highlight: true tells the caller
     * not to put the selection's own row back. Rows Tabulator loaded again
     * are highlighted again.
     */
    keepKeyboardRow(): boolean {
      if (this.keyNavRequestedPage !== null && Date.now() - this.keyNavRequestedAt < KEY_PAGE_TIMEOUT_MS) {
        return true
      }
      if (this.keySelectTimer === null || this.keyboardRowId === null || !this.tabulator) return false
      const row = this.tabulator.getRow(this.keyboardRowId as string | number) as any
      if (row && !row.isSelected()) {
        this.tabulator.deselectRow()
        row.select()
      }
      if (row) row.scrollTo('nearest', false).catch(() => {})
      return true
    },

    /**
     * Update table data without full rebuild.
     * Uses Tabulator's replaceData() to preserve scroll position, sorting, and user filters.
     * This is much faster than destroying and recreating the table.
     */
    updateTableData(): void {
      // New rows: the row the user unhighlighted is highlighted again
      this.unhighlightedSelection = null
      console.log('[TabulatorTable] updateTableData called', {
        hasTabulator: !!this.tabulator,
        isServerSidePagination: this.isServerSidePagination,
        paginationState: this.paginationState,
        isNavigatingPages: this.isNavigatingPages,
        dataLength: this.preparedTableData?.length,
      })

      if (!this.tabulator) {
        this.drawTable()
        return
      }

      // Store pagination state BEFORE replaceData (which resets Tabulator's internal page)
      // We capture these values now because by the time the async .then() callback runs,
      // the reactive paginationState may have changed to newer values
      const targetPage = this.paginationState?.page
      const capturedTotalRows = this.paginationState?.total_rows
      const capturedTotalPages = this.paginationState?.total_pages

      const tab = this.tabulator as any
      console.log('[TabulatorTable] Before replaceData - Tabulator internal state:', {
        hasPageModule: !!tab.modules?.page,
        maxPage: tab.modules?.page?.max,
        lastPage: tab.modules?.page?.lastPage,
        currentPage: tab.modules?.page?.page,
        size: tab.modules?.page?.size,
      })

      // replaceData silently replaces all data without updating scroll position, sort or filtering.
      // A table that resets its sort on new rows also starts them at the top (setData)
      const resetRows = this.args.resetSort && !this.isServerSidePagination
      const loaded = resetRows
        ? this.tabulator.setData(this.preparedTableData)
        : this.tabulator.replaceData(this.preparedTableData)
      loaded.then(() => {
        console.log('[TabulatorTable] After replaceData - Tabulator internal state:', {
          hasPageModule: !!tab.modules?.page,
          maxPage: tab.modules?.page?.max,
          lastPage: tab.modules?.page?.lastPage,
          currentPage: tab.modules?.page?.page,
        })

        // Clear loading overlay if we were navigating programmatically via navigate_to_page
        // setPage() shows loading, but replaceData() doesn't clear it
        if (this.pendingPageNavigation && (this.tabulator as any).clearAlert) {
          ;(this.tabulator as any).clearAlert()
          this.pendingPageNavigation = false
          // Select the target row after programmatic navigation
          this.$nextTick(() => {
            this.selectPendingTargetRow()
          })
        }

        // Only re-apply filters if NOT navigating pages
        // During page navigation, filter state is already correct - calling applyFilters()
        // would incorrectly reset the page to 1 (server-side pagination always resets page)
        if (!this.isNavigatingPages) {
          this.applyFilters()
        }

        // Update pagination limits when data changes (filter applied, data refreshed)
        // This ensures the page count shown matches the actual filtered data from Python
        // Use captured values (from before replaceData) to avoid stale closure issues
        if (
          this.isServerSidePagination &&
          capturedTotalRows !== undefined &&
          capturedTotalPages !== undefined
        ) {
          if (tab.modules?.page) {
            try {
              // Use captured primitive values to avoid Vue Proxy and stale closure issues
              const totalRows = Number(capturedTotalRows)
              const totalPages = Number(capturedTotalPages)

              console.log('[TabulatorTable] Calling setMaxRows and setMaxPage', {
                totalRows,
                totalPages,
              })
              tab.modules.page.setMaxRows(totalRows)
              tab.modules.page.setMaxPage(totalPages)
              console.log('[TabulatorTable] After setMaxRows/setMaxPage:', {
                maxPage: tab.modules?.page?.max,
              })
              // Force redraw to update the pagination UI
              tab.redraw(true)
              // Trigger setPage to refresh pagination counter (Showing X of Y rows)
              // setMaxRows/setMaxPage update internal state but don't trigger _setPageCounter()
              tab.setPage(targetPage || tab.getPage() || 1).catch(() => {})
            } catch (error) {
              console.error('[TabulatorTable] Error setting pagination limits:', error)
            }
          }
        }

        // CRITICAL FIX: Always set the page after replaceData() for server-side pagination
        // This triggers a second AJAX cycle that properly completes Tabulator's internal state.
        // Even for page 1, this is necessary because replaceData() + the initial AJAX resolution
        // leaves Tabulator in an inconsistent state without this explicit setPage() call.
        if (this.isServerSidePagination && targetPage && this.isNavigatingPages) {
          ;(this.tabulator as any).setPage(targetPage).catch(() => {})
        }

        // New rows start in the initial order again when the table asks so
        if (this.args.resetSort && !this.isServerSidePagination) {
          ;(this.tabulator as any)?.setSort(this.args.initialSort || [])
        }

        // Only sync selection if not navigating pages
        if (!this.isNavigatingPages) {
          this.selectDefaultRow()
        }
        // Clear navigation flag after data update cycle completes
        this.isNavigatingPages = false

        // Update Streamlit frame height - use specified height if provided
        this.$nextTick(() => {
          if (this.args.height && this.isServerSidePagination) {
            Streamlit.setFrameHeight(this.args.height)
          } else if (!this.isServerSidePagination) {
            // The table's own height: while Tabulator lays out new rows, the
            // document is briefly taller than the table
            Streamlit.setFrameHeight((this.$el as HTMLElement).offsetHeight)
          } else {
            Streamlit.setFrameHeight()
          }
        })
      })
    },

    isColumnVisible(field: string): boolean {
      if (field in this.columnVisibility) return this.columnVisibility[field]
      return !this.defaultHiddenColumns.has(field)
    },
    setColumnVisible(field: string, visible: boolean): void {
      this.columnVisibility = { ...this.columnVisibility, [field]: visible }
      this.applyColumnVisibility()
      this.saveColumnVisibility()
    },
    resetColumnVisibility(): void {
      this.columnVisibility = {}
      this.applyColumnVisibility()
      this.saveColumnVisibility()
    },
    applyColumnVisibility(): void {
      if (!this.tabulator) return
      for (const col of this.columnNames) {
        const column = this.tabulator.getColumn(col.field)
        if (!column) continue
        if (this.isColumnVisible(col.field)) {
          column.show()
        } else {
          column.hide()
        }
      }
    },
    loadColumnVisibility(): void {
      try {
        const stored = window.localStorage.getItem(this.columnVisibilityKey)
        const parsed = stored ? JSON.parse(stored) : {}
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          this.columnVisibility = Object.fromEntries(
            Object.entries(parsed).filter(([, v]) => typeof v === 'boolean')
          ) as Record<string, boolean>
        }
      } catch {
        // Storage can be unavailable (private window, blocked site data)
      }
    },
    saveColumnVisibility(): void {
      try {
        if (Object.keys(this.columnVisibility).length === 0) {
          window.localStorage.removeItem(this.columnVisibilityKey)
        } else {
          window.localStorage.setItem(this.columnVisibilityKey, JSON.stringify(this.columnVisibility))
        }
      } catch {
        // Storage can be unavailable (private window, blocked site data)
      }
    },
    downloadTable(): void {
      // A server-side paginated table only holds the current page, and only the
      // displayed columns, so ask Python for the whole filtered, sorted table.
      const paginationIdentifier = this.args.paginationIdentifier as string | undefined
      if (this.isServerSidePagination && paginationIdentifier) {
        const requestId = Date.now()
        this.pendingDownloadId = requestId
        this.selectionStore.updateSelection(paginationIdentifier, {
          page: this.paginationState?.page || 1,
          page_size: this.paginationState?.page_size || this.args.pageSize || 100,
          sort_column: this.requestedSortColumn || undefined,
          sort_dir: this.requestedSortDir,
          column_filters: this.currentColumnFilters,
              ...this.viewFiltersPatch,
          download_request: requestId,
        })
        return
      }
      if (this.tabulator) {
        this.tabulator.download('csv', `${this.args.title || 'table'}.csv`)
      }
    },

    // Filter methods
    openFilterDialog(): void {
      if (this.canUseTeleport()) {
        this.openTeleportDialog()
      }
    },

    toggleColumnSelection(columnField: string): void {
      const index = this.selectedColumns.indexOf(columnField)
      if (index > -1) {
        this.selectedColumns.splice(index, 1)
        this.cleanupFilterForColumn(columnField)
      } else {
        this.selectedColumns.push(columnField)
        this.$nextTick(() => {
          this.initializeFilterValue(columnField)
        })
      }
    },

    analyzeColumn(
      columnField: string
    ): {
      uniqueValues: (string | number)[]
      minValue?: number
      maxValue?: number
      dataType: 'categorical' | 'numeric' | 'text'
    } {
      if (this.columnAnalysis[columnField]) {
        return this.columnAnalysis[columnField]
      }

      // For server-side pagination, use precomputed column metadata from Python
      if (this.isServerSidePagination && this.serverColumnMetadata[columnField]) {
        const meta = this.serverColumnMetadata[columnField]
        const analysis = {
          uniqueValues: (meta.unique_values || []).map((v) =>
            typeof v === 'string' || typeof v === 'number' ? v : String(v)
          ) as (string | number)[],
          minValue: meta.min,
          maxValue: meta.max,
          // A threshold, however few values the column has
          dataType: this.numericFilterConfig[columnField] ? ('numeric' as const) : meta.type,
        }
        this.columnAnalysis[columnField] = analysis
        this.filterTypes[columnField] = analysis.dataType
        return analysis
      }

      // Fallback to client-side analysis (for non-streaming tables)
      const column = (this.args.columnDefinitions || []).find((col) => col.field === columnField)
      const values = this.preparedTableData
        .map((row) => row[columnField])
        .filter((v) => v != null && v !== '')

      const uniqueValues = [...new Set(values)]
      const sorter = column?.sorter

      let dataType: 'categorical' | 'numeric' | 'text'
      let minValue: number | undefined
      let maxValue: number | undefined

      if (sorter === 'number') {
        const numericValues = values.filter(
          (v) => typeof v === 'number' || !isNaN(Number(v))
        )
        if (numericValues.length > 0) {
          const numbers = numericValues.map((v) => Number(v))
          minValue = Math.min(...numbers)
          maxValue = Math.max(...numbers)
          dataType = uniqueValues.length <= 10 ? 'categorical' : 'numeric'
        } else {
          dataType = 'text'
        }
      } else {
        dataType = uniqueValues.length <= 50 ? 'categorical' : 'text'
      }
      if (this.numericFilterConfig[columnField]) {
        dataType = 'numeric'
      }

      const analysis = {
        uniqueValues: uniqueValues.slice(0, 100).map((v) =>
          typeof v === 'string' || typeof v === 'number' ? v : String(v)
        ) as (string | number)[],
        minValue,
        maxValue,
        dataType,
      }

      this.columnAnalysis[columnField] = analysis
      this.filterTypes[columnField] = dataType

      return analysis
    },

    getFilterType(columnField: string): 'categorical' | 'numeric' | 'text' {
      if (!this.filterTypes[columnField]) {
        this.analyzeColumn(columnField)
      }
      return this.filterTypes[columnField]
    },

    getUniqueValues(columnField: string): string[] {
      const analysis = this.analyzeColumn(columnField)
      return analysis.uniqueValues.map((v) => String(v)).sort()
    },

    getMinValue(columnField: string): number {
      const analysis = this.analyzeColumn(columnField)
      return analysis.minValue ?? 0
    },

    getMaxValue(columnField: string): number {
      const analysis = this.analyzeColumn(columnField)
      return analysis.maxValue ?? 100
    },

    initializeFilterValue(columnField: string): void {
      if (!this.filterValues[columnField]) {
        const filterType = this.getFilterType(columnField)
        const newFilterValue: FilterValue = {}

        switch (filterType) {
          case 'categorical':
            newFilterValue.categorical = []
            break
          case 'numeric':
            // Open until the viewer sets a bound
            newFilterValue.numeric = {
              op: this.numericFilterConfig[columnField]?.op || 'between',
              min: null,
              max: null,
            }
            break
          case 'text':
            newFilterValue.text = ''
            break
        }

        this.filterValues[columnField] = newFilterValue
      }
    },

    applyFilters(): void {
      if (!this.tabulator) return

      // For server-side pagination, build filter array and send to Python
      if (this.isServerSidePagination) {
        const serverFilters: Array<{ field: string; type: string; value: unknown }> = []

        this.selectedColumns.forEach((columnField) => {
          const filterValue = this.filterValues[columnField]
          const filterType = this.filterTypes[columnField]

          if (!filterValue) return

          switch (filterType) {
            case 'categorical':
              if (filterValue.categorical?.length) {
                const column = (this.args.columnDefinitions || []).find(
                  (col) => col.field === columnField
                )
                const isNumericColumn = column?.sorter === 'number'
                const values = isNumericColumn
                  ? filterValue.categorical.map((v) => {
                      const num = Number(v)
                      return isNaN(num) ? v : num
                    })
                  : filterValue.categorical
                serverFilters.push({ field: columnField, type: 'in', value: values })
              }
              break
            case 'numeric':
              for (const bound of this.numericBounds(columnField)) {
                serverFilters.push({ field: columnField, type: bound.type, value: bound.value })
              }
              break
            case 'text':
              if (filterValue.text) {
                serverFilters.push({ field: columnField, type: 'regex', value: filterValue.text })
              }
              break
          }
        })

        // Store filters and request page 1 of the re-filtered rows
        this.currentColumnFilters = serverFilters
        this.requestFilteredRows()
        return
      }

      // Client-side filtering (for non-streaming tables)
      this.tabulator.clearFilter(true)

      this.selectedColumns.forEach((columnField) => {
        const filterValue = this.filterValues[columnField]
        const filterType = this.filterTypes[columnField]

        if (!filterValue) return

        switch (filterType) {
          case 'categorical':
            if (filterValue.categorical?.length) {
              const column = (this.args.columnDefinitions || []).find(
                (col) => col.field === columnField
              )
              const isNumericColumn = column?.sorter === 'number'

              const filterValues = isNumericColumn
                ? filterValue.categorical.map((v) => {
                    const num = Number(v)
                    return isNaN(num) ? v : num
                  })
                : filterValue.categorical

              this.tabulator?.addFilter(columnField, 'in', filterValues)
            }
            break
          case 'numeric':
            for (const bound of this.numericBounds(columnField)) {
              this.tabulator?.addFilter(columnField, bound.type, bound.value)
            }
            break
          case 'text':
            if (filterValue.text) {
              this.tabulator?.addFilter(columnField, 'regex', filterValue.text)
            }
            break
        }
      })
    },

    cleanupFilterForColumn(columnField: string): void {
      delete this.filterValues[columnField]
      delete this.filterTypes[columnField]
      delete this.columnAnalysis[columnField]
      this.applyFilters()
    },

    // multi_select: a check box per row, and one in the header for all rows
    multiSelectColumns(): ColumnDefinition[] {
      if (!this.multiSelectEnabled) return []
      return [{
        title: '',
        field: '__multi_select',
        visible: this.checkboxesShown,
        headerSort: false,
        resizable: false,
        width: 36,
        minWidth: 36,
        hozAlign: 'center',
        headerHozAlign: 'center',
        download: false,
        responsive: 0,
        headerTooltip: false,
        tooltip: 'Add to the selection (Shift: a range)',
        formatter: (cell: CellComponent) => this.checkboxHtml(this.isRowChecked(cell.getRow().getData() as Record<string, unknown>)),
        titleFormatter: () => `<span class="multi-select-header" title="Select every row (all pages, filters applied)">${this.checkboxHtml(false)}</span>`,
        headerClick: () => {
          this.toggleAllRows()
        },
        cellClick: (event: UIEvent, cell: CellComponent) => {
          this.checkboxClicked = true
          // rowClick fires after cellClick; reset the flag if it does not
          setTimeout(() => { this.checkboxClicked = false }, 0)
          this.toggleRow(cell, (event as MouseEvent).shiftKey)
        },
      } as unknown as ColumnDefinition]
    },

    toggleCheckboxes(): void {
      this.checkboxesShown = !this.checkboxesShown
      const column = this.tabulator?.getColumn('__multi_select')
      if (column) {
        if (this.checkboxesShown) column.show()
        else column.hide()
      }
      this.refreshCheckboxes()
    },

    checkboxHtml(checked: boolean | 'some'): string {
      const state = checked === 'some' ? ' some' : checked ? ' checked' : ''
      const mark = checked === 'some' ? 'mdi-minus' : 'mdi-check'
      return `<span class="multi-select-box${state}" role="checkbox" aria-checked="${checked === 'some' ? 'mixed' : !!checked}"><i class="mdi ${mark}"></i></span>`
    },

    isRowChecked(row: Record<string, unknown>): boolean {
      for (const [identifier, column] of Object.entries(this.args.multiSelect || {})) {
        const set = this.selectionStore.$state[identifier]
        if (Array.isArray(set) && row[column] !== undefined && set.includes(row[column])) return true
      }
      return false
    },

    applyCheckedRows(rows: Record<string, unknown>[], mode: 'add' | 'remove'): void {
      for (const [identifier, column] of Object.entries(this.args.multiSelect || {})) {
        const current = this.selectionStore.$state[identifier] ?? null
        const next = combineSelection(current, rows.map((r) => r[column]), mode)
        if (JSON.stringify(current) !== JSON.stringify(next)) {
          this.selectionStore.updateSelection(identifier, next)
        }
      }
    },

    toggleRow(cell: CellComponent, shift: boolean): void {
      const row = cell.getRow()
      const data = row.getData() as Record<string, unknown>
      const mode = this.isRowChecked(data) ? 'remove' : 'add'
      const active = this.tabulator ? this.tabulator.getRows('active') : []
      const position = active.findIndex((r) => r.getIndex() === row.getIndex())
      let rows = [data]
      if (shift && this.lastCheckedPosition !== null && position >= 0) {
        const from = Math.min(this.lastCheckedPosition, position)
        const to = Math.max(this.lastCheckedPosition, position)
        rows = active.slice(from, to + 1).map((r) => r.getData() as Record<string, unknown>)
      }
      if (position >= 0) this.lastCheckedPosition = position
      this.applyCheckedRows(rows, mode)
    },

    /** Header box: every row passing the filters, or none of them. */
    toggleAllRows(): void {
      if (!this.tabulator) return
      const active = this.tabulator.getRows('active').map((r) => r.getData() as Record<string, unknown>)
      const allChecked = active.length > 0 && active.every((row) => this.isRowChecked(row))
      const mode = allChecked ? 'remove' : 'add'
      if (this.isServerSidePagination) {
        // Only one page is here: Python selects the rows of every page
        this.streamlitDataStore.sendEvent({ type: 'multi_select_all', mode })
      } else {
        this.applyCheckedRows(active, mode)
      }
    },

    /** Redraw the check boxes after the checked rows changed. */
    refreshCheckboxes(): void {
      if (!this.tabulator || !this.isTableBuilt || !this.multiSelectEnabled) return
      const rows = this.tabulator.getRows('active')
      let checked = 0
      for (const row of rows) {
        const data = row.getData() as Record<string, unknown>
        const isChecked = this.isRowChecked(data)
        if (isChecked) checked += 1
        // Selected rows are marked whether or not the check boxes are shown
        row.getElement().classList.toggle('multi-selected', isChecked)
        const cell = (row as unknown as { getCell: (f: string) => { getElement: () => HTMLElement } | false }).getCell('__multi_select')
        if (cell) {
          const element = cell.getElement()
          const html = this.checkboxHtml(isChecked)
          if (element.innerHTML !== html) element.innerHTML = html
        }
      }
      const header = document.querySelector(`#${this.id} .multi-select-header`)
      if (header) {
        const state = checked === 0 ? false : checked === rows.length ? true : 'some'
        header.innerHTML = this.checkboxHtml(state)
      }
    },

    // Row overview: a button per row that shows every column of that row
    rowOverviewColumns(): ColumnDefinition[] {
      if (!this.args.rowOverview) return []
      return [{
        title: '',
        field: '__row_overview',
        headerSort: false,
        resizable: false,
        width: 36,
        minWidth: 36,
        hozAlign: 'center',
        download: false,
        // Never folded away by the collapsed layout
        responsive: 0,
        headerTooltip: false,
        tooltip: 'Show the whole row',
        formatter: () => '<i class="mdi mdi-text-box-search-outline row-overview-button" aria-label="Show the whole row"></i>',
        cellClick: (_event: UIEvent, cell: CellComponent) => {
          this.openRowOverview(cell.getRow().getData() as Record<string, unknown>)
        },
      } as unknown as ColumnDefinition]
    },

    rowOverviewValue(col: Record<string, any>, value: unknown): string {
      const placeholders = (col.formatterParams && col.formatterParams.placeholders) || {}
      if (value !== null && value !== undefined && String(value) in placeholders) {
        return String(placeholders[String(value)])
      }
      if (value === null || value === undefined || value === '') return '-'
      if (typeof value === 'number') {
        if (Number.isNaN(value)) return '-'
        const precision = col.formatterParams && col.formatterParams.precision
        if (typeof precision === 'number' && !Number.isInteger(value)) return value.toFixed(precision)
        return Number.isInteger(value) ? String(value) : String(Math.round(value * 1e4) / 1e4)
      }
      if (typeof value === 'boolean') return value ? 'yes' : 'no'
      if (Array.isArray(value)) return value.map((v) => (v === null ? '-' : String(v))).join(', ')
      return String(value)
    },

    // Title of the overview: rowOverviewTitle with {field} replaced by the row's values
    rowOverviewTitle(row: Record<string, unknown>): string {
      const template = this.args.rowOverviewTitle
      if (!template) return 'Row details'
      const columns = (this.args.columnDefinitions || []) as Record<string, any>[]
      return template.replace(/\{([^{}]+)\}/g, (_match: string, field: string) => {
        const col = columns.find((c) => c.field === field) || {}
        return this.rowOverviewValue(col, row[field])
      })
    },

    openRowOverview(row: Record<string, unknown>): void {
      if (!this.parentDocument) this.initializeTeleport()
      if (!this.parentDocument || this.teleportBackdrop) return
      const doc = this.parentDocument
      const dark = this.streamlitDataStore.theme?.base === 'dark'
      const colors = dark
        ? { bg: '#262730', fg: '#fafafa', muted: '#a3a8b8', line: '#3d3f4b' }
        : { bg: '#ffffff', fg: '#31333f', muted: '#6b6f80', line: '#e6e7eb' }

      this.createTeleportBackdrop()
      this.createTeleportContainer()
      const container = this.teleportContainer as HTMLElement
      container.style.background = colors.bg
      container.style.color = colors.fg
      container.style.width = '640px'

      const header = doc.createElement('div')
      header.style.cssText = `display: flex; justify-content: space-between; align-items: center;
        padding: 14px 20px; border-bottom: 1px solid ${colors.line};`
      const title = doc.createElement('span')
      title.textContent = this.rowOverviewTitle(row)
      title.style.cssText = 'font-size: 18px; font-weight: 600;'
      const close = doc.createElement('button')
      close.textContent = '×'
      close.setAttribute('aria-label', 'Close')
      close.style.cssText = `background: none; border: none; font-size: 24px; cursor: pointer;
        color: ${colors.muted}; padding: 0 6px;`
      header.append(title, close)

      const body = doc.createElement('div')
      body.style.cssText = 'overflow: auto; padding: 8px 20px 16px;'
      const table = doc.createElement('table')
      table.style.cssText = 'width: 100%; border-collapse: collapse; font-size: 14px;'
      for (const col of (this.args.columnDefinitions || []) as Record<string, any>[]) {
        if (!col.field) continue
        const tr = doc.createElement('tr')
        tr.style.borderBottom = `1px solid ${colors.line}`
        const name = doc.createElement('th')
        name.textContent = String(col.title || col.field)
        name.style.cssText = `text-align: left; font-weight: 500; color: ${colors.muted};
          padding: 6px 16px 6px 0; vertical-align: top; white-space: nowrap;`
        const value = doc.createElement('td')
        value.textContent = this.rowOverviewValue(col, row[col.field])
        value.style.cssText = 'padding: 6px 0; word-break: break-word;'
        tr.append(name, value)
        table.appendChild(tr)
      }
      body.appendChild(table)
      container.append(header, body)

      // Close on the button, a click outside or Escape; each way removes the
      // Escape listeners so they cannot close a later dialog. Escape is heard
      // on the page and in this component's frame, which keeps the focus
      // after the row button is clicked.
      const docs = doc === document ? [doc] : [doc, document]
      const unlisten = () => docs.forEach((d) => d.removeEventListener('keydown', onKey))
      const closeOverview = () => {
        unlisten()
        this.closeTeleportDialog()
      }
      const onKey = (event: KeyboardEvent) => {
        if (event.key === 'Escape') closeOverview()
      }
      close.addEventListener('click', closeOverview)
      const backdrop = this.teleportBackdrop as HTMLElement | null
      backdrop?.addEventListener('click', (event: MouseEvent) => {
        if (event.target === backdrop) unlisten()
      })
      docs.forEach((d) => d.addEventListener('keydown', onKey))
    },

    // Teleport functionality for filter dialog
    canUseTeleport(): boolean {
      try {
        return !!(window.parent && window.parent.document && window.parent !== window)
      } catch {
        return false
      }
    },

    initializeTeleport(): void {
      if (this.canUseTeleport()) {
        this.parentDocument = window.parent.document
      }
    },

    openTeleportDialog(): void {
      if (!this.parentDocument || this.teleportDialog) return

      this.teleportDialog = true
      this.createTeleportBackdrop()
      this.createTeleportContainer()
      this.renderFilterDialog()
    },

    createTeleportBackdrop(): void {
      if (!this.parentDocument) return

      this.teleportBackdrop = this.parentDocument.createElement('div')
      this.teleportBackdrop.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background-color: rgba(0, 0, 0, 0.5);
        z-index: 9999;
        display: flex;
        align-items: center;
        justify-content: center;
      `

      this.teleportBackdrop.addEventListener('click', (e) => {
        if (e.target === this.teleportBackdrop) {
          this.closeTeleportDialog()
        }
      })

      this.parentDocument.body.appendChild(this.teleportBackdrop)
    },

    createTeleportContainer(): void {
      if (!this.parentDocument || !this.teleportBackdrop) return

      this.teleportContainer = this.parentDocument.createElement('div')
      this.teleportContainer.style.cssText = `
        background: white;
        border-radius: 8px;
        max-width: 90vw;
        max-height: 90vh;
        width: 800px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
        display: flex;
        flex-direction: column;
        overflow: hidden;
      `

      this.teleportBackdrop.appendChild(this.teleportContainer)
    },

    renderFilterDialog(): void {
      if (!this.teleportContainer || !this.parentDocument) return

      // Header
      const header = this.parentDocument.createElement('div')
      header.style.cssText = `
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 16px 24px;
        border-bottom: 1px solid #e0e0e0;
        background: white;
      `

      const title = this.parentDocument.createElement('span')
      title.textContent = 'Filter Options'
      title.style.cssText = 'font-size: 20px; font-weight: 500; color: #333;'

      const closeBtn = this.parentDocument.createElement('button')
      closeBtn.innerHTML = '×'
      closeBtn.style.cssText = `
        background: none;
        border: none;
        font-size: 24px;
        cursor: pointer;
        color: #666;
        padding: 4px 8px;
        border-radius: 4px;
      `
      closeBtn.addEventListener('click', () => this.closeTeleportDialog())
      closeBtn.addEventListener('mouseenter', () => {
        closeBtn.style.backgroundColor = '#f5f5f5'
      })
      closeBtn.addEventListener('mouseleave', () => {
        closeBtn.style.backgroundColor = 'transparent'
      })

      header.appendChild(title)
      header.appendChild(closeBtn)

      // Content
      const content = this.parentDocument.createElement('div')
      content.style.cssText = `
        padding: 24px;
        overflow-y: auto;
        flex: 1;
        min-height: 0;
      `

      // A table with suggested thresholds opens on them; the column choice follows
      if (Object.keys(this.numericFilterConfig).length > 0) {
        this.renderFilterControls(content)
        this.renderColumnSelection(content)
      } else {
        this.renderColumnSelection(content)
        this.renderFilterControls(content)
      }

      // Footer
      const footer = this.parentDocument.createElement('div')
      footer.style.cssText = `
        padding: 16px 24px;
        border-top: 1px solid #e0e0e0;
        display: flex;
        justify-content: flex-end;
        background: white;
      `

      const closeFooterBtn = this.parentDocument.createElement('button')
      closeFooterBtn.textContent = 'Close'
      closeFooterBtn.style.cssText = `
        background: ${this.accentColor};
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
      `
      closeFooterBtn.addEventListener('click', () => this.closeTeleportDialog())
      closeFooterBtn.addEventListener('mouseenter', () => {
        closeFooterBtn.style.backgroundColor = this.accentHover
      })
      closeFooterBtn.addEventListener('mouseleave', () => {
        closeFooterBtn.style.backgroundColor = this.accentColor
      })

      footer.appendChild(closeFooterBtn)

      this.teleportContainer.appendChild(header)
      this.teleportContainer.appendChild(content)
      this.teleportContainer.appendChild(footer)
    },

    renderColumnSelection(content: HTMLElement): void {
      if (!this.parentDocument) return

      const columnSection = this.parentDocument.createElement('div')
      columnSection.style.cssText = `
        background-color: white;
        border-radius: 4px;
        border: 1px solid #e0e0e0;
        padding: 16px;
        margin-bottom: 24px;
      `

      const columnTitle = this.parentDocument.createElement('h6')
      columnTitle.textContent = 'Select Columns:'
      columnTitle.style.cssText =
        'color: #333; margin: 0 0 12px 0; font-size: 16px; font-weight: 500;'

      const chipsContainer = this.parentDocument.createElement('div')
      chipsContainer.style.cssText = 'display: flex; flex-wrap: wrap; gap: 8px;'

      this.columnNames.forEach((column) => {
        if (!this.parentDocument) return
        const chip = this.parentDocument.createElement('div')
        const isSelected = this.selectedColumns.includes(column.field)

        chip.textContent = column.title
        chip.style.cssText = `
          padding: 6px 12px;
          border-radius: 16px;
          font-size: 14px;
          cursor: pointer;
          user-select: none;
          transition: all 0.2s;
          ${
            isSelected
              ? `background: ${this.accentColor}; color: white; border: 1px solid ${this.accentColor};`
              : 'background: white; color: #333; border: 1px solid #e0e0e0;'
          }
        `

        chip.addEventListener('click', () => {
          this.toggleColumnSelection(column.field)
          this.refreshTeleportDialog()
        })
        chip.addEventListener('mouseenter', () => {
          if (!isSelected) chip.style.backgroundColor = '#f5f5f5'
        })
        chip.addEventListener('mouseleave', () => {
          if (!isSelected) chip.style.backgroundColor = 'white'
        })

        chipsContainer.appendChild(chip)
      })

      const actionsContainer = this.parentDocument.createElement('div')
      actionsContainer.style.cssText = `
        margin-top: 16px;
        padding-top: 16px;
        border-top: 1px solid #e0e0e0;
        display: flex;
        justify-content: space-between;
        align-items: center;
      `

      const selectionInfo = this.parentDocument.createElement('span')
      selectionInfo.textContent = `${this.selectedColumns.length} of ${this.columnNames.length} columns selected`
      selectionInfo.style.cssText = 'color: #666; font-size: 14px;'

      const buttonsDiv = this.parentDocument.createElement('div')
      buttonsDiv.appendChild(
        this.createActionButton('Select All', () => {
          this.selectAllColumns()
          this.refreshTeleportDialog()
        })
      )
      buttonsDiv.appendChild(
        this.createActionButton('Clear All', () => {
          this.clearColumnSelection()
          this.refreshTeleportDialog()
        })
      )

      actionsContainer.appendChild(selectionInfo)
      actionsContainer.appendChild(buttonsDiv)

      columnSection.appendChild(columnTitle)
      columnSection.appendChild(chipsContainer)
      columnSection.appendChild(actionsContainer)
      content.appendChild(columnSection)
    },

    createActionButton(text: string, onClick: () => void): HTMLElement {
      const btn = this.parentDocument!.createElement('button')
      btn.textContent = text
      btn.style.cssText = `
        background: white;
        color: ${this.accentColor};
        border: 1px solid ${this.accentColor};
        padding: 6px 12px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
        margin-left: 8px;
      `
      btn.addEventListener('click', onClick)
      btn.addEventListener('mouseenter', () => {
        btn.style.backgroundColor = '#f5f5f5'
      })
      btn.addEventListener('mouseleave', () => {
        btn.style.backgroundColor = 'white'
      })
      return btn
    },

    selectAllColumns(): void {
      this.selectedColumns = this.columnNames.map((column) => column.field)
    },

    clearColumnSelection(): void {
      this.selectedColumns = []
      this.filterValues = {}
      this.filterTypes = {}
      this.columnAnalysis = {}
      this.applyFilters()
    },

    renderFilterControls(content: HTMLElement): void {
      if (this.selectedColumns.length === 0 || !this.parentDocument) return

      const filterSection = this.parentDocument.createElement('div')
      filterSection.style.cssText = 'margin-bottom: 24px;'

      const filterTitle = this.parentDocument.createElement('h6')
      filterTitle.textContent = 'Filter Settings:'
      filterTitle.style.cssText =
        'color: #333; margin: 0 0 16px 0; font-size: 16px; font-weight: 500;'

      const filterContainer = this.parentDocument.createElement('div')
      filterContainer.style.cssText = `
        display: flex;
        flex-direction: column;
        gap: 16px;
        background-color: #f9f9f9;
        border-radius: 4px;
        padding: 16px;
      `

      this.columnNames.forEach((column) => {
        if (this.selectedColumns.includes(column.field)) {
          const filterItem = this.createFilterItem(column.field)
          filterContainer.appendChild(filterItem)
        }
      })

      filterSection.appendChild(filterTitle)
      filterSection.appendChild(filterContainer)
      content.appendChild(filterSection)
    },

    createFilterItem(columnField: string): HTMLElement {
      if (!this.parentDocument) {
        throw new Error('Parent document not available')
      }

      const filterItem = this.parentDocument.createElement('div')
      filterItem.style.cssText = `
        display: flex;
        flex-direction: column;
        gap: 8px;
        padding: 12px;
        background-color: white;
        border-radius: 4px;
        border: 1px solid #e0e0e0;
      `

      const label = this.parentDocument.createElement('label')
      label.style.cssText = 'font-weight: 500; font-size: 14px; color: #555;'

      const column = (this.args.columnDefinitions || []).find((col) => col.field === columnField)
      const title = (column?.title as string) || columnField
      const type = this.getFilterType(columnField)
      label.innerHTML = `${title} <span style="font-size: 12px; color: #888; font-weight: normal;">(${type})</span>`

      filterItem.appendChild(label)

      if (type === 'categorical') {
        const select = this.createCategoricalFilter(columnField)
        filterItem.appendChild(select)
      } else if (type === 'numeric') {
        const numericFilter = this.createNumericFilter(columnField)
        filterItem.appendChild(numericFilter)
      } else {
        const textFilter = this.createTextFilter(columnField)
        filterItem.appendChild(textFilter)
      }

      return filterItem
    },

    createCategoricalFilter(columnField: string): HTMLElement {
      if (!this.parentDocument) {
        throw new Error('Parent document not available')
      }

      const container = this.parentDocument.createElement('div')

      const select = this.parentDocument.createElement('select')
      select.multiple = true
      select.style.cssText = `
        width: 100%;
        padding: 8px;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-size: 14px;
        min-height: 80px;
      `

      const uniqueValues = this.getUniqueValues(columnField)
      const currentValues = this.filterValues[columnField]?.categorical || []

      uniqueValues.forEach((value) => {
        if (!this.parentDocument) return
        const option = this.parentDocument.createElement('option')
        option.value = value
        option.textContent = value
        option.selected = currentValues.includes(value)
        select.appendChild(option)
      })

      select.addEventListener('change', () => {
        const selectedValues = Array.from(select.selectedOptions).map((opt) => opt.value)
        if (!this.filterValues[columnField]) {
          this.filterValues[columnField] = {}
        }
        this.filterValues[columnField].categorical = selectedValues
        this.applyFilters()
      })

      container.appendChild(select)
      return container
    },

    createNumericFilter(columnField: string): HTMLElement {
      if (!this.parentDocument) {
        throw new Error('Parent document not available')
      }
      const doc = this.parentDocument
      const config = this.numericFilterConfig[columnField]
      const dataMin = this.getMinValue(columnField)
      const dataMax = this.getMaxValue(columnField)
      if (!this.filterValues[columnField]?.numeric) {
        this.filterValues[columnField] = {
          ...(this.filterValues[columnField] || {}),
          numeric: { op: config?.op || 'between', min: null, max: null },
        }
      }
      const numeric = this.filterValues[columnField].numeric!

      const container = doc.createElement('div')
      container.style.cssText = 'display: flex; flex-direction: column; gap: 8px;'

      const inputStyle =
        'width: 120px; padding: 4px 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px;'
      const row = doc.createElement('div')
      row.style.cssText = 'display: flex; gap: 8px; align-items: center; flex-wrap: wrap;'

      // Which side the threshold keeps: at least, at most, or a range
      const opSelect = doc.createElement('select')
      opSelect.style.cssText = 'padding: 4px 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px;'
      for (const [op, text] of [
        ['>=', '≥ at least'],
        ['<=', '≤ at most'],
        ['between', 'between'],
      ] as const) {
        const option = doc.createElement('option')
        option.value = op
        option.textContent = text
        option.selected = numeric.op === op
        opSelect.appendChild(option)
      }

      const makeInput = (value: number | null, placeholder: number): HTMLInputElement => {
        const input = doc.createElement('input')
        input.type = 'number'
        input.step = 'any'
        input.value = value === null ? '' : String(value)
        input.placeholder = formatNumber(placeholder)
        input.style.cssText = inputStyle
        return input
      }
      const minInput = makeInput(numeric.min, dataMin)
      const maxInput = makeInput(numeric.max, dataMax)
      const toLabel = doc.createElement('span')
      toLabel.textContent = 'to'

      const range = doc.createElement('span')
      range.textContent = `values ${formatNumber(dataMin)} – ${formatNumber(dataMax)}`
      range.style.cssText = 'font-size: 12px; color: #888;'

      const layout = () => {
        const op = numeric.op
        minInput.style.display = op === '<=' ? 'none' : ''
        maxInput.style.display = op === '>=' ? 'none' : ''
        toLabel.style.display = op === 'between' ? '' : 'none'
      }
      const parse = (input: HTMLInputElement): number | null => {
        if (input.value.trim() === '') return null
        const value = parseFloat(input.value)
        return Number.isFinite(value) ? value : null
      }
      const update = () => {
        numeric.op = opSelect.value as NumericOp
        numeric.min = parse(minInput)
        numeric.max = parse(maxInput)
        layout()
        this.applyFilters()
        markSuggestions()
      }
      opSelect.addEventListener('change', update)
      minInput.addEventListener('change', update)
      maxInput.addEventListener('change', update)

      row.appendChild(opSelect)
      row.appendChild(minInput)
      row.appendChild(toLabel)
      row.appendChild(maxInput)
      row.appendChild(range)
      layout()
      container.appendChild(row)

      // One-click thresholds offered by the app, and "Any" to remove the filter
      const buttons: Array<{ button: HTMLButtonElement; value: number | null }> = []
      const markSuggestions = () => {
        const bound = numeric.op === '>=' ? numeric.min : numeric.op === '<=' ? numeric.max : undefined
        const open = numeric.min === null && numeric.max === null
        for (const { button, value } of buttons) {
          const active = value === null ? open : numeric.op === config?.op && bound === value
          button.style.background = active ? this.accentColor : 'white'
          button.style.color = active ? 'white' : this.accentColor
        }
      }
      if (config) {
        const chips = doc.createElement('div')
        chips.style.cssText = 'display: flex; gap: 6px; flex-wrap: wrap; align-items: center;'
        const symbol = config.op === '>=' ? '≥' : '≤'
        const choices: Array<{ value: number | null; text: string; tip: string }> = [
          { value: null, text: 'Any', tip: 'No filter on this column' },
          ...(config.suggestions || []).map((s) => ({
            value: s.value,
            text: s.label || `${symbol} ${formatNumber(s.value)}`,
            tip: `${this.columnTitle(columnField)} ${symbol} ${formatNumber(s.value)}`,
          })),
        ]
        for (const choice of choices) {
          const button = doc.createElement('button')
          button.textContent = choice.text
          button.title = choice.tip
          button.style.cssText =
            `border: 1px solid ${this.accentColor}; border-radius: 14px; padding: 2px 10px; font-size: 13px; cursor: pointer;`
          button.addEventListener('click', () => {
            opSelect.value = config.op
            numeric.op = config.op
            numeric.min = config.op === '>=' ? choice.value : null
            numeric.max = config.op === '<=' ? choice.value : null
            minInput.value = numeric.min === null ? '' : String(numeric.min)
            maxInput.value = numeric.max === null ? '' : String(numeric.max)
            layout()
            this.applyFilters()
            markSuggestions()
          })
          buttons.push({ button, value: choice.value })
          chips.appendChild(button)
        }
        container.appendChild(chips)
        markSuggestions()
      }
      return container
    },

    createTextFilter(columnField: string): HTMLElement {
      if (!this.parentDocument) {
        throw new Error('Parent document not available')
      }

      const input = this.parentDocument.createElement('input')
      input.type = 'text'
      input.placeholder = 'Search pattern (regex supported)'
      input.value = this.filterValues[columnField]?.text || ''
      input.style.cssText = `
        width: 100%;
        padding: 8px;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-size: 14px;
      `

      input.addEventListener('input', () => {
        if (!this.filterValues[columnField]) {
          this.filterValues[columnField] = {}
        }
        this.filterValues[columnField].text = input.value
        this.applyFilters()
      })

      return input
    },

    refreshTeleportDialog(): void {
      if (!this.teleportDialog || !this.teleportContainer) return
      this.teleportContainer.innerHTML = ''
      this.renderFilterDialog()
    },

    closeTeleportDialog(): void {
      this.teleportDialog = false
      this.cleanupTeleport()
    },

    cleanupTeleport(): void {
      if (this.teleportBackdrop && this.parentDocument) {
        this.parentDocument.body.removeChild(this.teleportBackdrop)
        this.teleportBackdrop = null
      }
      if (this.teleportContainer) {
        this.teleportContainer = null
      }
    },

    // Go-to functionality
    initializeGoTo(): void {
      if (this.args.goToFields && this.args.goToFields.length > 0) {
        this.selectedGoToField = this.args.goToFields[0]
      }
    },

    toggleGoTo(): void {
      this.showGoTo = !this.showGoTo
      if (this.showGoTo && this.args.goToFields && this.args.goToFields.length > 0) {
        this.selectedGoToField = this.args.goToFields[0]
      }
      this.$nextTick(() => {
        this.redrawTableWithNewHeight()
      })
    },

    redrawTableWithNewHeight(): void {
      if (!this.tabulator) return
      this.tabulator.destroy()
      this.drawTable()
    },

    findRowByValue(field: string, value: string): number {
      const searchValue = isNaN(Number(value)) ? value : Number(value)
      return this.preparedTableData.findIndex((row) => row[field] === searchValue)
    },

    performGoTo(): void {
      if (!this.goToInputValue.trim()) return

      // For server-side pagination, send go-to request to Python
      if (this.isServerSidePagination) {
        const paginationIdentifier = this.args.paginationIdentifier
        if (paginationIdentifier) {
          this.selectionStore.updateSelection(paginationIdentifier, {
            page: this.paginationState?.page || 1,
            page_size: this.paginationState?.page_size || this.args.pageSize || 100,
            sort_column: this.requestedSortColumn || undefined,
            sort_dir: this.requestedSortDir,
            column_filters: this.currentColumnFilters,
              ...this.viewFiltersPatch,
            go_to_request: {
              field: this.selectedGoToField,
              value: this.goToInputValue.trim(),
            },
          })
        }
        this.goToInputValue = ''
        return
      }

      // Client-side go-to (for non-streaming tables)
      const rowIndex = this.findRowByValue(this.selectedGoToField, this.goToInputValue.trim())

      if (rowIndex >= 0) {
        const indexField = this.args.tableIndexField || 'id'
        const rowId = this.preparedTableData[rowIndex][indexField]
        const row = this.tabulator?.getRow(rowId)
        if (row) {
          row.scrollTo('top', false).catch(() => {})
          this.tabulator?.deselectRow()
          row.select()
          // Update selection store
          const rowData = row.getData()
          if (rowData) {
            const interactivity = this.args.interactivity || {}
            for (const [identifier, column] of Object.entries(interactivity)) {
              const value = rowData[column as string]
              this.selectionStore.updateSelection(identifier, value)
            }
          }
        }
        this.goToInputValue = ''
      }
    },

    getGoToFieldLabel(field: string): string {
      const column = (this.args.columnDefinitions || []).find((col) => col.field === field)
      if (column?.title) {
        return column.title as string
      }
      return field
    },

    getGoToPlaceholder(): string {
      const fieldLabel = this.getGoToFieldLabel(this.selectedGoToField)
      return `Enter ${fieldLabel.toLowerCase()}...`
    },
  },
})
</script>

<style>
@import 'tabulator-tables/dist/css/tabulator_bootstrap4.min.css';

.tabulator-col-title,
.tabulator-cell {
  font-size: 14px;
}

/* Toolbar above the table: buttons | title | toggle filters.
   The side tracks share the free space so the title stays centred, but never
   shrink below their content: the buttons stay on one line however narrow the
   Streamlit column is, and the title gives way (ellipsis) instead. */
.table-toolbar {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(max-content, 1fr) minmax(0, max-content) minmax(min-content, 1fr);
  align-items: center;
  column-gap: 8px;
}

.table-toolbar-buttons {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: flex-start;
}

.table-toolbar-title {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
}

.table-toolbar-title h4 {
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.table-toolbar-toggles {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  column-gap: 8px;
}

.v-checkbox.v-input.toggle-filter,
.toggle-filter .v-selection-control {
  flex: 0 1 auto;
}

/* Vuetify sizes the control track minmax(0, 1fr), which reports a min-content
   width of 0 and lets the label spill over the title */
.v-input--horizontal.toggle-filter {
  grid-template-columns: max-content minmax(min-content, 1fr) max-content;
}

/* When space is short, break a toggle label between words, never inside one */
.toggle-filter .v-label {
  min-width: min-content;
  white-space: normal;
  word-break: keep-all;
  overflow-wrap: normal;
}

.toggle-filter .v-label {
  opacity: 0.6;
}

/* Toolbar search box: as tall as the buttons beside it */
.table-search {
  flex: 0 1 240px;
  min-width: 140px;
  margin-left: 8px;
}

.table-search .v-field {
  font-size: 14px;
  --v-field-padding-start: 8px;
}

.table-search .v-field__input {
  min-height: 32px;
  padding-top: 4px;
  padding-bottom: 4px;
}

.table-search .v-field__prepend-inner > .v-icon,
.table-search .v-field__clearable > .v-icon {
  font-size: 18px;
}

/* The filters in force, under the toolbar */
.table-filter-chips {
  display: flex;
  flex-wrap: nowrap;
  overflow-x: auto;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  margin: 2px 0 2px 4px;
}

.table-filter-chips .v-chip {
  flex: 0 0 auto;
}

.filter-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  background-color: #f44336;
  color: white;
  border-radius: 50%;
  min-width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  z-index: 10;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}

/* Compact pagination styling */
.tabulator .tabulator-footer {
  padding: 4px 8px;
  min-height: unset;
}

.tabulator .tabulator-footer .tabulator-paginator {
  font-size: 12px;
}

.tabulator .tabulator-footer .tabulator-page {
  padding: 2px 8px;
  font-size: 12px;
  min-width: unset;
}

.tabulator .tabulator-footer .tabulator-page-size {
  padding: 2px 4px;
  font-size: 12px;
}

.tabulator .tabulator-footer .tabulator-pages {
  margin: 0 4px;
}

.tabulator .tabulator-footer .tabulator-page-counter {
  font-size: 11px;
  margin-right: 8px;
}

.tabulator,
.table-toolbar {
  --ms-accent: #1e88e5;
  --ms-accent-soft: rgba(30, 136, 229, 0.16);
}
.multi-select-box {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: 1.5px solid currentColor;
  border-radius: 5px;
  opacity: 0.45;
  cursor: pointer;
  vertical-align: middle;
  transition: background-color 0.12s, border-color 0.12s, opacity 0.12s, transform 0.12s;
}
.multi-select-box .mdi {
  font-size: 13px;
  line-height: 1;
  color: #fff;
  transform: scale(0);
  transition: transform 0.12s;
}
.tabulator-cell:hover .multi-select-box,
.multi-select-header:hover .multi-select-box {
  opacity: 0.8;
  border-color: var(--ms-accent);
}
.multi-select-box.checked,
.multi-select-box.some {
  opacity: 1;
  background: var(--ms-accent);
  border-color: var(--ms-accent);
  box-shadow: 0 0 0 3px var(--ms-accent-soft);
}
.multi-select-box.checked .mdi,
.multi-select-box.some .mdi {
  transform: scale(1);
}
.tabulator-row.multi-selected {
  box-shadow: inset 3px 0 0 var(--ms-accent);
  background-image: linear-gradient(90deg, var(--ms-accent-soft), transparent 60%);
}
.multi-select-toggle {
  border-radius: 8px !important;
  transition: background-color 0.15s, color 0.15s;
}
.multi-select-toggle.active {
  color: var(--ms-accent) !important;
  background: var(--ms-accent-soft);
}

/* Dark mode pagination styling */
.row-overview-button {
  cursor: pointer;
  font-size: 18px;
  opacity: 0.7;
}
.row-overview-button:hover {
  opacity: 1;
}

.table-dark .tabulator-footer {
  background-color: #1e1e1e;
  border-color: #444;
  color: #e0e0e0;
}

.table-dark .tabulator-footer .tabulator-paginator label {
  color: #e0e0e0;
}

.table-dark .tabulator-footer .tabulator-page {
  background-color: #2d2d2d;
  border-color: #444;
  color: #e0e0e0;
}

.table-dark .tabulator-footer .tabulator-page:hover {
  background-color: #3d3d3d;
  color: #fff;
}

.table-dark .tabulator-footer .tabulator-page.active {
  background-color: #0d6efd;
  border-color: #0d6efd;
  color: #fff;
}

.table-dark .tabulator-footer .tabulator-page:disabled {
  background-color: #1e1e1e;
  border-color: #333;
  color: #666;
}

.table-dark .tabulator-footer .tabulator-page-size {
  background-color: #2d2d2d;
  border-color: #444;
  color: #e0e0e0;
}

.table-dark .tabulator-footer .tabulator-page-counter {
  color: #aaa;
}

/* Dark mode selected row: the bootstrap4 theme keeps its light-mode blue,
   which leaves the white row text unreadable */
.tabulator.table-dark .tabulator-row.tabulator-selected {
  background-color: #2b4c7e;
}

.tabulator.table-dark .tabulator-row.tabulator-selected:hover {
  background-color: #355d99;
}

/* Light mode - ensure consistent styling */
.table-light .tabulator-footer {
  background-color: #f8f9fa;
  border-color: #dee2e6;
}

.table-light .tabulator-footer .tabulator-page.active {
  background-color: #0d6efd;
  border-color: #0d6efd;
  color: #fff;
}
</style>
