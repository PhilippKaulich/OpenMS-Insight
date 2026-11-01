<template>
  <!-- A table fitted to a few rows stays at least 200 px tall -->
  <div
    style="padding: 8px; width: 98%; box-sizing: border-box"
    :style="isServerSidePagination ? {} : { minHeight: '200px' }"
  >
    <div class="d-flex">
      <div style="width: 100%; display: grid; grid-template-columns: 1fr 1fr 1fr">
        <div class="d-flex justify-start" style="grid-column: 1 / span 1">
          <div style="position: relative; display: inline-block">
            <v-btn
              variant="text"
              size="small"
              icon="mdi-download"
              :loading="pendingDownloadId !== null"
              :title="isServerSidePagination ? 'Download all rows and columns as CSV' : undefined"
              @click="downloadTable"
            />
            <v-btn variant="text" size="small" icon="mdi-filter" @click="openFilterDialog" />
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
        </div>
        <div class="d-flex justify-center" style="grid-column: 2 / span 1">
          <h4>{{ args.title ?? '' }}</h4>
        </div>
        <div class="d-flex justify-end" style="grid-column: 3 / span 1">
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

    <div :id="id" :class="tableClasses"></div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import { TabulatorFull as Tabulator, type ColumnDefinition, type Options } from 'tabulator-tables'
import { Streamlit } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { TableComponentArgs, PaginationState, ColumnMetadata } from '@/types/component'
import { isCustomFormatter, getCustomFormatter } from './formatters'

// Global counter for unique table IDs
let tableIdCounter = 0

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
      filterValues: {} as Record<
        string,
        {
          categorical?: string[]
          numeric?: { min: number; max: number }
          text?: string
        }
      >,
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
    }
  },
  computed: {
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
    /** Toggle state to merge into pagination requests (nothing when the table has none). */
    togglesPatch(): Record<string, unknown> {
      return this.toggleFilters.length > 0 ? { toggles: { ...this.currentToggles } } : {}
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
      let count = 0
      for (const columnField of this.selectedColumns) {
        const filterValue = this.filterValues[columnField]
        if (!filterValue) continue

        const filterType = this.filterTypes[columnField]
        let hasActiveFilter = false

        switch (filterType) {
          case 'categorical':
            hasActiveFilter = !!(filterValue.categorical && filterValue.categorical.length > 0)
            break
          case 'numeric':
            if (filterValue.numeric) {
              const dataMin = this.getMinValue(columnField)
              const dataMax = this.getMaxValue(columnField)
              hasActiveFilter =
                filterValue.numeric.min !== dataMin || filterValue.numeric.max !== dataMax
            }
            break
          case 'text':
            hasActiveFilter = !!(filterValue.text && filterValue.text.trim() !== '')
            break
        }

        if (hasActiveFilter) count++
      }
      return count
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
        const newMaxHeight = newHeight - 56 - (this.showGoTo ? 58 : 0)
        this.tabulator.setHeight(Math.max(newMaxHeight, 50))
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
    this.cleanupTeleport()
    this.rootResizeObserver?.disconnect()
  },
  methods: {
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
        ...this.togglesPatch,
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
      const passedHeight = this.args.height
      const defaultHeight = this.args.title ? 320 : 310
      const baseHeight = passedHeight ? passedHeight - 56 : defaultHeight
      const goToHeight = this.showGoTo ? 58 : 0
      const tableMaxHeight = baseHeight - goToHeight

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
        columns: (this.args.columnDefinitions || []).map((col) => {
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
        }),
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
        // The table is as tall as its rows, up to the height it was given
        delete tabulatorOptions.height
        tabulatorOptions.minHeight = 50
        tabulatorOptions.maxHeight = Math.max(tableMaxHeight, 50)
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
              ...this.togglesPatch,
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
        this.tableData.length > 0
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
              ...this.togglesPatch,
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
              ...this.togglesPatch,
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
              ...this.togglesPatch,
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
          dataType: meta.type,
        }
        this.columnAnalysis[columnField] = analysis
        this.filterTypes[columnField] = meta.type
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
        const newFilterValue: {
          categorical?: string[]
          numeric?: { min: number; max: number }
          text?: string
        } = {}

        switch (filterType) {
          case 'categorical':
            newFilterValue.categorical = []
            break
          case 'numeric':
            newFilterValue.numeric = {
              min: this.getMinValue(columnField),
              max: this.getMaxValue(columnField),
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
              if (filterValue.numeric) {
                serverFilters.push({ field: columnField, type: '>=', value: filterValue.numeric.min })
                serverFilters.push({ field: columnField, type: '<=', value: filterValue.numeric.max })
              }
              break
            case 'text':
              if (filterValue.text) {
                serverFilters.push({ field: columnField, type: 'regex', value: filterValue.text })
              }
              break
          }
        })

        // Store filters and trigger server request
        this.currentColumnFilters = serverFilters

        // Send pagination request with new filters (reset to page 1)
        const paginationIdentifier = this.args.paginationIdentifier
        if (paginationIdentifier) {
          this.selectionStore.updateSelection(paginationIdentifier, {
            page: 1, // Reset to first page when filters change
            page_size: this.paginationState?.page_size || this.args.pageSize || 100,
            sort_column: this.requestedSortColumn || undefined,
            sort_dir: this.requestedSortDir,
            column_filters: serverFilters,
              ...this.togglesPatch,
          })
        }
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
            if (filterValue.numeric) {
              this.tabulator?.addFilter(columnField, '>=', filterValue.numeric.min)
              this.tabulator?.addFilter(columnField, '<=', filterValue.numeric.max)
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

      this.renderColumnSelection(content)
      this.renderFilterControls(content)

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
        background: #1976d2;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
      `
      closeFooterBtn.addEventListener('click', () => this.closeTeleportDialog())
      closeFooterBtn.addEventListener('mouseenter', () => {
        closeFooterBtn.style.backgroundColor = '#1565c0'
      })
      closeFooterBtn.addEventListener('mouseleave', () => {
        closeFooterBtn.style.backgroundColor = '#1976d2'
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
              ? 'background: #1976d2; color: white; border: 1px solid #1976d2;'
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
        color: #1976d2;
        border: 1px solid #1976d2;
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

      const container = this.parentDocument.createElement('div')
      container.style.cssText = 'padding: 8px 0;'

      const minValue = Math.floor(this.getMinValue(columnField))
      const maxValue = Math.ceil(this.getMaxValue(columnField))
      const currentFilter = this.filterValues[columnField]?.numeric

      const range = maxValue - minValue
      const step = range > 1 ? 1 : 0.01

      // Values display
      const valuesDisplay = this.parentDocument.createElement('div')
      valuesDisplay.style.cssText =
        'display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; color: #333;'

      const minValueDisplay = this.parentDocument.createElement('span')
      minValueDisplay.textContent = String(currentFilter?.min || minValue)
      minValueDisplay.style.cssText =
        'font-weight: 500; padding: 4px 8px; background: #f0f0f0; border-radius: 4px;'

      const maxValueDisplay = this.parentDocument.createElement('span')
      maxValueDisplay.textContent = String(currentFilter?.max || maxValue)
      maxValueDisplay.style.cssText =
        'font-weight: 500; padding: 4px 8px; background: #f0f0f0; border-radius: 4px;'

      valuesDisplay.appendChild(minValueDisplay)
      valuesDisplay.appendChild(maxValueDisplay)

      // Simple min/max inputs
      const inputsContainer = this.parentDocument.createElement('div')
      inputsContainer.style.cssText = 'display: flex; gap: 8px; align-items: center;'

      const minInput = this.parentDocument.createElement('input')
      minInput.type = 'number'
      minInput.value = String(currentFilter?.min || minValue)
      minInput.min = String(minValue)
      minInput.max = String(maxValue)
      minInput.step = String(step)
      minInput.style.cssText = 'width: 100px; padding: 4px 8px; border: 1px solid #ddd; border-radius: 4px;'

      const toLabel = this.parentDocument.createElement('span')
      toLabel.textContent = 'to'

      const maxInput = this.parentDocument.createElement('input')
      maxInput.type = 'number'
      maxInput.value = String(currentFilter?.max || maxValue)
      maxInput.min = String(minValue)
      maxInput.max = String(maxValue)
      maxInput.step = String(step)
      maxInput.style.cssText = 'width: 100px; padding: 4px 8px; border: 1px solid #ddd; border-radius: 4px;'

      const updateFilter = () => {
        const minVal = parseFloat(minInput.value) || minValue
        const maxVal = parseFloat(maxInput.value) || maxValue

        if (!this.filterValues[columnField]) {
          this.filterValues[columnField] = {}
        }
        this.filterValues[columnField].numeric = { min: minVal, max: maxVal }
        minValueDisplay.textContent = String(minVal)
        maxValueDisplay.textContent = String(maxVal)
        this.applyFilters()
      }

      minInput.addEventListener('change', updateFilter)
      maxInput.addEventListener('change', updateFilter)

      inputsContainer.appendChild(minInput)
      inputsContainer.appendChild(toLabel)
      inputsContainer.appendChild(maxInput)

      container.appendChild(valuesDisplay)
      container.appendChild(inputsContainer)
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
              ...this.togglesPatch,
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

.v-checkbox.v-input.toggle-filter,
.toggle-filter .v-selection-control {
  flex: 1 1 auto;
}

.toggle-filter .v-label {
  opacity: 0.6;
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

/* Dark mode pagination styling */
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
