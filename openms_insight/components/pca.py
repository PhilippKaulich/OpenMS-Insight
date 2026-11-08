"""PCAPlot component for sample-level dimensionality reduction visualization."""

from typing import Any

import numpy as np
import polars as pl

from ..core.base import BaseComponent
from ..core.image_format import image_format_args, validate_image_format
from ..core.zoom import validate_zoom_identifier, zoom_args
from ..core.measure import (
    measure_args,
    validate_measure,
)
from ..core.registry import register_component


@register_component("pca")
class PCAPlot(BaseComponent):
    """
    Interactive PCA (Principal Component Analysis) scatter plot for samples.

    Computes PCA directly from a wide-format quantification matrix (rows =
    features/proteins, one column per sample) plus a sample metadata table
    (sample_id -> group), then renders sample scores colored by group.

    Rendering is handled by the dedicated PlotlyPca Vue component: one
    marker trace per group (for a proper legend), optional 95% confidence
    ellipses per group, and zero-reference lines on both axes.

    Which pair of principal components is displayed (pc_x/pc_y) can be
    changed at render time without invalidating the cache, similar to how
    VolcanoPlot handles its significance thresholds - PCA itself is only
    recomputed when the underlying data/metadata/n_components change.

    Example:
        pca = PCAPlot(
            cache_id="protein_pca",
            data=quantification_data,   # wide: id_col + one column per sample
            metadata=metadata_df,       # columns: sample_id, group
            interactivity={'sample': 'sample_id'},
            title="Sample PCA",
        )
        pca(state_manager=state, pc_x=1, pc_y=2)
    """

    _component_type: str = "pca"

    def __init__(
        self,
        cache_id: str,
        metadata: pl.DataFrame | None = None,
        data: pl.LazyFrame | None = None,
        data_path: str | None = None,
        sample_id_field: str = "sample_id",
        group_field: str = "group",
        n_components: int = 2,
        pc_x: int = 1,
        pc_y: int = 2,
        standardize: bool = True,
        filters: dict[str, str] | None = None,
        filter_defaults: dict[str, Any] | None = None,
        interactivity: dict[str, str] | None = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        title: str | None = None,
        x_label: str | None = None,
        y_label: str | None = None,
        group_colors: dict[str, str] | None = None,
        show_ellipses: bool = True,
        measure: bool = True,
        image_format: str | None = None,
        zoom_identifier: str | None = None,
        **kwargs,
    ):
        """
        Initialize the PCAPlot component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
                Creates a folder {cache_path}/{cache_id}/ for cached data.
            metadata: DataFrame mapping samples to groups. Must contain
                sample_id_field and group_field columns. Required whenever
                data/data_path is provided (creation mode).
            data: Polars LazyFrame with the quantification matrix in wide
                format (one row per feature/protein, one column per sample).
                Optional if cache exists.
            data_path: Path to parquet file (preferred for large datasets).
            sample_id_field: Column in `metadata` naming the sample columns
                to look up in `data` (default: "sample_id").
            group_field: Column in `metadata` with the group/condition label
                used for categorical coloring (default: "group").
            n_components: Number of principal components to compute
                (default: 2). Increase this to allow inspecting additional
                component pairs at render time via pc_x/pc_y without
                recomputing PCA.
            pc_x: Which principal component to plot on the x-axis, 1-indexed
                (default: 1, i.e. PC1). Can be overridden at render time.
            pc_y: Which principal component to plot on the y-axis, 1-indexed
                (default: 2, i.e. PC2). Can be overridden at render time.
            standardize: If True (default), z-score each feature across
                samples before fitting PCA (recommended when features are on
                different scales).
            filters: Mapping of identifier names to column names (of the
                computed PCA table: sample_id_field, group_field, PC1..PCn)
                for filtering.
            filter_defaults: Default values for filter identifiers when no
                selection is present in state.
            interactivity: Mapping of identifier names to column names (of
                the computed PCA table) for clicks.
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            title: Plot title displayed above the plot.
            x_label: X-axis label. Defaults to "PC{n} (xx.x%)" using the
                explained variance ratio.
            y_label: Y-axis label. Defaults to "PC{n} (xx.x%)" using the
                explained variance ratio.
            group_colors: Optional mapping of group values to colors
                (e.g. {"Control": "#1f77b4", "Treatment": "#d62728"}).
            show_ellipses: If True (default), draw a 95% confidence ellipse
                per group (only drawn for groups with >= 3 samples).
            measure: Show a "Measure" button in the mode bar (default True;
                False hides it). In measure mode, clicking two samples draws a
                line between them labelled with their differences along both
                components (signed, second point minus first). Esc cancels a
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
        if (data is not None or data_path is not None) and metadata is None:
            raise ValueError(
                "PCAPlot requires 'metadata' (sample_id/group table) when "
                "creating the cache (data= or data_path= provided)."
            )

        self._metadata = metadata
        self._sample_id_field = sample_id_field
        self._group_field = group_field
        self._n_components = n_components
        self._standardize = standardize
        self._title = title
        self._x_label = x_label
        self._y_label = y_label
        self._group_colors = group_colors or {}
        self._show_ellipses = show_ellipses

        # Render-time display selection (which PC pair to plot). Overridable
        # per-call via __call__() without invalidating the cache.
        self._current_pc_x = pc_x
        self._current_pc_y = pc_y

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
            # Pass component-specific params for subprocess recreation
            metadata=metadata,
            sample_id_field=sample_id_field,
            group_field=group_field,
            n_components=n_components,
            pc_x=pc_x,
            pc_y=pc_y,
            standardize=standardize,
            title=title,
            x_label=x_label,
            y_label=y_label,
            group_colors=group_colors,
            show_ellipses=show_ellipses,
            **kwargs,
        )

    def _validate_mappings(self) -> None:
        """Validate metadata presence; column-level checks happen after PCA runs.

        filters/interactivity map to columns of the COMPUTED PCA scores table
        (sample_id_field, group_field, PC1..PCn), not the raw wide-format
        quantification data, so we can't validate them against raw_data's
        schema the way BaseComponent does. See _preprocess() for the actual
        column checks, run once the PCA output schema is known.
        """
        if self._raw_data is None:
            return  # Skip validation when reconstructing from cache

        if self._metadata is None:
            raise ValueError(
                "PCAPlot requires 'metadata' (DataFrame with sample_id/group "
                "columns) in creation mode."
            )

        metadata_cols = set(self._metadata.columns)
        if self._sample_id_field not in metadata_cols:
            raise ValueError(
                f"metadata is missing sample_id_field '{self._sample_id_field}'. "
                f"Available columns: {sorted(metadata_cols)}"
            )
        if self._group_field not in metadata_cols:
            raise ValueError(
                f"metadata is missing group_field '{self._group_field}'. "
                f"Available columns: {sorted(metadata_cols)}"
            )

    def _get_cache_config(self) -> dict[str, Any]:
        """Get configuration that affects cache validity."""
        metadata_map: dict[str, Any] = {}
        if self._metadata is not None:
            sample_ids = (
                self._metadata.select(self._sample_id_field).to_series().to_list()
            )
            groups = self._metadata.select(self._group_field).to_series().to_list()
            metadata_map = {
                str(sid): grp for sid, grp in zip(sample_ids, groups, strict=True)
            }

        return {
            "metadata_map": metadata_map,
            "sample_id_field": self._sample_id_field,
            "group_field": self._group_field,
            "n_components": self._n_components,
            "standardize": self._standardize,
            "title": self._title,
            "x_label": self._x_label,
            "y_label": self._y_label,
            "group_colors": self._group_colors,
            "show_ellipses": self._show_ellipses,
            # Note: pc_x/pc_y are NOT included - they're render-time params
        }

    def _restore_cache_config(self, config: dict[str, Any]) -> None:
        """Restore component-specific configuration from cached config."""
        self._sample_id_field = config.get("sample_id_field", "sample_id")
        self._group_field = config.get("group_field", "group")
        self._n_components = config.get("n_components", 2)
        self._standardize = config.get("standardize", True)
        self._title = config.get("title")
        self._x_label = config.get("x_label")
        self._y_label = config.get("y_label")
        self._group_colors = config.get("group_colors", {})
        self._show_ellipses = config.get("show_ellipses", True)
        self._metadata = None  # not needed after PCA has been precomputed

        # Only set defaults if not already set by __init__ (reconstruction
        # mode calls this without pc_x/pc_y ever being passed)
        if not hasattr(self, "_current_pc_x"):
            self._current_pc_x = 1
        if not hasattr(self, "_current_pc_y"):
            self._current_pc_y = 2

    def _preprocess(self) -> None:
        """Compute PCA from the wide-format quantification matrix.

        Transposes the feature x sample matrix to sample x feature, optionally
        standardizes each feature, fits sklearn's PCA, and stores per-sample
        scores (PC1..PCn) alongside the sample's group label.
        """
        from sklearn.decomposition import PCA as SklearnPCA
        from sklearn.preprocessing import StandardScaler

        if self._raw_data is None:
            raise ValueError("No data provided and no cache exists")
        if self._metadata is None:
            raise ValueError("PCAPlot requires 'metadata' to compute PCA")

        schema_names = self._raw_data.collect_schema().names()

        all_sample_ids = (
            self._metadata.select(self._sample_id_field).to_series().to_list()
        )
        all_groups = self._metadata.select(self._group_field).to_series().to_list()
        group_map = dict(zip(all_sample_ids, all_groups, strict=True))

        sample_ids = [sid for sid in all_sample_ids if sid in schema_names]
        if len(sample_ids) < 2:
            raise ValueError(
                f"PCA requires at least 2 sample columns present in data; "
                f"found {len(sample_ids)} matching metadata "
                f"'{self._sample_id_field}' values. Available data columns: "
                f"{schema_names}"
            )

        # Drop features with any missing value across the selected samples
        matrix_df = self._raw_data.select(sample_ids).drop_nulls().collect()
        n_features = matrix_df.height
        n_samples = len(sample_ids)
        if n_features < 2:
            raise ValueError(
                "PCA requires at least 2 complete (non-null) features across "
                "all samples."
            )

        # features (rows) x samples (cols) -> samples (rows) x features (cols)
        X = matrix_df.to_numpy().T.astype(np.float64)

        if self._standardize:
            X = StandardScaler().fit_transform(X)

        max_components = min(n_samples, n_features)
        n_components = max(1, min(self._n_components, max_components))

        pca = SklearnPCA(n_components=n_components)
        scores = pca.fit_transform(X)
        variance_ratio = pca.explained_variance_ratio_.tolist()

        pc_columns = [f"PC{i + 1}" for i in range(n_components)]
        result: dict[str, list[Any]] = {
            self._sample_id_field: sample_ids,
            self._group_field: [group_map.get(sid) for sid in sample_ids],
        }
        for i, col in enumerate(pc_columns):
            result[col] = scores[:, i].tolist()

        pca_df = pl.DataFrame(result)

        final_cols = set(pca_df.columns)
        for identifier, column in {**self._filters, **self._interactivity}.items():
            if column not in final_cols:
                raise ValueError(
                    f"Column '{column}' (for identifier '{identifier}') not "
                    f"found in computed PCA data. Available columns: "
                    f"{sorted(final_cols)}"
                )

        self._preprocessed_data = {
            "pcaData": pca_df,
            "variance_ratio": variance_ratio,
            "n_components": n_components,
            "pc_columns": pc_columns,
        }

    def get_variance_ratio(self) -> list[float]:
        """Return the explained variance ratio for each computed principal component."""
        return list(self._preprocessed_data.get("variance_ratio", []))

    def get_pc_columns(self) -> list[str]:
        """Return names of computed principal component columns (e.g. ['PC1', 'PC2'])."""
        return list(self._preprocessed_data.get("pc_columns", []))

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        return "PlotlyPca"

    def _get_data_key(self) -> str:
        """Return the key for the primary data in Vue payload."""
        return "pcaData"

    def _prepare_vue_data(self, state: dict[str, Any]) -> dict[str, Any]:
        """Prepare filtered PCA scores for Vue component."""
        data = self._preprocessed_data["pcaData"]
        df_polars = data.collect() if isinstance(data, pl.LazyFrame) else data

        if self._filters:
            from ..preprocessing.filtering import filter_and_collect_cached

            df_pandas, data_hash = filter_and_collect_cached(
                df_polars.lazy(),
                self._filters,
                state,
                filter_defaults=self._filter_defaults,
            )
        else:
            from ..preprocessing.filtering import compute_dataframe_hash

            data_hash = compute_dataframe_hash(df_polars)
            df_pandas = df_polars.to_pandas()

        return {"pcaData": df_pandas, "_hash": data_hash}

    def _axis_label(
        self, pc_index: int, base_label: str | None, variance_ratio: list[float]
    ) -> str:
        """Build an axis label like 'PC1 (43.2%)' unless overridden."""
        if base_label:
            return base_label
        col = f"PC{pc_index}"
        if 0 <= pc_index - 1 < len(variance_ratio):
            return f"{col} ({variance_ratio[pc_index - 1] * 100:.1f}%)"
        return col

    def _get_component_args(self) -> dict[str, Any]:
        """Return configuration for the PlotlyPca Vue component."""
        variance_ratio = self._preprocessed_data.get("variance_ratio", [])
        pc_columns = self._preprocessed_data.get("pc_columns", [])

        pc_x_col = f"PC{self._current_pc_x}"
        pc_y_col = f"PC{self._current_pc_y}"
        if pc_x_col not in pc_columns or pc_y_col not in pc_columns:
            raise ValueError(
                f"pc_x={self._current_pc_x}/pc_y={self._current_pc_y} select "
                f"components beyond the {len(pc_columns)} computed "
                f"(n_components={self._n_components}). Available: {pc_columns}"
            )

        args: dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "xColumn": pc_x_col,
            "yColumn": pc_y_col,
            "xLabel": self._axis_label(
                self._current_pc_x, self._x_label, variance_ratio
            ),
            "yLabel": self._axis_label(
                self._current_pc_y, self._y_label, variance_ratio
            ),
            "groupColumn": self._group_field,
            "groupColors": self._group_colors,
            "sampleIdColumn": self._sample_id_field,
            "showEllipses": self._show_ellipses,
            "interactivity": self._interactivity or {},
        }
        if self._title:
            args["title"] = self._title
        args.update(measure_args(self._measure))
        args.update(image_format_args(self._image_format))
        args.update(zoom_args(self._zoom_identifier))
        return args

    def __call__(
        self,
        key: str | None = None,
        state_manager: Any | None = None,
        height: int | None = None,
        pc_x: int | None = None,
        pc_y: int | None = None,
    ) -> Any:
        """
        Render the PCA plot component.

        Args:
            key: Optional unique key for this component instance.
            state_manager: StateManager for cross-component linking.
            height: Optional height override in pixels.
            pc_x: Which principal component to plot on the x-axis, 1-indexed.
                Overrides the value set at construction time without
                recomputing PCA (as long as it's within n_components).
            pc_y: Which principal component to plot on the y-axis, 1-indexed.

        Returns:
            Component result for Streamlit rendering.
        """
        if pc_x is not None:
            self._current_pc_x = pc_x
        if pc_y is not None:
            self._current_pc_y = pc_y

        return super().__call__(key=key, state_manager=state_manager, height=height)
