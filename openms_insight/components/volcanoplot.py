"""VolcanoPlot component for differential expression visualization."""

from typing import Any

import polars as pl

from ..core.base import BaseComponent
from ..core.image_format import image_format_args, validate_image_format
from ..core.measure import (
    measure_args,
    validate_measure,
)
from ..core.multi_select import normalize_multi_select
from ..core.registry import register_component
from ..core.zoom import validate_zoom_identifier, zoom_args
from ..preprocessing.scatter import build_scatter_columns


@register_component("volcanoplot")
class VolcanoPlot(BaseComponent):
    """
    Interactive volcano plot for differential expression analysis.

    Displays log2 fold change (x-axis) vs -log10(p-value) (y-axis) with
    three-category coloring based on significance thresholds. Thresholds
    are passed at render time to avoid cache invalidation when adjusting
    sliders.

    Features:
    - Client-side significance computation (instant threshold updates)
    - Three-category coloring (up-regulated, down-regulated, not significant)
    - Threshold lines at ±fc_threshold and -log10(p_threshold)
    - Optional labels on significant points
    - Click-to-select with cross-component linking
    - SVG export

    Example:
        volcano = VolcanoPlot(
            cache_id="protein_volcano",
            data_path="proteins.parquet",
            log2fc_column="log2FC",
            pvalue_column="pvalue",
            label_column="protein_name",
            interactivity={'protein': 'protein_id'},
            filters={'comparison': 'comparison_id'},
        )

        # Thresholds passed at render time - no cache impact
        volcano(
            state_manager=state,
            fc_threshold=1.0,
            p_threshold=0.05,
            height=500,
        )
    """

    _supports_stepper = True

    _component_type: str = "volcanoplot"

    def __init__(
        self,
        cache_id: str,
        log2fc_column: str = "log2FC",
        pvalue_column: str = "pvalue",
        data: pl.LazyFrame | None = None,
        data_path: str | None = None,
        label_column: str | None = None,
        filters: dict[str, str] | None = None,
        filter_defaults: dict[str, Any] | None = None,
        interactivity: dict[str, str] | None = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        title: str | None = None,
        x_label: str | None = None,
        y_label: str | None = None,
        up_color: str = "#E74C3C",
        down_color: str = "#3498DB",
        ns_color: str = "#95A5A6",
        show_threshold_lines: bool = True,
        threshold_line_style: str = "dash",
        multi_select: dict[str, str] | None = None,
        selection_presets: bool = False,
        preset_labels: dict[str, str] | None = None,
        measure: bool = True,
        image_format: str | None = None,
        zoom_identifier: str | None = None,
        **kwargs,
    ):
        """
        Initialize the VolcanoPlot component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
                Creates a folder {cache_path}/{cache_id}/ for cached data.
            log2fc_column: Name of column for log2 fold change (x-axis).
            pvalue_column: Name of column for p-value. Will be transformed
                to -log10(pvalue) for display on y-axis.
            data: Polars LazyFrame with volcano data. Optional if cache exists.
            data_path: Path to parquet file (preferred for large datasets).
            label_column: Name of column for point labels (shown on hover and
                optionally as annotations on significant points).
            filters: Mapping of identifier names to column names for filtering.
                Example: {'comparison': 'comparison_id'} filters by comparison.
            filter_defaults: Default values for filter identifiers when no
                selection is present in state.
            interactivity: Mapping of identifier names to column names for clicks.
                When a point is clicked, sets each identifier to the clicked
                point's value in the corresponding column.
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            title: Plot title displayed above the volcano plot.
            x_label: X-axis label (default: "log2 Fold Change").
            y_label: Y-axis label (default: "-log10(p-value)").
            up_color: Color for up-regulated points (default: red #E74C3C).
            down_color: Color for down-regulated points (default: blue #3498DB).
            ns_color: Color for not significant points (default: gray #95A5A6).
            show_threshold_lines: Show threshold lines on plot (default: True).
            threshold_line_style: Line style for thresholds (default: "dash").
            multi_select: Mapping of identifier names to column names for
                selecting several points at once with Plotly's box and lasso
                select (mode bar; Shift adds to the selection). The identifier
                holds the sorted distinct values of the column over the
                selected points (None when none are), and the selected points
                are marked, whichever component chose them.
            selection_presets: With ``multi_select``, show buttons above the
                plot that select every significant, every up- or every
                down-regulated point (default: False).
            preset_labels: Labels of those buttons, keys "changed", "up",
                "down" and "clear" (defaults: "All changed", "Up", "Down",
                "Clear").
            measure: Show a "Measure" button in the mode bar (default True;
                False hides it). In measure mode, clicking two points draws a
                line between them labelled with their fold change and p-value
                differences (signed, second point minus first). Esc cancels a
                half-finished measurement, clicking a label removes it and
                "Clear measurements" removes all; they are cleared when other
                data is plotted and are part of the image download. With measure
                mode off, clicks select as before. Render-time only: not part
                of the cache.
            image_format: Format of the image download: 'svg', 'png', 'jpeg'
                or 'webp'. None (default) follows
                ``openms_insight.set_image_format()`` (default 'svg') when the
                component is drawn. Render-time only: not part of the cache.
            zoom_identifier: State identifier the plot keeps its zoom under,
                ``{"x": [lo, hi], "y": [lo, hi]}`` (default None: the zoom stays
                in the browser). The plot reports its ranges there after a zoom
                or pan and zooms to a value set there, e.g. by a saved view.
                Render-time only: not part of the cache.
            **kwargs: Additional configuration options.
        """
        self._log2fc_column = log2fc_column
        self._pvalue_column = pvalue_column
        self._label_column = label_column
        self._title = title
        self._x_label = x_label or "log2 Fold Change"
        self._y_label = y_label or "-log10(p-value)"
        self._up_color = up_color
        self._down_color = down_color
        self._ns_color = ns_color
        self._show_threshold_lines = show_threshold_lines
        self._threshold_line_style = threshold_line_style
        self._multi_select = normalize_multi_select(multi_select)
        self._selection_presets = bool(selection_presets)
        self._preset_labels = dict(preset_labels or {})

        # Render-time threshold values (set in __call__)
        self._current_fc_threshold: float = 1.0
        self._current_p_threshold: float = 0.05
        self._current_max_labels: int = 10

        # Computed -log10(pvalue) column name
        self._neglog10p_column = "_neglog10_pvalue"

        # Render-time options, kept out of the cache config (see core/measure.py)
        self._measure = validate_measure(measure)

        # Render-time option, kept out of the cache config (see core/image_format.py)
        self._image_format = validate_image_format(image_format, allow_none=True)

        # Render-time option, kept out of the cache config (see core/zoom.py)
        self._zoom_identifier = validate_zoom_identifier(zoom_identifier)

        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            filters=filters,
            filter_defaults=filter_defaults,
            interactivity=interactivity,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            multi_select=multi_select,
            selection_presets=selection_presets,
            preset_labels=preset_labels,
            **kwargs,
        )
        for key in ("multi_select", "selection_presets", "preset_labels"):
            self._config.pop(key, None)

    def _validate_columns(self, schema: pl.Schema) -> None:
        """Validate that required columns exist in the data schema."""
        available = set(schema.names())

        required = [self._log2fc_column, self._pvalue_column]
        missing = [col for col in required if col not in available]
        if missing:
            raise ValueError(
                f"Missing required columns: {missing}. "
                f"Available columns: {sorted(available)}"
            )

        for identifier, column in self._multi_select.items():
            if column not in available:
                raise ValueError(
                    f"multi_select column '{column}' for identifier "
                    f"'{identifier}' not found. Available columns: {sorted(available)}"
                )

        if self._label_column and self._label_column not in available:
            raise ValueError(
                f"Label column '{self._label_column}' not found. "
                f"Available columns: {sorted(available)}"
            )

    def _get_component_config_hash_inputs(self) -> dict[str, Any]:
        """Get inputs for component config hash (cache invalidation)."""
        return {
            "log2fc_column": self._log2fc_column,
            "pvalue_column": self._pvalue_column,
            "label_column": self._label_column,
            # Note: thresholds are NOT included - they're render-time params
        }

    def _get_cache_config(self) -> dict[str, Any]:
        """Get configuration that affects cache validity."""
        return {
            "log2fc_column": self._log2fc_column,
            "pvalue_column": self._pvalue_column,
            "label_column": self._label_column,
            "title": self._title,
            "x_label": self._x_label,
            "y_label": self._y_label,
            "up_color": self._up_color,
            "down_color": self._down_color,
            "ns_color": self._ns_color,
            "show_threshold_lines": self._show_threshold_lines,
            "threshold_line_style": self._threshold_line_style,
            # Only when set, so caches built without them keep their hash
            **({"multi_select": self._multi_select} if self._multi_select else {}),
            **({"selection_presets": True} if self._selection_presets else {}),
            **({"preset_labels": self._preset_labels} if self._preset_labels else {}),
        }

    def _extra_columns(self) -> list[str]:
        """Label and multi_select columns, carried along with the points."""
        extra = [self._label_column] if self._label_column else []
        extra += [c for c in self._multi_select.values() if c not in extra]
        return extra

    def _restore_cache_config(self, config: dict[str, Any]) -> None:
        """Restore component-specific configuration from cached config."""
        self._log2fc_column = config.get("log2fc_column", "log2FC")
        self._pvalue_column = config.get("pvalue_column", "pvalue")
        self._label_column = config.get("label_column")
        self._title = config.get("title")
        self._x_label = config.get("x_label", "log2 Fold Change")
        self._y_label = config.get("y_label", "-log10(p-value)")
        self._up_color = config.get("up_color", "#E74C3C")
        self._down_color = config.get("down_color", "#3498DB")
        self._ns_color = config.get("ns_color", "#95A5A6")
        self._show_threshold_lines = config.get("show_threshold_lines", True)
        self._threshold_line_style = config.get("threshold_line_style", "dash")
        self._multi_select = dict(config.get("multi_select") or {})
        self._selection_presets = bool(config.get("selection_presets", False))
        self._preset_labels = dict(config.get("preset_labels") or {})
        for key in ("multi_select", "selection_presets", "preset_labels"):
            self._config.pop(key, None)

    def _preprocess(self) -> None:
        """Preprocess data for volcano plot.

        Computes -log10(pvalue) and caches the result. No downsampling is
        typically needed for volcano plots (<10K proteins), but we handle
        it if datasets get large.
        """
        if self._raw_data is None:
            raise ValueError("No data provided and no cache exists")

        # Build list of columns to select
        # Note: pvalue is passed as y_column only (no duplicate value_column)
        extra_cols = self._extra_columns()
        columns = build_scatter_columns(
            x_column=self._log2fc_column,
            y_column=self._pvalue_column,
            value_column=self._pvalue_column,
            interactivity=self._interactivity,
            filters=self._filters,
            extra_columns=extra_cols if extra_cols else None,
        )
        # Remove duplicates while preserving order
        columns = list(dict.fromkeys(columns))

        # Select columns and compute -log10(pvalue)
        schema_names = self._raw_data.collect_schema().names()
        available_cols = [c for c in columns if c in schema_names]

        df = (
            self._raw_data.select(available_cols)
            .with_columns(
                pl.when(pl.col(self._pvalue_column) > 0)
                .then(-pl.col(self._pvalue_column).log(10))
                .otherwise(0.0)
                .alias(self._neglog10p_column)
            )
            .collect()
        )

        self._preprocessed_data = {"volcanoData": df}

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        return "PlotlyVolcano"

    def _get_data_key(self) -> str:
        """Return the key for the primary data in Vue payload."""
        return "volcanoData"

    def _prepare_vue_data(self, state: dict[str, Any]) -> dict[str, Any]:
        """Prepare filtered data for Vue component.

        Uses shared prepare_scatter_data for filtering and conversion.
        """
        if self._preprocessed_data is None or not self._preprocessed_data:
            self._load_preprocessed_data()

        data = self._preprocessed_data["volcanoData"]
        # Handle both LazyFrame (from cache) and DataFrame
        if isinstance(data, pl.LazyFrame):
            df_polars = data.collect()
        else:
            df_polars = data

        # Build columns to select (remove duplicates)
        extra_cols = self._extra_columns() + [self._pvalue_column]
        columns = build_scatter_columns(
            x_column=self._log2fc_column,
            y_column=self._neglog10p_column,
            value_column=self._neglog10p_column,
            interactivity=self._interactivity,
            filters=self._filters,
            extra_columns=extra_cols,
        )
        # Remove duplicates while preserving order
        columns = list(dict.fromkeys(columns))

        # Apply filters if any
        if self._filters:
            from ..preprocessing.filtering import (
                compute_dataframe_hash,
                filter_and_collect_cached,
            )

            df_pandas, data_hash = filter_and_collect_cached(
                df_polars.lazy(),
                self._filters,
                state,
                columns=columns,
                filter_defaults=self._filter_defaults,
            )

            # Sort by significance (most significant on top for rendering)
            if len(df_pandas) > 0 and self._neglog10p_column in df_pandas.columns:
                df_pandas = df_pandas.sort_values(
                    self._neglog10p_column, ascending=True
                ).reset_index(drop=True)

            return {"volcanoData": df_pandas, "_hash": data_hash}
        else:
            # No filters - select columns and convert to pandas
            available_cols = [c for c in columns if c in df_polars.columns]
            df_filtered = df_polars.select(available_cols)

            # Sort by significance
            if self._neglog10p_column in df_filtered.columns:
                df_filtered = df_filtered.sort(self._neglog10p_column, descending=False)

            from ..preprocessing.filtering import compute_dataframe_hash

            data_hash = compute_dataframe_hash(df_filtered)
            df_pandas = df_filtered.to_pandas()

            return {"volcanoData": df_pandas, "_hash": data_hash}

    def _get_component_args(self) -> dict[str, Any]:
        """Return configuration for Vue component."""
        args: dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "log2fcColumn": self._log2fc_column,
            "neglog10pColumn": self._neglog10p_column,
            "pvalueColumn": self._pvalue_column,
            "labelColumn": self._label_column,
            "title": self._title,
            "xLabel": self._x_label,
            "yLabel": self._y_label,
            "upColor": self._up_color,
            "downColor": self._down_color,
            "nsColor": self._ns_color,
            "showThresholdLines": self._show_threshold_lines,
            "thresholdLineStyle": self._threshold_line_style,
            # Render-time threshold values
            "fcThreshold": self._current_fc_threshold,
            "pThreshold": self._current_p_threshold,
            "maxLabels": self._current_max_labels,
            "interactivity": self._interactivity or {},
            **({"multiSelect": self._multi_select} if self._multi_select else {}),
            **({"selectionPresets": True} if self._selection_presets else {}),
            **({"presetLabels": self._preset_labels} if self._preset_labels else {}),
        }
        args.update(measure_args(self._measure))
        args.update(image_format_args(self._image_format))
        args.update(zoom_args(self._zoom_identifier))
        return args

    def __call__(
        self,
        key: str | None = None,
        state_manager: Any | None = None,
        height: int | None = None,
        fc_threshold: float = 1.0,
        p_threshold: float = 0.05,
        max_labels: int = 10,
    ) -> Any:
        """
        Render the volcano plot component.

        Args:
            key: Optional unique key for this component instance.
            state_manager: StateManager for cross-component linking.
            height: Optional height override in pixels.
            fc_threshold: Fold change threshold for significance
                (default: 1.0, meaning |log2FC| >= 1).
            p_threshold: P-value threshold for significance
                (default: 0.05). Points with p < threshold are significant.
            max_labels: Maximum number of labels to show on significant
                points (default: 10). Labels are shown for top N by
                significance.

        Returns:
            Component result for Streamlit rendering.
        """
        # Store render-time threshold values
        self._current_fc_threshold = fc_threshold
        self._current_p_threshold = p_threshold
        self._current_max_labels = max_labels

        # Update height if provided
        if height is not None:
            self._height = height

        return super().__call__(key=key, state_manager=state_manager, height=height)
