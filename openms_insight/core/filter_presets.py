"""Filter presets: ready-made filters a table lists at the top of its filter dialog.

A preset that is on keeps only the rows matching all of its conditions. The
same shape is used by ``Table(filter_presets=...)`` and by the fragment table
of the sequence view (``js-component/src/components/filterPresets.ts``).
"""

from typing import Any

import polars as pl

PRESET_OPS = ("==", "!=", "<=", ">=", "<", ">", "in", "not in")


def _normalize_condition(entry: dict[str, Any], where: str) -> dict[str, Any]:
    if "column" not in entry:
        raise ValueError(f"{where} needs a 'column': {entry}")
    op = entry.get("op", "==")
    if op not in PRESET_OPS:
        raise ValueError(
            f"{where}: 'op' must be one of {', '.join(PRESET_OPS)}, not {op!r}"
        )
    value = entry.get("value")
    if op in ("in", "not in"):
        if not isinstance(value, (list, tuple, set)):
            raise ValueError(f"{where}: {op!r} needs a list as 'value', not {value!r}")
        value = list(value)
    return {"column": str(entry["column"]), "op": op, "value": value}


def normalize_filter_presets(
    presets: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Validate filter preset entries and fill in their defaults.

    Each entry needs a ``label`` and either ``filters`` (a list of
    ``{"column", "op", "value"}``) or a single condition given as ``column``,
    ``op`` and ``value`` on the entry. ``help``, ``default`` (False) and ``id``
    (the label) are optional; ids must be unique.
    """
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in presets or []:
        if not entry.get("label"):
            raise ValueError(f"filter_presets entry needs a 'label': {entry}")
        label = str(entry["label"])
        preset_id = str(entry.get("id") or label)
        if preset_id in seen:
            raise ValueError(f"filter_presets: two presets share the id {preset_id!r}")
        seen.add(preset_id)
        where = f"filter_presets[{preset_id!r}]"
        if "filters" in entry:
            conditions = [
                _normalize_condition(dict(c), where) for c in entry["filters"] or []
            ]
        else:
            conditions = [_normalize_condition(entry, where)]
        if not conditions:
            raise ValueError(f"{where} has no conditions")
        normalized.append(
            {
                "id": preset_id,
                "label": label,
                "filters": conditions,
                "default": bool(entry.get("default", False)),
                **({"help": str(entry["help"])} if entry.get("help") else {}),
            }
        )
    return normalized


def _condition_expression(condition: dict[str, Any]) -> pl.Expr:
    column = pl.col(condition["column"])
    op, value = condition["op"], condition["value"]
    if op == "==":
        return column.eq_missing(value)
    if op == "!=":
        return column.ne_missing(value)
    if op == "<=":
        return column <= value
    if op == ">=":
        return column >= value
    if op == "<":
        return column < value
    if op == ">":
        return column > value
    if op == "in":
        return column.is_in(value)
    # "not in": a missing value is not in the list
    return column.is_null() | ~column.is_in(value)


def preset_expression(preset: dict[str, Any]) -> pl.Expr:
    """A polars expression true for the rows a (normalized) preset keeps."""
    expression = pl.lit(True)
    for condition in preset["filters"]:
        expression = expression & _condition_expression(condition).fill_null(False)
    return expression
