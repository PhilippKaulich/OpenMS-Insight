"""Shared helpers for ``multi_select``: selecting several entries at once.

A component with ``multi_select={'proteins': 'accession'}`` lets the user pick
several rows or points (a box or lasso drag on a plot, the check boxes of a
table, the preset buttons of a volcano plot). The identifier then holds the
sorted list of the distinct values of the column over the picked entries, or
None when nothing is picked. Every component with the same identifier shows
the same set, and any component or page can read it with
``state_manager.get_selection('proteins')``.

A multi-selection is a selection level like any other: a component with
``filters={'proteins': 'accession'}`` shows the rows whose accession is in the
set, just as it shows the rows of one selected value for a single selection.

A filter column may hold a list per row (the modifications of a proteoform,
say): the row is shown when one of its values is selected. And
``filter_defaults={'shift': ALL}`` makes a filter show every row while nothing
is selected, instead of none, so clearing a selection lifts the filter.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl


def _int_if_whole(value: Any) -> Any:
    # JavaScript numbers arrive as floats; an Int64 column needs an int
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def selection_key(value: Any) -> Any:
    """A hashable form of a selection value (a list becomes a tuple)."""
    if isinstance(value, list):
        return tuple(value)
    return value


#: A ``filter_defaults`` value: while the filter's identifier has no
#: selection, every row is shown. A string, so it survives the JSON manifest
#: of a cached component.
ALL = "__openms_insight_all_rows__"


def match_selection(column: str, value: Any, dtype: Any = None) -> pl.Expr:
    """Rows of ``column`` matching a selection: the one selected value, or any
    of the values of a multi-selection (a list). With the column's ``dtype``
    a list column matches when one of its values is selected. ``ALL``
    matches every row."""
    if isinstance(value, str) and value == ALL:
        return pl.lit(True)
    is_list = dtype is not None and isinstance(dtype, (pl.List, pl.Array))
    if isinstance(value, (list, tuple)):
        values = [_int_if_whole(v) for v in value]
        if is_list:
            return (
                pl.col(column)
                .list.eval(pl.element().is_in(values))
                .list.any()
                .fill_null(False)
            )
        return pl.col(column).is_in(values)
    if is_list:
        return pl.col(column).list.contains(_int_if_whole(value)).fill_null(False)
    return pl.col(column) == _int_if_whole(value)


def filter_selection(data: pl.LazyFrame, column: str, value: Any) -> pl.LazyFrame:
    """``data`` narrowed to the rows matching a selection (``match_selection``
    with the column's type looked up)."""
    if isinstance(value, str) and value == ALL:
        return data
    dtype = data.collect_schema().get(column)
    return data.filter(match_selection(column, value, dtype))


def normalize_multi_select(multi_select: dict[str, str] | None) -> dict[str, str]:
    """Validate a ``multi_select`` mapping (identifier -> column)."""
    if not multi_select:
        return {}
    if not isinstance(multi_select, dict):
        raise ValueError("multi_select must map identifier names to column names")
    for identifier, column in multi_select.items():
        if not isinstance(identifier, str) or not isinstance(column, str):
            raise ValueError("multi_select must map identifier names to column names")
        if identifier.endswith("_page"):
            raise ValueError(
                f"multi_select identifier {identifier!r} must not end in '_page' "
                "(reserved for pagination state)"
            )
    return dict(multi_select)


def _plain(value: Any) -> Any:
    """A JSON-friendly Python scalar."""
    if isinstance(value, np.generic):
        return value.item()
    return value


def selection_values(values) -> list[Any] | None:
    """Sorted distinct non-null values, or None for an empty selection."""
    distinct = {_plain(v) for v in values if v is not None}
    distinct.discard(None)
    if not distinct:
        return None
    try:
        return sorted(distinct)
    except TypeError:  # mixed types
        return sorted(distinct, key=str)


def combine(current: Any, picked: list[Any] | None, mode: str) -> list[Any] | None:
    """The new selection: ``picked`` replacing, added to or removed from
    ``current``."""
    current_values = list(current) if isinstance(current, (list, tuple)) else []
    picked = picked or []
    if mode == "add":
        return selection_values(current_values + picked)
    if mode == "remove":
        removed = set(picked)
        return selection_values(v for v in current_values if v not in removed)
    return selection_values(picked)


def selected_set(state: dict[str, Any], identifier: str) -> list[Any]:
    """The values selected for ``identifier`` (an empty list when none)."""
    value = state.get(identifier)
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def region_mask(x: np.ndarray, y: np.ndarray, region: dict[str, Any]) -> np.ndarray:
    """Points inside a selection region sent by a plot.

    ``region`` is ``{'type': 'box', 'x': [x0, x1], 'y': [y0, y1]}`` or
    ``{'type': 'lasso', 'x': [...], 'y': [...]}`` (the polygon's corners), in
    data coordinates.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    xs = [float(v) for v in region.get("x") or []]
    ys = [float(v) for v in region.get("y") or []]
    if region.get("type") == "box":
        if len(xs) < 2 or len(ys) < 2:
            return np.zeros(len(x), dtype=bool)
        x0, x1 = sorted(xs[:2])
        y0, y1 = sorted(ys[:2])
        return (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
    if len(xs) < 3 or len(xs) != len(ys):
        return np.zeros(len(x), dtype=bool)
    # Even-odd rule (ray casting), vectorised over the points
    inside = np.zeros(len(x), dtype=bool)
    n = len(xs)
    j = n - 1
    for i in range(n):
        xi, yi, xj, yj = xs[i], ys[i], xs[j], ys[j]
        crosses = (yi > y) != (yj > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
        inside ^= crosses & (x < x_cross)
        j = i
    return inside


def values_in_region(
    frame: pl.LazyFrame | pl.DataFrame,
    x_column: str,
    y_column: str,
    column: str,
    region: dict[str, Any],
) -> list[Any] | None:
    """Distinct values of ``column`` over the points of ``frame`` in ``region``."""
    if isinstance(frame, pl.LazyFrame):
        frame = frame.select(x_column, y_column, column).collect()
    else:
        frame = frame.select(x_column, y_column, column)
    if frame.height == 0:
        return None
    mask = region_mask(frame[x_column].to_numpy(), frame[y_column].to_numpy(), region)
    return selection_values(frame.filter(pl.Series(mask))[column].to_list())
