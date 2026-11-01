"""3D plot component (stems or polylines) using Plotly.js."""

from typing import Any

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.filtering import filter_and_collect_cached


@register_component("plot3d")
class Plot3D(BaseComponent):
    """
    Interactive 3D plot drawn as vertical stems or as polylines.

    - ``mode='stems'``: every point is a vertical line from the floor to its z
      value, e.g. the isotope peaks of a deconvolved mass across charge states
      (x = mass, y = charge, z = intensity).
    - ``mode='lines'``: points sharing a ``trace_column`` value are joined in
      order, each trace rising from the floor at its first point, e.g. the
      mass traces of a feature (x = m/z, y = retention time, z = intensity).

    The data is tidy (one row per point), or holds list columns with all points
    of one entity per row (e.g. one row per mass with the peaks of that mass).
    List columns must have equal lengths within a row; they are spread into
    points after filtering, which keeps the cache compact and per-selection
    reads small.

    Points are coloured and listed in the legend by ``series_column``.

    Example:
        signals = Plot3D(
            cache_id="mass_signals",
            data=peaks,  # columns: scan, mass_idx, kind, mass, charge, intensity
            filters={"spectrum": "scan", "mass": "mass_idx"},
            filter_defaults={"mass": -1},
            x_column="mass",
            y_column="charge",
            z_column="intensity",
            series_column="kind",
            series_colors={"Signal": "#3366CC", "Noise": "#DC3912"},
            title="Precursor signals",
            selection_titles={"mass": "Mass signals"},
        )
        signals(key="signals", state_manager=state_manager)
    """

    _component_type: str = "plot3d"
    _parquet_row_group_size = 4096

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
        z_column: str = "z",
        mode: str = "stems",
        series_column: str | None = None,
        series_names: dict[str, str] | None = None,
        series_name_template: str | None = None,
        series_colors: dict[str, str] | None = None,
        color: str = "#3366CC",
        trace_column: str | None = None,
        title: str | None = None,
        selection_titles: dict[str, str] | None = None,
        x_label: str | None = None,
        y_label: str | None = None,
        z_label: str | None = None,
        y_dtick: float | None = None,
        camera_eye: dict[str, float] | None = None,
        show_legend: bool = True,
        svg_filename: str | None = None,
        title_bold: bool = True,
        border: bool = True,
        export_format: str = "svg",
        **kwargs,
    ):
        """
        Initialize the Plot3D component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
            data: Polars LazyFrame with one row per point.
            data_path: Path to a parquet file with the data.
            filters: Mapping of identifier names to column names for filtering.
            filter_defaults: Default values for filters when state is None, e.g.
                {'mass': -1} to show rows stored under -1 while no mass is selected.
            interactivity: Accepted for API symmetry; 3D points are not clickable.
            cache_path: Base path for cache storage.
            regenerate_cache: Rebuild the cache even if a matching one exists.
            x_column, y_column, z_column: Columns with the coordinates. z is the
                height of a stem or the value along a trace.
            mode: 'stems' or 'lines' (see class docstring).
            series_column: Column naming the legend entry of each point. None
                draws a single trace.
            series_names: Legend name per series value (default: the value, or
                series_name_template). Series are drawn in this order first.
            series_name_template: Legend name pattern, '{}' is replaced by the
                series value (e.g. 'Charge: {}').
            series_colors: Colour per series value.
            color: Colour for series without an entry in series_colors.
            trace_column: In 'lines' mode, column separating the polylines within
                a series. Without it each series is one polyline.
            title: Plot title.
            selection_titles: Title to use while an identifier has a selection,
                checked in order, e.g. {'mass': 'Mass signals'}.
            x_label, y_label, z_label: Axis titles (default: column names).
            y_dtick: Tick spacing on the y axis (e.g. 1 for charge states).
            camera_eye: Initial camera position, e.g. {'x': 2.5, 'y': 0, 'z': 0.2}.
            show_legend: Show the legend.
            svg_filename: File name for the SVG download (default: title).
            title_bold: Draw the title in bold.
            border: Draw a border around the plot.
            export_format: 'svg' (a "Download as SVG" button) or 'png'
                (Plotly's own PNG download).
            **kwargs: Additional configuration options.
        """
        if mode not in ("stems", "lines"):
            raise ValueError(f"mode must be 'stems' or 'lines', got {mode!r}")
        self._x_column = x_column
        self._y_column = y_column
        self._z_column = z_column
        self._mode = mode
        self._series_column = series_column
        self._series_names = series_names or {}
        self._series_name_template = series_name_template
        self._series_colors = series_colors or {}
        self._color = color
        self._trace_column = trace_column
        self._title = title
        self._selection_titles = selection_titles or {}
        self._x_label = x_label or x_column
        self._y_label = y_label or y_column
        self._z_label = z_label or z_column
        self._y_dtick = y_dtick
        self._camera_eye = camera_eye
        self._show_legend = show_legend
        self._svg_filename = svg_filename
        if export_format not in ("svg", "png"):
            raise ValueError(
                f"export_format must be 'svg' or 'png', got {export_format!r}"
            )
        self._title_bold = title_bold
        self._border = border
        self._export_format = export_format

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
            z_column=z_column,
            mode=mode,
            series_column=series_column,
            series_names=series_names,
            series_name_template=series_name_template,
            series_colors=series_colors,
            color=color,
            trace_column=trace_column,
            title=title,
            selection_titles=selection_titles,
            x_label=x_label,
            y_label=y_label,
            z_label=z_label,
            y_dtick=y_dtick,
            camera_eye=camera_eye,
            show_legend=show_legend,
            svg_filename=svg_filename,
            title_bold=title_bold,
            border=border,
            export_format=export_format,
            **kwargs,
        )

    def _get_cache_config(self) -> dict[str, Any]:
        return {
            "x_column": self._x_column,
            "y_column": self._y_column,
            "z_column": self._z_column,
            "mode": self._mode,
            "series_column": self._series_column,
            "series_names": self._series_names,
            "series_name_template": self._series_name_template,
            "series_colors": self._series_colors,
            "color": self._color,
            "trace_column": self._trace_column,
            "title": self._title,
            "selection_titles": self._selection_titles,
            "x_label": self._x_label,
            "y_label": self._y_label,
            "z_label": self._z_label,
            "y_dtick": self._y_dtick,
            "camera_eye": self._camera_eye,
            "show_legend": self._show_legend,
            "svg_filename": self._svg_filename,
            # Only when set, so caches built without them keep their hash
            **({"title_bold": False} if not self._title_bold else {}),
            **({"border": False} if not self._border else {}),
            **(
                {"export_format": self._export_format}
                if self._export_format != "svg"
                else {}
            ),
        }

    def _restore_cache_config(self, config: dict[str, Any]) -> None:
        self._x_column = config.get("x_column", "x")
        self._y_column = config.get("y_column", "y")
        self._z_column = config.get("z_column", "z")
        self._mode = config.get("mode", "stems")
        self._series_column = config.get("series_column")
        self._series_names = config.get("series_names") or {}
        self._series_name_template = config.get("series_name_template")
        self._series_colors = config.get("series_colors") or {}
        self._color = config.get("color", "#3366CC")
        self._trace_column = config.get("trace_column")
        self._title = config.get("title")
        self._selection_titles = config.get("selection_titles") or {}
        self._x_label = config.get("x_label", self._x_column)
        self._y_label = config.get("y_label", self._y_column)
        self._z_label = config.get("z_label", self._z_column)
        self._y_dtick = config.get("y_dtick")
        self._camera_eye = config.get("camera_eye")
        self._show_legend = config.get("show_legend", True)
        self._svg_filename = config.get("svg_filename")
        self._title_bold = config.get("title_bold", True)
        self._border = config.get("border", True)
        self._export_format = config.get("export_format", "svg")

    def _validate_mappings(self) -> None:
        super()._validate_mappings()
        columns = self._raw_data.collect_schema().names()
        for name, column in (
            ("x_column", self._x_column),
            ("y_column", self._y_column),
            ("z_column", self._z_column),
            ("series_column", self._series_column),
            ("trace_column", self._trace_column),
        ):
            if column is not None and column not in columns:
                raise ValueError(
                    f"{name} '{column}' not found in data. Available columns: {columns}"
                )

    def _preprocess(self) -> None:
        data = self._raw_data
        # Cluster rows by filter value for predicate pushdown. The sort is stable,
        # so the point order of every trace is kept.
        if self._filters:
            data = data.sort(list(self._filters.values()), maintain_order=True)
        self._preprocessed_data["data"] = data

    def _get_vue_component_name(self) -> str:
        return "Plotly3D"

    def _get_data_key(self) -> str:
        return "plotData"

    def _columns(self) -> list[str]:
        columns = [self._x_column, self._y_column, self._z_column]
        for column in [
            self._series_column,
            self._trace_column,
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
        # List columns hold one entity's points per row (e.g. every peak of one
        # mass); spread them into one row per point now that only the selected
        # rows are left.
        list_columns = self._list_columns()
        if list_columns and len(df_pandas) > 0:
            df_pandas = df_pandas.explode(list_columns, ignore_index=True)
            df_pandas = df_pandas.dropna(subset=[self._x_column]).astype(
                {
                    c: "float64"
                    for c in (self._x_column, self._y_column, self._z_column)
                    if c in list_columns
                }
            )
        return {"plotData": df_pandas, "_hash": data_hash}

    def _list_columns(self) -> list[str]:
        """Columns of the cached data that hold lists of points."""
        data = self._preprocessed_data.get("data")
        if data is None:
            data = self._raw_data
        if data is None:
            return []
        schema = data.collect_schema()
        return [
            column
            for column in self._columns()
            if column in schema.names() and isinstance(schema[column], pl.List)
        ]

    def _get_component_args(self) -> dict[str, Any]:
        args: dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "xColumn": self._x_column,
            "yColumn": self._y_column,
            "zColumn": self._z_column,
            "mode": self._mode,
            "seriesColumn": self._series_column,
            "seriesNames": [[k, v] for k, v in self._series_names.items()],
            "seriesNameTemplate": self._series_name_template,
            "seriesColors": self._series_colors,
            "color": self._color,
            "traceColumn": self._trace_column,
            "title": self._title or "",
            # Lists keep the priority order of selection_titles through JSON
            "selectionTitles": [[k, v] for k, v in self._selection_titles.items()],
            "xLabel": self._x_label,
            "yLabel": self._y_label,
            "zLabel": self._z_label,
            "yDtick": self._y_dtick,
            "cameraEye": self._camera_eye,
            "showLegend": self._show_legend,
        }
        if self._svg_filename:
            args["svgFilename"] = self._svg_filename
        if not self._title_bold:
            args["titleBold"] = False
        if not self._border:
            args["border"] = False
        if self._export_format != "svg":
            args["exportFormat"] = self._export_format
        return args
