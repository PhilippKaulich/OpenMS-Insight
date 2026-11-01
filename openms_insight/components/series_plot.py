"""Series plot component: one line (or marker) trace per group using Plotly.js."""

from typing import Any

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.filtering import filter_and_collect_cached


@register_component("series_plot")
class SeriesPlot(BaseComponent):
    """
    Line and marker plot with one trace per series.

    Suited to continuous curves such as score distributions (target vs. decoy
    densities), calibration curves or chromatogram overlays, where the x values
    are sampled points rather than peaks. For stick spectra use LinePlot.

    Data is tidy: one row per point, with an optional series column naming the
    trace each point belongs to. Points are drawn in the order of the data.

    Example:
        fdr_plot = SeriesPlot(
            cache_id="fdr_density",
            data=densities,  # columns: x, y, kind ('target' / 'decoy')
            x_column="x",
            y_column="y",
            series_column="kind",
            series_names={"target": "Target scores", "decoy": "Decoy scores"},
            series_colors={"target": "green", "decoy": "red"},
            title="FDR Plot",
            x_label="Score",
            y_label="Density",
        )
        fdr_plot(key="fdr", state_manager=state_manager)
    """

    _component_type: str = "series_plot"

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
        x_column: str = "x",
        y_column: str = "y",
        series_column: str | None = None,
        series_names: dict[str, str] | None = None,
        series_colors: dict[str, str] | None = None,
        mode: str = "lines+markers",
        title: str | None = None,
        x_label: str | None = None,
        y_label: str | None = None,
        show_legend: bool = True,
        fixed_y_range: bool = False,
        svg_filename: str | None = None,
        font: dict[str, str] | None = None,
        **kwargs,
    ):
        """
        Initialize the SeriesPlot component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
            data: Polars LazyFrame with one row per point.
            data_path: Path to a parquet file with the data.
            filters: Mapping of identifier names to column names for filtering.
            filter_defaults: Default values for filters when state is None.
            interactivity: Mapping of identifier names to column names. Clicking
                a point sets each identifier to that point's column value.
            cache_path: Base path for cache storage.
            regenerate_cache: Rebuild the cache even if a matching one exists.
            x_column: Column with x values.
            y_column: Column with y values.
            series_column: Column naming the series of each point. None draws a
                single trace.
            series_names: Legend name per series value (default: the value).
                Series are drawn in this mapping's order, then any others in
                order of appearance.
            series_colors: Colour per series value (default: Plotly's palette).
            mode: Plotly scatter mode: 'lines', 'markers' or 'lines+markers'.
            title: Plot title.
            x_label: X-axis label (default: x_column).
            y_label: Y-axis label (default: y_column).
            show_legend: Show the legend.
            fixed_y_range: Disable zooming along the y axis.
            svg_filename: File name for the SVG download (default: title).
            font: Plotly font of the plot, e.g. {'family': 'Arial', 'color':
                'black'} (default: the Streamlit theme's font and text colour).
            **kwargs: Additional configuration options.
        """
        if mode not in ("lines", "markers", "lines+markers"):
            raise ValueError(
                f"mode must be 'lines', 'markers' or 'lines+markers', got {mode!r}"
            )
        self._x_column = x_column
        self._y_column = y_column
        self._series_column = series_column
        self._series_names = series_names or {}
        self._series_colors = series_colors or {}
        self._mode = mode
        self._title = title
        self._x_label = x_label or x_column
        self._y_label = y_label or y_column
        self._show_legend = show_legend
        self._fixed_y_range = fixed_y_range
        self._svg_filename = svg_filename
        self._font = dict(font) if font else None

        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            filters=filters,
            filter_defaults=filter_defaults,
            interactivity=interactivity,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            x_column=x_column,
            y_column=y_column,
            series_column=series_column,
            series_names=series_names,
            series_colors=series_colors,
            mode=mode,
            title=title,
            x_label=x_label,
            y_label=y_label,
            show_legend=show_legend,
            fixed_y_range=fixed_y_range,
            svg_filename=svg_filename,
            font=font,
            **kwargs,
        )

    def _get_cache_config(self) -> dict[str, Any]:
        return {
            "x_column": self._x_column,
            "y_column": self._y_column,
            "series_column": self._series_column,
            "series_names": self._series_names,
            "series_colors": self._series_colors,
            "mode": self._mode,
            "title": self._title,
            "x_label": self._x_label,
            "y_label": self._y_label,
            "show_legend": self._show_legend,
            "fixed_y_range": self._fixed_y_range,
            "svg_filename": self._svg_filename,
            # Only when set, so caches built without it keep their hash
            **({"font": self._font} if self._font else {}),
        }

    def _restore_cache_config(self, config: dict[str, Any]) -> None:
        self._x_column = config.get("x_column", "x")
        self._y_column = config.get("y_column", "y")
        self._series_column = config.get("series_column")
        self._series_names = config.get("series_names") or {}
        self._series_colors = config.get("series_colors") or {}
        self._mode = config.get("mode", "lines+markers")
        self._title = config.get("title")
        self._x_label = config.get("x_label", self._x_column)
        self._y_label = config.get("y_label", self._y_column)
        self._show_legend = config.get("show_legend", True)
        self._fixed_y_range = config.get("fixed_y_range", False)
        self._svg_filename = config.get("svg_filename")
        self._font = config.get("font")

    def _validate_mappings(self) -> None:
        super()._validate_mappings()
        columns = self._raw_data.collect_schema().names()
        for name, column in (
            ("x_column", self._x_column),
            ("y_column", self._y_column),
            ("series_column", self._series_column),
        ):
            if column is not None and column not in columns:
                raise ValueError(
                    f"{name} '{column}' not found in data. Available columns: {columns}"
                )

    def _preprocess(self) -> None:
        # Points keep their order: a curve is drawn through them as given
        self._preprocessed_data["data"] = self._raw_data

    def _get_vue_component_name(self) -> str:
        return "PlotlySeries"

    def _get_data_key(self) -> str:
        return "plotData"

    def _columns(self) -> list[str]:
        columns = [self._x_column, self._y_column]
        for column in [
            self._series_column,
            *(self._interactivity or {}).values(),
            *(self._filters or {}).values(),
        ]:
            if column is not None and column not in columns:
                columns.append(column)
        return columns

    def _prepare_vue_data(self, state: dict[str, Any]) -> dict[str, Any]:
        data = self._preprocessed_data.get("data")
        if data is None:
            data = self._raw_data
        df_pandas, data_hash = filter_and_collect_cached(
            data,
            self._filters,
            state,
            columns=self._columns(),
            filter_defaults=self._filter_defaults,
        )
        return {"plotData": df_pandas, "_hash": data_hash}

    def _get_component_args(self) -> dict[str, Any]:
        args: dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "xColumn": self._x_column,
            "yColumn": self._y_column,
            "seriesColumn": self._series_column,
            # Lists keep the order of series_names through JSON
            "seriesNames": [[k, v] for k, v in self._series_names.items()],
            "seriesColors": self._series_colors,
            "mode": self._mode,
            "xLabel": self._x_label,
            "yLabel": self._y_label,
            "showLegend": self._show_legend,
            "fixedYRange": self._fixed_y_range,
            "interactivity": self._interactivity or {},
        }
        if self._title:
            args["title"] = self._title
        if self._svg_filename:
            args["svgFilename"] = self._svg_filename
        if self._font:
            args["font"] = self._font
        return args
