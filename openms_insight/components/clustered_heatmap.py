"""ClusteredHeatmap component: a real grid heatmap with optional row/column dendrograms."""

from typing import Any

import numpy as np
import polars as pl

from ..core.base import BaseComponent
from ..core.image_format import image_format_args, validate_image_format
from ..core.multi_select import normalize_multi_select
from ..core.registry import register_component


@register_component("clustered_heatmap")
class ClusteredHeatmap(BaseComponent):
    """
    Grid (matrix) heatmap for categorical row/column axes, e.g. protein
    abundance across samples, with optional hierarchical clustering
    (dendrograms) on either axis.

    Unlike `Heatmap` (a scattergl point-cloud plot built for continuous
    numeric axes like RT vs m/z, with zoom-based multi-resolution
    downsampling for millions of points), this renders an actual grid where
    both axes are categorical labels (e.g. protein names, sample names).
    Datasets are expected to be small (tens to low-thousands of cells), so
    there is no filtering/pagination/zoom machinery - the full matrix is
    sent to the frontend in one payload, similar to `PCAPlot`.

    Example:
        heatmap = ClusteredHeatmap(
            cache_id="protein_heatmap",
            data=wide_quant_data,   # wide: id_col + one column per sample
            id_col="ProteinName",
            metadata=metadata_df,   # columns: sample_id, group
            row_cluster=True,
            col_cluster=True,
            title="Protein Abundance",
        )
        heatmap(state_manager=state)
    """

    _component_type: str = "clustered_heatmap"

    def __init__(
        self,
        cache_id: str,
        id_col: str | None = None,
        data: pl.LazyFrame | None = None,
        data_path: str | None = None,
        metadata: pl.DataFrame | None = None,
        sample_id_field: str = "sample_id",
        group_field: str = "group",
        row_cluster: bool = True,
        col_cluster: bool = True,
        linkage_method: str = "average",
        linkage_metric: str = "euclidean",
        cache_path: str = ".",
        regenerate_cache: bool = False,
        title: str | None = None,
        x_label: str | None = None,
        y_label: str | None = None,
        colorscale: str | list | None = None,
        reversescale: bool = True,
        intensity_label: str | None = None,
        group_colors: dict[str, str] | None = None,
        multi_select: dict[str, str] | None = None,
        image_format: str | None = None,
        **kwargs,
    ):
        """
        Initialize the ClusteredHeatmap component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
                Creates a folder {cache_path}/{cache_id}/ for cached data.
            id_col: Column in `data` naming each row (e.g. "ProteinName").
                All other columns are treated as sample/value columns.
                Required whenever data/data_path is provided (creation mode).
            data: Polars LazyFrame in wide format: one id column plus one
                column per sample. Optional if cache exists.
            data_path: Path to parquet file (preferred for large datasets).
            metadata: Optional DataFrame mapping samples to groups, with
                `sample_id_field` and `group_field` columns. When provided,
                a group color annotation bar is rendered alongside the
                heatmap.
            sample_id_field: Column in `metadata` naming the sample columns
                to look up in `data` (default: "sample_id").
            group_field: Column in `metadata` with the group/condition
                label used for the annotation bar (default: "group").
            row_cluster: If True (default), hierarchically cluster rows and
                render a row (left-side) dendrogram. Automatically skipped
                if fewer than 2 rows are present.
            col_cluster: If True (default), hierarchically cluster columns
                and render a column (top) dendrogram. Automatically skipped
                if fewer than 2 columns are present.
            linkage_method: `scipy.cluster.hierarchy.linkage` method
                (default: "average").
            linkage_metric: `scipy.cluster.hierarchy.linkage` distance
                metric (default: "euclidean").
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            title: Plot title displayed above the plot.
            x_label: X-axis (column) label.
            y_label: Y-axis (row) label.
            colorscale: Plotly colorscale name or [fraction, color] stop list
                for cell intensity. None (default) draws a diverging scale
                centred on 0 (blue, the page colour, orange) that follows the
                app's light or dark theme.
            reversescale: Reverse the colorscale direction (default: True).
                Applies to a ``colorscale`` given here only.
            intensity_label: Custom label for the colorbar (default: "Value").
            group_colors: Optional mapping of group values to colors (e.g.
                {"Control": "#1f77b4", "Treatment": "#d62728"}). Auto-
                assigned from a default palette for any group not given an
                explicit color.
            multi_select: Mapping of an identifier name to ``id_col`` for
                selecting several rows at once with a box or lasso drag over
                the cells (Shift adds, Alt removes). The identifier holds the
                sorted labels of the selected rows, or None, and the selected
                rows are outlined, whichever component chose them.
            image_format: Format of the image download: 'svg', 'png', 'jpeg'
                or 'webp'. None (default) follows
                ``openms_insight.set_image_format()`` (default 'svg') when the
                component is drawn. Render-time only: not part of the cache.
            **kwargs: Additional configuration options.
        """
        if (data is not None or data_path is not None) and not id_col:
            raise ValueError(
                "ClusteredHeatmap requires 'id_col' when creating the cache "
                "(data= or data_path= provided)."
            )

        self._id_col = id_col
        self._metadata = metadata
        self._sample_id_field = sample_id_field
        self._group_field = group_field
        self._row_cluster = row_cluster
        self._col_cluster = col_cluster
        self._linkage_method = linkage_method
        self._linkage_metric = linkage_metric
        self._title = title
        self._x_label = x_label
        self._y_label = y_label
        self._colorscale = colorscale
        self._reversescale = reversescale
        self._intensity_label = intensity_label
        self._group_colors = group_colors or {}
        self._multi_select = normalize_multi_select(multi_select)
        for identifier, column in self._multi_select.items():
            if id_col is not None and column != id_col:
                raise ValueError(
                    f"multi_select of a ClusteredHeatmap selects rows: map "
                    f"{identifier!r} to id_col {id_col!r}, not {column!r}"
                )

        # Render-time option, kept out of the cache config (see core/image_format.py)
        self._image_format = validate_image_format(image_format, allow_none=True)

        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            # Pass component-specific params for subprocess recreation
            id_col=id_col,
            metadata=metadata,
            sample_id_field=sample_id_field,
            group_field=group_field,
            row_cluster=row_cluster,
            col_cluster=col_cluster,
            linkage_method=linkage_method,
            linkage_metric=linkage_metric,
            title=title,
            x_label=x_label,
            y_label=y_label,
            colorscale=colorscale,
            reversescale=reversescale,
            intensity_label=intensity_label,
            group_colors=group_colors,
            multi_select=multi_select,
            **kwargs,
        )

    def _validate_mappings(self) -> None:
        """Validate id_col and metadata presence against the raw data schema.

        Row/column-count eligibility for clustering is checked later, in
        `_preprocess()`, once the matrix has actually been collected.
        """
        if self._raw_data is None:
            return  # Skip validation when reconstructing from cache

        schema_names = self._raw_data.collect_schema().names()
        if self._id_col not in schema_names:
            raise ValueError(
                f"id_col '{self._id_col}' not found in data. "
                f"Available columns: {schema_names}"
            )

        if self._metadata is not None:
            metadata_cols = set(self._metadata.columns)
            if self._sample_id_field not in metadata_cols:
                raise ValueError(
                    f"metadata is missing sample_id_field "
                    f"'{self._sample_id_field}'. Available columns: "
                    f"{sorted(metadata_cols)}"
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
            "id_col": self._id_col,
            "metadata_map": metadata_map,
            "sample_id_field": self._sample_id_field,
            "group_field": self._group_field,
            "row_cluster": self._row_cluster,
            "col_cluster": self._col_cluster,
            "linkage_method": self._linkage_method,
            "linkage_metric": self._linkage_metric,
            "title": self._title,
            "x_label": self._x_label,
            "y_label": self._y_label,
            "colorscale": self._colorscale,
            "reversescale": self._reversescale,
            "intensity_label": self._intensity_label,
            "group_colors": self._group_colors,
            # Only when set, so caches built without it keep their hash
            **({"multi_select": self._multi_select} if self._multi_select else {}),
        }

    def _restore_cache_config(self, config: dict[str, Any]) -> None:
        """Restore component-specific configuration from cached config."""
        self._id_col = config.get("id_col")
        self._sample_id_field = config.get("sample_id_field", "sample_id")
        self._group_field = config.get("group_field", "group")
        self._row_cluster = config.get("row_cluster", True)
        self._col_cluster = config.get("col_cluster", True)
        self._linkage_method = config.get("linkage_method", "average")
        self._linkage_metric = config.get("linkage_metric", "euclidean")
        self._title = config.get("title")
        self._x_label = config.get("x_label")
        self._y_label = config.get("y_label")
        self._colorscale = config.get("colorscale")
        self._reversescale = config.get("reversescale", True)
        self._intensity_label = config.get("intensity_label")
        self._group_colors = config.get("group_colors", {})
        self._multi_select = dict(config.get("multi_select") or {})
        self._metadata = None  # not needed after clustering has been precomputed

    def _compute_dendrogram(self, matrix: np.ndarray) -> dict[str, Any]:
        """Run hierarchical clustering and return leaf order + line coordinates.

        Args:
            matrix: 2D array where each ROW is one observation to cluster
                (for column clustering, pass the transposed matrix so each
                sample becomes a row/observation).

        Returns:
            Dict with "leafOrder" (list[int], the clustered row/column
            index order) and "icoord"/"dcoord" (list[list[float]], the x
            and y coordinates of each dendrogram line segment, in the
            format `scipy.cluster.hierarchy.dendrogram` produces).
        """
        from scipy.cluster.hierarchy import dendrogram, leaves_list, linkage

        Z = linkage(matrix, method=self._linkage_method, metric=self._linkage_metric)
        leaf_order = [int(i) for i in leaves_list(Z)]
        ddata = dendrogram(Z, no_plot=True)

        return {
            "leafOrder": leaf_order,
            "icoord": ddata["icoord"],
            "dcoord": ddata["dcoord"],
        }

    def _preprocess(self) -> None:
        """Compute (optional) row/column clustering and the reordered matrix.

        Clustering on an axis is skipped (leaving that axis in its original
        order, with no dendrogram data) whenever that axis has fewer than 2
        entries, since `scipy.cluster.hierarchy.linkage` requires at least 2
        observations.
        """
        if self._raw_data is None:
            raise ValueError("No data provided and no cache exists")

        df = self._raw_data.collect()
        row_labels = df.select(self._id_col).to_series().to_list()
        col_labels = [c for c in df.columns if c != self._id_col]

        if len(col_labels) < 2:
            raise ValueError(
                f"ClusteredHeatmap requires at least 2 sample columns; "
                f"found {len(col_labels)}."
            )

        values = df.select(col_labels).to_numpy().astype(np.float64)

        # scipy's linkage rejects non-finite values with an error that never
        # mentions the caller's data. Only clustering needs a complete matrix —
        # an unclustered heatmap renders gaps perfectly well — so check just
        # the axes that are actually about to be clustered.
        will_cluster = (self._row_cluster and len(row_labels) >= 2) or (
            self._col_cluster and len(col_labels) >= 2
        )
        if will_cluster and not np.isfinite(values).all():
            incomplete = int((~np.isfinite(values)).any(axis=1).sum())
            raise ValueError(
                f"ClusteredHeatmap cannot cluster a matrix containing missing "
                f"values; {incomplete} of {len(row_labels)} rows contain them. "
                f"Impute first, e.g. with "
                f"openms_insight.analysis.imputation.impute_mar(), or pass "
                f"row_cluster=False and col_cluster=False."
            )

        row_dendrogram: dict[str, Any] | None = None
        if self._row_cluster and len(row_labels) >= 2:
            row_dendrogram = self._compute_dendrogram(values)
            row_order = row_dendrogram["leafOrder"]
            values = values[row_order, :]
            row_labels = [row_labels[i] for i in row_order]

        col_dendrogram: dict[str, Any] | None = None
        if self._col_cluster and len(col_labels) >= 2:
            col_dendrogram = self._compute_dendrogram(values.T)
            col_order = col_dendrogram["leafOrder"]
            values = values[:, col_order]
            col_labels = [col_labels[i] for i in col_order]

        col_groups: list[str | None] = [None] * len(col_labels)
        group_colors = dict(self._group_colors)
        if self._metadata is not None:
            sample_ids = (
                self._metadata.select(self._sample_id_field).to_series().to_list()
            )
            groups = self._metadata.select(self._group_field).to_series().to_list()
            group_map = dict(zip(sample_ids, groups, strict=True))
            col_groups = [group_map.get(c) for c in col_labels]

            default_palette = [
                "#1f77b4",
                "#ff7f0e",
                "#2ca02c",
                "#d62728",
                "#9467bd",
                "#8c564b",
                "#e377c2",
                "#7f7f7f",
                "#bcbd22",
                "#17becf",
            ]
            unique_groups = sorted({g for g in col_groups if g is not None})
            for i, g in enumerate(unique_groups):
                if g not in group_colors:
                    group_colors[g] = default_palette[i % len(default_palette)]

        matrix_df = (
            pl.DataFrame(values, schema=col_labels)
            .with_columns(pl.Series(self._id_col, row_labels))
            .select([self._id_col] + col_labels)
        )

        self._preprocessed_data = {
            "matrix": matrix_df,
            "row_labels": row_labels,
            "col_labels": col_labels,
            "row_dendrogram": row_dendrogram,
            "col_dendrogram": col_dendrogram,
            "col_groups": col_groups,
            "group_colors": group_colors,
        }

    def get_row_labels(self) -> list[str]:
        """Return row labels in clustered (or original) order."""
        return list(self._preprocessed_data.get("row_labels", []))

    def get_col_labels(self) -> list[str]:
        """Return column labels in clustered (or original) order."""
        return list(self._preprocessed_data.get("col_labels", []))

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        return "PlotlyClusteredHeatmap"

    def _get_data_key(self) -> str:
        """Return the key for the primary data in Vue payload."""
        return "heatmapMatrix"

    def _prepare_vue_data(self, state: dict[str, Any]) -> dict[str, Any]:
        """Prepare the (already reordered) matrix for the Vue component.

        No filtering/interactivity in this first version - the full matrix
        is always sent, matching the small-dataset assumption documented on
        the class.
        """
        from ..preprocessing.filtering import compute_dataframe_hash

        data = self._preprocessed_data["matrix"]
        df_polars = data.collect() if isinstance(data, pl.LazyFrame) else data

        data_hash = compute_dataframe_hash(df_polars)
        df_pandas = df_polars.to_pandas()

        return {"heatmapMatrix": df_pandas, "_hash": data_hash}

    def _get_component_args(self) -> dict[str, Any]:
        """Return configuration for the Vue component."""
        args: dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "idCol": self._id_col,
            "rowLabels": self.get_row_labels(),
            "colLabels": self.get_col_labels(),
            "rowDendrogram": self._preprocessed_data.get("row_dendrogram"),
            "colDendrogram": self._preprocessed_data.get("col_dendrogram"),
            "colGroups": self._preprocessed_data.get("col_groups", []),
            "groupColors": self._preprocessed_data.get("group_colors", {}),
            "xLabel": self._x_label,
            "yLabel": self._y_label,
            "colorscale": self._colorscale,
            "reversescale": self._reversescale,
            "intensityLabel": self._intensity_label or "Value",
        }
        if self._title:
            args["title"] = self._title
        if self._multi_select:
            args["multiSelect"] = self._multi_select
        args.update(image_format_args(self._image_format))
        return args
