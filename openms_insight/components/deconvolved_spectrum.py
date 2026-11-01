"""Deconvolved spectrum component: masses, their charge-state peaks and sequence tags."""

from typing import Any

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.filtering import filter_and_collect_cached

# What each view draws and what it is called
VIEWS: dict[str, dict[str, str]] = {
    "deconvolved": {"title": "Deconvolved Spectrum", "x_label": "Monoisotopic Mass"},
    "annotated": {"title": "Annotated Spectrum", "x_label": "m/z"},
    "ladder": {
        "title": "Deconvolved Spectrum with Sequence Tag",
        "x_label": "Monoisotopic Mass",
    },
}


@register_component("deconvolved_spectrum")
class DeconvolvedSpectrum(BaseComponent):
    """
    Spectrum plot for charge-state deconvolution results.

    One row of data per spectrum, with list columns: the deconvolved masses and
    their intensities, the raw peaks, and for each mass the raw peaks assigned to
    it (its signal peaks). The selected mass is an index into the mass list of the
    selected spectrum, held in ``mass_identifier``.

    Views:

    - ``'deconvolved'``: the masses as sticks; the selected mass is highlighted and
      labelled with its value. Clicking a mass selects it.
    - ``'annotated'``: the raw peaks; the signal peaks of the selected mass are
      highlighted and each charge state is labelled ``z=N`` at the intensity
      weighted mean m/z of its peaks. A toolbar toggle highlights the signal peaks
      of every mass.
    - ``'ladder'``: the masses, with a sequence tag drawn as a ladder: the tag's
      masses are highlighted and labelled, and arrows between consecutive masses
      carry the residue explaining the gap (hover: the mass difference). Clicking
      a ladder mass switches to its raw peaks as in ``'annotated'``; a back button
      returns. Set the tag at render time with :meth:`set_ladder`.

    All views share the annotation toggle, the same zoom rules (the
    view fits the highlighted masses and narrows until their labels no longer
    overlap) and SVG export.

    Example:
        spectrum = DeconvolvedSpectrum(
            cache_id="deconv_spectrum",
            data=spectra,  # one row per scan, list columns
            filters={"scan": "scan_idx"},
            mass_identifier="mass",
            view="deconvolved",
        )
        spectrum(key="spectrum", state_manager=state_manager)
    """

    _component_type: str = "deconvolved_spectrum"
    # One row holds a whole spectrum: keep row groups small so that selecting a
    # spectrum reads a few spectra rather than a large slice of the run.
    _parquet_row_group_size = 64

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
        view: str = "deconvolved",
        mass_identifier: str | None = None,
        mass_column: str = "masses",
        mass_intensity_column: str = "intensities",
        peak_mz_column: str | None = "peak_mz",
        peak_intensity_column: str | None = "peak_intensity",
        signal_column: str | None = "signal_peaks",
        title: str | None = None,
        styling: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        svg_filename: str = "spectrum",
        drilldown_title: str | None = None,
        **kwargs,
    ):
        """
        Initialize the DeconvolvedSpectrum component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
            data: Polars LazyFrame, one row per spectrum (see column arguments).
            data_path: Path to a parquet file with the data.
            filters: Mapping of identifier names to column names, normally
                selecting one spectrum, e.g. {'scan': 'scan_idx'}.
            filter_defaults: Default values for filters when state is None.
            interactivity: Not used; clicks set ``mass_identifier``.
            cache_path: Base path for cache storage.
            regenerate_cache: Rebuild the cache even if a matching one exists.
            view: 'deconvolved', 'annotated' or 'ladder' (see class docstring).
            mass_identifier: Selection identifier holding the index of the
                selected mass within the spectrum's mass list. None disables
                mass selection.
            mass_column: List column with the deconvolved masses.
            mass_intensity_column: List column with the mass intensities.
            peak_mz_column: List column with the raw peak m/z values. Needed for
                'annotated' and for drilling down in 'ladder'.
            peak_intensity_column: List column with the raw peak intensities.
            signal_column: List column with, per mass, the list of its signal
                peaks as [peak index, m/z, intensity, charge]. The m/z values
                must equal the raw peak m/z values they refer to.
            title: Plot title (default: the view's title).
            drilldown_title: Title while a ladder view shows the raw peaks of a
                mass (default: "Annotated Spectrum").
            styling: Colour overrides: highlightColor, selectedColor,
                unhighlightedColor, highlightHiddenColor and annotationColors
                (massButton, selectedMassButton, sequenceArrow,
                selectedSequenceArrow, background, buttonHover).
            config: Label layout overrides: xPosScalingFactor (27.5),
                xPosScalingThreshold (30).
            svg_filename: File name for the SVG download.
            **kwargs: Additional configuration options.
        """
        if view not in VIEWS:
            raise ValueError(f"view must be one of {list(VIEWS)}, got {view!r}")
        self._view = view
        self._mass_identifier = mass_identifier
        self._mass_column = mass_column
        self._mass_intensity_column = mass_intensity_column
        self._peak_mz_column = peak_mz_column
        self._peak_intensity_column = peak_intensity_column
        self._signal_column = signal_column
        self._title = title
        self._styling = styling or {}
        self._plot_config = config or {}
        self._svg_filename = svg_filename
        self._drilldown_title = drilldown_title
        # Sequence tag drawn in the 'ladder' view (set per render, not cached)
        self._ladder: dict[str, Any] | None = None

        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            filters=filters,
            filter_defaults=filter_defaults,
            interactivity=interactivity,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            view=view,
            mass_identifier=mass_identifier,
            mass_column=mass_column,
            mass_intensity_column=mass_intensity_column,
            peak_mz_column=peak_mz_column,
            peak_intensity_column=peak_intensity_column,
            signal_column=signal_column,
            title=title,
            styling=styling,
            config=config,
            svg_filename=svg_filename,
            drilldown_title=drilldown_title,
            **kwargs,
        )

    def _get_cache_config(self) -> dict[str, Any]:
        return {
            "view": self._view,
            "mass_identifier": self._mass_identifier,
            "mass_column": self._mass_column,
            "mass_intensity_column": self._mass_intensity_column,
            "peak_mz_column": self._peak_mz_column,
            "peak_intensity_column": self._peak_intensity_column,
            "signal_column": self._signal_column,
            "title": self._title,
            "styling": self._styling,
            "plot_config": self._plot_config,
            "svg_filename": self._svg_filename,
            # Only when set, so caches built without it keep their hash
            **(
                {"drilldown_title": self._drilldown_title}
                if self._drilldown_title
                else {}
            ),
        }

    def _restore_cache_config(self, config: dict[str, Any]) -> None:
        self._view = config.get("view", "deconvolved")
        self._mass_identifier = config.get("mass_identifier")
        self._mass_column = config.get("mass_column", "masses")
        self._mass_intensity_column = config.get("mass_intensity_column", "intensities")
        self._peak_mz_column = config.get("peak_mz_column")
        self._peak_intensity_column = config.get("peak_intensity_column")
        self._signal_column = config.get("signal_column")
        self._title = config.get("title")
        self._styling = config.get("styling") or {}
        self._plot_config = config.get("plot_config") or {}
        self._svg_filename = config.get("svg_filename", "spectrum")
        self._drilldown_title = config.get("drilldown_title")
        self._ladder = None

    def _data_columns(self) -> list[str]:
        """Columns this view draws from (filter columns are added separately)."""
        columns = [self._mass_column, self._mass_intensity_column]
        if self._view != "deconvolved":
            columns += [
                c
                for c in (
                    self._peak_mz_column,
                    self._peak_intensity_column,
                    self._signal_column,
                )
                if c is not None
            ]
        return columns

    def _validate_mappings(self) -> None:
        super()._validate_mappings()
        if self._view != "deconvolved" and (
            self._peak_mz_column is None or self._peak_intensity_column is None
        ):
            raise ValueError(
                f"view '{self._view}' needs peak_mz_column and peak_intensity_column"
            )
        columns = self._raw_data.collect_schema().names()
        for column in self._data_columns():
            if column not in columns:
                raise ValueError(
                    f"Column '{column}' not found in data. Available columns: {columns}"
                )

    def _preprocess(self) -> None:
        data = self._raw_data
        keep = list(dict.fromkeys(self._data_columns() + list(self._filters.values())))
        data = data.select(keep)
        if self._filters:
            data = data.sort(list(self._filters.values()), maintain_order=True)
        self._preprocessed_data["data"] = data

    def _get_vue_component_name(self) -> str:
        return "PlotlyDeconvolvedSpectrum"

    def _get_data_key(self) -> str:
        return "plotData"

    def get_state_dependencies(self) -> list[str]:
        # The mass selection only changes highlighting, which Vue does: it must
        # not invalidate the data payload.
        return list(self._filters.keys())

    def _prepare_vue_data(self, state: dict[str, Any]) -> dict[str, Any]:
        data = self._preprocessed_data.get("data")
        if data is None:
            data = self._raw_data
        columns = list(
            dict.fromkeys(self._data_columns() + list(self._filters.values()))
        )
        df_pandas, data_hash = filter_and_collect_cached(
            data,
            self._filters,
            state,
            columns=columns,
            filter_defaults=self._filter_defaults,
        )
        # One spectrum is drawn: the first row left after filtering
        return {"plotData": df_pandas.head(1), "_hash": data_hash}

    def set_ladder(
        self,
        masses: list[float] | None,
        sequence: str = "",
        selected_index: int | None = None,
        key: Any = None,
    ) -> "DeconvolvedSpectrum":
        """
        Set the sequence tag drawn in the 'ladder' view for the next render.

        Args:
            masses: The tag's masses, as they appear in the spectrum's mass list
                (matched within 1e-5 Da). None or empty clears the ladder.
            sequence: The tag's residues; residue ``len - 1 - i`` labels the gap
                between the i-th and (i+1)-th mass.
            selected_index: Residue of the tag to emphasise (0-based along
                ``sequence``), or None.
            key: Identifies the tag. When it changes, the plot leaves a drilled
                down m/z view and clears the mass selection.

        Returns:
            Self for method chaining.
        """
        if not masses:
            self._ladder = None
        else:
            self._ladder = {
                "masses": [float(m) for m in masses],
                "sequence": sequence or "",
                "selectedIndex": selected_index,
                "key": key,
            }
        return self

    def _get_component_args(self) -> dict[str, Any]:
        view = VIEWS[self._view]
        args: dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "view": self._view,
            "title": self._title or view["title"],
            "massIdentifier": self._mass_identifier,
            "massColumn": self._mass_column,
            "massIntensityColumn": self._mass_intensity_column,
            "peakMzColumn": self._peak_mz_column,
            "peakIntensityColumn": self._peak_intensity_column,
            "signalColumn": self._signal_column,
            "styling": self._styling,
            "config": self._plot_config,
            "svgFilename": self._svg_filename,
            "ladder": self._ladder,
        }
        if self._drilldown_title:
            args["drilldownTitle"] = self._drilldown_title
        return args
