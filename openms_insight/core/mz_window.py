"""A shaded m/z window on LinePlot, driven by the shared state: ``window_identifier``.

A plot given a ``window_identifier`` shades the x range stored there, for
example the m/z window an extracted ion chromatogram (XIC) elsewhere on the
page is built from. The stored value is plain JSON:

* a number: the centre, widened by ``window_tolerance`` on each side;
* ``[low, high]``: that range as it is;
* ``None`` (or nothing): no band.

``window_tolerance`` is a number of Da (default 0.01) or a string such as
``"10 ppm"``, ``"0.02 Da"`` or ``"0.5 m/z"`` (an absolute width on the m/z
axis; ``"mz"`` and ``"Th"`` mean the same). Both are render-time arguments, never part of
the cache configuration.
"""

import math
import re
from typing import Any

#: Default half-width of the band around a stored centre, in Da.
DEFAULT_WINDOW_TOLERANCE = 0.01

_TOLERANCE = re.compile(
    r"^\s*([0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*(da|ppm|th|m/z|mz)?\s*$", re.I
)


_UNITS = {"da": "Da", "ppm": "ppm", "th": "m/z", "m/z": "m/z", "mz": "m/z"}


def validate_window_identifier(identifier: Any) -> str | None:
    """Check ``window_identifier`` is a non-empty string or None and return it."""
    if identifier is None:
        return None
    if not isinstance(identifier, str) or not identifier:
        raise ValueError(
            f"window_identifier must be a non-empty string or None, got {identifier!r}"
        )
    return identifier


def validate_window_tolerance(tolerance: Any) -> tuple[float, str]:
    """``window_tolerance`` as ``(value, unit)``, unit ``"Da"``, ``"m/z"`` or ``"ppm"``."""
    value: float | None = None
    unit = "Da"
    if isinstance(tolerance, bool):
        value = None
    elif isinstance(tolerance, (int, float)):
        value = float(tolerance)
    elif isinstance(tolerance, str):
        match = _TOLERANCE.match(tolerance)
        if match:
            value = float(match.group(1))
            unit = _UNITS[(match.group(2) or "da").lower()]
    limit = 10_000.0 if unit == "ppm" else 100.0
    if value is None or not math.isfinite(value) or not 0 < value <= limit:
        raise ValueError(
            "window_tolerance must be a positive number of Da or a string such "
            "as '10 ppm', '0.02 Da' or '0.5 m/z' (at most 100 Da or m/z, or "
            f"10000 ppm), got {tolerance!r}"
        )
    return value, unit


def mz_window_args(
    identifier: str | None, tolerance: tuple[float, str]
) -> dict[str, Any]:
    """The Vue arguments: where the window is kept and how wide a centre is."""
    if not identifier:
        return {}
    value, unit = tolerance
    return {
        "windowIdentifier": identifier,
        "windowTolerance": value,
        "windowToleranceUnit": unit,
    }
