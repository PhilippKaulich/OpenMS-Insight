"""Table collapse_columns: scroll sideways instead of folding columns away."""

import polars as pl

from openms_insight import Table


def _table(cache_path, **kwargs) -> Table:
    return Table(
        cache_id="collapse",
        data=pl.LazyFrame({"id": [1, 2], "scan": [10, 20]}),
        cache_path=str(cache_path),
        index_field="id",
        **kwargs,
    )


def test_collapses_by_default(mock_streamlit, temp_cache_dir):
    assert "collapseColumns" not in _table(temp_cache_dir)._get_component_args()


def test_scrolls_when_turned_off(mock_streamlit, temp_cache_dir):
    args = _table(temp_cache_dir, collapse_columns=False)._get_component_args()
    assert args["collapseColumns"] is False


def test_cache_is_shared(mock_streamlit, temp_cache_dir):
    first = _table(temp_cache_dir)
    second = _table(temp_cache_dir, collapse_columns=False)
    assert first._input_config_hash == second._input_config_hash
