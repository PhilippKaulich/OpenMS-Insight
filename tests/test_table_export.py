"""Tests for the Table's full CSV export.

The in-table download used to hand Tabulator's own CSV export the rows it held,
which for a server-side paginated table is one page, and only the displayed
columns. The export is now built in Python from the cached data.
"""

import io

import polars as pl
import pytest

from openms_insight import Table


@pytest.fixture
def psm_data() -> pl.LazyFrame:
    n_rows = 250
    return pl.LazyFrame(
        {
            "id_idx": list(range(n_rows)),
            "file_index": [i % 2 for i in range(n_rows)],
            "sequence": [f"PEPTIDE{i}" for i in range(n_rows)],
            "score": [float(n_rows - i) for i in range(n_rows)],
            "hidden_meta": [f"meta_{i}" for i in range(n_rows)],
        }
    )


def _table(tmp, data, **kwargs) -> Table:
    return Table(
        cache_id="export_table",
        data=data,
        cache_path=str(tmp),
        column_definitions=[
            {"field": "sequence", "title": "Sequence"},
            {"field": "score", "title": "Score", "sorter": "number"},
        ],
        index_field="id_idx",
        page_size=50,
        **kwargs,
    )


def _read(payload: dict) -> pl.DataFrame:
    return pl.read_csv(io.StringIO(payload["csv"]))


def test_no_download_payload_without_request(mock_streamlit, temp_cache_dir, psm_data):
    table = _table(temp_cache_dir, psm_data)
    result = table._prepare_vue_data({})
    assert "_download" not in result
    # The page itself stays projected to the displayed columns
    assert "hidden_meta" not in result["tableData"].columns


def test_download_contains_all_rows_and_columns(
    mock_streamlit, temp_cache_dir, psm_data
):
    table = _table(temp_cache_dir, psm_data, title="PSMs")
    state = {"export_table_page": {"page": 3, "download_request": 42}}

    result = table._prepare_vue_data(state)

    payload = result["_download"]
    assert payload["request_id"] == 42
    assert payload["filename"] == "PSMs.csv"
    exported = _read(payload)
    assert exported.height == 250
    # Displayed columns first, in display order, then every other cached column
    assert exported.columns[:2] == ["sequence", "score"]
    assert set(exported.columns) == {
        "sequence",
        "score",
        "id_idx",
        "file_index",
        "hidden_meta",
    }
    # The page sent for display is unchanged by the export
    assert len(result["tableData"]) == 50


def test_download_honours_sort_and_column_filters(
    mock_streamlit, temp_cache_dir, psm_data
):
    table = _table(temp_cache_dir, psm_data)
    state = {
        "export_table_page": {
            "page": 1,
            "sort_column": "score",
            "sort_dir": "asc",
            "column_filters": [{"field": "score", "type": "<=", "value": 10.0}],
            "download_request": 1,
        }
    }

    exported = _read(table._prepare_vue_data(state)["_download"])

    assert exported["score"].to_list() == [float(v) for v in range(1, 11)]


def test_download_honours_cross_component_filters(
    mock_streamlit, temp_cache_dir, psm_data
):
    table = _table(temp_cache_dir, psm_data, filters={"file": "file_index"})
    state = {"file": 1, "export_table_page": {"download_request": 7}}

    exported = _read(table._prepare_vue_data(state)["_download"])

    assert exported.height == 125
    assert set(exported["file_index"].to_list()) == {1}


def test_export_data_without_state_is_whole_table(
    mock_streamlit, temp_cache_dir, psm_data
):
    table = _table(
        temp_cache_dir,
        psm_data,
        initial_sort=[{"column": "score", "dir": "asc"}],
    )

    exported = table.export_data()

    assert exported.height == 250
    assert exported["score"][0] == 1.0
    assert "hidden_meta" in exported.columns


def test_export_data_from_cache_only(mock_streamlit, temp_cache_dir, psm_data):
    """A table reloaded from its cache (no data=) exports every cached column."""
    _table(temp_cache_dir, psm_data)
    reloaded = Table(cache_id="export_table", cache_path=str(temp_cache_dir))

    exported = reloaded.export_data()

    assert exported.height == 250
    assert "hidden_meta" in exported.columns


def test_download_changes_the_hash(mock_streamlit, temp_cache_dir, psm_data):
    """The bridge sends no data with an unchanged hash to a view that holds it,
    so the export has to change the hash to reach the browser."""
    table = Table(cache_id="hash_table", data=psm_data, cache_path=str(temp_cache_dir))
    plain = table._prepare_vue_data({})["_hash"]
    state = {"hash_table_page": {"page": 1, "download_request": 7}}
    assert table._prepare_vue_data(state)["_hash"] != plain


def test_download_neutralises_spreadsheet_formulas(mock_streamlit, temp_cache_dir):
    data = pl.LazyFrame(
        {
            "id_idx": [0, 1, 2, 3, 4],
            "sequence": ["=1+1", "+SUM(A1)", "-2+3", "@cmd", "PEPTIDE"],
            "score": [-1.5, 2.0, 3.0, 4.0, 5.0],
        }
    )
    table = _table(temp_cache_dir, data)
    state = {"export_table_page": {"download_request": 1}}

    payload = table._prepare_vue_data(state)["_download"]
    exported = _read(payload).sort("id_idx")

    assert exported["sequence"].to_list() == [
        "'=1+1",
        "'+SUM(A1)",
        "'-2+3",
        "'@cmd",
        "PEPTIDE",
    ]
    # Numbers are not text, so a negative score stays a number
    assert exported["score"][0] == -1.5
    # The table itself still holds the original text
    assert table.export_data()["sequence"].sort().to_list()[0] == "+SUM(A1)"


def test_csv_safe_handles_tabs_categoricals_and_nulls():
    from openms_insight.components.table import csv_safe

    df = pl.DataFrame(
        {
            "text": ["\tx", "\ry", None, "ok"],
            "cat": pl.Series(["=A", "B", "C", "-D"], dtype=pl.Categorical),
            "n": [1, -2, 3, 4],
        }
    )
    safe = csv_safe(df)
    assert safe["text"].to_list() == ["'\tx", "'\ry", None, "ok"]
    assert safe["cat"].to_list() == ["'=A", "B", "C", "'-D"]
    assert safe["n"].to_list() == [1, -2, 3, 4]
