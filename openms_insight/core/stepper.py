"""Previous / next buttons for one filter of a plot: ``stepper``.

Any plot with a toolbar (LinePlot, MirrorPlot, DeconvolvedSpectrum, Heatmap,
Plot3D, SeriesPlot, VolcanoPlot, PCAPlot) takes it; BaseComponent handles the
argument. A plot given ``stepper="frame"`` (an identifier of its ``filters``) gets two
buttons in its toolbar, ``◀ frame 12`` and ``▶``, that set that identifier to
the previous or next value of its column, in sorted order. A peak map of one
ion-mobility frame (m/z × 1/K0) can so step through the frames, and a spectrum
plot through its spectra, without a table next to it.

Without a value for the filter (and no ``filter_defaults`` entry) the plot
starts at the first value.

The sorted values are read once from the component's cache and kept for the
process. The buttons get the current value, its position and its neighbours
with every render; the value list itself never reaches the browser. Render-time
only, never part of the cache configuration.
"""

import bisect
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import polars as pl

_LOCK = threading.Lock()
_VALUES: dict[tuple[str, str, float], list[Any]] = {}


def validate_stepper(stepper: Any, filters: dict[str, str]) -> str | None:
    """Check ``stepper`` names one of the component's filters and return it."""
    if stepper is None:
        return None
    if not isinstance(stepper, str) or not stepper:
        raise ValueError(
            f"stepper must be a filter identifier (a non-empty string) or None, got {stepper!r}"
        )
    if stepper not in filters:
        raise ValueError(
            f"stepper {stepper!r} is not one of the component's filters "
            f"({', '.join(sorted(filters)) or 'none'})"
        )
    return stepper


def _plain(value: Any) -> Any:
    """A JSON value for numpy / polars scalars."""
    item = getattr(value, "item", None)
    return item() if callable(item) else value


def sorted_values(
    cache_dir: Path, column: str, load: Callable[[], list[Any]]
) -> list[Any]:
    """The sorted distinct values of ``column``, read once per cache version."""
    manifest = Path(cache_dir) / "manifest.json"
    try:
        version = manifest.stat().st_mtime
    except OSError:
        version = 0.0
    key = (str(cache_dir), column, version)
    with _LOCK:
        if key in _VALUES:
            return _VALUES[key]
    values = sorted(_plain(v) for v in load() if v is not None)
    with _LOCK:
        # One entry per cache directory and column
        for old in [k for k in _VALUES if k[:2] == key[:2]]:
            del _VALUES[old]
        _VALUES[key] = values
    return values


def unique_values(data: pl.LazyFrame | None, column: str) -> list[Any]:
    """Distinct values of a column of a LazyFrame (empty without data)."""
    if data is None:
        return []
    return (
        data.select(pl.col(column).unique())
        .collect()
        .to_series()
        .drop_nulls()
        .to_list()
    )


def first_step(
    identifier: str | None,
    values: list[Any],
    state: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any] | None:
    """The first value, as the initial selection while the filter has none.

    A filtered plot with no value for its filter shows nothing, so a plot
    with a stepper starts at the first value (unless the filter has a default).
    """
    if not identifier or not values or identifier in (defaults or {}):
        return None
    if state.get(identifier) is not None:
        return None
    return {identifier: values[0]}


def stepper_args(
    identifier: str | None, label: str, values: list[Any], current: Any
) -> dict[str, Any]:
    """The Vue argument: the current value, its position and its neighbours."""
    if not identifier:
        return {}
    count = len(values)
    index: int | None = None
    prev = nxt = None
    if count:
        if current is None:
            nxt = values[0]
        else:
            try:
                pos = bisect.bisect_left(values, current)
            except TypeError:
                pos = count
            if pos < count and values[pos] == current:
                index = pos
                prev = values[pos - 1] if pos > 0 else None
                nxt = values[pos + 1] if pos + 1 < count else None
            else:
                # A value not in the column: step to the nearest ones
                prev = values[pos - 1] if pos > 0 else None
                nxt = values[pos] if pos < count else None
    return {
        "stepper": {
            "identifier": identifier,
            "label": label,
            "value": _plain(current),
            "index": index,
            "count": count,
            "prev": prev,
            "next": nxt,
        }
    }
