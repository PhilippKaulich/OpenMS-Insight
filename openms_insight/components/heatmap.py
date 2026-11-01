"""Heatmap component using Plotly scattergl."""

from typing import Any

import polars as pl

from ..core.base import BaseComponent
from ..core.cache import atomic_write
from ..core.registry import register_component
from ..preprocessing.compression import (
    compute_compression_levels,
    compute_optimal_bins,
    downsample_2d,
    downsample_2d_simple,
    downsample_2d_streaming,
    get_data_range,
)
from ..preprocessing.filtering import (
    compute_dataframe_hash,
    filter_and_collect_cached,
    from_pandas_safe,
)


# Cache key only includes zoom state (not other selections)
def _make_zoom_cache_key(zoom: dict[str, Any] | None) -> tuple:
    """Create hashable cache key from zoom state."""
    if zoom is None:
        return (None,)
    return (
        ("x0", zoom.get("xRange", [-1, -1])[0]),
        ("x1", zoom.get("xRange", [-1, -1])[1]),
        ("y0", zoom.get("yRange", [-1, -1])[0]),
        ("y1", zoom.get("yRange", [-1, -1])[1]),
    )


@register_component("heatmap")
class Heatmap(BaseComponent):
    """
    Interactive 2D scatter/heatmap component using Plotly scattergl.

    Designed for large datasets (millions of points) using multi-resolution
    preprocessing with zoom-based level selection. Points are colored by
    intensity using a log-scale colormap.

    Features:
    - Multi-resolution downsampling for large datasets
    - Zoom-based automatic level selection
    - Click-to-select with cross-component linking
    - Log-scale intensity colormap
    - SVG export

    Example:
        heatmap = Heatmap(
            cache_id="peaks_heatmap",
            data=peaks_df,
            x_column='retention_time',
            y_column='mass',
            intensity_column='intensity',
            interactivity={
                'spectrum': 'scan_id',
                'peak': 'mass',
            },
            title="Peak Heatmap",
        )
        heatmap(state_manager=state_manager)
    """

    _component_type: str = "heatmap"

    def __init__(
        self,
        cache_id: str,
        x_column: str | None = None,
        y_column: str | None = None,
        data: pl.LazyFrame | None = None,
        data_path: str | None = None,
        intensity_column: str | None = None,
        filters: dict[str, str] | None = None,
        filter_defaults: dict[str, Any] | None = None,
        interactivity: dict[str, str] | None = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        min_points: int = 10000,
        display_aspect_ratio: float = 16 / 9,
        x_bins: int | None = None,
        y_bins: int | None = None,
        zoom_identifier: str = "heatmap_zoom",
        title: str | None = None,
        x_label: str | None = None,
        y_label: str | None = None,
        colorscale: str = "Portland",
        reversescale: bool = False,
        use_simple_downsample: bool = False,
        use_streaming: bool = True,
        categorical_filters: list[str] | None = None,
        category_column: str | None = None,
        category_colors: dict[str, str] | None = None,
        log_scale: bool = True,
        low_values_on_top: bool = False,
        intensity_label: str | None = None,
        levels: list[pl.LazyFrame] | None = None,
        downsample_zoomed: bool = True,
        svg_filename: str | None = None,
        scroll_zoom: bool = True,
        **kwargs,
    ):
        """
        Initialize the Heatmap component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
                Creates a folder {cache_path}/{cache_id}/ for cached data.
            x_column: Name of column for x-axis values
            y_column: Name of column for y-axis values
            data: Polars LazyFrame with heatmap data. Optional if cache exists.
            data_path: Path to parquet file (preferred for large datasets).
            intensity_column: Name of column for intensity/color values
            filters: Mapping of identifier names to column names for filtering
            interactivity: Mapping of identifier names to column names for clicks.
                When a point is clicked, sets each identifier to the clicked
                point's value in the corresponding column.
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            min_points: Target number of points to display (default: 10000).
                Cache levels are built at 2× this value; final downsample
                at render time reduces to exactly min_points.
            display_aspect_ratio: Expected display width/height ratio for
                optimal bin computation during caching (default: 16/9).
                At render time, the actual zoom region's aspect ratio is used.
            x_bins: Number of bins along x-axis for downsampling. If None
                (default), auto-computed from display_aspect_ratio such that
                x_bins × y_bins ≈ 2×min_points with even spatial distribution.
            y_bins: Number of bins along y-axis for downsampling. If None
                (default), auto-computed from display_aspect_ratio.
            zoom_identifier: State key for storing zoom range (default: 'heatmap_zoom')
            title: Heatmap title displayed above the plot
            x_label: X-axis label (defaults to x_column)
            y_label: Y-axis label (defaults to y_column)
            colorscale: Plotly colorscale name (default: 'Portland')
            use_simple_downsample: If True, use simple top-N downsampling instead
                of spatial binning (doesn't require scipy)
            use_streaming: If True (default), use streaming downsampling that
                stays lazy until render time. Reduces memory on init.
            categorical_filters: List of filter identifiers that should have
                per-value compression levels. This ensures constant point counts
                are sent to the client regardless of filter selection. Should be
                used for filters with a small number of unique values (<20).
                Example: ['im_dimension'] for ion mobility filtering.
            category_column: Optional column name for categorical coloring.
                When provided, points are colored by discrete category values
                instead of the continuous intensity colorscale. Useful for
                condition-based heatmaps (e.g., coloring by sample group).
            category_colors: Optional mapping of category values to colors.
                Keys should match values in category_column.
                Values should be CSS color strings (e.g., '#FF0000', 'red').
                If not provided, default Plotly colors will be used.
            log_scale: If True (default), apply log10 transformation to intensity
                values for color mapping. Set to False for linear color mapping.
            low_values_on_top: If True, invert the intensity priority for both downsampling
                and display order. Default False keeps high-intensity points during
                downsampling and draws them on top. Set to True when lower values are
                "better" (e.g., e-values, PEP scores, q-values) so that low values are
                preserved during downsampling and appear on top of high values.
            intensity_label: Custom label for the colorbar. Default is "Intensity".
                Useful when displaying non-intensity values like scores or counts.
            levels: Downsampled versions of ``data`` the caller has computed already,
                smallest first. They are stored as the resolution levels as given,
                with ``data`` as the full-resolution level, instead of being built
                from ``data``. Each needs the columns of ``data``. Requires ``data``
                and cannot be combined with ``categorical_filters``.
            downsample_zoomed: If False, a zoomed view shows every point of the
                first level with at least min_points points in the zoomed range,
                instead of downsampling them to min_points.
            svg_filename: File name for the SVG download (default: title).
            scroll_zoom: If False, the mouse wheel scrolls the page instead of
                zooming the plot.
            **kwargs: Additional configuration options
        """
        if levels is not None and data is None:
            raise ValueError("levels= requires data= to be provided")
        if levels is not None and categorical_filters:
            raise ValueError("levels= cannot be combined with categorical_filters")
        self._precomputed_levels = levels
        self._downsample_zoomed = downsample_zoomed
        self._x_column = x_column
        self._y_column = y_column
        self._intensity_column = intensity_column
        self._min_points = min_points
        self._display_aspect_ratio = display_aspect_ratio
        self._x_bins = x_bins
        self._y_bins = y_bins
        self._zoom_identifier = zoom_identifier
        self._title = title
        self._x_label = x_label or x_column
        self._y_label = y_label or y_column
        self._colorscale = colorscale
        self._reversescale = reversescale
        self._use_simple_downsample = use_simple_downsample
        self._category_column = category_column
        self._category_colors = category_colors or {}
        self._svg_filename = svg_filename
        self._scroll_zoom = scroll_zoom
        self._log_scale = log_scale
        self._low_values_on_top = low_values_on_top
        self._intensity_label = intensity_label
        self._use_streaming = use_streaming
        self._categorical_filters = categorical_filters or []

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
            x_column=x_column,
            y_column=y_column,
            intensity_column=intensity_column,
            min_points=min_points,
            display_aspect_ratio=display_aspect_ratio,
            x_bins=x_bins,
            y_bins=y_bins,
            zoom_identifier=zoom_identifier,
            title=title,
            x_label=x_label,
            y_label=y_label,
            colorscale=colorscale,
            use_simple_downsample=use_simple_downsample,
            use_streaming=use_streaming,
            categorical_filters=categorical_filters,
            category_column=category_column,
            category_colors=category_colors,
            downsample_zoomed=downsample_zoomed,
            svg_filename=svg_filename,
            scroll_zoom=scroll_zoom,
            **kwargs,
        )

    def _get_cache_config(self) -> dict[str, Any]:
        """
        Get configuration that affects cache validity.

        Returns:
            Dict of config values that affect preprocessing
        """
        return {
            "x_column": self._x_column,
            "y_column": self._y_column,
            "intensity_column": self._intensity_column,
            "min_points": self._min_points,
            "display_aspect_ratio": self._display_aspect_ratio,
            "x_bins": self._x_bins,
            "y_bins": self._y_bins,
            "use_simple_downsample": self._use_simple_downsample,
            "use_streaming": self._use_streaming,
            "categorical_filters": sorted(self._categorical_filters),
            "zoom_identifier": self._zoom_identifier,
            "title": self._title,
            "x_label": self._x_label,
            "y_label": self._y_label,
            "colorscale": self._colorscale,
            "category_column": self._category_column,
            "log_scale": self._log_scale,
            "low_values_on_top": self._low_values_on_top,
            "intensity_label": self._intensity_label,
            # Note: category_colors is render-time styling, doesn't affect cache
            # Only when set, so caches built without levels keep their hash
            **(
                {"precomputed_levels": len(self._precomputed_levels)}
                if self._precomputed_levels is not None
                else {}
            ),
            **({"downsample_zoomed": False} if not self._downsample_zoomed else {}),
            # Only when set, so caches built without them keep their hash; stored
            # so a component loaded from its cache keeps them
            **({"svg_filename": self._svg_filename} if self._svg_filename else {}),
            **({"scroll_zoom": False} if not self._scroll_zoom else {}),
        }

    def _restore_cache_config(self, config: dict[str, Any]) -> None:
        """Restore component-specific configuration from cached config."""
        self._x_column = config.get("x_column")
        self._y_column = config.get("y_column")
        self._intensity_column = config.get("intensity_column", "intensity")
        self._min_points = config.get("min_points", 10000)
        self._display_aspect_ratio = config.get("display_aspect_ratio", 16 / 9)
        # x_bins/y_bins are computed during preprocessing and stored in cache
        # Fallback to old defaults for backward compatibility with old caches
        self._x_bins = config.get("x_bins", 400)
        self._y_bins = config.get("y_bins", 50)
        self._use_simple_downsample = config.get("use_simple_downsample", False)
        self._use_streaming = config.get("use_streaming", True)
        self._categorical_filters = config.get("categorical_filters", [])
        self._zoom_identifier = config.get("zoom_identifier", "heatmap_zoom")
        self._title = config.get("title")
        self._x_label = config.get("x_label", self._x_column)
        self._y_label = config.get("y_label", self._y_column)
        self._colorscale = config.get("colorscale", "Portland")
        self._category_column = config.get("category_column")
        self._log_scale = config.get("log_scale", True)
        self._low_values_on_top = config.get("low_values_on_top", False)
        self._intensity_label = config.get("intensity_label")
        self._downsample_zoomed = config.get("downsample_zoomed", True)
        self._svg_filename = config.get("svg_filename")
        self._scroll_zoom = config.get("scroll_zoom", True)
        # category_colors is not stored in cache (render-time styling)

    def get_state_dependencies(self) -> list:
        """
        Return list of state keys that affect this component's data.

        Heatmaps depend on both filters (like other components) and
        the zoom state, which determines which resolution level is used.

        Returns:
            List of state identifier keys including zoom_identifier
        """
        deps = list(self._filters.keys()) if self._filters else []
        deps.append(self._zoom_identifier)
        return deps

    def _preprocess(self) -> None:
        """
        Preprocess heatmap data by computing multi-resolution levels.

        This is STAGE 1 processing. In streaming mode (default), levels stay
        as lazy LazyFrames and are only collected at render time. In non-streaming
        mode, levels are eagerly computed for faster rendering but higher memory.

        If categorical_filters is specified, creates separate compression levels
        for each unique value of those filters, ensuring constant point counts
        regardless of filter selection.
        """
        if self._categorical_filters:
            self._preprocess_with_categorical_filters()
        elif self._precomputed_levels is not None:
            self._preprocess_precomputed()
        elif self._use_streaming:
            self._preprocess_streaming()
        else:
            self._preprocess_eager()

    def _build_cascading_levels(
        self,
        source_data: pl.LazyFrame,
        level_sizes: list,
        x_range: tuple,
        y_range: tuple,
        cache_dir,
        prefix: str = "level",
    ) -> dict:
        """
        Build cascading compression levels from source data.

        Each level is built from the previous larger level rather than from
        raw data. This is efficient (raw data read once) and produces identical
        results because the downsampling keeps top N highest-intensity points
        per bin - points surviving at larger levels will also be selected at
        smaller levels.

        Args:
            source_data: LazyFrame with raw/filtered data
            level_sizes: List of target sizes for compressed levels (smallest first)
            x_range: (x_min, x_max) for consistent bin boundaries
            y_range: (y_min, y_max) for consistent bin boundaries
            cache_dir: Path to save parquet files
            prefix: Filename prefix (e.g., "level" or "cat_level_im_0")

        Returns:
            Dict with level LazyFrames keyed by "{prefix}_{idx}" and "num_levels"
        """
        import sys

        result = {}
        num_compressed = len(level_sizes)

        # Get total count
        total = source_data.select(pl.len()).collect().item()

        # First: save full resolution as the largest level
        full_res_path = cache_dir / f"{prefix}_{num_compressed}.parquet"
        full_res = source_data.sort([self._x_column, self._y_column])
        # Atomic: a reader with this level mapped must not have it truncated underneath
        # it. The cascade reads each level back to build the next, so the file is only
        # scanned after the rename has completed.
        with atomic_write(full_res_path) as tmp:
            full_res.sink_parquet(tmp, compression="zstd")
        print(
            f"[HEATMAP] Saved {prefix}_{num_compressed} ({total:,} pts)",
            file=sys.stderr,
        )

        # Start cascading from full resolution
        current_source = pl.scan_parquet(full_res_path)
        current_size = total

        # Build compressed levels from largest to smallest
        for i, target_size in enumerate(reversed(level_sizes)):
            level_idx = num_compressed - 1 - i
            level_path = cache_dir / f"{prefix}_{level_idx}.parquet"

            # If target size equals or exceeds current, just copy reference
            if target_size >= current_size:
                level = current_source
            elif self._use_simple_downsample:
                level = downsample_2d_simple(
                    current_source,
                    max_points=target_size,
                    intensity_column=self._intensity_column,
                    descending=not self._low_values_on_top,
                )
            else:
                level = downsample_2d_streaming(
                    current_source,
                    max_points=target_size,
                    x_column=self._x_column,
                    y_column=self._y_column,
                    intensity_column=self._intensity_column,
                    x_bins=self._x_bins,
                    y_bins=self._y_bins,
                    x_range=x_range,
                    y_range=y_range,
                    descending=not self._low_values_on_top,
                )

            # Sort and save immediately
            level = level.sort([self._x_column, self._y_column])
            with atomic_write(level_path) as tmp:
                level.sink_parquet(tmp, compression="zstd")

            print(
                f"[HEATMAP] Saved {prefix}_{level_idx} (target {target_size:,} pts)",
                file=sys.stderr,
            )

            # Next iteration uses this level as source (cascading)
            current_source = pl.scan_parquet(level_path)
            current_size = target_size

        # Load all levels back as LazyFrames
        for i in range(num_compressed + 1):
            level_path = cache_dir / f"{prefix}_{i}.parquet"
            result[f"{prefix}_{i}"] = pl.scan_parquet(level_path)

        result["num_levels"] = num_compressed + 1

        return result

    def _preprocess_with_categorical_filters(self) -> None:
        """
        Preprocess with per-filter-value compression levels using cascading.

        For each unique value of each categorical filter, creates separate
        compression levels using cascading (building smaller levels from larger).
        This ensures that when a filter is applied at render time, the resulting
        data has ~min_points regardless of the filter value selected.

        Uses cascading downsampling for efficiency - each level is built from
        the previous larger level rather than from raw data.

        Data is sorted by x, y columns for efficient range query predicate pushdown.

        Example: For im_dimension with values [0, 1, 2, 3], creates:
        - cat_level_im_dimension_0_0: 20K points with im_id=0
        - cat_level_im_dimension_0_1: 20K points with im_id=1
        - etc.
        """
        import sys

        # Get data ranges (for the full dataset)
        # These ranges are used for ALL levels to ensure consistent binning
        x_range, y_range = get_data_range(
            self._raw_data,
            self._x_column,
            self._y_column,
        )
        self._preprocessed_data["x_range"] = x_range
        self._preprocessed_data["y_range"] = y_range

        # Compute optimal bins if not provided
        # Cache at 2×min_points, use display_aspect_ratio for bin computation
        cache_target = 2 * self._min_points
        if self._x_bins is None or self._y_bins is None:
            # Use display aspect ratio (not data aspect ratio) for optimal bins
            self._x_bins, self._y_bins = compute_optimal_bins(
                cache_target,
                (0, self._display_aspect_ratio),  # Fake x_range matching aspect
                (0, 1.0),  # Fake y_range
            )
            print(
                f"[HEATMAP] Auto-computed bins: {self._x_bins}x{self._y_bins} "
                f"= {self._x_bins * self._y_bins:,} (cache target: {cache_target:,}, "
                f"display aspect: {self._display_aspect_ratio:.2f})",
                file=sys.stderr,
            )

        # Get total count
        total = self._raw_data.select(pl.len()).collect().item()
        self._preprocessed_data["total"] = total

        # Create cache directory for immediate level saving
        cache_dir = self._cache_dir / "preprocessed"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Store metadata about categorical filters
        self._preprocessed_data["has_categorical_filters"] = True
        self._preprocessed_data["categorical_filter_values"] = {}

        # Process each categorical filter
        for filter_id in self._categorical_filters:
            if filter_id not in self._filters:
                print(
                    f"[HEATMAP] Warning: categorical_filter '{filter_id}' not in filters, skipping",
                    file=sys.stderr,
                )
                continue

            column_name = self._filters[filter_id]

            # Get unique values for this filter
            unique_values = (
                self._raw_data.select(pl.col(column_name))
                .unique()
                .collect()
                .to_series()
                .to_list()
            )
            unique_values = sorted(
                [v for v in unique_values if v is not None and v >= 0]
            )

            print(
                f"[HEATMAP] Categorical filter '{filter_id}' ({column_name}): {len(unique_values)} unique values",
                file=sys.stderr,
            )

            self._preprocessed_data["categorical_filter_values"][filter_id] = (
                unique_values
            )

            # Create compression levels for each filter value using cascading
            for filter_value in unique_values:
                # Filter data to this value
                filtered_data = self._raw_data.filter(
                    pl.col(column_name) == filter_value
                )
                filtered_total = filtered_data.select(pl.len()).collect().item()

                # Compute level sizes for this filtered subset (2× for cache buffer)
                level_sizes = compute_compression_levels(cache_target, filtered_total)

                print(
                    f"[HEATMAP]   Value {filter_value}: {filtered_total:,} pts → levels {level_sizes}",
                    file=sys.stderr,
                )

                # Store level sizes for this filter value
                self._preprocessed_data[
                    f"cat_level_sizes_{filter_id}_{filter_value}"
                ] = level_sizes

                # Build cascading levels using helper
                prefix = f"cat_level_{filter_id}_{filter_value}"
                levels_result = self._build_cascading_levels(
                    source_data=filtered_data,
                    level_sizes=level_sizes,
                    x_range=x_range,
                    y_range=y_range,
                    cache_dir=cache_dir,
                    prefix=prefix,
                )

                # Copy results to preprocessed_data
                for key, value in levels_result.items():
                    if key == "num_levels":
                        self._preprocessed_data[
                            f"cat_num_levels_{filter_id}_{filter_value}"
                        ] = value
                    else:
                        self._preprocessed_data[key] = value

        # Also create global levels for when no categorical filter is selected
        # (fallback to standard behavior) - using cascading with 2× cache buffer
        level_sizes = compute_compression_levels(cache_target, total)
        self._preprocessed_data["level_sizes"] = level_sizes

        # Build global cascading levels using helper
        levels_result = self._build_cascading_levels(
            source_data=self._raw_data,
            level_sizes=level_sizes,
            x_range=x_range,
            y_range=y_range,
            cache_dir=cache_dir,
            prefix="level",
        )

        # Copy results to preprocessed_data
        for key, value in levels_result.items():
            if key == "num_levels":
                self._preprocessed_data["num_levels"] = value
            else:
                self._preprocessed_data[key] = value

        # Mark that files are already saved
        self._preprocessed_data["_files_already_saved"] = True

    def _preprocess_streaming(self) -> None:
        """
        Streaming preprocessing with cascading - builds smaller levels from larger.

        Uses cascading downsampling: each level is built from the previous larger
        level rather than from raw data. This is more efficient (raw data read once)
        and produces identical results because the downsampling algorithm keeps
        the TOP N highest-intensity points per bin - points that survive at a larger
        level will also be selected at smaller levels.

        Levels are saved to disk immediately after creation, then read back as the
        source for the next smaller level. This keeps memory low while enabling
        cascading.

        Data is sorted by x, y columns for efficient range query predicate pushdown.
        """
        import sys

        # Get data ranges (minimal collect - just 4 values)
        # These ranges are used for ALL levels to ensure consistent binning
        x_range, y_range = get_data_range(
            self._raw_data,
            self._x_column,
            self._y_column,
        )
        self._preprocessed_data["x_range"] = x_range
        self._preprocessed_data["y_range"] = y_range

        # Compute optimal bins if not provided
        # Cache at 2×min_points, use display_aspect_ratio for bin computation
        cache_target = 2 * self._min_points
        if self._x_bins is None or self._y_bins is None:
            # Use display aspect ratio (not data aspect ratio) for optimal bins
            # This ensures even distribution in the expected display dimensions
            self._x_bins, self._y_bins = compute_optimal_bins(
                cache_target,
                (0, self._display_aspect_ratio),  # Fake x_range matching aspect
                (0, 1.0),  # Fake y_range
            )
            print(
                f"[HEATMAP] Auto-computed bins: {self._x_bins}x{self._y_bins} "
                f"= {self._x_bins * self._y_bins:,} (cache target: {cache_target:,}, "
                f"display aspect: {self._display_aspect_ratio:.2f})",
                file=sys.stderr,
            )

        # Get total count
        total = self._raw_data.select(pl.len()).collect().item()
        self._preprocessed_data["total"] = total

        # Compute target sizes for levels (use 2×min_points for smallest cache level)
        level_sizes = compute_compression_levels(cache_target, total)
        self._preprocessed_data["level_sizes"] = level_sizes

        # Create cache directory for immediate level saving
        cache_dir = self._cache_dir / "preprocessed"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Build cascading levels using helper
        levels_result = self._build_cascading_levels(
            source_data=self._raw_data,
            level_sizes=level_sizes,
            x_range=x_range,
            y_range=y_range,
            cache_dir=cache_dir,
            prefix="level",
        )

        # Copy results to preprocessed_data
        for key, value in levels_result.items():
            if key == "num_levels":
                self._preprocessed_data["num_levels"] = value
            else:
                self._preprocessed_data[key] = value

        # Mark that files are already saved (base class should skip saving)
        self._preprocessed_data["_files_already_saved"] = True

    def _preprocess_precomputed(self) -> None:
        """
        Store the levels the caller downsampled, with the full data as the last.

        Bins are still computed, because a zoomed view with more points than
        min_points is downsampled at render time.
        """
        import sys

        x_range, y_range = get_data_range(
            self._raw_data,
            self._x_column,
            self._y_column,
        )
        self._preprocessed_data["x_range"] = x_range
        self._preprocessed_data["y_range"] = y_range

        if self._x_bins is None or self._y_bins is None:
            self._x_bins, self._y_bins = compute_optimal_bins(
                2 * self._min_points,
                (0, self._display_aspect_ratio),
                (0, 1.0),
            )

        self._preprocessed_data["total"] = (
            self._raw_data.select(pl.len()).collect().item()
        )

        columns = self._raw_data.collect_schema().names()
        levels = [
            (level.lazy() if isinstance(level, pl.DataFrame) else level).select(columns)
            for level in self._precomputed_levels
        ]
        self._preprocessed_data["level_sizes"] = [
            level.select(pl.len()).collect().item() for level in levels
        ]

        cache_dir = self._cache_dir / "preprocessed"
        cache_dir.mkdir(parents=True, exist_ok=True)
        for i, level in enumerate([*levels, self._raw_data]):
            level_path = cache_dir / f"level_{i}.parquet"
            with atomic_write(level_path) as tmp:
                level.sort([self._x_column, self._y_column]).sink_parquet(
                    tmp, compression="zstd"
                )
            self._preprocessed_data[f"level_{i}"] = pl.scan_parquet(level_path)
        self._preprocessed_data["num_levels"] = len(levels) + 1
        print(
            f"[HEATMAP] Stored {len(levels)} precomputed levels "
            f"{self._preprocessed_data['level_sizes']}",
            file=sys.stderr,
        )

        self._preprocessed_data["_files_already_saved"] = True

    def _preprocess_eager(self) -> None:
        """
        Eager preprocessing - levels are computed upfront.

        Uses more memory at init but faster rendering. Uses scipy-based
        downsampling for better spatial distribution.
        Data is sorted by x, y columns for efficient range query predicate pushdown.
        """
        import sys

        # Get data ranges
        x_range, y_range = get_data_range(
            self._raw_data,
            self._x_column,
            self._y_column,
        )
        self._preprocessed_data["x_range"] = x_range
        self._preprocessed_data["y_range"] = y_range

        # Compute optimal bins if not provided
        # Cache at 2×min_points, use display_aspect_ratio for bin computation
        cache_target = 2 * self._min_points
        if self._x_bins is None or self._y_bins is None:
            # Use display aspect ratio (not data aspect ratio) for optimal bins
            self._x_bins, self._y_bins = compute_optimal_bins(
                cache_target,
                (0, self._display_aspect_ratio),  # Fake x_range matching aspect
                (0, 1.0),  # Fake y_range
            )
            print(
                f"[HEATMAP] Auto-computed bins: {self._x_bins}x{self._y_bins} "
                f"= {self._x_bins * self._y_bins:,} (cache target: {cache_target:,}, "
                f"display aspect: {self._display_aspect_ratio:.2f})",
                file=sys.stderr,
            )

        # Get total count
        total = self._raw_data.select(pl.len()).collect().item()
        self._preprocessed_data["total"] = total

        # Compute compression level target sizes (2× for cache buffer)
        level_sizes = compute_compression_levels(cache_target, total)
        self._preprocessed_data["level_sizes"] = level_sizes

        # Build levels from largest to smallest
        if level_sizes:
            current = self._raw_data

            for i, size in enumerate(reversed(level_sizes)):
                # If target size equals total, skip downsampling - use all data
                if size >= total:
                    downsampled = current
                elif self._use_simple_downsample:
                    downsampled = downsample_2d_simple(
                        current,
                        max_points=size,
                        intensity_column=self._intensity_column,
                    )
                else:
                    downsampled = downsample_2d(
                        current,
                        max_points=size,
                        x_column=self._x_column,
                        y_column=self._y_column,
                        intensity_column=self._intensity_column,
                        x_bins=self._x_bins,
                        y_bins=self._y_bins,
                    )
                # Sort by x, y for efficient range query predicate pushdown
                if isinstance(downsampled, pl.LazyFrame):
                    downsampled = downsampled.sort([self._x_column, self._y_column])
                else:
                    downsampled = downsampled.sort([self._x_column, self._y_column])
                # Store LazyFrame for streaming to disk
                level_idx = len(level_sizes) - 1 - i
                if isinstance(downsampled, pl.LazyFrame):
                    self._preprocessed_data[f"level_{level_idx}"] = (
                        downsampled  # Keep lazy
                    )
                else:
                    # DataFrame from downsample_2d - convert back to lazy
                    self._preprocessed_data[f"level_{level_idx}"] = downsampled.lazy()
                current = downsampled

        # Add full resolution as final level (for zoom fallback)
        # Also sorted for consistent predicate pushdown behavior
        num_compressed = len(level_sizes)
        self._preprocessed_data[f"level_{num_compressed}"] = self._raw_data.sort(
            [self._x_column, self._y_column]
        )

        # Store number of levels for reconstruction (includes full resolution)
        self._preprocessed_data["num_levels"] = num_compressed + 1

    def _get_levels(self) -> list:
        """
        Get compression levels list for rendering.

        Reconstructs the levels list from preprocessed data,
        adding full resolution at the end.
        """
        num_levels = self._preprocessed_data.get("num_levels", 0)
        levels = []

        for i in range(num_levels):
            level_data = self._preprocessed_data.get(f"level_{i}")
            if level_data is not None:
                levels.append(level_data)

        return levels

    def _get_categorical_levels(
        self,
        filter_id: str,
        filter_value: Any,
    ) -> tuple[list, pl.LazyFrame | None]:
        """
        Get compression levels for a specific categorical filter value.

        Args:
            filter_id: The filter identifier (e.g., 'im_dimension')
            filter_value: The filter value to get levels for (e.g., 0)

        Returns:
            Tuple of (levels list, filtered raw data for full resolution)
            Returns ([], None) if no categorical levels exist for this filter
        """
        # Check if we have categorical levels for this filter/value
        num_levels_key = f"cat_num_levels_{filter_id}_{filter_value}"
        num_levels = self._preprocessed_data.get(num_levels_key, 0)

        if num_levels == 0:
            return [], None

        levels = []
        for i in range(num_levels):
            level_key = f"cat_level_{filter_id}_{filter_value}_{i}"
            level_data = self._preprocessed_data.get(level_key)
            if level_data is not None:
                levels.append(level_data)

        return levels, None  # Full resolution included in cached levels

    def _get_levels_for_state(
        self, state: dict[str, Any]
    ) -> tuple[list, pl.LazyFrame | None]:
        """
        Get appropriate compression levels based on current filter state.

        If categorical_filters are configured and a matching filter value is
        selected in state, returns the per-value levels. Otherwise returns
        the global levels.

        Args:
            state: Current selection state

        Returns:
            Tuple of (levels list, raw data for full resolution)
        """
        # Check if we have categorical filters and a selected value
        if self._preprocessed_data.get("has_categorical_filters"):
            cat_filter_values = self._preprocessed_data.get(
                "categorical_filter_values", {}
            )

            for filter_id in self._categorical_filters:
                if filter_id not in cat_filter_values:
                    continue

                selected_value = state.get(filter_id)
                if selected_value is None:
                    continue

                # Convert float to int if needed (JS numbers come as floats)
                if isinstance(selected_value, float) and selected_value.is_integer():
                    selected_value = int(selected_value)

                # Check if this value has per-filter levels
                if selected_value in cat_filter_values[filter_id]:
                    levels, filtered_raw = self._get_categorical_levels(
                        filter_id, selected_value
                    )
                    if levels:
                        return levels, filtered_raw

        # Fall back to global levels
        return self._get_levels(), self._raw_data

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        return "PlotlyHeatmap"

    def _get_data_key(self) -> str:
        """Return the key used to send primary data to Vue."""
        return "heatmapData"

    def _is_no_zoom(self, zoom: dict[str, Any] | None) -> bool:
        """Check if zoom state represents no zoom (full view)."""
        if zoom is None:
            return True
        x_range = zoom.get("xRange", [-1, -1])
        y_range = zoom.get("yRange", [-1, -1])
        return x_range[0] < 0 and x_range[1] < 0 and y_range[0] < 0 and y_range[1] < 0

    def _select_level_for_zoom(
        self,
        zoom: dict[str, Any],
        state: dict[str, Any],
        levels: list,
        filtered_raw: pl.LazyFrame | None,
        non_categorical_filters: dict[str, str],
    ) -> pl.DataFrame:
        """
        Select appropriate resolution level based on zoom range.

        Iterates from smallest to largest resolution, finding the smallest
        level that has at least min_points in the zoomed view.

        Args:
            zoom: Zoom state with xRange and yRange
            state: Full selection state for applying filters
            levels: List of compression levels to use
            filtered_raw: Filtered raw data for full resolution (optional)
            non_categorical_filters: Filters to apply (excluding categorical ones)

        Returns:
            Filtered Polars DataFrame at appropriate resolution
        """
        import sys

        x0, x1 = zoom["xRange"]
        y0, y1 = zoom["yRange"]

        # Add raw data as final level if available
        all_levels = list(levels)
        if filtered_raw is not None:
            all_levels.append(filtered_raw)

        last_filtered = None

        for level_idx, level_data in enumerate(all_levels):
            # Ensure we have a LazyFrame for filtering
            if isinstance(level_data, pl.DataFrame):
                level_data = level_data.lazy()

            # Filter to zoom range
            filtered_lazy = level_data.filter(
                (pl.col(self._x_column) >= x0)
                & (pl.col(self._x_column) <= x1)
                & (pl.col(self._y_column) >= y0)
                & (pl.col(self._y_column) <= y1)
            )

            # Apply non-categorical filters if any
            if non_categorical_filters:
                # filter_and_collect_cached returns (pandas DataFrame, hash)
                # We need Polars DataFrame for further processing
                df_pandas, _ = filter_and_collect_cached(
                    filtered_lazy,
                    non_categorical_filters,
                    state,
                    filter_defaults=self._filter_defaults,
                )
                # Guarded: concurrent pandas->polars conversion corrupts memory.
                filtered = from_pandas_safe(df_pandas)
            else:
                filtered = filtered_lazy.collect()

            count = len(filtered)
            last_filtered = filtered
            print(
                f"[HEATMAP] Level {level_idx}: {count} pts in zoom range",
                file=sys.stderr,
            )

            if count >= self._min_points:
                # This level has enough detail
                if count > self._min_points and self._downsample_zoomed:
                    # Over limit - downsample to exactly min_points
                    # Compute optimal bins from ACTUAL zoom region aspect ratio
                    zoom_x_range = (x0, x1)
                    zoom_y_range = (y0, y1)
                    render_x_bins, render_y_bins = compute_optimal_bins(
                        self._min_points, zoom_x_range, zoom_y_range
                    )
                    print(
                        f"[HEATMAP] Render downsample: {count:,} → {self._min_points:,} pts "
                        f"(bins: {render_x_bins}x{render_y_bins})",
                        file=sys.stderr,
                    )
                    if self._use_streaming or self._use_simple_downsample:
                        if self._use_simple_downsample:
                            return downsample_2d_simple(
                                filtered.lazy(),
                                max_points=self._min_points,
                                intensity_column=self._intensity_column,
                            ).collect()
                        else:
                            return downsample_2d_streaming(
                                filtered.lazy(),
                                max_points=self._min_points,
                                x_column=self._x_column,
                                y_column=self._y_column,
                                intensity_column=self._intensity_column,
                                x_bins=render_x_bins,
                                y_bins=render_y_bins,
                                x_range=zoom_x_range,
                                y_range=zoom_y_range,
                            ).collect()
                    else:
                        return downsample_2d(
                            filtered.lazy(),
                            max_points=self._min_points,
                            x_column=self._x_column,
                            y_column=self._y_column,
                            intensity_column=self._intensity_column,
                            x_bins=render_x_bins,
                            y_bins=render_y_bins,
                        ).collect()
                return filtered

        # Even largest level has fewer points than threshold
        return last_filtered if last_filtered is not None else pl.DataFrame()

    def _prepare_vue_data(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Prepare heatmap data for Vue component.

        Selects appropriate resolution level based on zoom state.
        If categorical_filters are configured, uses per-filter-value levels
        to ensure constant point counts regardless of filter selection.

        Returns pandas DataFrame for efficient Arrow serialization.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with heatmapData (pandas DataFrame) and _hash for change detection
        """
        import sys

        zoom = state.get(self._zoom_identifier)

        # Build columns to select (filter out None values)
        columns_to_select = [
            col
            for col in [self._x_column, self._y_column, self._intensity_column]
            if col is not None
        ]
        # Include category column if specified
        if self._category_column and self._category_column not in columns_to_select:
            columns_to_select.append(self._category_column)
        # Include columns needed for interactivity
        if self._interactivity:
            for col in self._interactivity.values():
                if col not in columns_to_select:
                    columns_to_select.append(col)
        # Include filter columns
        if self._filters:
            for col in self._filters.values():
                if col not in columns_to_select:
                    columns_to_select.append(col)

        # Get levels based on current state (may use per-filter levels)
        levels, filtered_raw = self._get_levels_for_state(state)
        level_sizes = [
            len(lvl) if isinstance(lvl, pl.DataFrame) else "?" for lvl in levels
        ]

        # Determine which filters still need to be applied at render time
        # (filters not in categorical_filters need runtime application)
        non_categorical_filters = {}
        if self._filters:
            for filter_id, column in self._filters.items():
                if filter_id not in self._categorical_filters:
                    non_categorical_filters[filter_id] = column

        if self._is_no_zoom(zoom):
            # No zoom - use smallest level
            if not levels:
                # No levels available
                print("[HEATMAP] No levels available", file=sys.stderr)
                return {"heatmapData": pl.DataFrame().to_pandas(), "_hash": ""}

            data = levels[0]
            using_cat = self._preprocessed_data.get("has_categorical_filters", False)
            print(
                f"[HEATMAP] No zoom → level 0 ({level_sizes[0]} pts), levels={level_sizes}, categorical={using_cat}",
                file=sys.stderr,
            )

            # Ensure we have a LazyFrame
            if isinstance(data, pl.DataFrame):
                data = data.lazy()

            # Apply non-categorical filters if any - returns (pandas DataFrame, hash)
            if non_categorical_filters:
                df_pandas, data_hash = filter_and_collect_cached(
                    data,
                    non_categorical_filters,
                    state,
                    columns=columns_to_select,
                    filter_defaults=self._filter_defaults,
                )
                # Sort for render order (last drawn = on top in scattergl)
                # Default: ascending (high on top). low_values_on_top: descending (low on top)
                if (
                    self._intensity_column
                    and self._intensity_column in df_pandas.columns
                ):
                    df_pandas = df_pandas.sort_values(
                        self._intensity_column, ascending=not self._low_values_on_top
                    ).reset_index(drop=True)
            else:
                # No filters to apply - levels already filtered by categorical filter
                schema_names = data.collect_schema().names()
                available_cols = [c for c in columns_to_select if c in schema_names]
                df_polars = data.select(available_cols).collect()
                # Sort for render order (last drawn = on top in scattergl)
                # Default: ascending (high on top). low_values_on_top: descending (low on top)
                if (
                    self._intensity_column
                    and self._intensity_column in df_polars.columns
                ):
                    df_polars = df_polars.sort(
                        self._intensity_column, descending=self._low_values_on_top
                    )
                data_hash = compute_dataframe_hash(df_polars)
                df_pandas = df_polars.to_pandas()
        else:
            # Zoomed - select appropriate level
            print(f"[HEATMAP] Zoom {zoom} → selecting level...", file=sys.stderr)
            df_polars = self._select_level_for_zoom(
                zoom, state, levels, filtered_raw, non_categorical_filters
            )
            # Select only needed columns
            available_cols = [c for c in columns_to_select if c in df_polars.columns]
            df_polars = df_polars.select(available_cols)
            # Sort for render order (last drawn = on top in scattergl)
            # Default: ascending (high on top). low_values_on_top: descending (low on top)
            if self._intensity_column and self._intensity_column in df_polars.columns:
                df_polars = df_polars.sort(
                    self._intensity_column, descending=self._low_values_on_top
                )
            print(
                f"[HEATMAP] Selected {len(df_polars)} pts for zoom, levels={level_sizes}",
                file=sys.stderr,
            )
            data_hash = compute_dataframe_hash(df_polars)
            df_pandas = df_polars.to_pandas()

        return {
            "heatmapData": df_pandas,
            "_hash": data_hash,
        }

    def _get_component_args(self) -> dict[str, Any]:
        """
        Get component arguments to send to Vue.

        Returns:
            Dict with all heatmap configuration for Vue
        """
        args: dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "xColumn": self._x_column,
            "yColumn": self._y_column,
            "intensityColumn": self._intensity_column,
            "xLabel": self._x_label,
            "yLabel": self._y_label,
            "colorscale": self._colorscale,
            "reversescale": self._reversescale,
            "zoomIdentifier": self._zoom_identifier,
            "interactivity": self._interactivity,
        }

        if self._title:
            args["title"] = self._title
        if self._svg_filename:
            args["svgFilename"] = self._svg_filename
        if not self._scroll_zoom:
            args["scrollZoom"] = False

        # Add category column configuration for categorical coloring mode
        if self._category_column:
            args["categoryColumn"] = self._category_column
            if self._category_colors:
                args["categoryColors"] = self._category_colors

        # Add log scale and intensity label configuration
        args["logScale"] = self._log_scale
        if self._intensity_label:
            args["intensityLabel"] = self._intensity_label

        # Add any extra config options
        args.update(self._config)

        return args

    def with_styling(
        self,
        colorscale: str | None = None,
        x_label: str | None = None,
        y_label: str | None = None,
    ) -> "Heatmap":
        """
        Update heatmap styling.

        Args:
            colorscale: Plotly colorscale name
            x_label: X-axis label
            y_label: Y-axis label

        Returns:
            Self for method chaining
        """
        if colorscale is not None:
            self._colorscale = colorscale
        if x_label is not None:
            self._x_label = x_label
        if y_label is not None:
            self._y_label = y_label
        return self
