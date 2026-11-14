"""Labelled x markers of LinePlot: ``x_markers`` and ``x_marker_tolerance``.

``x_markers`` gives positions on the x axis to mark, as ``{label: x}`` or as a
list of ``{"x", "label", "color"}`` dicts (``label`` and ``color`` optional).
Each marker gets a dotted guide over the plot's height, in its own colour, and
its label at the top. With ``x_marker_tolerance`` the most intense peak within
that distance of a marker is its peak: it gets a dot in the marker's colour,
the label moves above it, and the hover read-out names the marker. Both are
render-time arguments, never part of the cache configuration.

    LinePlot(..., x_markers={"126": 126.1277, "127N": 127.1248},
             x_marker_tolerance=0.003)
"""

from typing import Any

#: Most markers one plot takes.
MAX_X_MARKERS = 200


def _number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def validate_x_markers(markers: Any) -> list[dict[str, Any]] | None:
    """Turn ``x_markers`` into ``[{"x", "label", "color"}]`` sorted by x, or None."""
    if markers is None:
        return None
    if isinstance(markers, dict):
        items = [{"label": label, "x": x} for label, x in markers.items()]
    elif isinstance(markers, (list, tuple)):
        items = list(markers)
    else:
        raise ValueError(
            "x_markers must be a dict of label -> x or a list of "
            f"{{'x', 'label', 'color'}} dicts, got {type(markers).__name__}"
        )
    if not 0 < len(items) <= MAX_X_MARKERS:
        raise ValueError(
            f"x_markers must have 1 to {MAX_X_MARKERS} markers, got {len(items)}"
        )
    result = []
    for item in items:
        if not isinstance(item, dict) or not set(item) <= {"x", "label", "color"}:
            raise ValueError(
                f"each x marker must be a dict with 'x' and optional 'label' and "
                f"'color', got {item!r}"
            )
        x = item.get("x")
        if not _number(x) or x != x or x in (float("inf"), float("-inf")):
            raise ValueError(f"x marker positions must be finite numbers, got {x!r}")
        label = item.get("label", "")
        if not isinstance(label, str):
            raise ValueError(f"x marker labels must be text, got {label!r}")
        color = item.get("color")
        if color is not None and (not isinstance(color, str) or not color.strip()):
            raise ValueError(f"x marker colours must be CSS colours, got {color!r}")
        marker: dict[str, Any] = {"x": float(x), "label": label.strip()}
        if color is not None:
            marker["color"] = color.strip()
        result.append(marker)
    return sorted(result, key=lambda marker: marker["x"])


def validate_x_marker_tolerance(tolerance: Any) -> float | None:
    """Check ``x_marker_tolerance`` is None or a positive number (x units)."""
    if tolerance is None:
        return None
    if not _number(tolerance) or not 0 < tolerance < float("inf"):
        raise ValueError(
            "x_marker_tolerance must be None or a positive number in x units, "
            f"got {tolerance!r}"
        )
    return float(tolerance)


def x_marker_args(
    markers: list[dict[str, Any]] | None, tolerance: float | None
) -> dict[str, Any]:
    """The Vue arguments: the markers (or None) and the matching tolerance."""
    if not markers:
        return {}
    return {"xMarkers": markers, "xMarkerTolerance": tolerance}
