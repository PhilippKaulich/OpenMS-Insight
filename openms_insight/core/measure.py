"""The measure tool of the 2D plots: argument checks and what reaches Vue.

Every 2D Plotly component (LinePlot, MirrorPlot, SeriesPlot,
DeconvolvedSpectrum, Heatmap, VolcanoPlot, PCAPlot) takes ``measure``, on by
default: a "Measure" button in the Plotly mode bar with which two clicked points are
measured (see ``js-component/src/composables/useMeasure.ts``). Components whose
x axis is m/z or mass also take ``measure_tolerance`` and ``measure_residues``
for matching a difference to amino-acid residue masses.

The options only change what the view draws. They are render-time arguments
kept on the component, never part of its cache configuration, so switching
the tool on or off, or changing its default, never rebuilds a cache.
"""

import math
from typing import Any

DEFAULT_MEASURE_TOLERANCE = 0.02


def validate_measure(measure: Any) -> bool:
    """Check ``measure`` is a bool and return it."""
    if not isinstance(measure, bool):
        raise ValueError(f"measure must be True or False, got {measure!r}")
    return measure


def validate_measure_tolerance(tolerance: Any) -> float:
    """Check ``measure_tolerance`` is a finite number >= 0 and return it as float."""
    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not math.isfinite(tolerance)
        or tolerance < 0
    ):
        raise ValueError(
            f"measure_tolerance must be a non-negative number, got {tolerance!r}"
        )
    return float(tolerance)


def validate_measure_residues(residues: Any) -> dict[str, float]:
    """Check ``measure_residues`` maps names to positive masses; None -> {}."""
    if residues is None:
        return {}
    if not isinstance(residues, dict):
        raise ValueError(
            "measure_residues must be a dict of name -> mass, "
            f"got {type(residues).__name__}"
        )
    validated: dict[str, float] = {}
    for name, mass in residues.items():
        if not isinstance(name, str) or not name:
            raise ValueError(
                f"measure_residues names must be non-empty strings, got {name!r}"
            )
        if (
            isinstance(mass, bool)
            or not isinstance(mass, (int, float))
            or not math.isfinite(mass)
            or mass <= 0
        ):
            raise ValueError(
                f"measure_residues['{name}'] must be a positive mass, got {mass!r}"
            )
        validated[name] = float(mass)
    return validated


def measure_args(
    measure: bool,
    tolerance: float | None = None,
    residues: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Component args for the view.

    Args:
        measure: Whether the Measure button is shown.
        tolerance: Residue matching tolerance (components that match residues).
        residues: Extra residue masses (components that match residues).

    Returns:
        ``{"measure": measure}``, plus ``measureTolerance`` and
        ``measureResidues`` (when given and non-empty) while measuring is on.
    """
    args: dict[str, Any] = {"measure": measure}
    if measure:
        if tolerance is not None:
            args["measureTolerance"] = tolerance
        if residues:
            args["measureResidues"] = dict(residues)
    return args
