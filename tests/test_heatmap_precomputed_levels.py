"""A Heatmap given its levels stores them as they are instead of building its own.

An application that downsampled its data while processing it passes those levels,
so the cache holds the same points it computed, and it is not built a second time.
"""

from __future__ import annotations

import polars as pl
import pytest

from openms_insight import Heatmap


@pytest.fixture
def full() -> pl.LazyFrame:
    n = 5000
    return pl.LazyFrame(
        {
            "rt": [float(i % 100) for i in range(n)],
            "mz": [float(i) for i in range(n)],
            "intensity": [float((i * 37) % 1000) for i in range(n)],
            "scan_id": [i % 100 for i in range(n)],
        }
    )


def _levels(full):
    # Deliberately not what Heatmap's own downsampling would choose
    return [full.filter(pl.col("mz") < 100), full.filter(pl.col("mz") < 1000)]


def _heatmap(cache_dir, data=None, cache_id="pre", **kwargs):
    return Heatmap(
        cache_id=cache_id,
        data=data,
        cache_path=str(cache_dir),
        x_column="rt",
        y_column="mz",
        intensity_column="intensity",
        interactivity={"scan": "scan_id"},
        min_points=50,
        **kwargs,
    )


def test_levels_are_stored_as_given(mock_streamlit, temp_cache_dir, full):
    plot = _heatmap(temp_cache_dir, full, levels=_levels(full))

    levels = plot._get_levels()
    sizes = [lvl.select(pl.len()).collect().item() for lvl in levels]
    assert sizes == [100, 1000, 5000]
    assert levels[0].collect()["mz"].max() < 100


def test_smallest_level_is_drawn_without_zoom(mock_streamlit, temp_cache_dir, full):
    plot = _heatmap(temp_cache_dir, full, levels=_levels(full))

    payload = plot._prepare_vue_data({})

    assert len(payload["heatmapData"]) == 100
    assert "scan_id" in payload["heatmapData"].columns


def test_reconstructed_from_cache(mock_streamlit, temp_cache_dir, full):
    _heatmap(temp_cache_dir, full, levels=_levels(full))

    page = Heatmap(cache_id="pre", cache_path=str(temp_cache_dir))

    assert len(page._get_levels()) == 3


def test_extra_columns_of_a_level_are_dropped(mock_streamlit, temp_cache_dir, full):
    levels = [full.head(10).with_columns(pl.lit(1).alias("rank"))]

    plot = _heatmap(temp_cache_dir, full, levels=levels)

    assert "rank" not in plot._get_levels()[0].collect_schema().names()


def test_hash_unchanged_without_levels(temp_cache_dir, full):
    plot = _heatmap(temp_cache_dir, full, cache_id="plain")

    assert "precomputed_levels" not in plot._get_cache_config()


def test_levels_need_data(temp_cache_dir):
    with pytest.raises(ValueError, match="requires data"):
        _heatmap(temp_cache_dir, levels=[])


def test_levels_exclude_categorical_filters(temp_cache_dir, full):
    with pytest.raises(ValueError, match="categorical_filters"):
        _heatmap(
            temp_cache_dir,
            full,
            levels=[],
            filters={"scan": "scan_id"},
            categorical_filters=["scan"],
        )


def test_export_name_and_wheel_reach_vue(tmp_path, full):
    """They reach Vue, also from a component loaded from its cache, and leave
    the cache of a heatmap without them as it was."""
    plain = _heatmap(tmp_path, data=full, cache_id="plain")
    args = plain._get_component_args()
    assert "svgFilename" not in args and "scrollZoom" not in args
    assert "svg_filename" not in plain._get_cache_config()

    _heatmap(
        tmp_path, data=full, cache_id="styled", svg_filename="heat", scroll_zoom=False
    )
    loaded = Heatmap(cache_id="styled", cache_path=str(tmp_path))
    args = loaded._get_component_args()
    assert args["svgFilename"] == "heat"
    assert args["scrollZoom"] is False
