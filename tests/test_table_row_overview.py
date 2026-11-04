"""Table `row_overview`: a button per row opens the whole row."""

from __future__ import annotations

import polars as pl

from openms_insight import Table


def _table(cache_dir, cache_id, **kwargs):
    return Table(
        cache_id=cache_id,
        data=pl.LazyFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]}),
        cache_path=str(cache_dir),
        index_field="id",
        pagination=False,
        **kwargs,
    )


def test_off_by_default(mock_streamlit, temp_cache_dir):
    args = _table(temp_cache_dir, "plain")._get_component_args()

    assert "rowOverview" not in args
    assert "row_overview" not in args


def test_reaches_args_and_survives_reload(mock_streamlit, temp_cache_dir):
    _table(temp_cache_dir, "filled", row_overview=True)

    reloaded = Table(cache_id="filled", cache_path=str(temp_cache_dir))
    args = reloaded._get_component_args()

    assert args["rowOverview"] is True
    assert "row_overview" not in args


def test_title_template_reaches_args_and_survives_reload(
    mock_streamlit, temp_cache_dir
):
    _table(temp_cache_dir, "titled", row_overview="{name}, id {id}")

    reloaded = Table(cache_id="titled", cache_path=str(temp_cache_dir))
    args = reloaded._get_component_args()

    assert args["rowOverview"] is True
    assert args["rowOverviewTitle"] == "{name}, id {id}"


def test_true_sends_no_title(mock_streamlit, temp_cache_dir):
    args = _table(temp_cache_dir, "untitled", row_overview=True)._get_component_args()

    assert "rowOverviewTitle" not in args
