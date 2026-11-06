"""Protein sequence view: fragment coverage, tags and modifications of a sequence."""

import hashlib
import json
import math
from functools import lru_cache
from typing import Any

import polars as pl

from ..core.base import BaseComponent
from ..core.image_format import image_format_args, validate_image_format
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
    "edited",
)


# Ion series the views match: the base series (whose masses the data carries)
# and their radical / hydrogen-shifted variants, with accepted spellings
ION_TYPES: tuple[str, ...] = ("a", "b", "c", "x", "y", "z")
ION_VARIANTS: dict[str, str] = {
    "a•": "a•",
    "a+1": "a•",
    "a.": "a•",
    "x•": "x•",
    "x+1": "x•",
    "x.": "x•",
    "y-1": "y-1",
    "y−1": "y-1",
    "z•": "z•",
    "z+1": "z•",
    "z.": "z•",
    "z-dot": "z•",
    "zp1": "z•",
}
# Fragmentation methods and the ion series they select (as in ProSight Lite)
FRAGMENTATION_METHODS: dict[str, tuple[str, ...]] = {
    "CID/HCD": ("b", "y"),
    "ETD/ECD": ("c", "z•"),
    "EThcD": ("b", "c", "y", "z•"),
    "UVPD": ("a", "a•", "b", "c", "x", "x•", "y", "y-1", "z"),
}
_METHOD_ALIASES = {"cid/hcd", "cid", "hcd", "etd/ecd", "etd", "ecd", "ethcd", "uvpd"}


def check_fragment_settings(settings: dict[str, Any] | None) -> None:
    """Raise ValueError for a fragment setting the views cannot apply.

    Checks the keys ``tolerance_unit`` ('ppm' or 'Da') and ``fragmentation``
    (a key of ``FRAGMENTATION_METHODS``, or 'CID', 'HCD', 'ETD', 'ECD'; case
    and spaces ignored). ``tolerance`` and ``ion_types`` are passed on as
    before: the view ignores ion series it does not know (see ``ION_TYPES``
    and ``ION_VARIANTS`` for the ones it draws).
    """
    if not isinstance(settings, dict):
        return
    unit = settings.get("tolerance_unit")
    if unit is not None and (
        not isinstance(unit, str) or unit.lower() not in ("ppm", "da")
    ):
        raise ValueError(
            f"settings['tolerance_unit'] must be 'ppm' or 'Da', not {unit!r}"
        )
    method = settings.get("fragmentation")
    if method is not None and (
        not isinstance(method, str)
        or method.replace(" ", "").lower() not in _METHOD_ALIASES
    ):
        raise ValueError(
            f"Unknown fragmentation method {method!r}; "
            f"use one of {list(FRAGMENTATION_METHODS)}"
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


def _pyopenms_text(value: Any) -> str:
    """pyOpenMS returns some names as bytes (latin-1 for the "®" in TMT names)."""
    if not isinstance(value, bytes):
        return str(value)
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.decode("latin-1")


@lru_cache(maxsize=1)
def _pyopenms_modifications() -> tuple:
    try:
        from pyopenms import ModificationsDB, ResidueModification
    except ImportError as e:  # pragma: no cover - depends on the environment
        raise ImportError(
            "modification_library='pyopenms' needs pyopenms (pip install pyopenms)"
        ) from e
    term = ResidueModification.TermSpecificity
    db = ModificationsDB()
    entries: dict[str, dict[str, Any]] = {}
    for i in range(db.getNumberOfModifications()):
        mod = db.getModification(i)
        full_id = _pyopenms_text(mod.getFullId())
        if full_id in entries:
            continue
        specificity = mod.getTermSpecificity()
        if specificity in (term.N_TERM, term.PROTEIN_N_TERM):
            site = "N-term"
        elif specificity in (term.C_TERM, term.PROTEIN_C_TERM):
            site = "C-term"
        else:
            site = _pyopenms_text(mod.getOrigin())
        entries[full_id] = {
            "id": full_id,
            "mass": float(mod.getDiffMonoMass()),
            "site": site,
        }
    return tuple(sorted(entries.values(), key=lambda e: (e["id"].lower(), e["site"])))


def _modification_library(
    library: list[dict[str, Any]] | str | None,
) -> list[dict[str, Any]] | None:
    """A modification library as the component args carry it."""
    if isinstance(library, str):
        if library != "pyopenms":
            raise ValueError(
                f"a modification library must be a list, 'pyopenms' or None, not {library!r}"
            )
        library = _pyopenms_modifications()
    if library is None:
        return None
    return [
        {"id": str(m["id"]), "mass": float(m["mass"]), "site": m.get("site")}
        for m in library
    ]


def pyopenms_modification_library() -> list[dict[str, Any]]:
    """Every modification in pyOpenMS ``ModificationsDB`` (Unimod and more), as
    the dicts ``modification_library`` takes: ``id`` (the full id, e.g.
    ``'Carbamidomethyl (C)'``, which ``AASequence.fromString`` and
    ``ModificationsDB.getModification`` accept), ``mass`` (monoisotopic mass
    shift) and ``site`` (a residue, ``'N-term'`` or ``'C-term'``).

    Raises ImportError without pyopenms.
    """
    return [dict(e) for e in _pyopenms_modifications()]


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
      by an external tool, see ``AnnotatedFragment`` in the Vue types),
      ``edited`` (True for an entry the user edited, see ``edit_identifier``).
    - Spectrum columns: ``mass_column`` (list of deconvolved masses) and
      ``precursor_mass_column``.

    Alternatively pass one fixed entry as ``sequence`` (a dict with the
    sequence columns); then each row of data is just a spectrum, e.g. to match
    a user-given sequence against the selected scan.

    Without annotated fragments, fragments are matched here against the
    spectrum's masses within the tolerance (ppm), honouring variable
    modifications the user sets on residues (right click). For each such
    modification the view works out from the matched fragments which residues
    it can sit on: fragments that match only with its mass shift place it
    inside them, fragments that match only without it place it outside. When
    several residues remain (or the shift fits several modifications of the
    library at those residues), the view marks the residues with a dashed
    line and lists the alternatives in the tooltip and the list of applied
    modifications; it also notes a modification the fragments place on other
    residues.

    With ``edit_identifier``, an identification can be edited: a pencil
    button asks the app to start from the search result, after which the
    residue menus, the "change sequence" dialog and a reset button write
    edits (see ``edit_identifier``).

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
        fragmentation_column: str | None = None,
        spectrum_key_column: str | None = None,
        mass_identifier: str | None = None,
        aa_identifier: str | None = None,
        sequence_identifier: str | None = None,
        modification_library: list[dict[str, Any]] | str | None = None,
        modifications_identifier: str | None = None,
        modifications: list[str] | None = None,
        proforma_copy: bool = False,
        variable_modification_library: list[dict[str, Any]] | str | None = None,
        variable_modification_suggestions: dict[str, list[str]] | None = None,
        settings: dict[str, Any] | None = None,
        title: str | None = "Sequence View",
        annotation_title: str = "Fragment annotation",
        svg_filename: str = "sequence",
        accent_color: str | None = None,
        fragment_identifier: str | None = None,
        edit_identifier: str | None = None,
        fragment_matches_identifier: str | None = None,
        entry_title: str = "Identification",
        observed_mass_label: str = "Observed mass",
        image_format: str | None = None,
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
            spectrum_key_column: Column identifying the spectrum of a row (e.g.
                its scan index), sent with the matched fragments (see
                ``fragment_matches_identifier``) so a spectrum view marks them
                only on that spectrum.
            fragmentation_column: Column with the fragmentation method of the
                spectrum (a ``fragmentation`` value of ``settings``, e.g.
                'ETD' or 'HCD'; None or unknown keeps the current ion series).
                When the selected spectrum's method changes, the view selects
                that method's ion series and shows the method in the mass
                summary; not with annotated fragments, which were annotated
                for the search's ion types.
            mass_identifier: Identifier holding the selected mass, as an index
                into the masses of the spectrum (e.g. a mass table's selection).
                Selecting a fragment selects its mass and vice versa.
            aa_identifier: Identifier holding the selected residue (0-based).
                Clicking a residue covered by tags toggles it.
            sequence_identifier: Identifier the "change sequence" dialog writes a
                new sequence to. None hides the button. The app reads it and
                rebuilds the view for the new sequence.
            modification_library: Fixed modifications offered in the "change
                sequence" dialog, as dicts with ``id`` (e.g.
                ``'Carbamidomethyl (C)'``) and ``mass`` (the mass shift); a
                ``site`` key is shown when given. ``'pyopenms'`` offers every
                modification in pyOpenMS ``ModificationsDB`` (see
                ``pyopenms_modification_library``; needs pyopenms). None shows
                no picker.
            modifications_identifier: Identifier the dialog writes the ids of
                the picked modifications to (a list), before it writes the
                sequence. Needs ``modification_library``.
            modifications: Ids preselected in the picker, e.g. the fixed
                modifications the current sequence carries.
            variable_modification_library: Variable modifications the menu of
                a residue (right click) offers instead of the built-in six, in
                the form of ``modification_library`` (``'pyopenms'`` included);
                each residue and terminus lists the entries of its ``site``.
                The menu gets a search field (name or mass) and lists
                suggested modifications for the residue until something is
                typed; a list under the sequence shows the applied
                modifications with their total mass. None keeps the built-in
                menu.
            variable_modification_suggestions: Library ids suggested in the
                menu per site (a residue letter, ``'N-term'`` or
                ``'C-term'``), e.g. ``{'K': ['Acetyl (K)', 'GG (K)']}``. None
                uses built-in suggestions of common biological modifications
                and artefacts; ``{}`` suggests nothing.
            settings: Initial fragment settings, all keys optional:
                ``tolerance`` (default 10), ``tolerance_unit`` ('ppm' default,
                or 'Da'), ``ion_types`` (a b c x y z and the variants a• x•
                y-1 z•, also written a+1 x+1 z+1; default b and y) and
                ``fragmentation`` ('CID/HCD', 'ETD/ECD', 'EThcD' or 'UVPD',
                selecting that method's ion series when ``ion_types`` is not
                given). The user can change all of them in the view. See
                ``check_fragment_settings``.
            title: Title above the view (None: no title).
            annotation_title: Label of the ``annotation_summary`` line.
            svg_filename: File name (without extension) of the image download;
                the extension follows the image format.
            accent_color: Colour of the dialog buttons (default: the theme's
                primary colour).
            proforma_copy: Show a "Copy as ProForma" button that copies the
                shown proteoform in ProForma 2.0 notation, with its fixed,
                localized and user-set modifications.
            fragment_identifier: Identifier the selected fragment's bounds are
                written to, as {'name', 'kind' ('N', 'C' or 'I'), 'start',
                'end'} (positions in the sequence), e.g. for a
                ``ProteinStructureView``.
            edit_identifier: Identifier edits of an identification are
                written to, each a dict with ``action`` and a fresh ``nonce``
                (apply each nonce once). None (default): identifications are
                not editable. ``'edit'``: the user wants to edit the shown
                identification; the app then gives the entry with
                ``edited=True``, fragment masses of the unmodified sequence,
                no annotated fragments, and the search's modifications each
                on one residue (``start == end``). The view sets those on
                the residues, matches fragments here, and adds them to the
                theoretical mass. ``'update'``: the edited entry, with
                ``sequence`` (string), ``start_position``, ``end_position``
                and ``modifications`` (list of {start, end, mass_diff,
                labels}; -1 the N-terminus, the sequence length the
                C-terminus). ``'reset'``: back to the search result.
                Render-time only: not part of the cache.
            fragment_matches_identifier: Identifier the matched fragment
                ions are written to whenever they change (another entry or
                spectrum, an edited sequence or modification, the ion types,
                the tolerance), so spectra can mark them: a dict with
                ``spectrum`` (the value of ``spectrum_key_column``, or None),
                ``tolerance`` ({'value', 'unit'}) and ``fragments``, one dict
                per matched ion with ``name`` (e.g. 'b12'), ``ion`` (its ion
                type, e.g. 'b' or 'z+1'), ``kind`` ('N', 'C' or 'I'),
                ``mass`` (the observed mass), ``massIndex`` (its index in the
                spectrum's mass list, or None) and, for annotated fragments,
                ``charge`` and ``mz``. None while no spectrum is matched. Pass
                the same identifier to ``DeconvolvedSpectrum``. Render-time
                only: not part of the cache.
            entry_title: Heading of the mass summary of an entry with an
                observed mass.
            observed_mass_label: Label of the entry's observed mass in that
                summary.
            float_precision: Masses are compared at ppm level, so they are kept
                as Float64 by default.
            image_format: Format of the image download: 'svg', 'png', 'jpeg'
                or 'webp'. None (default) follows
                ``openms_insight.set_image_format()`` (default 'svg') when the
                component is drawn. Render-time only: not part of the cache.
            **kwargs: Additional configuration options.
        """
        self._sequence = _json_safe(sequence) if sequence is not None else None
        self._mass_column = mass_column
        self._precursor_mass_column = precursor_mass_column
        self._fragmentation_column = fragmentation_column
        self._spectrum_key_column = spectrum_key_column
        self._mass_identifier = mass_identifier
        self._aa_identifier = aa_identifier
        self._sequence_identifier = sequence_identifier
        # Per render, not cached: the picker of the "change sequence" dialog
        self.set_modification_picker(
            modification_library, modifications_identifier, modifications
        )
        # Per render, not cached
        self._proforma_copy = bool(proforma_copy)
        self.set_variable_modification_library(
            variable_modification_library, variable_modification_suggestions
        )
        check_fragment_settings(settings)
        self._settings = settings
        self._title = title
        self._annotation_title = annotation_title
        self._svg_filename = svg_filename
        # Render-time option, kept out of the cache config (see core/image_format.py)
        self._image_format = validate_image_format(image_format, allow_none=True)
        self._accent_color = accent_color
        self._fragment_identifier = fragment_identifier
        # Render-time option, kept out of the cache config
        self._edit_identifier = edit_identifier
        # Render-time option, kept out of the cache config
        self._fragment_matches_identifier = fragment_matches_identifier
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
            fragmentation_column=fragmentation_column,
            spectrum_key_column=spectrum_key_column,
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
        if self._fragmentation_column is not None:
            config["fragmentation_column"] = self._fragmentation_column
        if self._spectrum_key_column is not None:
            config["spectrum_key_column"] = self._spectrum_key_column
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
        self._fragmentation_column = config.get("fragmentation_column")
        self._spectrum_key_column = config.get("spectrum_key_column")
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
            c
            for c in (
                self._mass_column,
                self._precursor_mass_column,
                self._fragmentation_column,
                self._spectrum_key_column,
            )
            if c is not None
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
                if self._fragmentation_column is not None:
                    spectrum_data["fragmentation"] = row.get(self._fragmentation_column)
                if self._spectrum_key_column is not None:
                    spectrum_data["key"] = _json_safe(row.get(self._spectrum_key_column))
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

    def set_modification_picker(
        self,
        library: list[dict[str, Any]] | str | None,
        identifier: str | None = None,
        selected: list[str] | None = None,
    ) -> "ProteinSequenceView":
        """Offer fixed modifications in the "change sequence" dialog.

        Not cached, so a view loaded from its cache can set it per render. See
        ``modification_library``, ``modifications_identifier`` and
        ``modifications`` in the constructor.

        Returns:
            Self for method chaining.
        """
        self._modification_library = _modification_library(library)
        self._modifications_identifier = identifier
        self._modifications = list(selected) if selected is not None else []
        return self

    def set_variable_modification_library(
        self,
        library: list[dict[str, Any]] | str | None,
        suggested: dict[str, list[str]] | None = None,
    ) -> "ProteinSequenceView":
        """Offer these variable modifications in the residue menus.

        Not cached, so a view loaded from its cache can set it per render. See
        ``variable_modification_library`` and
        ``variable_modification_suggestions`` in the constructor.

        Returns:
            Self for method chaining.
        """
        self._variable_modification_library = _modification_library(library)
        if suggested is not None:
            suggested = {
                str(site): [str(i) for i in ids] for site, ids in suggested.items()
            }
        self._variable_modification_suggestions = suggested
        return self

    def set_edit_identifier(self, identifier: str | None) -> "ProteinSequenceView":
        """Make identifications editable, writing edits to ``identifier``.

        Not cached, so a view loaded from its cache can set it per render.
        See ``edit_identifier`` in the constructor.

        Returns:
            Self for method chaining.
        """
        self._edit_identifier = identifier
        return self

    def set_fragment_matches_identifier(
        self, identifier: str | None
    ) -> "ProteinSequenceView":
        """Write the matched fragment ions to ``identifier`` for spectra to mark.

        Not cached, so a view loaded from its cache can set it per render.
        See ``fragment_matches_identifier`` in the constructor.

        Returns:
            Self for method chaining.
        """
        self._fragment_matches_identifier = identifier
        return self

    def set_proforma_copy(self, enabled: bool = True) -> "ProteinSequenceView":
        """Show or hide the "Copy as ProForma" button.

        Not cached, so a view loaded from its cache can set it per render. See
        ``proforma_copy`` in the constructor.

        Returns:
            Self for method chaining.
        """
        self._proforma_copy = bool(enabled)
        return self

    def _get_component_args(self) -> dict[str, Any]:
        return {
            "componentType": self._get_vue_component_name(),
            "title": self._title,
            "annotationTitle": self._annotation_title,
            "massIdentifier": self._mass_identifier,
            "aaIdentifier": self._aa_identifier,
            "sequenceIdentifier": self._sequence_identifier,
            "modificationLibrary": self._modification_library,
            "modificationsIdentifier": self._modifications_identifier,
            "modifications": self._modifications,
            "proformaCopy": self._proforma_copy,
            "variableModificationLibrary": self._variable_modification_library,
            "variableModificationSuggestions": self._variable_modification_suggestions,
            "settings": self._settings,
            "tag": self._tag,
            "svgFilename": self._svg_filename,
            **image_format_args(self._image_format),
            "accentColor": self._accent_color,
            "fragmentIdentifier": self._fragment_identifier,
            "editIdentifier": self._edit_identifier,
            "fragmentMatchesIdentifier": self._fragment_matches_identifier,
            "entryTitle": self._entry_title,
            "observedMassLabel": self._observed_mass_label,
        }
