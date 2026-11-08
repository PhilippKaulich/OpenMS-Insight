"""Table height: `fill_height` keeps the height it is rendered with; `fill_row` grows to its row."""

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

    assert "fillHeight" not in args
    assert "fill_height" not in args


def test_reaches_args_and_survives_reload(mock_streamlit, temp_cache_dir):
    _table(temp_cache_dir, "filled", fill_height=True)

    reloaded = Table(cache_id="filled", cache_path=str(temp_cache_dir))
    args = reloaded._get_component_args()

    assert args["fillHeight"] is True
    assert "fill_height" not in args


def test_fills_its_row_by_default(mock_streamlit, temp_cache_dir):
    args = _table(temp_cache_dir, "row")._get_component_args()

    # The table grows to the height of its row unless told otherwise
    assert "fillRow" not in args
    assert "fill_row" not in args


def test_row_fill_can_be_turned_off_and_survives_reload(mock_streamlit, temp_cache_dir):
    _table(temp_cache_dir, "own-height", fill_row=False)

    reloaded = Table(cache_id="own-height", cache_path=str(temp_cache_dir))
    args = reloaded._get_component_args()

    assert args["fillRow"] is False
    assert "fill_row" not in args
