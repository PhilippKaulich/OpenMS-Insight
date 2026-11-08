"""The zoom of a plot, kept in the shared state: ``zoom_identifier``.

A plot given a ``zoom_identifier`` reports its axis ranges there after a zoom
or pan, and zooms to a value set there from Python, for instance when a page
opens a saved view. The value is plain JSON, so it can be written before the
plot was ever drawn::

    state_manager.set_selection("zoom@spectrum", {"x": [400.0, 900.0]})

``x`` and ``y`` are ``[low, high]``; a missing axis shows its full extent and
``None`` is the full view. The heatmap's ``{"xRange", "yRange"}`` form, with
``[-1, -1]`` for no zoom, is read as well. Like ``keep_zoom`` it is a
render-time argument, never part of the cache configuration, except for the
heatmap, whose zoom picks the resolution level of its data.

Each report reruns the script once (debounced), as any change of the state
does, so give a plot an identifier only where its zoom should be kept.
"""

import math
from typing import Any, Optional


def validate_zoom_identifier(identifier: Any) -> Optional[str]:
    """Check ``zoom_identifier`` is a non-empty string or None and return it."""
    if identifier is None:
        return None
    if not isinstance(identifier, str) or not identifier:
        raise ValueError(
            f"zoom_identifier must be a non-empty string or None, got {identifier!r}"
        )
    return identifier


def zoom_args(identifier: Optional[str]) -> dict[str, Any]:
    """The Vue argument: the identifier the plot keeps its zoom under."""
    return {"zoomIdentifier": identifier} if identifier else {}


def _range(value: Any) -> Optional[list[float]]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        low, high = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(low) and math.isfinite(high)) or low == high:
        return None
    if low == -1 and high == -1:
        return None
    return [min(low, high), max(low, high)]


def normalize_zoom(value: Any) -> Optional[dict[str, list[float]]]:
    """A stored zoom as ``{"x": [lo, hi], "y": [lo, hi]}`` (axes optional), or None.

    None stands for the full view: no value, an unreadable one, or one without
    any usable axis.
    """
    if not isinstance(value, dict):
        return None
    zoom = {}
    for axis in ("x", "y"):
        r = _range(value.get(axis, value.get(f"{axis}Range")))
        if r is not None:
            zoom[axis] = r
    return zoom or None
