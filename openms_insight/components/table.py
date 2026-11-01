"""Table component using Tabulator.js."""

import logging
import re
from typing import Any

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.filtering import compute_dataframe_hash

# A spreadsheet reads a cell starting with one of these as a formula, so a value
# like ``=HYPERLINK(...)`` in exported text would run when the CSV is opened.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(df: pl.DataFrame) -> pl.DataFrame:
    """
    Neutralise spreadsheet formulas in the text columns of ``df`` (CSV injection).

    Text that starts with ``= + - @``, a tab or a carriage return gets a leading
    single quote, which spreadsheets show as text and do not evaluate (the OWASP
    recommendation). Numeric columns are left alone, so negative numbers stay
    numbers.
    """
    pattern = "^[" + re.escape("".join(FORMULA_PREFIXES)) + "]"
    text_columns = [
        name
        for name, dtype in df.schema.items()
        if dtype in (pl.Utf8, pl.Categorical) or isinstance(dtype, pl.Enum)
    ]
    if not text_columns:
        return df
    return df.with_columns(
        pl.when(pl.col(name).cast(pl.Utf8).str.contains(pattern))
        .then(pl.lit("'") + pl.col(name).cast(pl.Utf8))
        .otherwise(pl.col(name).cast(pl.Utf8))
        .alias(name)
        for name in text_columns
    )


logger = logging.getLogger(__name__)

# Numeric data types for dtype checking
NUMERIC_DTYPES = (
    pl.Int8,
    pl.Int16,
    pl.Int32,
    pl.Int64,
    pl.UInt8,
    pl.UInt16,
    pl.UInt32,
    pl.UInt64,
    pl.Float32,
    pl.Float64,
)

# Session state key for tracking last rendered selection per table component
_LAST_SELECTION_KEY = "_svc_table_last_selection"
# Session state key for tracking last sort/filter state per table component
_LAST_SORT_FILTER_KEY = "_svc_table_last_sort_filter"


@register_component("table")
class Table(BaseComponent):
    """
    Interactive table component using Tabulator.js.

    Features:
    - Column definitions with formatters, sorters, tooltips
    - Row selection with cross-component linking
    - Filtering dialog (categorical, numeric, text)
    - Go-to functionality for navigation by field value
    - CSV download
    - Automatic column type detection

    Tables can have separate `filters` and `interactivity` mappings:
    - `filters`: Which selections filter this table's data
    - `interactivity`: What selection is set when a row is clicked

    Example:
        # Master table - shows all data, clicking sets 'spectrum' selection
        master_table = Table(
            cache_id="spectra_table",
            data=spectra_df,
            interactivity={'spectrum': 'scan_id'},
        )

        # Detail table - filters by 'spectrum', clicking sets 'peak' selection
        detail_table = Table(
            cache_id="peaks_table",
            data=peaks_df,
            filters={'spectrum': 'scan_id'},
            interactivity={'peak': 'mass'},
        )
    """

    _component_type: str = "table"

    def __init__(
        self,
        cache_id: str,
        data: pl.LazyFrame | None = None,
        data_path: str | None = None,
        filters: dict[str, str] | None = None,
        filter_defaults: dict[str, Any] | None = None,
        interactivity: dict[str, str] | None = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        column_definitions: list[dict[str, Any]] | None = None,
        title: str | None = None,
        index_field: str = "id",
        go_to_fields: list[str] | None = None,
        layout: str = "fitDataFill",
        default_row: int = 0,
        initial_sort: list[dict[str, Any]] | None = None,
        pagination: bool = True,
        page_size: int = 100,
        pagination_identifier: str | None = None,
        toggle_filters: list[dict[str, Any]] | None = None,
        range_filters: dict[str, list[str]] | None = None,
        on_select: dict[str, Any] | None = None,
        reclick: str = "keep",
        default_row_selects: bool = True,
        scroll_position: str = "center",
        hidden_columns: list[str] | None = None,
        column_menu: bool = True,
        reset_sort: bool = False,
        reset_sort_on: list[str] | None = None,
        **kwargs,
    ):
        """
        Initialize the Table component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
                Creates a folder {cache_path}/{cache_id}/ for cached data.
            data: Polars LazyFrame with table data. Optional if cache exists.
            data_path: Path to parquet file (preferred for large datasets).
            filters: Mapping of identifier names to column names for filtering.
                Example: {'spectrum': 'scan_id'}
                When 'spectrum' selection exists, table shows only rows where
                scan_id equals the selected value.
            filter_defaults: Default values for filters when state is None.
                Example: {'identification': -1}
                When 'identification' selection is None, filter uses -1 instead.
            interactivity: Mapping of identifier names to column names for clicks.
                Example: {'peak': 'mass'}
                When a row is clicked, sets 'peak' selection to that row's mass.
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            column_definitions: List of Tabulator column definition dicts.
                Each dict can contain:
                - field: Column field name (required)
                - title: Display title (defaults to field name)
                - sorter: 'number', 'string', 'alphanum', 'boolean', 'date', etc.
                - formatter: 'money', 'progress', 'star', 'tickCross', etc.
                - formatterParams: Dict of formatter parameters
                - headerTooltip: True or tooltip string
                - hozAlign: 'left', 'center', 'right'
                - width: Column width (number or string like '100px')
                If None, auto-generates from data schema.
            title: Table title displayed above the table
            index_field: Field used as row index for selection (default: 'id')
            go_to_fields: List of field names for "Go to" navigation feature
            layout: Tabulator layout mode ('fitData', 'fitDataFill', 'fitColumns', etc.)
            default_row: Default row to select on load (-1 for none)
            initial_sort: List of sort configurations like [{'column': 'field', 'dir': 'asc'}]
            pagination: Enable pagination for large tables (default: True).
                When enabled, uses server-side pagination where only the current
                page of data is sent to the frontend, dramatically reducing browser
                memory usage for large datasets. Without it every row is sent,
                and the browser sorts, filters and exports them itself.
            page_size: Number of rows per page when pagination is enabled (default: 100)
            pagination_identifier: State key for storing pagination state (page, sort,
                filters). Default: "{cache_id}_page". Used by StateManager to track
                pagination state across reruns.
            toggle_filters: Checkboxes shown in the title row, each restricting the
                table to rows where a boolean column is true. Each entry is a dict:
                - label: Checkbox label
                - column: Boolean column the checkbox filters on
                - default: Initial state (default: True)
                - group_column: Optional column. When ticking the box hides the
                  selected row, the selection moves to the first remaining row
                  sharing its value in this column (e.g. the best hit of the
                  same spectrum) instead of to the first row of the table.
                - color: Optional checkbox colour (default: the theme's primary)
                Example: [{'label': 'Best per spectrum', 'column': 'is_best',
                'group_column': 'scan'}]
            range_filters: Mapping of identifier names to [start_column, end_column]
                pairs. While the identifier has a selection, only rows with
                start_column <= value <= end_column are shown; without one the
                table is not restricted. Example: {'residue': ['start', 'end']}
            on_select: Selections to set whenever the user clicks a row, in addition
                to those in ``interactivity``. A value of None clears the
                identifier. Example: {'peak': None} clears a dependent selection.
                Not applied to the automatic default-row selection.
            reclick: What clicking the highlighted row again does: "keep" (the
                default) keeps it selected and highlighted, "unhighlight" only
                removes the highlight (the selection stays until another row is
                clicked), "deselect" clears the ``interactivity`` selections. With
                "deselect" the default row is not selected again until the
                table's filter values change.
            default_row_selects: If False, the default row is only highlighted
                while nothing is selected, and no selection is set for it.
            scroll_position: Where a row selected from elsewhere is scrolled to:
                "center" (the default), "top", "bottom" or "nearest". Other than
                "center", a clicked row that is cut off is scrolled there too.
            hidden_columns: Fields of ``column_definitions`` to hide until the
                viewer turns them on in the column menu. Use it for optional
                columns that most viewers do not need. A column definition with
                ``"visible": False`` is treated the same way. The viewer's
                choice is kept in their browser, per table.
            column_menu: Show the toolbar button that lists the columns to show
                or hide.
            reset_sort: Without pagination, sort new rows (e.g. after a filter
                value changed) by ``initial_sort`` again instead of keeping the
                viewer's sort.
            reset_sort_on: Identifiers whose selection, when it changes, sorts
                the rows by ``initial_sort`` again, whether or not the rows
                change (e.g. a table of the tags of the selected protein).
            **kwargs: Additional configuration options
        """
        self._column_definitions = column_definitions
        self._title = title
        self._index_field = index_field
        self._go_to_fields = go_to_fields
        self._layout = layout
        self._default_row = default_row
        self._initial_sort = initial_sort
        self._pagination = pagination
        self._page_size = page_size
        # Display-only, so not part of the cache config
        self._hidden_columns = list(hidden_columns or [])
        self._column_menu = bool(column_menu)
        self._reset_sort = bool(reset_sort)
        self._reset_sort_on = list(reset_sort_on or [])
        # Default pagination identifier based on cache_id
        self._pagination_identifier = pagination_identifier or f"{cache_id}_page"
        self._toggle_filters = self._normalize_toggle_filters(toggle_filters)
        self._range_filters = {k: list(v) for k, v in (range_filters or {}).items()}
        self._on_select = dict(on_select) if on_select else {}
        if reclick not in ("keep", "unhighlight", "deselect"):
            raise ValueError(
                f"reclick must be 'keep', 'unhighlight' or 'deselect', not {reclick!r}"
            )
        self._reclick = reclick
        self._default_row_selects = bool(default_row_selects)
        if scroll_position not in ("center", "top", "bottom", "nearest"):
            raise ValueError(
                "scroll_position must be 'center', 'top', 'bottom' or 'nearest', "
                f"not {scroll_position!r}"
            )
        self._scroll_position = scroll_position

        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            filters=filters,
            filter_defaults=filter_defaults,
            interactivity=interactivity,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            # Pass component-specific params for subprocess recreation
            column_definitions=column_definitions,
            title=title,
            index_field=index_field,
            go_to_fields=go_to_fields,
            layout=layout,
            default_row=default_row,
            initial_sort=initial_sort,
            pagination=pagination,
            page_size=page_size,
            pagination_identifier=self._pagination_identifier,
            toggle_filters=toggle_filters,
            range_filters=range_filters,
            on_select=on_select,
            reclick=reclick,
            default_row_selects=default_row_selects,
            scroll_position=scroll_position,
            column_menu=column_menu,
            reset_sort=reset_sort,
            reset_sort_on=reset_sort_on,
            **kwargs,
        )

    @staticmethod
    def _normalize_toggle_filters(
        toggle_filters: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        """Validate toggle filter entries and fill in their defaults."""
        normalized = []
        for entry in toggle_filters or []:
            if "column" not in entry:
                raise ValueError(f"toggle_filters entry needs a 'column': {entry}")
            normalized.append(
                {
                    "label": entry.get("label", entry["column"]),
                    "column": entry["column"],
                    "default": bool(entry.get("default", True)),
                    "group_column": entry.get("group_column"),
                    **({"color": entry["color"]} if entry.get("color") else {}),
                }
            )
        return normalized

    def _get_cache_config(self) -> dict[str, Any]:
        """
        Get configuration that affects cache validity.

        Returns:
            Dict of config values that affect preprocessing
        """
        return {
            "column_definitions": self._column_definitions,
            "index_field": self._index_field,
            "title": self._title,
            "go_to_fields": self._go_to_fields,
            "layout": self._layout,
            "default_row": self._default_row,
            "initial_sort": self._initial_sort,
            "pagination": self._pagination,
            "page_size": self._page_size,
            "pagination_identifier": self._pagination_identifier,
            # Only present when used, so tables that do not use them keep the
            # configuration hash (and with it the cache) they had before.
            **(
                {"toggle_filters": self._toggle_filters} if self._toggle_filters else {}
            ),
            **({"range_filters": self._range_filters} if self._range_filters else {}),
            **({"on_select": self._on_select} if self._on_select else {}),
            **({"reclick": self._reclick} if self._reclick != "keep" else {}),
            **({"default_row_selects": False} if not self._default_row_selects else {}),
            **(
                {"scroll_position": self._scroll_position}
                if self._scroll_position != "center"
                else {}
            ),
            **({"column_menu": False} if not self._column_menu else {}),
            **({"reset_sort": True} if self._reset_sort else {}),
            **({"reset_sort_on": self._reset_sort_on} if self._reset_sort_on else {}),
        }

    def _restore_cache_config(self, config: dict[str, Any]) -> None:
        """Restore component-specific configuration from cached config."""
        self._column_definitions = config.get("column_definitions")
        self._index_field = config.get("index_field", "id")
        self._title = config.get("title")
        self._go_to_fields = config.get("go_to_fields")
        self._layout = config.get("layout", "fitDataFill")
        self._default_row = config.get("default_row", 0)
        self._initial_sort = config.get("initial_sort")
        self._pagination = config.get("pagination", True)
        self._page_size = config.get("page_size", 100)
        self._pagination_identifier = config.get(
            "pagination_identifier", f"{self._cache_id}_page"
        )
        self._toggle_filters = config.get("toggle_filters", [])
        self._range_filters = config.get("range_filters", {})
        self._on_select = config.get("on_select", {})
        self._reclick = config.get("reclick", "keep")
        self._default_row_selects = config.get("default_row_selects", True)
        self._scroll_position = config.get("scroll_position", "center")
        self._column_menu = config.get("column_menu", True)
        self._reset_sort = config.get("reset_sort", False)
        self._reset_sort_on = config.get("reset_sort_on") or []
        # These are passed on to Vue explicitly; keep them out of the extra options
        for key in (
            "toggle_filters",
            "range_filters",
            "on_select",
            "reclick",
            "default_row_selects",
            "scroll_position",
            "column_menu",
            "reset_sort",
            "reset_sort_on",
        ):
            self._config.pop(key, None)

    def get_state_dependencies(self) -> list[str]:
        """
        Return list of state keys that affect this component's data.

        Tables depend on:
        - filters (for data filtering)
        - pagination state (for page, sort, and column filters)
        - interactivity identifiers (for page navigation to selected row)

        Returns:
            List of state identifier keys
        """
        deps = list(self._filters.keys()) if self._filters else []
        deps.extend(k for k in self._range_filters if k not in deps)
        deps.append(self._pagination_identifier)
        # Include interactivity identifiers for page navigation
        if self._interactivity:
            deps.extend(self._interactivity.keys())
        return deps

    def auto_selection_scope(self, state: dict[str, Any]) -> tuple | None:
        """
        What the default row is selected for: the table and its filter values.

        Only with reclick="deselect" (else None, and the default row is selected
        whenever nothing is). A row the user deselected is then not selected again
        until the scope changes, e.g. the table is filtered to another spectrum.
        """
        if self._reclick != "deselect":
            return None
        identifiers = [*self._filters, *self._range_filters]
        return (self._cache_id, *(repr(state.get(i)) for i in identifiers))

    def get_initial_selection(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """
        Compute the initial selection for this table WITHOUT triggering Vue updates.

        Only returns a value on INITIAL LOAD when:
        - Table has interactivity configured
        - default_row >= 0 (not disabled)
        - No selection already exists for any interactivity identifier
        - Not awaiting a required filter value
        - No pagination state exists yet (truly initial load, not page navigation)

        This is safe because:
        - We compute from the same data _prepare_vue_data() returns
        - Initial load always shows page 1 with default sort
        - No user-applied column filters exist yet

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict mapping identifier names to their initial values,
            or None if no initial selection should be set.
        """
        # Skip if no interactivity or default_row disabled
        if (
            not self._interactivity
            or self._default_row < 0
            or not self._default_row_selects
        ):
            return None

        # Skip if selection already exists for ANY interactivity identifier
        for identifier in self._interactivity.keys():
            if state.get(identifier) is not None:
                return None

        # Skip if NOT initial load (pagination state exists = user already interacted)
        # This ensures we only pre-compute for the true first render
        pagination_state = state.get(self._pagination_identifier)
        if pagination_state is not None:
            return None

        # Skip if awaiting required filter (no data to select from)
        for identifier in self._filters.keys():
            filter_value = state.get(identifier)
            has_default = self._filter_defaults and identifier in self._filter_defaults
            if filter_value is None and not has_default:
                return None

        # Get first page data and extract default row values
        try:
            vue_data = self._prepare_vue_data(state)
            if not self._pagination:
                # tableData holds the rows unsorted; the browser sorts them
                return vue_data.get("_auto_selection") or None
            table_data = vue_data.get("tableData")
            if table_data is None or len(table_data) == 0:
                return None

            # Clamp to available rows
            default_idx = min(self._default_row, len(table_data) - 1)
            if default_idx < 0:
                return None

            result = {}
            for identifier, column in self._interactivity.items():
                if column in table_data.columns:
                    value = table_data[column].iloc[default_idx]
                    # Convert numpy types to Python types for JSON serialization
                    if hasattr(value, "item"):
                        value = value.item()
                    result[identifier] = value

            return result if result else None

        except Exception:
            # If anything fails, let Vue handle it normally
            return None

    def _preprocess(self) -> None:
        """
        Preprocess table data.

        Sorts by filter columns for efficient predicate pushdown, then
        collects the LazyFrame and generates column definitions if needed.
        Also computes column metadata for server-side filtering in filter dialogs.
        Data is cached by base class for fast subsequent loads.
        """
        data = self._raw_data

        # Sort by filter columns for efficient predicate pushdown.
        # This clusters identical filter values together, enabling Polars
        # to skip row groups that don't contain the target value when
        # filtering by selection state. Stable, so the rows of one filter value
        # keep their order (sorting them again keeps that order on ties).
        if self._filters:
            sort_columns = list(self._filters.values())
            data = data.sort(sort_columns, maintain_order=True)

        # Collect schema for auto-generating column definitions if needed
        schema = data.collect_schema()

        if self._column_definitions is None:
            # Auto-generate column definitions from schema
            self._column_definitions = []
            for name, dtype in zip(schema.names(), schema.dtypes(), strict=True):
                col_def: dict[str, Any] = {
                    "field": name,
                    "title": name.replace("_", " ").title(),
                    "headerTooltip": True,
                }
                # Set sorter based on data type
                if dtype in (
                    pl.Int8,
                    pl.Int16,
                    pl.Int32,
                    pl.Int64,
                    pl.UInt8,
                    pl.UInt16,
                    pl.UInt32,
                    pl.UInt64,
                    pl.Float32,
                    pl.Float64,
                ):
                    col_def["sorter"] = "number"
                    col_def["hozAlign"] = "right"
                elif dtype == pl.Boolean:
                    col_def["sorter"] = "boolean"
                elif dtype in (pl.Date, pl.Datetime, pl.Time):
                    col_def["sorter"] = "date"
                else:
                    col_def["sorter"] = "string"

                self._column_definitions.append(col_def)

        # Store column definitions in preprocessed data for serialization
        self._preprocessed_data["column_definitions"] = self._column_definitions

        # Compute column metadata for server-side filter dialogs
        # This is computed once at preprocessing time and cached
        column_metadata: dict[str, dict[str, Any]] = {}
        for name, dtype in zip(schema.names(), schema.dtypes(), strict=True):
            meta: dict[str, Any] = {}

            if dtype in (
                pl.Int8,
                pl.Int16,
                pl.Int32,
                pl.Int64,
                pl.UInt8,
                pl.UInt16,
                pl.UInt32,
                pl.UInt64,
                pl.Float32,
                pl.Float64,
            ):
                # Numeric column - compute min/max and unique count
                stats = data.select(
                    [
                        pl.col(name).min().alias("min"),
                        pl.col(name).max().alias("max"),
                        pl.col(name).n_unique().alias("n_unique"),
                    ]
                ).collect()
                min_val = stats["min"][0]
                max_val = stats["max"][0]
                n_unique = stats["n_unique"][0]

                # If few unique values, treat as categorical
                if n_unique is not None and n_unique <= 10:
                    meta["type"] = "categorical"
                    unique_vals = (
                        data.select(pl.col(name))
                        .unique()
                        .sort(name)
                        .collect()
                        .to_series()
                        .to_list()
                    )
                    meta["unique_values"] = [v for v in unique_vals if v is not None][
                        :100
                    ]
                else:
                    meta["type"] = "numeric"
                    if min_val is not None:
                        meta["min"] = float(min_val)
                    if max_val is not None:
                        meta["max"] = float(max_val)
            elif dtype == pl.Utf8:
                # String column - check unique count
                n_unique = data.select(pl.col(name).n_unique()).collect().item()
                if n_unique is not None and n_unique <= 50:
                    meta["type"] = "categorical"
                    unique_vals = (
                        data.select(pl.col(name))
                        .unique()
                        .sort(name, nulls_last=True)
                        .collect()
                        .to_series()
                        .to_list()
                    )
                    meta["unique_values"] = [
                        v for v in unique_vals if v is not None and v != ""
                    ][:100]
                else:
                    meta["type"] = "text"
            elif dtype == pl.Boolean:
                meta["type"] = "categorical"
                meta["unique_values"] = [True, False]
            else:
                meta["type"] = "text"

            column_metadata[name] = meta

        self._preprocessed_data["column_metadata"] = column_metadata

        # Auto-detect go-to fields if not explicitly provided
        if self._go_to_fields is None:
            self._go_to_fields = self._auto_detect_go_to_fields(data)
        elif self._go_to_fields == []:
            # Explicitly disabled - keep empty list
            pass
        # else: use user-provided list as-is

        # Store LazyFrame for streaming to disk (filter happens at render time)
        # Base class will use sink_parquet() to stream without full materialization
        self._preprocessed_data["data"] = data  # Keep lazy

    def _auto_detect_go_to_fields(self, data: pl.LazyFrame) -> list[str]:
        """
        Auto-detect columns suitable for go-to navigation.

        Criteria:
        - Integer or String (Utf8) type only (excludes Float)
        - 100% unique values (no duplicates)
        - Samples first 10,000 rows for performance

        Args:
            data: LazyFrame to analyze for unique columns

        Returns:
            List of column names in original schema order
        """
        schema = data.collect_schema()
        sample = data.head(10000)

        candidates = []
        for col_name in schema.names():
            dtype = schema[col_name]

            # Only Integer and String types (exclude Float)
            if dtype not in (
                pl.Int8,
                pl.Int16,
                pl.Int32,
                pl.Int64,
                pl.UInt8,
                pl.UInt16,
                pl.UInt32,
                pl.UInt64,
                pl.Utf8,
            ):
                continue

            # Check 100% uniqueness in sample
            stats = sample.select(
                [
                    pl.col(col_name).len().alias("count"),
                    pl.col(col_name).n_unique().alias("n_unique"),
                ]
            ).collect()

            count = stats["count"][0]
            n_unique = stats["n_unique"][0]

            # Must be 100% unique (count == n_unique)
            if count > 0 and count == n_unique:
                candidates.append(col_name)

        return candidates

    def _get_columns_to_select(self) -> list[str] | None:
        """Get list of columns needed for this table."""
        if not self._column_definitions:
            return None

        # Once per field: a field may be shown in more than one column
        columns_to_select = list(
            dict.fromkeys(
                col_def["field"]
                for col_def in self._column_definitions
                if "field" in col_def
            )
        )
        # Always include index field for row identification
        if self._index_field and self._index_field not in columns_to_select:
            columns_to_select.append(self._index_field)
        # Include columns needed for interactivity
        if self._interactivity:
            for col in self._interactivity.values():
                if col not in columns_to_select:
                    columns_to_select.append(col)
        # Include columns needed for filtering
        if self._filters:
            for col in self._filters.values():
                if col not in columns_to_select:
                    columns_to_select.append(col)

        return columns_to_select if columns_to_select else None

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        return "TabulatorTable"

    def _get_data_key(self) -> str:
        """Return the key used to send primary data to Vue."""
        return "tableData"

    def _prepare_vue_data(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Prepare table data for Vue component with server-side pagination.

        Implements streaming pagination where only the current page of data
        is sent to the frontend. Handles server-side sorting, column filtering,
        and cross-component selection navigation.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with tableData (pandas DataFrame), _hash, _pagination metadata,
            and optional _navigate_to_page/_target_row_index for selection navigation
        """
        import time

        logger.info(f"[Table._prepare_vue_data] ===== START ===== ts={time.time()}")
        logger.info(f"[Table._prepare_vue_data] cache_id={self._cache_id}")
        logger.info(
            f"[Table._prepare_vue_data] pagination_identifier={self._pagination_identifier}"
        )
        pagination_state_for_log = state.get(self._pagination_identifier)
        logger.info(
            f"[Table._prepare_vue_data] pagination_state={pagination_state_for_log}"
        )

        # Get columns to select for projection pushdown
        columns = self._get_columns_to_select()

        # Get cached data (DataFrame or LazyFrame)
        data = self._preprocessed_data.get("data")
        if data is None:
            data = self._raw_data

        # Ensure we have a LazyFrame for filtering
        if isinstance(data, pl.DataFrame):
            data = data.lazy()

        # Column projection is applied after filtering and sorting (Polars pushes
        # it down anyway), so a CSV export can still see every cached column.
        def project(frame: pl.LazyFrame) -> pl.LazyFrame:
            if columns:
                schema_names = frame.collect_schema().names()
                available_cols = [c for c in columns if c in schema_names]
                if available_cols:
                    return frame.select(available_cols)
            return frame

        # Apply cross-component filters (from self._filters)
        for identifier, column in self._filters.items():
            selected_value = state.get(identifier)
            # Apply default if value is None and default exists
            if (
                selected_value is None
                and self._filter_defaults
                and identifier in self._filter_defaults
            ):
                selected_value = self._filter_defaults[identifier]

            if selected_value is None:
                # No selection for this filter - return empty DataFrame
                df_polars = project(data).head(0).collect()
                data_hash = compute_dataframe_hash(df_polars)
                return {
                    "tableData": df_polars.to_pandas(),
                    "_hash": data_hash,
                    "_pagination": {
                        "page": 1,
                        "page_size": self._page_size,
                        "total_rows": 0,
                        "total_pages": 0,
                    },
                    "_auto_selection": {},  # No data = no auto-selection
                }

            # Convert float to int for integer columns (JS numbers come as floats)
            if isinstance(selected_value, float) and selected_value.is_integer():
                selected_value = int(selected_value)
            data = data.filter(pl.col(column) == selected_value)

        data = self._apply_range_filters(data, state)

        # Get pagination state
        pagination_state = state.get(self._pagination_identifier)
        if pagination_state is None:
            pagination_state = {}

        # Rows before the toggle filters, for moving a selection a toggle hid
        # to another row of the same group
        untoggled_data = data

        page = pagination_state.get("page", 1)
        page_size = pagination_state.get("page_size", self._page_size)
        sort_column = pagination_state.get("sort_column")
        sort_dir = pagination_state.get("sort_dir", "asc")
        column_filters = pagination_state.get("column_filters", [])
        go_to_request = pagination_state.get("go_to_request")
        download_request = pagination_state.get("download_request")

        data = self._apply_toggle_filters(data, pagination_state)
        data = self._apply_column_filters(data, column_filters)
        # Without pagination Tabulator sorts the rows itself, starting each sort
        # from the order they arrive in (it keeps that order on ties), so they
        # are sent unsorted
        unsorted_data = data
        data = self._apply_sort(data, sort_column, sort_dir)

        # Full-table CSV export: every row that passes the current filters, in the
        # current sort order, with every cached column (not just the current page
        # and the displayed columns, which is all Tabulator's own download sees).
        download_payload = None
        if download_request is not None:
            download_payload = {
                "request_id": download_request,
                "filename": f"{self._title or self._cache_id}.csv",
                "csv": csv_safe(self._order_export_columns(data.collect())).write_csv(),
            }

        data = project(data)

        # Get total row count (after filters, before pagination)
        total_rows = data.select(pl.len()).collect().item()
        if not self._pagination:
            # Every row in one page; Tabulator sorts and filters them itself
            page, page_size = 1, max(total_rows, 1)
        total_pages = max(1, (total_rows + page_size - 1) // page_size)

        # Handle go-to request (server-side search for row by field value)
        navigate_to_page = None
        target_row_index = None
        go_to_not_found = False

        if go_to_request:
            go_to_field = go_to_request.get("field")
            go_to_value = go_to_request.get("value")
            if go_to_field and go_to_value is not None:
                # Only convert to numeric if the target column is numeric
                schema = data.collect_schema()
                if go_to_field in schema and schema[go_to_field] in NUMERIC_DTYPES:
                    try:
                        go_to_value = float(go_to_value)
                        if go_to_value.is_integer():
                            go_to_value = int(go_to_value)
                    except (ValueError, TypeError):
                        # Non-numeric string for numeric column - mark as not found
                        go_to_not_found = True
                # If column is string (Utf8), keep go_to_value as-is

                # Only search if we have a valid value (not already marked as not found)
                if not go_to_not_found:
                    # Find the row with row_number
                    search_result = (
                        data.with_row_index("_row_num")
                        .filter(pl.col(go_to_field) == go_to_value)
                        .select("_row_num")
                        .head(1)
                        .collect()
                    )

                    if len(search_result) > 0:
                        row_num = search_result["_row_num"][0]
                        target_page = (row_num // page_size) + 1
                        navigate_to_page = target_page
                        target_row_index = row_num % page_size
                        page = target_page  # Jump to target page
                    else:
                        # Row not found - set flag for Vue to show "not found" feedback
                        go_to_not_found = True

        # === Selection and Sort/Filter based navigation ===
        # PURPOSE: When user sorts/filters, find where the selected row ended up and navigate there
        if self._interactivity and self._pagination:
            import json

            import streamlit as st

            # Initialize tracking dicts (per-component storage)
            if _LAST_SELECTION_KEY not in st.session_state:
                st.session_state[_LAST_SELECTION_KEY] = {}
            if _LAST_SORT_FILTER_KEY not in st.session_state:
                st.session_state[_LAST_SORT_FILTER_KEY] = {}

            component_key = self._cache_id  # Unique key for this table instance

            # Get PREVIOUS states (from last render)
            last_selections = st.session_state[_LAST_SELECTION_KEY].get(
                component_key, {}
            )
            last_sort_filter = st.session_state[_LAST_SORT_FILTER_KEY].get(
                component_key, {}
            )

            # Build CURRENT selection state
            current_selections = {}
            for identifier in self._interactivity.keys():
                current_selections[identifier] = state.get(identifier)

            # Build CURRENT sort/filter state
            # Use JSON for column_filters to enable deep comparison of nested dicts
            current_sort_filter = {
                "sort_column": sort_column,
                "sort_dir": sort_dir,
                "column_filters_json": json.dumps(column_filters, sort_keys=True),
            }
            if self._toggle_filters:
                current_sort_filter["toggles"] = self._toggle_states(pagination_state)

            # DETECT what changed by comparing current vs previous
            selection_changed = current_selections != last_selections
            sort_filter_changed = current_sort_filter != last_sort_filter

            # CRITICAL: Update tracking state AFTER detecting changes
            # This prevents infinite loops: next render will see no change
            st.session_state[_LAST_SELECTION_KEY][component_key] = current_selections
            st.session_state[_LAST_SORT_FILTER_KEY][component_key] = current_sort_filter

            # DECIDE whether to navigate
            # - Don't override go_to navigation (user explicitly requested a row)
            # - Navigate if selection changed (find new selection's page)
            # - Navigate if sort/filter changed AND we have a selection (find existing selection's new page)
            should_navigate = False
            if navigate_to_page is None:
                if selection_changed:
                    should_navigate = True
                elif sort_filter_changed and any(
                    v is not None for v in current_selections.values()
                ):
                    should_navigate = True

            if should_navigate:
                # PRIORITY: Use index_field for navigation if available
                # index_field is guaranteed unique, so we get the correct row position
                # Find the interactivity identifier that maps to index_field column
                nav_identifier = None
                nav_column = None
                if self._index_field:
                    for ident, col in self._interactivity.items():
                        if col == self._index_field:
                            nav_identifier = ident
                            nav_column = col
                            break

                # Fall back to first interactivity identifier if no index_field match
                if nav_identifier is None:
                    for ident, col in self._interactivity.items():
                        if state.get(ident) is not None:
                            nav_identifier = ident
                            nav_column = col
                            break

                if nav_identifier is not None and nav_column is not None:
                    selected_value = state.get(nav_identifier)
                    if selected_value is not None:
                        # Type conversion based on column dtype (same logic as go-to)
                        schema = data.collect_schema()
                        if nav_column in schema:
                            col_dtype = schema[nav_column]
                            if col_dtype in NUMERIC_DTYPES:
                                # Column is numeric - convert value to numeric if possible
                                if isinstance(selected_value, str):
                                    try:
                                        selected_value = float(selected_value)
                                        if selected_value.is_integer():
                                            selected_value = int(selected_value)
                                    except (ValueError, TypeError):
                                        pass
                                elif (
                                    isinstance(selected_value, float)
                                    and selected_value.is_integer()
                                ):
                                    selected_value = int(selected_value)
                            else:
                                # Column is string - convert value to string
                                if not isinstance(selected_value, str):
                                    selected_value = str(selected_value)

                        # SEARCH for the selected row in the sorted/filtered data
                        # with_row_index adds position so we know which page it's on
                        search_result = (
                            data.with_row_index("_row_num")
                            .filter(pl.col(nav_column) == selected_value)
                            .select("_row_num")
                            .head(1)
                            .collect()
                        )

                        if len(search_result) > 0:
                            # ROW FOUND - update page in pagination state if needed
                            row_num = search_result["_row_num"][0]
                            target_page = (row_num // page_size) + 1
                            if target_page != page:
                                # Update pagination state directly (same as Vue would)
                                state_manager = self._active_state_manager()
                                updated_pagination = {
                                    **pagination_state,
                                    "page": target_page,
                                }
                                state_manager.set_selection(
                                    self._pagination_identifier, updated_pagination
                                )
                                navigate_to_page = target_page
                                target_row_index = row_num % page_size
                                page = target_page  # Use new page for slicing
                        else:
                            # ROW NOT FOUND - it was filtered out
                            # Update selection to first row's value AND set page to 1
                            if sort_filter_changed and not selection_changed:
                                first_row_result = self._group_replacement_row(
                                    untoggled_data,
                                    data,
                                    nav_column,
                                    selected_value,
                                    last_sort_filter.get("toggles"),
                                    current_sort_filter.get("toggles"),
                                )
                                if first_row_result is None:
                                    first_row_result = (
                                        data.select(pl.col(nav_column))
                                        .head(1)
                                        .collect()
                                    )
                                if len(first_row_result) > 0:
                                    first_value = first_row_result[nav_column][0]
                                    if hasattr(first_value, "item"):
                                        first_value = first_value.item()

                                    state_manager = self._active_state_manager()

                                    # Update selection to first row
                                    state_manager.set_selection(
                                        nav_identifier, first_value
                                    )

                                    # Update pagination state to page 1
                                    updated_pagination = {
                                        **pagination_state,
                                        "page": 1,
                                    }
                                    state_manager.set_selection(
                                        self._pagination_identifier, updated_pagination
                                    )
                                    page = 1  # Use page 1 for slicing

        # Clamp page to valid range
        page = max(1, min(page, total_pages))

        # Compute auto-selection from first row (before pagination)
        # This provides the first row's values for interactivity columns
        # so downstream components can receive initial data when filters change
        auto_selection: dict[str, Any] = {}
        # default_row=-1: nothing is selected until the user clicks a row
        if (
            self._interactivity
            and total_rows > 0
            and self._default_row >= 0
            and self._default_row_selects
        ):
            # Get the first row of sorted/filtered data. Without pagination the
            # browser shows every row, sorted, and highlights default_row.
            if self._pagination:
                first_row = data.head(1).collect()
            else:
                first_row = data.slice(
                    min(self._default_row, total_rows - 1), 1
                ).collect()
            if first_row.height > 0:
                for identifier, column in self._interactivity.items():
                    if column in first_row.columns:
                        value = first_row[column][0]
                        # Convert numpy/polars types to Python types for JSON
                        if hasattr(value, "item"):
                            value = value.item()
                        auto_selection[identifier] = value

        # Slice to current page
        offset = (page - 1) * page_size
        if self._pagination:
            df_polars = data.slice(offset, page_size).collect()
        else:
            df_polars = project(unsorted_data).collect()

        # Compute hash for change detection
        data_hash = compute_dataframe_hash(df_polars)
        if download_payload is not None:
            # A view that holds this page already is only sent data with a new
            # hash, and the export has to reach it
            data_hash = f"{data_hash}-download-{download_request}"

        # Build result
        result: dict[str, Any] = {
            "tableData": df_polars.to_pandas(),
            "_hash": data_hash,
            "_pagination": {
                "page": page,
                "page_size": page_size,
                "total_rows": total_rows,
                "total_pages": total_pages,
                "sort_column": sort_column,
                "sort_dir": sort_dir,
                **(
                    {"toggles": self._toggle_states(pagination_state)}
                    if self._toggle_filters
                    else {}
                ),
            },
            "_auto_selection": auto_selection,
        }

        if navigate_to_page is not None:
            result["_navigate_to_page"] = navigate_to_page
        if target_row_index is not None:
            result["_target_row_index"] = target_row_index
        if go_to_not_found:
            result["_go_to_not_found"] = True
        if download_payload is not None:
            result["_download"] = download_payload

        logger.info(
            f"[Table._prepare_vue_data] Returning: page={page}, total_rows={total_rows}, data_rows={len(df_polars)}"
        )
        logger.info(
            f"[Table._prepare_vue_data] hash={data_hash[:8] if data_hash else 'None'}"
        )
        return result

    def _group_replacement_row(
        self,
        untoggled_data: pl.LazyFrame,
        data: pl.LazyFrame,
        nav_column: str,
        selected_value: Any,
        last_toggles: dict[str, bool] | None,
        current_toggles: dict[str, bool] | None,
    ) -> pl.DataFrame | None:
        """
        Find the row that takes over a selection hidden by ticking a toggle filter.

        Only toggles with a ``group_column`` do this: the selection moves to the first
        visible row sharing the hidden row's value in that column. Returns a
        one-row frame of ``nav_column``, or None to fall back to the first row.
        """
        if not current_toggles:
            return None
        for toggle in self._toggle_filters:
            column = toggle["column"]
            group_column = toggle.get("group_column")
            switched_on = current_toggles.get(column) and not (
                (last_toggles or {}).get(column, toggle["default"])
                if last_toggles is not None
                else False
            )
            if not group_column or not switched_on:
                continue
            group = (
                untoggled_data.filter(pl.col(nav_column) == selected_value)
                .select(pl.col(group_column))
                .head(1)
                .collect()
            )
            if group.height == 0:
                continue
            replacement = (
                data.filter(pl.col(group_column) == group[group_column][0])
                .select(pl.col(nav_column))
                .head(1)
                .collect()
            )
            if replacement.height > 0:
                return replacement
        return None

    def _active_state_manager(self):
        """The StateManager this table is being rendered with.

        Navigation (moving to the selected row's page, replacing a selection that
        was filtered out) writes state while preparing data. It must go to the
        manager the table was rendered with, not the default one, so that tables
        rendered with their own StateManager work.
        """
        from openms_insight.core.state import get_render_state_manager

        return get_render_state_manager()

    def _apply_range_filters(
        self, data: pl.LazyFrame, state: dict[str, Any]
    ) -> pl.LazyFrame:
        """Keep rows whose [start, end] range contains each set range selection."""
        for identifier, (start_column, end_column) in self._range_filters.items():
            value = state.get(identifier)
            if value is None:
                continue
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            data = data.filter(
                (pl.col(start_column) <= value) & (pl.col(end_column) >= value)
            )
        return data

    def _apply_validation_filters(
        self, data: pl.LazyFrame, state: dict[str, Any]
    ) -> pl.LazyFrame:
        """Restrictions beyond ``filters`` that the bridge validates selections against.

        Range filters hide rows the way a filter does, so a selection outside the
        range is dropped (and the table's default row takes over). Toggle filters
        are not included: the table itself moves a selection they hide.
        """
        return self._apply_range_filters(data, state)

    def _toggle_states(self, pagination_state: dict[str, Any]) -> dict[str, bool]:
        """Current on/off state of each toggle filter, keyed by column."""
        requested = pagination_state.get("toggles") or {}
        return {
            toggle["column"]: bool(requested.get(toggle["column"], toggle["default"]))
            for toggle in self._toggle_filters
        }

    def _apply_toggle_filters(
        self, data: pl.LazyFrame, pagination_state: dict[str, Any]
    ) -> pl.LazyFrame:
        """Keep rows whose column is true for every ticked toggle filter."""
        for column, enabled in self._toggle_states(pagination_state).items():
            if enabled:
                data = data.filter(pl.col(column))
        return data

    @staticmethod
    def _apply_column_filters(
        data: pl.LazyFrame, column_filters: list[dict[str, Any]]
    ) -> pl.LazyFrame:
        """Apply the filter dialog's column filters to ``data``."""
        for col_filter in column_filters:
            field = col_filter.get("field")
            filter_type = col_filter.get("type")
            value = col_filter.get("value")

            if not field or value is None:
                continue

            if filter_type == "in" and isinstance(value, list):
                # Categorical filter - match any of the values
                data = data.filter(pl.col(field).is_in(value))
            elif filter_type == ">=":
                data = data.filter(pl.col(field) >= value)
            elif filter_type == "<=":
                data = data.filter(pl.col(field) <= value)
            elif filter_type == "regex":
                # Text search with regex - invalid patterns match nothing
                try:
                    re.compile(value)
                    data = data.filter(pl.col(field).str.contains(value, literal=False))
                except re.error:
                    # Invalid regex pattern - filter to empty result
                    data = data.filter(pl.lit(False))
        return data

    def _apply_sort(
        self, data: pl.LazyFrame, sort_column: str | None, sort_dir: str = "asc"
    ) -> pl.LazyFrame:
        """Sort by the user's column, falling back to ``initial_sort``."""
        if sort_column:
            # User-applied sort from pagination state takes precedence
            return data.sort(
                sort_column, descending=sort_dir == "desc", maintain_order=True
            )
        if self._initial_sort:
            # initial_sort is a list of dicts: [{"column": "mass", "dir": "desc"}, ...]
            sort_columns = [s["column"] for s in self._initial_sort]
            sort_descending = [
                s.get("dir", "asc") == "desc" for s in self._initial_sort
            ]
            return data.sort(
                sort_columns, descending=sort_descending, maintain_order=True
            )
        return data

    def _order_export_columns(self, df: pl.DataFrame) -> pl.DataFrame:
        """Put the displayed columns first, in display order, then the rest."""
        shown = [
            col_def["field"]
            for col_def in (self._column_definitions or [])
            if col_def.get("field") in df.columns
        ]
        shown = list(dict.fromkeys(shown))
        rest = [c for c in df.columns if c not in shown]
        return df.select(shown + rest)

    def export_data(self, state: dict[str, Any] | None = None) -> pl.DataFrame:
        """
        Return the table's full data for export.

        Unlike the rendered table, this is not limited to the current page or
        to the columns in ``column_definitions``: every cached column and every
        row is included, displayed columns first.

        Args:
            state: Selection state to apply, as the table would when rendered.
                Cross-component ``filters`` whose selection is set, and the
                table's own pagination state (sort and column filters), are
                honoured. ``None`` exports the unfiltered table in its initial
                sort order.

        Returns:
            Polars DataFrame, ready for ``write_csv()`` / ``write_parquet()``.
            For a CSV that people open in a spreadsheet, pass it through
            ``csv_safe()`` first, as the in-table download does.
        """
        state = state or {}
        data = self._preprocessed_data.get("data")
        if data is None:
            data = self._raw_data
        if isinstance(data, pl.DataFrame):
            data = data.lazy()

        for identifier, column in self._filters.items():
            selected_value = state.get(identifier)
            if selected_value is None and self._filter_defaults:
                selected_value = self._filter_defaults.get(identifier)
            if selected_value is None:
                continue
            if isinstance(selected_value, float) and selected_value.is_integer():
                selected_value = int(selected_value)
            data = data.filter(pl.col(column) == selected_value)
        data = self._apply_range_filters(data, state)

        pagination_state = state.get(self._pagination_identifier) or {}
        data = self._apply_toggle_filters(data, pagination_state)
        data = self._apply_column_filters(
            data, pagination_state.get("column_filters", [])
        )
        data = self._apply_sort(
            data,
            pagination_state.get("sort_column"),
            pagination_state.get("sort_dir", "asc"),
        )
        return self._order_export_columns(data.collect())

    def _get_component_args(self) -> dict[str, Any]:
        """
        Get component arguments to send to Vue.

        Returns:
            Dict with all table configuration for Vue
        """
        # Get column definitions (may have been loaded from cache)
        column_defs = self._column_definitions
        if column_defs is None:
            column_defs = self._preprocessed_data.get("column_definitions", [])

        # Get column metadata for filter dialogs (computed during preprocessing)
        column_metadata = self._preprocessed_data.get("column_metadata", {})

        args: dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "columnDefinitions": column_defs,
            "tableIndexField": self._index_field,
            "tableLayoutParam": self._layout,
            "defaultRow": self._default_row,
            # Pass interactivity so Vue knows which identifier to update on row click
            "interactivity": self._interactivity,
            # Pagination settings - always use server-side pagination
            "pagination": self._pagination,
            "pageSize": self._page_size,
            "paginationIdentifier": self._pagination_identifier,
            # Column metadata for filter dialogs (precomputed unique values, min/max)
            "columnMetadata": column_metadata,
        }

        if self._title:
            args["title"] = self._title

        if self._go_to_fields:
            args["goToFields"] = self._go_to_fields

        if self._initial_sort:
            args["initialSort"] = self._initial_sort

        if self._hidden_columns:
            args["hiddenColumns"] = self._hidden_columns
        if not self._column_menu:
            args["columnMenu"] = False
        if self._reset_sort:
            args["resetSort"] = True
        if self._reset_sort_on:
            args["resetSortOn"] = self._reset_sort_on

        # Add any extra config options
        args.update(self._config)
        for key in (
            "toggle_filters",
            "range_filters",
            "on_select",
            "reclick",
            "default_row_selects",
            "scroll_position",
            "column_menu",
            "reset_sort",
            "reset_sort_on",
        ):
            args.pop(key, None)

        if self._toggle_filters:
            args["toggleFilters"] = self._toggle_filters
        if self._on_select:
            args["onSelect"] = self._on_select
        if self._reclick != "keep":
            args["reclick"] = self._reclick
        if not self._default_row_selects:
            args["highlightDefaultRow"] = True
        if self._scroll_position != "center":
            args["scrollPosition"] = self._scroll_position

        return args

    def with_column_formatter(
        self,
        field: str,
        formatter: str,
        formatter_params: dict[str, Any] | None = None,
    ) -> "Table":
        """
        Add or update a column formatter.

        Args:
            field: Column field name
            formatter: Tabulator formatter name
            formatter_params: Optional formatter parameters

        Returns:
            Self for method chaining
        """
        for col_def in self._column_definitions or []:
            if col_def.get("field") == field:
                col_def["formatter"] = formatter
                if formatter_params:
                    col_def["formatterParams"] = formatter_params
                break
        return self

    def with_money_format(
        self,
        field: str,
        precision: int = 2,
        symbol: str = "",
        thousand: str = ",",
        decimal: str = ".",
    ) -> "Table":
        """
        Format a column as currency/money.

        Args:
            field: Column field name
            precision: Number of decimal places
            symbol: Currency symbol (default: none)
            thousand: Thousands separator
            decimal: Decimal separator

        Returns:
            Self for method chaining
        """
        return self.with_column_formatter(
            field,
            "money",
            {
                "precision": precision,
                "symbol": symbol,
                "thousand": thousand,
                "decimal": decimal,
            },
        )

    def with_progress_bar(
        self,
        field: str,
        min_val: float = 0,
        max_val: float = 100,
        color: str | None = None,
    ) -> "Table":
        """
        Format a column as a progress bar.

        Args:
            field: Column field name
            min_val: Minimum value
            max_val: Maximum value
            color: Bar color (CSS color string)

        Returns:
            Self for method chaining
        """
        params: dict[str, Any] = {"min": min_val, "max": max_val}
        if color:
            params["color"] = color
        return self.with_column_formatter(field, "progress", params)
