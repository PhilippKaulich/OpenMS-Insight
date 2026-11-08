"""SequenceView component for peptide/protein sequence visualization with fragment matching."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import polars as pl

from ..core.cache import atomic_write, cache_lock
from ..core.image_format import image_format_args, validate_image_format
from ..core.registry import register_component
from ..core.storage import scan_parquet
from ..preprocessing.filtering import optimize_for_transfer

# Proton mass for m/z calculations
PROTON_MASS = 1.007276

# Cache version - increment when cache format changes
CACHE_VERSION = 1


def parse_openms_sequence(sequence_str: str) -> tuple[list[str], list[float | None]]:
    """Parse OpenMS sequence format to extract residues and modification mass shifts.

    Converts e.g. 'SHC(Carbamidomethyl)IAEVEK' to:
    - residues: ['S', 'H', 'C', 'I', 'A', 'E', 'V', 'E', 'K']
    - modifications: [None, None, 57.02, None, None, None, None, None, None]

    Args:
        sequence_str: Peptide sequence in OpenMS format with modifications in parentheses

    Returns:
        Tuple of (residues list, modifications list where None means unmodified)
    """
    try:
        from pyopenms import AASequence

        aa_seq = AASequence.fromString(sequence_str)
        residues = []
        modifications = []

        for i in range(aa_seq.size()):
            residue = aa_seq.getResidue(i)
            one_letter = residue.getOneLetterCode()
            residues.append(one_letter)

            mod = residue.getModification()
            if mod:
                diff_mono = mod.getDiffMonoMass()
                modifications.append(round(diff_mono, 2))
            else:
                modifications.append(None)

        return residues, modifications
    except ImportError:
        # Fallback: just extract single-letter codes (naive parsing)
        residues = []
        modifications = []
        i = 0
        while i < len(sequence_str):
            if sequence_str[i].isupper():
                residues.append(sequence_str[i])
                modifications.append(None)
                i += 1
            elif sequence_str[i] == "(":
                # Skip modification name in parentheses
                end = sequence_str.find(")", i)
                if end > i:
                    i = end + 1
                else:
                    i += 1
            else:
                i += 1
        return residues, modifications
    except Exception:
        # On any error, return the raw sequence as single letters
        return list(sequence_str), [None] * len(sequence_str)


def calculate_fragment_masses_pyopenms(
    sequence_str: str,
) -> dict[str, list[list[float]]]:
    """Calculate theoretical fragment masses using pyOpenMS TheoreticalSpectrumGenerator.

    Args:
        sequence_str: Peptide sequence string (can include modifications)

    Returns:
        Dict with fragment_masses_a, fragment_masses_b, etc.
        Each is a list of lists (one per position, supporting multiple masses).
    """
    try:
        from pyopenms import AASequence, MSSpectrum, TheoreticalSpectrumGenerator

        aa_seq = AASequence.fromString(sequence_str)
        n = aa_seq.size()

        # Configure TheoreticalSpectrumGenerator
        tsg = TheoreticalSpectrumGenerator()
        params = tsg.getParameters()

        params.setValue("add_a_ions", "true")
        params.setValue("add_b_ions", "true")
        params.setValue("add_c_ions", "true")
        params.setValue("add_x_ions", "true")
        params.setValue("add_y_ions", "true")
        params.setValue("add_z_ions", "true")
        params.setValue("add_first_prefix_ion", "true")  # Include b1/a1/c1 ions
        params.setValue("add_metainfo", "true")

        tsg.setParameters(params)

        # Generate spectrum for charge 1, then convert to neutral masses
        spec = MSSpectrum()
        tsg.getSpectrum(spec, aa_seq, 1, 1)

        ion_types = ["a", "b", "c", "x", "y", "z"]
        result = {f"fragment_masses_{ion}": [[] for _ in range(n)] for ion in ion_types}

        # Get ion names from StringDataArrays
        ion_names = []
        sdas = spec.getStringDataArrays()
        for sda in sdas:
            if sda.getName() == "IonNames":
                for i in range(sda.size()):
                    name = sda[i]
                    if isinstance(name, bytes):
                        name = name.decode("utf-8")
                    ion_names.append(name)
                break

        # Parse peaks and organize by ion type and position
        for i in range(spec.size()):
            peak = spec[i]
            # Convert singly-charged m/z to neutral mass
            mz_charge1 = peak.getMZ()
            neutral_mass = mz_charge1 - PROTON_MASS
            ion_name = ion_names[i] if i < len(ion_names) else ""

            if not ion_name:
                continue

            # Parse ion name (e.g., "b3+", "y5++")
            ion_type = None
            ion_number = None

            for t in ion_types:
                if ion_name.lower().startswith(t):
                    ion_type = t
                    try:
                        num_str = ""
                        for c in ion_name[1:]:
                            if c.isdigit():
                                num_str += c
                            else:
                                break
                        if num_str:
                            ion_number = int(num_str)
                    except (ValueError, IndexError):
                        pass
                    break

            if ion_type and ion_number and 1 <= ion_number <= n:
                idx = ion_number - 1
                key = f"fragment_masses_{ion_type}"
                if idx < len(result[key]):
                    result[key][idx].append(neutral_mass)

        return result

    except ImportError:
        # Fallback to simple calculation without pyOpenMS
        return _calculate_fragment_masses_simple(sequence_str)
    except Exception as e:
        print(f"Error calculating fragments for {sequence_str}: {e}")
        return {f"fragment_masses_{ion}": [] for ion in ["a", "b", "c", "x", "y", "z"]}


def _calculate_fragment_masses_simple(
    sequence_str: str,
) -> dict[str, list[list[float]]]:
    """Fallback fragment calculation without pyOpenMS."""
    # Amino acid monoisotopic masses
    AA_MASSES = {
        "A": 71.037114,
        "R": 156.101111,
        "N": 114.042927,
        "D": 115.026943,
        "C": 103.009185,
        "E": 129.042593,
        "Q": 128.058578,
        "G": 57.021464,
        "H": 137.058912,
        "I": 113.084064,
        "L": 113.084064,
        "K": 128.094963,
        "M": 131.040485,
        "F": 147.068414,
        "P": 97.052764,
        "S": 87.032028,
        "T": 101.047679,
        "U": 150.953633,
        "W": 186.079313,
        "Y": 163.063329,
        "V": 99.068414,
    }

    # Ion type offsets
    ION_OFFSETS = {
        "a": -27.994915,
        "b": 0.0,
        "c": 17.026549,
        "x": 43.989829,
        "y": 18.010565,
        "z": 1.991841,
    }

    # Extract plain sequence
    residues, _ = parse_openms_sequence(sequence_str)
    n = len(residues)
    result = {}

    # Calculate prefix masses
    prefix_masses = []
    mass = 0.0
    for aa in residues:
        mass += AA_MASSES.get(aa, 0.0)
        prefix_masses.append(mass)

    # Calculate suffix masses
    suffix_masses = []
    mass = 0.0
    for aa in reversed(residues):
        mass += AA_MASSES.get(aa, 0.0)
        suffix_masses.append(mass)
    suffix_masses = list(reversed(suffix_masses))

    # Prefix ions (a, b, c)
    for ion_type in ["a", "b", "c"]:
        masses = []
        for i in range(n):
            ion_mass = prefix_masses[i] + ION_OFFSETS[ion_type]
            masses.append([ion_mass])
        result[f"fragment_masses_{ion_type}"] = masses

    # Suffix ions (x, y, z)
    for ion_type in ["x", "y", "z"]:
        masses = []
        for i in range(n):
            idx = n - i - 1
            ion_mass = suffix_masses[idx] + ION_OFFSETS[ion_type]
            masses.append([ion_mass])
        result[f"fragment_masses_{ion_type}"] = masses

    return result


def get_theoretical_mass(sequence_str: str) -> float:
    """Calculate monoisotopic mass of a peptide sequence."""
    try:
        from pyopenms import AASequence

        aa_seq = AASequence.fromString(sequence_str)
        return aa_seq.getMonoWeight()
    except ImportError:
        # Fallback
        H2O = 18.010565
        AA_MASSES = {
            "A": 71.037114,
            "R": 156.101111,
            "N": 114.042927,
            "D": 115.026943,
            "C": 103.009185,
            "E": 129.042593,
            "Q": 128.058578,
            "G": 57.021464,
            "H": 137.058912,
            "I": 113.084064,
            "L": 113.084064,
            "K": 128.094963,
            "M": 131.040485,
            "F": 147.068414,
            "P": 97.052764,
            "S": 87.032028,
            "T": 101.047679,
            "U": 150.953633,
            "W": 186.079313,
            "Y": 163.063329,
            "V": 99.068414,
        }
        residues, _ = parse_openms_sequence(sequence_str)
        mass = H2O
        for aa in residues:
            mass += AA_MASSES.get(aa, 0.0)
        return mass
    except Exception:
        return 0.0


# Default annotation configuration
DEFAULT_ANNOTATION_CONFIG = {
    "ion_types": ["b", "y"],
    "neutral_losses": True,
    "proton_loss_addition": False,
    "tolerance": 20.0,
    "tolerance_ppm": True,
    "colors": {
        "a": "#9B59B6",
        "b": "#E74C3C",
        "c": "#E67E22",
        "x": "#1ABC9C",
        "y": "#3498DB",
        "z": "#2ECC71",
    },
}


# Mass shifts matched alongside each ion when neutral losses or proton
# loss/addition are enabled. Kept in step with extraFragmentTypeObject in
# js-component/src/components/sequence/modification.ts.
NEUTRAL_LOSSES = [("-H2O", -18.0105646863), ("-NH3", -17.0265491015)]
PROTON_SHIFTS = [("-H", -1.0078250319), ("+H", 1.0078250319)]

_PREFIX_IONS = ("a", "b", "c")


def match_fragment_ions(
    sequence_str: str,
    observed: "np.ndarray",
    precursor_charge: int = 1,
    annotation_config: dict[str, Any] | None = None,
    deconvolved: bool = False,
    intensities: Optional["np.ndarray"] = None,
    peak_ids: Optional["np.ndarray"] = None,
    include_unmatched: bool = False,
) -> list[dict[str, Any]]:
    """Match a peptide's theoretical fragment ions against one spectrum.

    Follows the matching the SequenceView draws: each selected ion type, with
    neutral losses and proton loss/addition when enabled, at every charge from
    1 to the precursor charge (neutral masses only when ``deconvolved``), and
    every observed peak within tolerance is reported.

    Args:
        sequence_str: Peptide sequence in OpenMS format.
        observed: Observed m/z values (or neutral masses when deconvolved).
        precursor_charge: Highest fragment charge to consider.
        annotation_config: ``ion_types``, ``neutral_losses``,
            ``proton_loss_addition``, ``tolerance`` and ``tolerance_ppm``;
            missing keys fall back to ``DEFAULT_ANNOTATION_CONFIG``.
        deconvolved: Whether ``observed`` holds neutral masses.
        intensities: Optional intensities, aligned with ``observed``.
        peak_ids: Optional peak ids, aligned with ``observed``.
        include_unmatched: Also emit a row, with empty observed columns, for
            every theoretical ion that no peak matched.

    Returns:
        One dict per matched (or, optionally, unmatched) fragment ion.
    """
    import numpy as np

    config = {**DEFAULT_ANNOTATION_CONFIG, **(annotation_config or {})}
    tolerance = float(config.get("tolerance") or 0.0)
    tolerance_ppm = bool(config.get("tolerance_ppm", True))

    shifts = [("", 0.0)]
    if config.get("neutral_losses"):
        shifts += NEUTRAL_LOSSES
    if config.get("proton_loss_addition"):
        shifts += PROTON_SHIFTS

    try:
        max_charge = max(1, int(precursor_charge or 1))
    except (TypeError, ValueError):
        max_charge = 1
    charges = [1] if deconvolved else list(range(1, max_charge + 1))

    observed = np.asarray(observed, dtype=float)
    order = np.argsort(observed, kind="stable")
    sorted_obs = observed[order]

    # Every theoretical ion as one row of parallel arrays, so the peak search
    # below is a single vectorised searchsorted per spectrum.
    fragment_masses = calculate_fragment_masses_pyopenms(sequence_str)
    ions: list[tuple[str, str, int, int, float]] = []
    for ion_type in config.get("ion_types") or []:
        per_position = fragment_masses.get(f"fragment_masses_{ion_type}") or []
        for position, masses in enumerate(per_position):
            ion_number = position + 1
            for neutral_mass in masses:
                for shift_name, shift_mass in shifts:
                    adjusted = neutral_mass + shift_mass
                    for charge in charges:
                        theoretical = (
                            adjusted
                            if deconvolved
                            else (adjusted + charge * PROTON_MASS) / charge
                        )
                        ions.append(
                            (
                                f"{ion_type}{ion_number}{shift_name}",
                                f"{ion_type}{shift_name}",
                                ion_number,
                                charge,
                                theoretical,
                            )
                        )
    if not ions:
        return []

    theoretical_values = np.array([ion[4] for ion in ions])
    window = (
        np.abs(theoretical_values) * tolerance / 1e6
        if tolerance_ppm
        else np.full(len(ions), tolerance)
    )
    lows = np.searchsorted(sorted_obs, theoretical_values - window, "left")
    highs = np.searchsorted(sorted_obs, theoretical_values + window, "right")

    rows: list[dict[str, Any]] = []
    for (ion, ion_type, ion_number, charge, theoretical), lo, hi in zip(
        ions, lows, highs, strict=True
    ):
        base = {
            "ion": ion,
            "ion_type": ion_type,
            "ion_number": ion_number,
            "charge": charge,
            "theoretical_mz": theoretical,
        }
        if hi <= lo:
            if include_unmatched:
                rows.append(
                    {
                        **base,
                        "observed_mz": None,
                        "intensity": None,
                        "mass_error_da": None,
                        "mass_error_ppm": None,
                        "peak_id": None,
                    }
                )
            continue
        for idx in order[lo:hi]:
            obs = float(observed[idx])
            diff = obs - theoretical
            rows.append(
                {
                    **base,
                    "observed_mz": obs,
                    "intensity": (
                        float(intensities[idx]) if intensities is not None else None
                    ),
                    "mass_error_da": diff,
                    "mass_error_ppm": diff / theoretical * 1e6 if theoretical else None,
                    "peak_id": int(peak_ids[idx]) if peak_ids is not None else None,
                }
            )
    return rows


@dataclass
class SequenceViewResult:
    """Result returned by SequenceView.__call__().

    Attributes:
        annotations: DataFrame with columns (peak_id, highlight_color, annotation)
            containing fragment annotations computed by Vue. None if not yet available.
    """

    annotations: pl.DataFrame | None = None


@register_component("sequence_view")
class SequenceView:
    """
    Interactive sequence view component for peptide/protein visualization.

    Displays amino acid sequence with fragment ion markers. When provided with
    peaks data, performs fragment matching on the Vue side and returns annotations.

    Features:
    - Amino acid grid display with configurable row width
    - Fragment ion markers (a, b, c, x, y, z) with configurable colors
    - Tolerance-based fragment matching (done in Vue)
    - Returns annotation dataframe for linked components
    - Supports filtering by spectrum and sequence identifiers

    Example:
        sequence_view = SequenceView(
            cache_id="peptide_view",
            sequence_data=pl.scan_parquet("sequences.parquet"),
            peaks_data=pl.scan_parquet("peaks.parquet"),
            filters={"spectrum": "scan_id", "sequence": "sequence_id"},
            annotation_config={"ion_types": ["b", "y"], "tolerance": 20.0},
        )
        result = sequence_view(key="sv", state_manager=state_manager)
        # result.annotations contains the matched fragment annotations
    """

    _component_type: str = "sequence_view"

    def __init__(
        self,
        cache_id: str,
        sequence_data: pl.LazyFrame | tuple[str, int] | str | None = None,
        sequence_data_path: str | None = None,
        peaks_data: pl.LazyFrame | None = None,
        peaks_data_path: str | None = None,
        filters: dict[str, str] | None = None,
        interactivity: dict[str, str] | None = None,
        deconvolved: bool = False,
        annotation_config: dict[str, Any] | None = None,
        cache_path: str = ".",
        title: str | None = None,
        height: int = 400,
        regenerate_cache: bool = False,
        svg_filename: str | None = None,
        image_format: str | None = None,
        **kwargs,
    ):
        """
        Initialize the SequenceView component.

        Args:
            cache_id: Unique identifier for this component instance.
            sequence_data: Sequence information in one of three formats:
                - LazyFrame with columns: sequence_id (if filtered), sequence, precursor_charge
                - Tuple of (sequence_string, precursor_charge)
                - String with just the sequence (charge defaults to 1)
            sequence_data_path: Path to parquet file with sequence data.
            peaks_data: LazyFrame with columns: scan_id (if filtered), peak_id, mass, intensity
            peaks_data_path: Path to parquet file with peaks data.
            filters: Mapping of identifier names to column names for filtering.
                Example: {"spectrum": "scan_id", "sequence": "sequence_id"}
            interactivity: Mapping of identifier names to column names for clicks.
                Example: {"peak": "peak_id"} sets 'peak' selection to clicked peak's ID.
            deconvolved: If False (default), peaks are m/z values and matching considers
                charge states 1 to precursor_charge. If True, peaks are neutral masses.
            annotation_config: Configuration for fragment matching:
                - ion_types: List of ion types to consider (default: ["b", "y"])
                - neutral_losses: Whether to consider -H2O, -NH3 losses (default: True)
                - tolerance: Mass tolerance value (default: 20.0)
                - tolerance_ppm: True for ppm, False for Da (default: True)
                - colors: Dict mapping ion types to hex colors
            cache_path: Base path for cache storage.
            title: Optional title displayed above the sequence.
            height: Component height in pixels.
            regenerate_cache: If True, rebuild the cache even when one matching this
                configuration already exists. Needed when the data behind a
                LazyFrame or file source changed but cache_id and config did not.
            svg_filename: File name (without extension) of the image download
                of the sequence (default: title, then "sequence"); the
                extension follows the image format. Render-time only.
            image_format: Format of the image download: 'svg', 'png', 'jpeg'
                or 'webp'. None (default) follows
                ``openms_insight.set_image_format()`` (default 'svg') when the
                component is drawn. Render-time only: not part of the cache.
            **kwargs: Additional configuration options.
        """
        self._cache_id = cache_id
        self._cache_path = Path(cache_path)
        self._cache_dir = self._cache_path / cache_id
        # Render-time options, kept out of the cache config (see core/image_format.py)
        self._svg_filename = svg_filename
        self._image_format = validate_image_format(image_format, allow_none=True)

        # Determine if data is provided (creation mode vs reconstruction mode)
        has_sequence_data = sequence_data is not None or sequence_data_path is not None

        # Check if any configuration arguments were provided
        has_config = (
            peaks_data is not None
            or peaks_data_path is not None
            or filters is not None
            or interactivity is not None
            or deconvolved is not False
            or annotation_config is not None
            or title is not None
            or height != 400
            or bool(kwargs)
        )

        if not has_sequence_data:
            # Reconstruction mode - only cache_id and cache_path allowed
            if has_config:
                raise ValueError(
                    "Configuration arguments require sequence_data= or sequence_data_path= to be provided. "
                    "For reconstruction from cache, use only cache_id and cache_path."
                )
            if not self._cache_exists():
                raise ValueError(
                    f"Cache not found at '{self._cache_dir}'. "
                    f"Provide sequence_data= or sequence_data_path= to create the cache."
                )
            self._load_from_cache()
        else:
            # Creation mode - use provided config
            self._title = title
            self._height = height
            self._deconvolved = deconvolved
            self._config = kwargs
            self._filters = filters or {}
            self._filter_defaults = {}
            for identifier in self._filters.keys():
                self._filter_defaults[identifier] = None
            self._interactivity = interactivity or {}

            # Store annotation config with defaults
            self._annotation_config = {**DEFAULT_ANNOTATION_CONFIG}
            if annotation_config:
                self._annotation_config.update(annotation_config)

            # Parse sequence data input
            if sequence_data is not None and sequence_data_path is not None:
                raise ValueError(
                    "Provide either 'sequence_data' or 'sequence_data_path', not both"
                )

            self._source_sequence_data: pl.LazyFrame | None = None
            self._source_static_sequence: str | None = None
            self._source_static_charge: int = 1

            if sequence_data_path is not None:
                self._source_sequence_data = scan_parquet(sequence_data_path)
            elif isinstance(sequence_data, pl.LazyFrame):
                self._source_sequence_data = sequence_data
            elif isinstance(sequence_data, tuple):
                self._source_static_sequence = sequence_data[0]
                self._source_static_charge = sequence_data[1]
            elif isinstance(sequence_data, str):
                self._source_static_sequence = sequence_data
                self._source_static_charge = 1

            # Parse peaks data input
            if peaks_data is not None and peaks_data_path is not None:
                raise ValueError(
                    "Provide either 'peaks_data' or 'peaks_data_path', not both"
                )

            self._source_peaks_data: pl.LazyFrame | None = None
            if peaks_data_path is not None:
                self._source_peaks_data = scan_parquet(peaks_data_path)
            elif peaks_data is not None:
                self._source_peaks_data = peaks_data

            # Reuse the cache on disk when it was built from this configuration.
            # Without this, every Streamlit rerun re-parses the sequence, re-matches
            # fragments and rewrites the Parquet files. The lock spans the check and
            # the build so concurrent script threads cannot write the same files.
            self._input_config_hash = self._compute_input_config_hash()
            with cache_lock(self._cache_dir):
                if (
                    not regenerate_cache
                    and self._cache_exists()
                    and self._cached_input_config_matches(self._input_config_hash)
                ):
                    self._source_sequence_data = None
                    self._source_static_sequence = None
                    self._source_peaks_data = None
                    self._load_from_cache()
                    return

                # Create and save cache
                self._create_cache()

                # Discard source references - only cache is used from now on
                self._source_sequence_data = None
                self._source_static_sequence = None
                self._source_peaks_data = None

                # Load cached LazyFrames for reading
                self._cached_sequences = scan_parquet(
                    self._cache_dir / "sequences.parquet"
                )
                peaks_path = self._cache_dir / "peaks.parquet"
                self._cached_peaks = (
                    scan_parquet(peaks_path) if peaks_path.exists() else None
                )

    def _get_cache_config(self) -> dict[str, Any]:
        """Get all configuration to store in cache."""
        return {
            "version": CACHE_VERSION,
            "filters": self._filters,
            "interactivity": self._interactivity,
            "title": self._title,
            "height": self._height,
            "deconvolved": self._deconvolved,
            "annotation_config": self._annotation_config,
        }

    def _compute_input_config_hash(self) -> str:
        """
        Reuse key for the cache, computed from the configuration as passed in.

        Includes the literal sequence when one was supplied directly. That is this
        component's data rather than its configuration, but it is a short string,
        hashing it is free, and a changed peptide under an unchanged cache_id is the
        mistake most likely to be made here.

        LazyFrame and file sources cannot be hashed without reading them, which is the
        expense the cache exists to avoid, so they follow the same contract as every
        other component: new data needs a new cache_id or regenerate_cache=True.

        Returns:
            Hex digest of the configuration.
        """
        payload = {
            **self._get_cache_config(),
            "static_sequence": self._source_static_sequence,
            "static_charge": self._source_static_charge,
            "has_sequence_frame": self._source_sequence_data is not None,
            "has_peaks": self._source_peaks_data is not None,
        }
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def _cached_input_config_matches(self, input_config_hash: str) -> bool:
        """
        Check whether the cache on disk was built from this configuration.

        Returns:
            True if the cached config records the same hash. False when it is
            unreadable, or predates this field -- in which case the cache is rebuilt
            so that it gains one, rather than assuming a match.
        """
        config_file = self._cache_dir / ".cache_config.json"
        try:
            with open(config_file) as f:
                cached = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False

        stored = cached.get("input_config_hash")
        if stored is None:
            return False

        return bool(stored == input_config_hash)

    def _cache_exists(self) -> bool:
        """Check if a valid cache exists that can be loaded."""
        config_file = self._cache_dir / ".cache_config.json"
        sequences_file = self._cache_dir / "sequences.parquet"

        if not config_file.exists() or not sequences_file.exists():
            return False

        try:
            with open(config_file) as f:
                cached_config = json.load(f)
            # Just check version matches
            return cached_config.get("version") == CACHE_VERSION
        except Exception:
            return False

    def _load_from_cache(self) -> None:
        """Load all configuration and data from cache."""
        config_file = self._cache_dir / ".cache_config.json"

        with open(config_file) as f:
            config = json.load(f)

        # Restore all configuration
        self._filters = config.get("filters", {})
        self._filter_defaults = {}
        for identifier in self._filters.keys():
            self._filter_defaults[identifier] = None
        self._interactivity = config.get("interactivity", {})
        self._title = config.get("title")
        self._height = config.get("height", 400)
        self._deconvolved = config.get("deconvolved", False)
        self._annotation_config = config.get(
            "annotation_config", {**DEFAULT_ANNOTATION_CONFIG}
        )
        self._config = {}

        # Load cached LazyFrames
        self._cached_sequences = scan_parquet(self._cache_dir / "sequences.parquet")
        peaks_path = self._cache_dir / "peaks.parquet"
        self._cached_peaks = scan_parquet(peaks_path) if peaks_path.exists() else None

    def _create_cache(self) -> None:
        """Create cache from source data."""
        # Create cache directory
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Preprocess and write caches
        self._preprocess_sequences()
        self._preprocess_peaks()

        # Write config last and atomically: it is what _cache_exists() and the reuse
        # check read, so a torn one would make an otherwise complete cache unusable.
        config_file = self._cache_dir / ".cache_config.json"
        stored = {
            **self._get_cache_config(),
            "input_config_hash": getattr(self, "_input_config_hash", None),
        }
        with atomic_write(config_file) as tmp:
            with open(tmp, "w") as f:
                json.dump(stored, f, indent=2)

    def _preprocess_sequences(self) -> None:
        """Preprocess and cache sequence data."""
        output_path = self._cache_dir / "sequences.parquet"

        if self._source_sequence_data is not None:
            # LazyFrame input - select required columns, sort by filters
            schema = self._source_sequence_data.collect_schema()
            filter_cols = [c for c in self._filters.values() if c in schema.names()]

            # Build column list: filter columns + required columns
            required = ["sequence", "precursor_charge"]
            cols = list(
                dict.fromkeys(
                    filter_cols + [c for c in required if c in schema.names()]
                )
            )

            lf = self._source_sequence_data.select(cols)

            # Sort by filter columns for predicate pushdown
            if filter_cols:
                lf = lf.sort(filter_cols)

            df = lf.collect()
        else:
            # Static input (string or tuple) - create single-row DataFrame
            df = pl.DataFrame(
                {
                    "sequence": [self._source_static_sequence or ""],
                    "precursor_charge": [self._source_static_charge],
                }
            )

        # Optimize types and write. Atomic: a concurrent reader must not observe a
        # truncated file, and polars may have this one memory-mapped.
        df = optimize_for_transfer(df)
        with atomic_write(output_path) as tmp:
            df.write_parquet(tmp, compression="zstd")

    def _preprocess_peaks(self) -> None:
        """Preprocess and cache peaks data."""
        if self._source_peaks_data is None:
            return  # No peaks to cache

        output_path = self._cache_dir / "peaks.parquet"
        schema = self._source_peaks_data.collect_schema()
        filter_cols = [c for c in self._filters.values() if c in schema.names()]

        # Build column list: filter columns + required columns
        required = ["peak_id", "mass"]
        optional = ["intensity"]
        cols = list(
            dict.fromkeys(
                filter_cols
                + [c for c in required if c in schema.names()]
                + [c for c in optional if c in schema.names()]
            )
        )

        lf = self._source_peaks_data.select(cols)

        # Sort by filter columns for predicate pushdown
        if filter_cols:
            lf = lf.sort(filter_cols)

        df = lf.collect()

        # Optimize types and write. Atomic: a concurrent reader must not observe a
        # truncated file, and polars may have this one memory-mapped.
        df = optimize_for_transfer(df)
        with atomic_write(output_path) as tmp:
            df.write_parquet(tmp, compression="zstd")

    def _get_sequence_for_state(self, state: dict[str, Any]) -> tuple[str, int]:
        """Get sequence and charge for current state.

        Reads from cached sequences.parquet with predicate pushdown.

        Returns:
            Tuple of (sequence_string, precursor_charge)
        """
        filtered = self._cached_sequences

        # Apply filters for columns that exist in cached data
        schema = filtered.collect_schema()
        for identifier, column in self._filters.items():
            if column in schema.names():
                filter_value = state.get(identifier)
                if filter_value is not None:
                    filtered = filtered.filter(pl.col(column) == filter_value)
                elif (
                    identifier in self._filter_defaults
                    and self._filter_defaults[identifier] is None
                ):
                    # Filter has None default and state is None - return empty intentionally
                    return "", 1

        # Collect and get first row
        try:
            df = filtered.select(["sequence", "precursor_charge"]).head(1).collect()
            if df.height > 0:
                return df["sequence"][0], df["precursor_charge"][0]
        except Exception:
            pass

        return "", 1

    def _get_peaks_for_state(self, state: dict[str, Any]) -> pl.DataFrame:
        """Get filtered peaks data for current state.

        Reads from cached peaks.parquet with predicate pushdown.

        Returns:
            DataFrame with columns: peak_id, mass, (intensity if available)
        """
        if self._cached_peaks is None:
            return pl.DataFrame(schema={"peak_id": pl.Int64, "mass": pl.Float64})

        filtered = self._cached_peaks

        # Apply filters for columns that exist in cached data
        schema = filtered.collect_schema()
        for identifier, column in self._filters.items():
            if column in schema.names():
                filter_value = state.get(identifier)
                if filter_value is not None:
                    filtered = filtered.filter(pl.col(column) == filter_value)
                elif (
                    identifier in self._filter_defaults
                    and self._filter_defaults[identifier] is None
                ):
                    # Filter has None default and state is None - return empty intentionally
                    return pl.DataFrame(
                        schema={"peak_id": pl.Int64, "mass": pl.Float64}
                    )

        # Select available columns
        cols = ["peak_id", "mass"]
        if "intensity" in schema.names():
            cols.append("intensity")

        try:
            return filtered.select(cols).collect()
        except Exception:
            return pl.DataFrame(schema={"peak_id": pl.Int64, "mass": pl.Float64})

    def _prepare_vue_data(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Prepare data for Vue component.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with sequenceData, peaksData, annotationConfig, etc.
        """
        # Get sequence for current state
        sequence_str, precursor_charge = self._get_sequence_for_state(state)

        # Parse sequence
        residues, modifications = parse_openms_sequence(sequence_str)

        # Calculate theoretical fragment masses
        fragment_masses = calculate_fragment_masses_pyopenms(sequence_str)

        # Calculate theoretical mass
        theoretical_mass = get_theoretical_mass(sequence_str)

        # Build sequence data structure
        sequence_data = {
            "sequence": residues,
            "modifications": modifications,
            "theoretical_mass": theoretical_mass,
            "fixed_modifications": [],
            # Include settings for Vue initialization
            "fragment_tolerance": self._annotation_config.get("tolerance"),
            "fragment_tolerance_ppm": self._annotation_config.get("tolerance_ppm"),
            "neutral_losses": self._annotation_config.get("neutral_losses"),
            "proton_loss_addition": self._annotation_config.get("proton_loss_addition"),
            **fragment_masses,
        }

        # Get filtered peaks
        peaks_df = self._get_peaks_for_state(state)

        # Extract arrays from peaks DataFrame for Vue
        # Vue expects observedMasses and peakIds as separate arrays
        observed_masses: list[float] = []
        peak_ids: list[int] = []
        precursor_mass: float = 0.0

        if peaks_df.height > 0:
            observed_masses = peaks_df["mass"].to_list()
            peak_ids = peaks_df["peak_id"].to_list()

        # Create hash for change detection
        hash_input = f"{sequence_str}:{peaks_df.height}:{precursor_charge}"
        data_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]

        result = {
            "sequenceData": sequence_data,
            "observedMasses": observed_masses,
            "peakIds": peak_ids,
            "precursorMass": precursor_mass,
            "annotationConfig": self._annotation_config,
            "precursorCharge": precursor_charge,
            "_hash": data_hash,
        }

        return result

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        return "SequenceView"

    def _get_data_key(self) -> str:
        """Return the key used to send primary data to Vue."""
        return "sequenceData"

    def _get_component_args(self) -> dict[str, Any]:
        """Get component arguments to send to Vue."""
        args: dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "height": self._height,
            "deconvolved": self._deconvolved,
        }

        if self._title:
            args["title"] = self._title

        if self._interactivity:
            args["interactivity"] = self._interactivity

        if self._svg_filename:
            args["svgFilename"] = self._svg_filename

        args.update(self._config)
        args.update(image_format_args(self._image_format))
        return args

    def export_fragment_ions(self, include_unmatched: bool = False) -> pl.DataFrame:
        """
        Export the fragment ions of every sequence against its spectrum.

        Runs the view's fragment matching (its ``annotation_config`` and
        ``deconvolved`` setting) over every row of the cached sequence data, not
        only the selected one, so a whole run can be written to one table.
        Each sequence is matched against the peaks that share its filter
        columns (e.g. ``file_index`` and ``scan_id``).

        Args:
            include_unmatched: Also list theoretical ions no peak matched,
                with empty observed columns.

        Returns:
            DataFrame with the sequence data's filter columns, ``sequence``,
            ``precursor_charge`` and one row per fragment ion: ``ion``,
            ``ion_type``, ``ion_number``, ``charge``, ``theoretical_mz``,
            ``observed_mz``, ``intensity``, ``mass_error_da``,
            ``mass_error_ppm`` and ``peak_id``. For deconvolved data the m/z
            columns hold neutral masses.
        """
        import numpy as np

        sequences = self._cached_sequences.collect()
        seq_filter_cols = [c for c in self._filters.values() if c in sequences.columns]
        seq_filter_cols = list(dict.fromkeys(seq_filter_cols))

        peaks = (
            self._cached_peaks.collect()
            if self._cached_peaks is not None
            else pl.DataFrame(schema={"peak_id": pl.Int64, "mass": pl.Float64})
        )
        join_cols = [c for c in seq_filter_cols if c in peaks.columns]
        has_intensity = "intensity" in peaks.columns

        def arrays(frame: pl.DataFrame) -> tuple:
            return (
                frame["mass"].to_numpy(),
                frame["intensity"].to_numpy() if has_intensity else None,
                frame["peak_id"].to_numpy(),
            )

        empty = (np.array([], dtype=float), None, None)
        if join_cols:
            peaks_by_key = {
                key: arrays(group)
                for key, group in peaks.partition_by(
                    join_cols, as_dict=True, maintain_order=True
                ).items()
            }
        else:
            all_peaks = arrays(peaks) if peaks.height else empty

        rows: list[dict[str, Any]] = []
        for record in sequences.iter_rows(named=True):
            sequence = record.get("sequence") or ""
            if not sequence:
                continue
            if join_cols:
                key = tuple(record[c] for c in join_cols)
                observed, intensities, peak_ids = peaks_by_key.get(key, empty)
            else:
                observed, intensities, peak_ids = all_peaks
            if len(observed) == 0 and not include_unmatched:
                continue
            charge = record.get("precursor_charge") or 1
            prefix = {c: record[c] for c in seq_filter_cols}
            prefix["sequence"] = sequence
            prefix["precursor_charge"] = charge
            for ion in match_fragment_ions(
                sequence,
                observed,
                precursor_charge=charge,
                annotation_config=self._annotation_config,
                deconvolved=self._deconvolved,
                intensities=intensities,
                peak_ids=peak_ids,
                include_unmatched=include_unmatched,
            ):
                rows.append({**prefix, **ion})

        schema = {c: sequences.schema[c] for c in seq_filter_cols}
        schema.update(
            {
                "sequence": pl.Utf8,
                "precursor_charge": pl.Int64,
                "ion": pl.Utf8,
                "ion_type": pl.Utf8,
                "ion_number": pl.Int64,
                "charge": pl.Int64,
                "theoretical_mz": pl.Float64,
                "observed_mz": pl.Float64,
                "intensity": pl.Float64,
                "mass_error_da": pl.Float64,
                "mass_error_ppm": pl.Float64,
                "peak_id": pl.Int64,
            }
        )
        return pl.DataFrame(rows, schema=schema)

    @property
    def peaks_data(self) -> pl.LazyFrame | None:
        """Return the cached peaks LazyFrame for linked components."""
        return self._cached_peaks

    def get_filters_mapping(self) -> dict[str, str]:
        """Return the filters identifier-to-column mapping."""
        return self._filters.copy()

    def get_interactivity_mapping(self) -> dict[str, str]:
        """Return the interactivity identifier-to-column mapping."""
        return self._interactivity.copy()

    def get_state_dependencies(self) -> list[str]:
        """Return list of state keys that affect this component's data."""
        return list(self._filters.keys())

    def __call__(
        self,
        key: str | None = None,
        state_manager: Optional["StateManager"] = None,
        height: int | None = None,
    ) -> SequenceViewResult:
        """
        Render the component in Streamlit.

        Args:
            key: Optional unique key for the Streamlit component
            state_manager: Optional StateManager for cross-component state.
                If not provided, uses a default shared StateManager.
            height: Optional height in pixels for the component

        Returns:
            SequenceViewResult with annotations DataFrame (if available)
        """
        from ..core.state import get_default_state_manager
        from ..rendering.bridge import get_component_annotations, render_component

        if state_manager is None:
            state_manager = get_default_state_manager()

        # Use provided height or default
        render_height = height if height is not None else self._height

        render_component(
            component=self, state_manager=state_manager, key=key, height=render_height
        )

        # Get annotations from session state (set by Vue)
        annotations = get_component_annotations(key) if key else None

        return SequenceViewResult(annotations=annotations)

    def __repr__(self) -> str:
        return (
            f"SequenceView("
            f"cache_id='{self._cache_id}', "
            f"filters={self._filters}, "
            f"interactivity={self._interactivity})"
        )


if TYPE_CHECKING:
    import numpy as np

    from ..core.state import StateManager
