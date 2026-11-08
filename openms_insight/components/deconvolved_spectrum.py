"""Deconvolved spectrum component: masses, their charge-state peaks and sequence tags."""

from typing import Any

import polars as pl

from ..core.base import BaseComponent
from ..core.image_format import image_format_args, validate_image_format
from ..core.zoom import validate_zoom_identifier, zoom_args
from ..core.keep_zoom import keep_zoom_args, validate_keep_zoom
from ..core.measure import (
    DEFAULT_MEASURE_TOLERANCE,
    measure_args,
    validate_measure,
    validate_measure_residues,
    validate_measure_tolerance,
)
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

    With ``fragment_matches_identifier`` set to the identifier a
    ``ProteinSequenceView`` writes its matched fragment ions to, every view
    marks those ions on the spectrum the sequence view matched: the matched
    masses (and in the m/z views their signal peaks) are coloured by the end
    of the sequence they cover (N-terminal a/b/c, C-terminal x/y/z, internal)
    and labelled with the ion's name. The marks follow the sequence view: an
    edited sequence or modification, another ion type or tolerance redraws
    them. A toolbar toggle hides them.

    In the m/z views, :meth:`set_envelope` adds the theoretical isotope envelope
    of the selected mass as open circles on its raw peaks, so the fit of the
    observed peaks can be judged by eye.

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
        measure: bool = True,
        measure_tolerance: float = DEFAULT_MEASURE_TOLERANCE,
        measure_residues: dict[str, float] | None = None,
        image_format: str | None = None,
        keep_zoom: bool = False,
        fragment_matches_identifier: str | None = None,
        zoom_identifier: str | None = None,
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
                unhighlightedColor, highlightHiddenColor, the fragment ion
                colours nTermColor, cTermColor and internalColor, and annotationColors
                (massButton, selectedMassButton, sequenceArrow,
                selectedSequenceArrow, background, buttonHover).
            config: Label layout overrides: xPosScalingFactor (27.5),
                xPosScalingThreshold (30).
            svg_filename: File name (without extension) of the image download;
                the extension follows the image format.
            measure: Show a "Measure" button in the mode bar (default True;
                False hides it). In measure mode, clicking two masses draws a
                bracket labelled with their difference ("Δmass 128.095 ≈ K"),
                matched to amino-acid residue masses as a neutral mass (1+
                only). Between raw peaks (the 'annotated' view, or a ladder
                drill-down) the difference is m/z and matched at 1+ and 2+. Esc
                cancels a half-finished measurement, clicking a label removes it
                and "Clear measurements" removes all; they are cleared when
                other data is plotted and are part of the image download. With
                measure mode off, clicks select masses as before. Render-time
                only: not part of the cache.
            measure_tolerance: Residue matching tolerance in Da per point
                (default 0.02); a difference matches within twice this.
            measure_residues: Extra named masses to match besides the 20
                standard residues, e.g. ``{"M(Oxidation)": 147.0354}``.
            image_format: Format of the image download: 'svg', 'png', 'jpeg'
                or 'webp'. None (default) follows
                ``openms_insight.set_image_format()`` (default 'svg') when the
                component is drawn. Render-time only: not part of the cache.
            keep_zoom: Start with the zoom pinned (default False). The pin
                button in the mode bar keeps the zoomed x range when the plot
                gets new data, e.g. when another spectrum is selected; unpinned,
                each new spectrum is shown in full. Double-click still resets
                the zoom. Render-time only: not part of the cache.
            fragment_matches_identifier: Identifier a ``ProteinSequenceView``
                writes its matched fragment ions to (its
                ``fragment_matches_identifier``). The ions are marked when the
                ``spectrum`` they were matched on equals this spectrum's value
                of its first filter column (or when either is unknown), so give
                the sequence view that column as ``spectrum_key_column``.
                Render-time only: not part of the cache.
            zoom_identifier: State identifier the plot keeps its zoom under,
                ``{"x": [lo, hi], "y": [lo, hi]}`` (default None: the zoom stays
                in the browser). The plot reports its ranges there after a zoom
                or pan and zooms to a value set there, e.g. by a saved view.
                Render-time only: not part of the cache.
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
        # Theoretical isotope envelope of one mass (set per render, not cached)
        self._envelope: dict[str, Any] | None = None
        # Isolation window marked in the m/z views (set per render, not cached)
        self._isolation_window: dict[str, float] | None = None

        # Render-time options, kept out of the cache config (see core/measure.py)
        self._measure = validate_measure(measure)
        self._measure_tolerance = validate_measure_tolerance(measure_tolerance)
        self._measure_residues = validate_measure_residues(measure_residues)

        # Render-time option, kept out of the cache config (see core/image_format.py)
        self._image_format = validate_image_format(image_format, allow_none=True)

        # Render-time option, kept out of the cache config (see core/keep_zoom.py)
        self._keep_zoom = validate_keep_zoom(keep_zoom)
        # Render-time option, kept out of the cache config
        self._fragment_matches_identifier = fragment_matches_identifier

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
        self._envelope = None
        self._isolation_window = None

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

    def set_envelope(
        self,
        mass_index: int | None,
        peaks: list[dict[str, Any]] | None,
    ) -> "DeconvolvedSpectrum":
        """
        Set the theoretical isotope envelope drawn for the next render.

        The m/z views ('annotated', and 'ladder' drilled down to a mass) draw
        the peaks as open circles while the mass at ``mass_index`` is selected,
        and only once the zoom puts neighbouring isotopes of a peak's charge
        (1.00235 / charge m/z apart, or the nearest other peak without a
        charge) at least 8 pixels apart.

        Args:
            mass_index: Index of the mass in the spectrum's mass list (the value
                ``mass_identifier`` holds when it is selected). None clears the
                envelope.
            peaks: One dict per theoretical peak with ``mz`` and ``intensity``,
                and optionally ``charge`` and ``isotope`` (shown on hover).
                None or empty clears the envelope.

        Returns:
            Self for method chaining.
        """
        if mass_index is None or not peaks:
            self._envelope = None
            return self
        envelope: dict[str, Any] = {
            "massIndex": int(mass_index),
            "mzs": [float(p["mz"]) for p in peaks],
            "intensities": [float(p["intensity"]) for p in peaks],
        }
        for key, name in (("charge", "charges"), ("isotope", "isotopes")):
            if all(p.get(key) is not None for p in peaks):
                envelope[name] = [int(p[key]) for p in peaks]
        self._envelope = envelope
        return self

    def set_isolation_window(
        self,
        lower_mz: float | None,
        upper_mz: float | None = None,
        target_mz: float | None = None,
    ) -> "DeconvolvedSpectrum":
        """
        Mark an isolation window in the m/z views for the next render.

        The window is shaded from ``lower_mz`` to ``upper_mz``, with a dashed
        line at ``target_mz`` when given. Use it on a precursor (MS1) spectrum
        to show the m/z range isolated for a fragmentation spectrum. It is
        drawn in the m/z views only: ``'annotated'``, and ``'ladder'`` drilled
        down to a mass.

        Args:
            lower_mz: Lower edge of the window. None clears the window.
            upper_mz: Upper edge of the window.
            target_mz: Isolation target, or None.

        Returns:
            Self for method chaining.
        """
        if lower_mz is None or upper_mz is None or not upper_mz > lower_mz:
            self._isolation_window = None
        else:
            self._isolation_window = {
                "lower": float(lower_mz),
                "upper": float(upper_mz),
            }
            if target_mz is not None:
                self._isolation_window["target"] = float(target_mz)
        return self

    def set_fragment_matches_identifier(
        self, identifier: str | None
    ) -> "DeconvolvedSpectrum":
        """Mark the fragment ions a ``ProteinSequenceView`` writes to ``identifier``.

        Not cached, so a view loaded from its cache can set it per render.
        See ``fragment_matches_identifier`` in the constructor.

        Returns:
            Self for method chaining.
        """
        self._fragment_matches_identifier = identifier
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
        if self._envelope:
            args["envelope"] = self._envelope
        if self._drilldown_title:
            args["drilldownTitle"] = self._drilldown_title
        # Only when set, so the args of other callers stay as they were
        if self._isolation_window:
            args["isolationWindow"] = self._isolation_window
        if self._fragment_matches_identifier:
            args["fragmentMatchesIdentifier"] = self._fragment_matches_identifier
            # The spectrum is told apart by its first filter column, which is
            # always among the data sent to Vue
            args["spectrumKeyColumn"] = next(iter(self._filters.values()), None)
        args.update(
            measure_args(self._measure, self._measure_tolerance, self._measure_residues)
        )
        args.update(image_format_args(self._image_format))
        args.update(zoom_args(self._zoom_identifier))
        args.update(keep_zoom_args(self._keep_zoom))
        return args
