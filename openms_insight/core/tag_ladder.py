"""Which residues of a sequence tag lie between each pair of its masses.

A tag from de novo sequencing has one residue between neighbouring masses, but
a tag can also span gaps that hold several residues (a long tag with missing
fragment masses, as FLASHTnT reports for whole proteoforms). Its masses may run
from either end of the sequence. :func:`ladder_steps` assigns the residues to
the gaps by mass, so a ladder labels every gap with the residues it measures.

Streamlit-free, so it can be tested on its own.
"""

from __future__ import annotations

import bisect
import itertools
from collections.abc import Sequence

# Monoisotopic residue masses
RESIDUE_MASSES: dict[str, float] = {
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
    "O": 237.147727,
}

# A gap may be off by an isotope (about 1 Da) plus the error of its two masses
MAX_GAP_ERROR = 1.6
# Below this difference in summed error, neither reading is clearly better
DIRECTION_MARGIN = 0.5


def _bounds(
    masses: Sequence[float], sequence: str
) -> tuple[list[int], float, float] | None:
    """Residue boundaries along ``sequence`` closest to each mass, measured from
    the first mass (so errors do not add up), with the summed and the worst
    error; None when the masses cannot be placed in order."""
    if any(residue not in RESIDUE_MASSES for residue in sequence):
        return None
    prefix = [0.0] + list(itertools.accumulate(RESIDUE_MASSES[r] for r in sequence))
    bounds = [0]
    total = worst = 0.0
    for mass in masses[1:]:
        target = abs(mass - masses[0])
        k = bisect.bisect_left(prefix, target)
        candidates = [c for c in (k - 1, k) if bounds[-1] < c < len(prefix)]
        if not candidates:
            return None
        best = min(candidates, key=lambda c: abs(prefix[c] - target))
        error = abs(prefix[best] - target)
        bounds.append(best)
        total += error
        worst = max(worst, error)
    return bounds, total, worst


def ladder_steps(
    masses: Sequence[float], sequence: str
) -> list[tuple[int, int]] | None:
    """The residues between each pair of neighbouring masses.

    Args:
        masses: The tag's masses in the order they are listed.
        sequence: The tag's residues, N- to C-terminal.

    Returns:
        One ``(start, end)`` slice of ``sequence`` per gap (``masses[i]`` to
        ``masses[i + 1]``), or None when the residues do not account for the
        gaps. A tag with one residue per gap reads its sequence backwards along
        the masses unless the masses clearly say otherwise.
    """
    masses = [float(m) for m in masses]
    if len(masses) < 2 or not sequence:
        return None
    n = len(sequence)
    backward = _bounds(masses, sequence[::-1])
    forward = _bounds(masses, sequence)

    def slices(bounds: list[int], reverse: bool) -> list[tuple[int, int]]:
        pairs = list(zip(bounds, bounds[1:], strict=False))
        if reverse:
            return [(n - end, n - start) for start, end in pairs]
        return pairs

    one_per_gap = n == len(masses) - 1
    if one_per_gap:
        # The usual tag: backwards, unless reading it forwards fits clearly better
        if forward and (
            backward is None or forward[1] + DIRECTION_MARGIN < backward[1]
        ):
            return slices(forward[0], reverse=False)
        return [(n - 1 - i, n - i) for i in range(n)]

    fits = [
        (result, reverse)
        for result, reverse in ((backward, True), (forward, False))
        if result is not None and result[2] <= MAX_GAP_ERROR
    ]
    if not fits:
        return None
    result, reverse = min(fits, key=lambda fit: fit[0][1])
    return slices(result[0], reverse)
