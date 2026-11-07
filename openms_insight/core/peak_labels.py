"""Your own labels on peaks: the ``peak_labels`` option of the spectrum views.

LinePlot and MirrorPlot take ``peak_labels``, on by default: a "Label peaks"
button in the Plotly mode bar with which a clicked peak gets a text of the
user's choosing (see ``js-component/src/composables/usePeakLabels.ts``). The
labels live in the browser, per spectrum, for as long as the plot is on the
page, and they are part of the image download.

Like the measure tool, the option only changes what the view draws: it is a
render-time argument kept on the component, never part of its cache
configuration, so switching it never rebuilds a cache.
"""

from typing import Any


def validate_peak_labels(peak_labels: Any) -> bool:
    """Check ``peak_labels`` is a bool and return it."""
    if not isinstance(peak_labels, bool):
        raise ValueError(f"peak_labels must be True or False, got {peak_labels!r}")
    return peak_labels


def peak_label_args(peak_labels: bool) -> dict[str, Any]:
    """Component args for the view."""
    return {"peakLabels": peak_labels}
