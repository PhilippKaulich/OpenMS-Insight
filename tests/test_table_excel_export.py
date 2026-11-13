"""The Table's Excel download: the filtered, sorted rows and an About sheet."""

import base64
import io
import zipfile
from datetime import datetime, timezone

import polars as pl
import pytest

from openms_insight import Table
from openms_insight.core.excel_export import about_rows, sheet_name, to_xlsx

pytest.importorskip("xlsxwriter")
openpyxl = pytest.importorskip("openpyxl")


@pytest.fixture
def psm_data() -> pl.LazyFrame:
    n_rows = 120
    return pl.LazyFrame(
        {
            "id_idx": list(range(n_rows)),
            "sequence": [f"PEPTIDE{i}" for i in range(n_rows)],
            "score": [float(n_rows - i) for i in range(n_rows)],
            "proteins": [[f"P{i}", f"Q{i}"] for i in range(n_rows)],
        }
    )


def _table(tmp, data, **kwargs) -> Table:
    return Table(
        cache_id="excel_table",
        data=data,
        cache_path=str(tmp),
        column_definitions=[
            {"field": "sequence", "title": "Peptide"},
            {"field": "score", "title": "Score", "sorter": "number"},
        ],
        index_field="id_idx",
        page_size=50,
        title="PSMs",
        **kwargs,
    )


def _workbook(payload: dict):
    return openpyxl.load_workbook(io.BytesIO(base64.b64decode(payload["xlsx"])))


def test_the_table_offers_excel_when_paginated(
    mock_streamlit, temp_cache_dir, psm_data
):
    assert _table(temp_cache_dir, psm_data)._get_component_args()["excelExport"] is True
    unpaginated = _table(temp_cache_dir, psm_data, pagination=False)
    assert "excelExport" not in unpaginated._get_component_args()


def test_excel_download_has_rows_titles_and_about(
    mock_streamlit, temp_cache_dir, psm_data
):
    table = _table(
        temp_cache_dir,
        psm_data,
        export_info={"Run": "Run 3", "Database": "yeast.fasta"},
    )
    state = {
        "excel_table_page": {
            "page": 2,
            "sort_column": "score",
            "sort_dir": "asc",
            "column_filters": [{"field": "score", "type": "<=", "value": 10.0}],
            "download_request": 5,
            "download_format": "xlsx",
        }
    }
    payload = table._prepare_vue_data(state)["_download"]
    assert (
        payload["request_id"] == 5
        and payload["filename"] == "PSMs.xlsx"
        and "csv" not in payload
    )
    book = _workbook(payload)
    assert book.sheetnames == ["PSMs", "About"]
    rows = list(book["PSMs"].values)
    # Column titles as the header, displayed columns first, then the rest
    assert rows[0] == ("Peptide", "Score", "id_idx", "proteins")
    assert [r[1] for r in rows[1:]] == [float(v) for v in range(1, 11)]
    assert rows[1][3] == "P119; Q119"
    about = dict(book["About"].values)
    assert about["Table"] == "PSMs" and about["Rows"] == "10"
    assert about["Sorted by"] == "Score (ascending)"
    assert about["Filters"] == "Score <= 10.0"
    assert about["Run"] == "Run 3" and about["Database"] == "yeast.fasta"


def test_csv_stays_the_default(mock_streamlit, temp_cache_dir, psm_data):
    table = _table(temp_cache_dir, psm_data)
    payload = table._prepare_vue_data({"excel_table_page": {"download_request": 1}})[
        "_download"
    ]
    assert payload["filename"] == "PSMs.csv" and "xlsx" not in payload


def test_text_is_never_written_as_a_formula():
    data = to_xlsx(
        pl.DataFrame({"note": ['=HYPERLINK("x")', "+1", "plain"]}),
        "t",
        [("Table", "=1+1")],
    )
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert not any(
            b"<f>" in z.read(n) for n in z.namelist() if n.startswith("xl/worksheets/")
        )
    book = openpyxl.load_workbook(io.BytesIO(data))
    assert book["t"]["A2"].value == '=HYPERLINK("x")'


def test_sheet_names_are_valid():
    assert sheet_name("PSMs: after FDR [1%]") == "PSMs after FDR 1%"
    assert sheet_name("A" * 40) == "A" * 31
    assert sheet_name(None) == "Rows"
    assert sheet_name("About") == "Rows"


def test_about_says_when_rows_were_left_out():
    about = dict(
        about_rows(
            "T",
            2_000_000,
            1_048_575,
            search="KR",
            now=datetime(2026, 11, 13, tzinfo=timezone.utc),
        )
    )
    assert about["Exported"] == "2026-11-13 00:00 UTC"
    assert "Only the first 1,048,575 of 2,000,000 rows" in about["Note"]
    assert about["Search"] == "KR"


def test_csv_download_joins_list_columns(mock_streamlit, temp_cache_dir, psm_data):
    table = _table(temp_cache_dir, psm_data)
    payload = table._prepare_vue_data({"excel_table_page": {"download_request": 1}})[
        "_download"
    ]
    exported = pl.read_csv(io.StringIO(payload["csv"]))
    assert exported.filter(pl.col("id_idx") == 0)["proteins"].item() == "P0; Q0"
