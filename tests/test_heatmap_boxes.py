"""Heatmap.set_boxes(): rectangles drawn over the points (e.g. LC-MS features)."""

from __future__ import annotations

import polars as pl
import pytest

from openms_insight import Heatmap
from openms_insight.rendering.bridge import _payload_cache_key


@pytest.fixture
def points() -> pl.LazyFrame:
    rows = {"rt": [], "mz": [], "intensity": []}
    for i in range(50):
        for j in range(20):
            rows["rt"].append(float(i))
            rows["mz"].append(100.0 + 10 * j)
            rows["intensity"].append(float(1 + i * j))
    return pl.LazyFrame(rows)


@pytest.fixture
def features() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "rt_start": [1.0, 20.0, 40.0],
            "rt_end": [3.0, 25.0, 45.0],
            "mz_start": [110.0, 150.0, 250.0],
            "mz_end": [111.0, 151.0, 251.0],
            "feature_id": [7, 8, 9],
        }
    )


def _heatmap(data, cache_dir, cache_id):
    return Heatmap(
        cache_id=cache_id,
        data=data,
        cache_path=str(cache_dir),
        x_column="rt",
        y_column="mz",
        intensity_column="intensity",
    )


def _set(plot, features, **kwargs):
    return plot.set_boxes(
        features,
        x_range=("rt_start", "rt_end"),
        y_range=("mz_start", "mz_end"),
        id_column="feature_id",
        **kwargs,
    )


def test_no_boxes_by_default(mock_streamlit, temp_cache_dir, points):
    plot = _heatmap(points, temp_cache_dir, "nobox")
    assert "boxData" not in plot._prepare_vue_data({})
    assert "boxes" not in plot._get_component_args()
    assert plot._get_render_key() is None


def test_boxes_reach_vue_with_renamed_columns(
    mock_streamlit, temp_cache_dir, points, features
):
    plot = _set(_heatmap(points, temp_cache_dir, "box"), features, selection="feature")

    boxes = plot._prepare_vue_data({})["boxData"]

    assert list(boxes.columns) == ["x0", "x1", "y0", "y1", "id"]
    assert boxes["id"].tolist() == [7, 8, 9]
    assert plot._get_component_args()["boxes"]["selection"] == "feature"


def test_only_boxes_in_the_zoom_are_sent(
    mock_streamlit, temp_cache_dir, points, features
):
    plot = _set(_heatmap(points, temp_cache_dir, "boxzoom"), features)

    payload = plot._prepare_vue_data(
        {"heatmap_zoom": {"xRange": [24.0, 30.0], "yRange": [140.0, 200.0]}}
    )

    assert payload["boxData"]["id"].tolist() == [8]


def test_max_boxes_keeps_the_first(mock_streamlit, temp_cache_dir, points, features):
    plot = _set(_heatmap(points, temp_cache_dir, "boxmax"), features, max_boxes=2)
    assert plot._prepare_vue_data({})["boxData"]["id"].tolist() == [7, 8]


def test_new_boxes_change_the_payload_key(
    mock_streamlit, temp_cache_dir, points, features
):
    plot = _set(_heatmap(points, temp_cache_dir, "boxkey"), features)
    first = plot._get_render_key()
    _set(plot, features.head(1))
    one = _payload_cache_key(plot, {}, set())
    _set(plot, features)
    assert _payload_cache_key(plot, {}, set()) != one
    assert plot._get_render_key() == first


def test_none_removes_the_boxes(mock_streamlit, temp_cache_dir, points, features):
    plot = _set(_heatmap(points, temp_cache_dir, "boxnone"), features)
    plot.set_boxes(None)
    assert "boxData" not in plot._prepare_vue_data({})
    assert plot._get_render_key() is None


def test_selection_needs_an_id(mock_streamlit, temp_cache_dir, points, features):
    plot = _heatmap(points, temp_cache_dir, "boxsel")
    with pytest.raises(ValueError):
        plot.set_boxes(
            features,
            x_range=("rt_start", "rt_end"),
            y_range=("mz_start", "mz_end"),
            selection="feature",
        )
