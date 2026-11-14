"""Series plot component: one line, marker, bar or box trace per group using Plotly.js."""

from typing import Any

import polars as pl

from ..core.base import BaseComponent
from ..core.image_format import image_format_args, validate_image_format
from ..core.measure import (
    measure_args,
    validate_measure,
)
from ..core.registry import register_component
from ..core.zoom import validate_zoom_identifier, zoom_args
from ..preprocessing.filtering import filter_and_collect_cached

# Plotly scatter modes, then bars and boxes
MODES = ("lines", "markers", "lines+markers", "bars", "box")


@register_component("series_plot")
class SeriesPlot(BaseComponent):
    """
    Line, marker, bar or box plot with one trace per series.

    Suited to continuous curves such as score distributions (target vs. decoy
    densities), calibration curves or chromatogram overlays, where the x values
    are sampled points rather than peaks. For stick spectra use LinePlot.

    ``mode="bars"`` draws bars, the series side by side: counts per sample,
    a histogram (one row per bin) or the top terms of an enrichment
    (``orientation="h"`` for long category names). ``mode="box"`` draws one box
    per x value and series from all y values of that x (one row per value),
    e.g. the distribution of abundances in every sample.

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

    _supports_stepper = True

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
        y_range_mode: str = "nonnegative",
        hover_column: str | None = None,
        orientation: str = "v",
        measure: bool = True,
        image_format: str | None = None,
        zoom_identifier: str | None = None,
        view_column: str | None = None,
        view_names: dict[str, str] | None = None,
        view_identifier: str | None = None,
        view_default: str | None = None,
        top_choices: list[int] | None = None,
        top_default: int | None = None,
        bar_height: int | None = None,
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
            mode: 'lines', 'markers' or 'lines+markers' (Plotly scatter modes),
                'bars' (bars, the series side by side) or 'box' (a box per x
                value and series, from the y values of its rows).
            title: Plot title.
            x_label: X-axis label (default: x_column).
            y_label: Y-axis label (default: y_column).
            show_legend: Show the legend.
            fixed_y_range: Disable zooming along the y axis.
            svg_filename: File name (without extension) of the image download
                (default: title); the extension follows the image format.
            font: Plotly font of the plot, e.g. {'family': 'Arial', 'color':
                'black'} (default: the Streamlit theme's font and text colour).
            y_range_mode: Plotly rangemode of the y axis: 'nonnegative' (from
                zero, for intensities and densities), 'tozero' or 'normal' (for
                signed values such as mass errors).
            hover_column: Column whose text is shown when hovering a point
                (e.g. a fragment name), above its x and y values.
            orientation: 'v' (default) or 'h': with 'h', bars and boxes lie
                horizontally, x_column on the vertical axis and y_column on
                the horizontal one (e.g. GO terms and their -log10 p-value).
                The axis labels follow their columns.
            measure: Show a "Measure" button in the mode bar (default True;
                False hides it). In measure mode, clicking two points draws a
                bracket labelled with their x difference ("ΔRT 12.400"). Esc
                cancels a half-finished measurement, clicking a label removes
                it and "Clear measurements" removes all; they are cleared when
                other data is plotted and are part of the image download. With
                measure mode off, clicks select as before. Render-time only:
                not part of the cache.
            image_format: Format of the image download: 'svg', 'png', 'jpeg'
                or 'webp'. None (default) follows
                ``openms_insight.set_image_format()`` (default 'svg') when the
                component is drawn. Render-time only: not part of the cache.
            zoom_identifier: State identifier the plot keeps its zoom under,
                ``{"x": [lo, hi], "y": [lo, hi]}`` (default None: the zoom stays
                in the browser). The plot reports its ranges there after a zoom
                or pan and zooms to a value set there, e.g. by a saved view.
                Render-time only: not part of the cache.
            view_column: Column splitting the data into views, of which the
                plot shows one at a time (e.g. the GO category of each term).
                The plot draws a switch with one button per view above its
                toolbar. None (default) shows all rows.
            view_names: Button label per view value (default: the value).
                Views are offered in this mapping's order, then any others in
                order of appearance. ``{view}`` in ``title`` is replaced by the
                label of the view shown.
            view_identifier: State identifier the picked view is written to
                (its value in view_column), so other components can follow it,
                e.g. a Table with ``filters={view_identifier: view_column}``.
                A value set there from Python picks the view. None (default):
                the pick stays in the browser. Render-time only.
            view_default: View shown until one is picked (default: the first).
            top_choices: Numbers of rows the plot can show, offered as a
                "Top n" menu in its toolbar: the plot shows the first n x
                values (of the view shown) in the order of the data, so sort
                it first (e.g. the most significant terms). None (default)
                shows all rows.
            top_default: The number shown until another is picked (default:
                the middle of top_choices).
            bar_height: Pixels per category of a horizontal bar or box plot:
                the plot grows with the categories shown (at least its
                height). Render-time only.
            **kwargs: Additional configuration options.
        """
        if y_range_mode not in ("nonnegative", "tozero", "normal"):
            raise ValueError(
                "y_range_mode must be 'nonnegative', 'tozero' or 'normal', "
                f"got {y_range_mode!r}"
            )
        if mode not in MODES:
            raise ValueError(
                f"mode must be one of {', '.join(repr(m) for m in MODES)}, got {mode!r}"
            )
        if orientation not in ("v", "h"):
            raise ValueError(f"orientation must be 'v' or 'h', got {orientation!r}")
        if top_choices is not None:
            top_choices = [int(n) for n in top_choices]
            if not top_choices or any(n < 1 for n in top_choices):
                raise ValueError("top_choices must be positive numbers")
            if top_default is None:
                top_default = top_choices[len(top_choices) // 2]
            if int(top_default) not in top_choices:
                raise ValueError(
                    f"top_default {top_default!r} is not one of top_choices {top_choices}"
                )
            top_default = int(top_default)
        elif top_default is not None:
            raise ValueError("top_default needs top_choices")
        if view_identifier is not None and view_column is None:
            raise ValueError("view_identifier needs view_column")
        if bar_height is not None and int(bar_height) < 1:
            raise ValueError("bar_height must be a positive number of pixels")
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
        self._y_range_mode = y_range_mode
        self._hover_column = hover_column
        self._orientation = orientation
        self._view_column = view_column
        self._view_names = dict(view_names or {})
        self._view_default = view_default
        self._top_choices = top_choices
        self._top_default = top_default

        # Render-time: the identifier the picked view goes to, the bar height
        self._view_identifier = view_identifier
        self._bar_height = int(bar_height) if bar_height is not None else None

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
            y_range_mode=y_range_mode,
            hover_column=hover_column,
            orientation=orientation,
            view_column=view_column,
            view_names=view_names,
            view_default=view_default,
            top_choices=top_choices,
            top_default=top_default,
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
            **(
                {"y_range_mode": self._y_range_mode}
                if self._y_range_mode != "nonnegative"
                else {}
            ),
            **({"hover_column": self._hover_column} if self._hover_column else {}),
            **({"orientation": self._orientation} if self._orientation != "v" else {}),
            **(
                {
                    "view_column": self._view_column,
                    "view_names": self._view_names,
                    "view_default": self._view_default,
                }
                if self._view_column
                else {}
            ),
            **(
                {"top_choices": self._top_choices, "top_default": self._top_default}
                if self._top_choices
                else {}
            ),
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
        self._y_range_mode = config.get("y_range_mode", "nonnegative")
        self._hover_column = config.get("hover_column")
        self._orientation = config.get("orientation", "v")
        self._view_column = config.get("view_column")
        self._view_names = config.get("view_names") or {}
        self._view_default = config.get("view_default")
        self._top_choices = config.get("top_choices")
        self._top_default = config.get("top_default")

    def _validate_mappings(self) -> None:
        super()._validate_mappings()
        columns = self._raw_data.collect_schema().names()
        for name, column in (
            ("x_column", self._x_column),
            ("y_column", self._y_column),
            ("series_column", self._series_column),
            ("hover_column", self._hover_column),
            ("view_column", self._view_column),
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
            self._hover_column,
            self._view_column,
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
            "yRangeMode": self._y_range_mode,
            "hoverColumn": self._hover_column,
            "orientation": self._orientation,
            "interactivity": self._interactivity or {},
        }
        if self._title:
            args["title"] = self._title
        if self._svg_filename:
            args["svgFilename"] = self._svg_filename
        if self._font:
            args["font"] = self._font
        args.update(measure_args(self._measure))
        args.update(image_format_args(self._image_format))
        args.update(zoom_args(self._zoom_identifier))
        if self._view_column:
            args["viewColumn"] = self._view_column
            # Lists keep the order of view_names through JSON
            args["viewNames"] = [[k, v] for k, v in self._view_names.items()]
            if self._view_default is not None:
                args["viewDefault"] = self._view_default
            if self._view_identifier:
                args["viewIdentifier"] = self._view_identifier
        if self._top_choices:
            args["topChoices"] = list(self._top_choices)
            args["topDefault"] = self._top_default
        if self._bar_height:
            args["barHeight"] = self._bar_height
        return args
