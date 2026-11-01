"""Protein sequence view: fragment coverage, tags and modifications of a sequence."""

import hashlib
import json
import math
from typing import Any

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.filtering import _make_cache_key

# Columns describing one sequence entry. Only
# 'sequence' is required; the others are drawn when present.
SEQUENCE_COLUMNS: tuple[str, ...] = (
    "sequence",
    "theoretical_mass",
    "fixed_modifications",
    "coverage",
    "maxCoverage",
    "fragment_masses_a",
    "fragment_masses_b",
    "fragment_masses_c",
    "fragment_masses_x",
    "fragment_masses_y",
    "fragment_masses_z",
    "start_position",
    "end_position",
    "observed_mass",
    "modifications",
    "annotated_fragments",
    "annotation_summary",
)


def _json_safe(value: Any) -> Any:
    """Replace NaN and infinities, which JSON cannot carry, with None."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


@register_component("protein_sequence_view")
class ProteinSequenceView(BaseComponent):
    """
    Sequence view of a protein (or peptide) with its fragment and tag evidence.

    Draws the protein sequence as a grid of residues and marks on it the matched
    fragment ions (a/b/c/x/y/z), sequence tag coverage, the selected tag,
    truncations, localized and ambiguous modifications and, with externally
    annotated fragments, internal fragments. Below the grid a table lists the matched
    fragments. Residues, fragment rows and the masses of the spectrum are linked:
    clicking one selects the others.

    Each row of data is one sequence entry (e.g. an identification) with its spectrum:

    - Sequence columns (see ``SEQUENCE_COLUMNS``): ``sequence`` (list of
      residues), ``fragment_masses_<ion>`` (per position, the theoretical
      masses), ``coverage``/``maxCoverage`` (tag coverage per residue),
      ``start_position``/``end_position`` (0-based, -1 when undetermined),
      ``theoretical_mass``, ``observed_mass`` (observed mass of the entry; its
      presence switches to the identification view with tags and truncations),
      ``modifications`` (list of {start, end, mass_diff, labels}),
      ``fixed_modifications`` (residues carrying a fixed modification),
      ``annotated_fragments`` and ``annotation_summary`` (fragments annotated
      by an external tool, see ``AnnotatedFragment`` in the Vue types).
    - Spectrum columns: ``mass_column`` (list of deconvolved masses) and
      ``precursor_mass_column``.

    Alternatively pass one fixed entry as ``sequence`` (a dict with the
    sequence columns); then each row of data is just a spectrum, e.g. to match
    a user-given sequence against the selected scan.

    Without annotated fragments, fragments are matched here against the
    spectrum's masses within the tolerance (ppm), honouring variable
    modifications the user sets on residues (right click).

    Example:
        view = ProteinSequenceView(
            cache_id="sequence_view",
            data=identifications,  # one row per identification
            filters={"protein": "hit_index"},
            mass_identifier="mass",
            aa_identifier="aa",
        )
        view.set_tag(start=12, end=18)
        view(key="sequence_view", state_manager=state_manager)
    """

    _component_type: str = "protein_sequence_view"
    # One row holds a whole sequence entry with its spectrum
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
        sequence: dict[str, Any] | None = None,
        mass_column: str | None = "masses",
        precursor_mass_column: str | None = "precursor_mass",
        mass_identifier: str | None = None,
        aa_identifier: str | None = None,
        sequence_identifier: str | None = None,
        settings: dict[str, Any] | None = None,
        title: str | None = "Sequence View",
        annotation_title: str = "Fragment annotation",
        svg_filename: str = "sequence",
        accent_color: str | None = None,
        fragment_identifier: str | None = None,
        entry_title: str = "Identification",
        observed_mass_label: str = "Observed mass",
        float_precision: str = "float64",
        **kwargs,
    ):
        """
        Initialize the ProteinSequenceView component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
            data: Polars LazyFrame, one row per entry (or per spectrum when
                ``sequence`` is given). See the class docstring for columns.
            data_path: Path to a parquet file with the data.
            filters: Mapping of identifier names to column names selecting the
                row to show, e.g. {'protein': 'hit_index'}.
            filter_defaults: Default values for filters when state is None.
            interactivity: Not used; clicks set the identifiers below.
            cache_path: Base path for cache storage.
            regenerate_cache: Rebuild the cache even if a matching one exists.
            sequence: One fixed entry (dict of sequence columns) shown for
                every row of data.
            mass_column: List column with the spectrum's deconvolved masses.
                None: no spectrum (fragments only from annotated_fragments).
            precursor_mass_column: Column with the precursor mass, shown against
                the theoretical mass when no observed mass is given.
            mass_identifier: Identifier holding the selected mass, as an index
                into the masses of the spectrum (e.g. a mass table's selection).
                Selecting a fragment selects its mass and vice versa.
            aa_identifier: Identifier holding the selected residue (0-based).
                Clicking a residue covered by tags toggles it.
            sequence_identifier: Identifier the "change sequence" dialog writes a
                new sequence to. None hides the button. The app reads it and
                rebuilds the view for the new sequence.
            settings: Initial fragment settings: {'tolerance': ppm,
                'ion_types': ['b', 'y', ...]}.
            title: Title above the view (None: no title).
            annotation_title: Label of the ``annotation_summary`` line.
            svg_filename: File name for the SVG download.
            accent_color: Colour of the dialog buttons (default: the theme's
                primary colour).
            fragment_identifier: Identifier the selected fragment's bounds are
                written to, as {'name', 'kind' ('N', 'C' or 'I'), 'start',
                'end'} (positions in the sequence), e.g. for a
                ``ProteinStructureView``.
            entry_title: Heading of the mass summary of an entry with an
                observed mass.
            observed_mass_label: Label of the entry's observed mass in that
                summary.
            float_precision: Masses are compared at ppm level, so they are kept
                as Float64 by default.
            **kwargs: Additional configuration options.
        """
        self._sequence = _json_safe(sequence) if sequence is not None else None
        self._mass_column = mass_column
        self._precursor_mass_column = precursor_mass_column
        self._mass_identifier = mass_identifier
        self._aa_identifier = aa_identifier
        self._sequence_identifier = sequence_identifier
        self._settings = settings
        self._title = title
        self._annotation_title = annotation_title
        self._svg_filename = svg_filename
        self._accent_color = accent_color
        self._fragment_identifier = fragment_identifier
        self._entry_title = entry_title
        self._observed_mass_label = observed_mass_label
        # Sequence tag marked on the sequence (set per render, not cached)
        self._tag: dict[str, int] | None = None

        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            filters=filters,
            filter_defaults=filter_defaults,
            interactivity=interactivity,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            float_precision=float_precision,
            sequence=self._sequence,
            mass_column=mass_column,
            precursor_mass_column=precursor_mass_column,
            mass_identifier=mass_identifier,
            aa_identifier=aa_identifier,
            sequence_identifier=sequence_identifier,
            settings=settings,
            title=title,
            annotation_title=annotation_title,
            svg_filename=svg_filename,
            accent_color=accent_color,
            fragment_identifier=fragment_identifier,
            entry_title=entry_title,
            observed_mass_label=observed_mass_label,
            **kwargs,
        )

    def _get_cache_config(self) -> dict[str, Any]:
        config = {
            "sequence": self._sequence,
            "mass_column": self._mass_column,
            "precursor_mass_column": self._precursor_mass_column,
            "mass_identifier": self._mass_identifier,
            "aa_identifier": self._aa_identifier,
            "sequence_identifier": self._sequence_identifier,
            "settings": self._settings,
            "title": self._title,
            "annotation_title": self._annotation_title,
            "svg_filename": self._svg_filename,
        }
        if self._accent_color is not None:
            config["accent_color"] = self._accent_color
        if self._fragment_identifier is not None:
            config["fragment_identifier"] = self._fragment_identifier
        if self._entry_title != "Identification":
            config["entry_title"] = self._entry_title
        if self._observed_mass_label != "Observed mass":
            config["observed_mass_label"] = self._observed_mass_label
        return config

    def _restore_cache_config(self, config: dict[str, Any]) -> None:
        self._sequence = config.get("sequence")
        self._mass_column = config.get("mass_column")
        self._precursor_mass_column = config.get("precursor_mass_column")
        self._mass_identifier = config.get("mass_identifier")
        self._aa_identifier = config.get("aa_identifier")
        self._sequence_identifier = config.get("sequence_identifier")
        self._settings = config.get("settings")
        self._title = config.get("title")
        self._annotation_title = config.get("annotation_title", "Fragment annotation")
        self._svg_filename = config.get("svg_filename", "sequence")
        self._accent_color = config.get("accent_color")
        self._fragment_identifier = config.get("fragment_identifier")
        self._entry_title = config.get("entry_title", "Identification")
        self._observed_mass_label = config.get("observed_mass_label", "Observed mass")
        self._tag = None

    def _spectrum_columns(self) -> list[str]:
        return [
            c for c in (self._mass_column, self._precursor_mass_column) if c is not None
        ]

    def _validate_mappings(self) -> None:
        super()._validate_mappings()
        columns = self._raw_data.collect_schema().names()
        if self._sequence is None and "sequence" not in columns:
            raise ValueError(
                "Data needs a 'sequence' column, or pass one entry as sequence=. "
                f"Available columns: {columns}"
            )
        if self._sequence is not None and "sequence" not in self._sequence:
            raise ValueError("sequence= needs a 'sequence' entry (list of residues)")
        for column in self._spectrum_columns():
            if column not in columns:
                raise ValueError(
                    f"Column '{column}' not found in data. Available columns: {columns}"
                )

    def _preprocess(self) -> None:
        data = self._raw_data
        available = data.collect_schema().names()
        keep: list[str] = []
        if self._sequence is None:
            keep += [c for c in SEQUENCE_COLUMNS if c in available]
        keep += self._spectrum_columns()
        keep += list(self._filters.values())
        keep = list(dict.fromkeys(keep))
        data = data.select(keep)
        if self._filters:
            data = data.sort(list(self._filters.values()), maintain_order=True)
        self._preprocessed_data["data"] = data

    def _get_vue_component_name(self) -> str:
        return "ProteinSequenceView"

    def _get_data_key(self) -> str:
        return "sequenceData"

    def get_state_dependencies(self) -> list[str]:
        # Mass and residue selections only change highlighting, done in Vue
        return list(self._filters.keys())

    def _selected_row(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """The first row of data matching the filters, or None."""
        data = self._preprocessed_data.get("data")
        if data is None:
            data = self._raw_data
        if data is None:
            return None
        if isinstance(data, pl.DataFrame):
            data = data.lazy()
        for identifier, value in _make_cache_key(
            self._filters, state, self._filter_defaults
        ):
            if value is None:
                return None
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            data = data.filter(pl.col(self._filters[identifier]) == value)
        rows = data.head(1).collect().to_dicts()
        return rows[0] if rows else None

    def _prepare_vue_data(self, state: dict[str, Any]) -> dict[str, Any]:
        row = self._selected_row(state)
        sequence_data: dict[str, Any] | None = None
        spectrum_data: dict[str, Any] | None = None
        if row is not None:
            if self._sequence is not None:
                sequence_data = self._sequence
            else:
                sequence_data = _json_safe(
                    {c: row[c] for c in SEQUENCE_COLUMNS if c in row}
                )
            if self._mass_column is not None:
                spectrum_data = _json_safe(
                    {
                        "masses": row.get(self._mass_column) or [],
                        "precursorMass": row.get(self._precursor_mass_column)
                        if self._precursor_mass_column
                        else None,
                    }
                )
        payload = {"sequenceData": sequence_data, "spectrumData": spectrum_data}
        data_hash = hashlib.md5(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        return {**payload, "_hash": data_hash}

    def set_tag(
        self, start: int | None, end: int | None = None
    ) -> "ProteinSequenceView":
        """
        Mark a sequence tag on the sequence for the next render.

        Args:
            start: First residue of the tag (0-based), or None to clear.
            end: Last residue of the tag (0-based, inclusive).

        Returns:
            Self for method chaining.
        """
        if start is None or end is None:
            self._tag = None
        else:
            self._tag = {"startPos": int(start), "endPos": int(end)}
        return self

    def _get_component_args(self) -> dict[str, Any]:
        return {
            "componentType": self._get_vue_component_name(),
            "title": self._title,
            "annotationTitle": self._annotation_title,
            "massIdentifier": self._mass_identifier,
            "aaIdentifier": self._aa_identifier,
            "sequenceIdentifier": self._sequence_identifier,
            "settings": self._settings,
            "tag": self._tag,
            "svgFilename": self._svg_filename,
            "accentColor": self._accent_color,
            "fragmentIdentifier": self._fragment_identifier,
            "entryTitle": self._entry_title,
            "observedMassLabel": self._observed_mass_label,
        }
