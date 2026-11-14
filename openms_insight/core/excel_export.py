"""Excel (.xlsx) export of a table, for the Table's download menu.

Writes two sheets: the rows, and "About" with what was exported (the table,
when, how many rows, the sort, the filters and the search) and whatever the
app adds with ``export_info``, such as the run and its settings.

Needs ``xlsxwriter`` (polars writes the workbook with it). Without it the
download offers CSV only.
"""

from __future__ import annotations

import base64
import importlib.util
import io
import re
from datetime import datetime, timezone
from typing import Any

import polars as pl

# Rows of an Excel worksheet, one of them the header
EXCEL_MAX_ROWS = 1_048_576
# Characters Excel refuses in a sheet name, and its length limit
_SHEET_FORBIDDEN = re.compile(r"[\[\]:*?/\\]")
_SHEET_MAX_LEN = 31


def excel_available() -> bool:
    """Whether xlsxwriter is installed, so a workbook can be written."""
    return importlib.util.find_spec("xlsxwriter") is not None


def sheet_name(title: str | None) -> str:
    """A valid worksheet name for a table title."""
    name = _SHEET_FORBIDDEN.sub(" ", title or "").strip().strip("'")
    name = re.sub(r"\s+", " ", name)[:_SHEET_MAX_LEN].strip()
    if not name or name.lower() == "about":
        return "Rows"
    return name


def flatten_nested(df: pl.DataFrame) -> pl.DataFrame:
    """Columns a cell (or CSV field) can hold: lists joined with '; ', structs as JSON, the rest as text."""
    columns = []
    for name, dtype in df.schema.items():
        if isinstance(dtype, (pl.List, pl.Array)):
            columns.append(
                pl.col(name).cast(pl.List(pl.Utf8)).list.join("; ").alias(name)
            )
        elif isinstance(dtype, pl.Struct):
            columns.append(pl.col(name).struct.json_encode().alias(name))
        elif dtype in (pl.Object, pl.Binary, pl.Null):
            columns.append(
                pl.col(name)
                .map_elements(
                    lambda v: None if v is None else str(v), return_dtype=pl.Utf8
                )
                .alias(name)
            )
    return df.with_columns(columns) if columns else df


def _describe_filters(column_filters: Any) -> str:
    if not column_filters:
        return ""
    parts = []
    for entry in column_filters if isinstance(column_filters, list) else []:
        if not isinstance(entry, dict):
            continue
        field = entry.get("field", "")
        kind = entry.get("type", "")
        value = entry.get("value")
        if kind == "in" and isinstance(value, list):
            parts.append(f"{field} is one of {', '.join(map(str, value))}")
        elif kind in (">=", "<=", "=", ">", "<") and value is not None:
            parts.append(f"{field} {kind} {value}")
        elif kind == "regex":
            parts.append(f"{field} matches {value}")
        else:
            parts.append(f"{field}: {kind} {value}".strip())
    return "; ".join(parts)


def about_rows(
    title: str | None,
    rows: int,
    exported_rows: int,
    sort_column: str | None = None,
    sort_dir: str = "asc",
    column_filters: Any = None,
    search: str | None = None,
    export_info: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> list[tuple[str, str]]:
    """The 'About' sheet as (what, value) pairs."""
    now = now or datetime.now(timezone.utc)
    about = [
        ("Table", title or ""),
        ("Exported", now.strftime("%Y-%m-%d %H:%M UTC")),
        ("Rows", f"{exported_rows:,}"),
    ]
    if exported_rows < rows:
        about.append(
            (
                "Note",
                f"Only the first {exported_rows:,} of {rows:,} rows: an Excel sheet "
                "holds no more. Download the CSV for every row.",
            )
        )
    if sort_column:
        about.append(
            (
                "Sorted by",
                f"{sort_column} ({'descending' if sort_dir == 'desc' else 'ascending'})",
            )
        )
    filters = _describe_filters(column_filters)
    if filters:
        about.append(("Filters", filters))
    if search:
        about.append(("Search", str(search)))
    for key, value in (export_info or {}).items():
        about.append((str(key), "" if value is None else str(value)))
    return about


def to_xlsx(df: pl.DataFrame, title: str | None, about: list[tuple[str, str]]) -> bytes:
    """A workbook with the rows of ``df`` and an 'About' sheet.

    Text is written as text, never as a formula, so a cell starting with ``=``
    does not run when the file is opened. Rows beyond what a sheet holds are
    left out (``about_rows`` says so).
    """
    df = flatten_nested(df.head(EXCEL_MAX_ROWS - 1))
    buffer = io.BytesIO()
    import xlsxwriter

    with xlsxwriter.Workbook(buffer, {"strings_to_formulas": False}) as workbook:
        df.write_excel(
            workbook,
            worksheet=sheet_name(title),
            autofit=True,
            table_style="Table Style Light 1",
            freeze_panes=(1, 0),
        )
        sheet = workbook.add_worksheet("About")
        bold = workbook.add_format({"bold": True})
        wrap = workbook.add_format({"text_wrap": True, "valign": "top"})
        sheet.set_column(0, 0, 18)
        sheet.set_column(1, 1, 90, wrap)
        for row, (what, value) in enumerate(about):
            sheet.write_string(row, 0, what, bold)
            sheet.write_string(row, 1, value)
    return buffer.getvalue()


def xlsx_payload(
    request_id: Any, filename: str, df: pl.DataFrame, title: str | None, about: list
) -> dict[str, Any]:
    """The download payload the table's Vue component saves as a file."""
    return {
        "request_id": request_id,
        "filename": filename,
        "xlsx": base64.b64encode(to_xlsx(df, title, about)).decode("ascii"),
    }
