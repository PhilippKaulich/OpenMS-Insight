"""The "Label top peaks" button of LinePlot.

Switched on, the most intense peaks in the visible x range show their x value
(the m/z of a spectrum) above the stick, placed again on every zoom or pan.
``top_peak_labels`` is how many peaks get a label (0 removes the button);
``show_top_peak_labels=True`` switches the labels on from the start. Both are
render-time arguments, never part of the cache configuration.
"""

from typing import Any

#: Most peaks the button labels at once.
MAX_TOP_PEAK_LABELS = 200


def validate_top_peak_labels(top_peak_labels: Any) -> int:
    """Check ``top_peak_labels`` is an int from 0 to MAX_TOP_PEAK_LABELS."""
    if (
        isinstance(top_peak_labels, bool)
        or not isinstance(top_peak_labels, int)
        or not 0 <= top_peak_labels <= MAX_TOP_PEAK_LABELS
    ):
        raise ValueError(
            "top_peak_labels must be a whole number from 0 to "
            f"{MAX_TOP_PEAK_LABELS}, got {top_peak_labels!r}"
        )
    return top_peak_labels


def validate_show_top_peak_labels(show: Any) -> bool:
    """Check ``show_top_peak_labels`` is a bool and return it."""
    if not isinstance(show, bool):
        raise ValueError(f"show_top_peak_labels must be True or False, got {show!r}")
    return show


def top_peak_label_args(top_peak_labels: int, show: bool) -> dict[str, Any]:
    """The Vue arguments: how many peaks, and whether the labels start shown."""
    return {"topPeakLabels": top_peak_labels, "showTopPeakLabels": show}
