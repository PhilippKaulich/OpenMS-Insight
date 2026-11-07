"""The "Pin zoom" button of the spectrum views: LinePlot, MirrorPlot, DeconvolvedSpectrum.

Each of them shows a new spectrum at its full extent. The pin button in their
Plotly mode bar keeps the zoomed x range instead, so one region can be compared
across spectra; ``keep_zoom=True`` starts with the zoom pinned. Like ``measure``
it is a render-time argument, never part of the cache configuration.
"""

from typing import Any


def validate_keep_zoom(keep_zoom: Any) -> bool:
    """Check ``keep_zoom`` is a bool and return it."""
    if not isinstance(keep_zoom, bool):
        raise ValueError(f"keep_zoom must be True or False, got {keep_zoom!r}")
    return keep_zoom


def keep_zoom_args(keep_zoom: bool) -> dict[str, Any]:
    """The Vue argument: whether the zoom starts pinned."""
    return {"keepZoom": keep_zoom}
