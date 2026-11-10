"""Heatmap `color_columns`, `layer_column` and `colorbar_editor`.

The toolbar of a heatmap offers further columns to color by, layers to show or
hide, and the colorbar below the plot opens an editor. Python only has to send
the columns and say which they are; the plot does the rest in the browser.
These options are render-time: a cache built without them is reused.
"""

from __future__ import annotations

import polars as pl
import pytest

from openms_insight import ClusteredHeatmap, Heatmap


@pytest.fixture
def peaks() -> pl.LazyFrame:
    n = 20_000
    return pl.LazyFrame(
        {
            "rt": [float(i % 2000) for i in range(n)],
            "mass": [1000.0 + (i * 7919) % 30000 for i in range(n)],
            "intensity": [float(1 + (i * 31) % 997) for i in range(n)],
            "qscore": [((i * 13) % 100) / 100 for i in range(n)],
            "ions": [(i * 7) % 60 for i in range(n)],
            "layer": ["Precursor" if i % 20 == 0 else "Survey" for i in range(n)],
        }
    )


def _heatmap(data, cache_dir, cache_id, **kwargs):
    return Heatmap(
        cache_id=cache_id,
        data=data,
        cache_path=str(cache_dir),
        x_column="rt",
        y_column="mass",
        intensity_column="intensity",
        min_points=1000,
        **kwargs,
    )


def test_color_and_layer_columns_reach_payload_and_args(
    mock_streamlit, temp_cache_dir, peaks
):
    plot = _heatmap(
        peaks,
        temp_cache_dir,
        "colors",
        color_columns={"QScore": "qscore", "# ions": "ions"},
        layer_column="layer",
    )

    for state in (
        {},
        {"heatmap_zoom": {"xRange": [100.0, 400.0], "yRange": [1000.0, 9000.0]}},
    ):
        columns = plot._prepare_vue_data(state)["heatmapData"].columns
        assert {"qscore", "ions", "layer"} <= set(columns)

    args = plot._get_component_args()
    assert args["colorColumns"] == {"QScore": "qscore", "# ions": "ions"}
    assert args["layerColumn"] == "layer"
    assert "colorbarEditor" not in args


def test_without_options_nothing_extra_is_sent(mock_streamlit, temp_cache_dir, peaks):
    plot = _heatmap(peaks, temp_cache_dir, "plain")

    columns = set(plot._prepare_vue_data({})["heatmapData"].columns)
    assert not {"qscore", "ions", "layer"} & columns
    args = plot._get_component_args()
    assert "colorColumns" not in args
    assert "layerColumn" not in args


def test_options_are_render_time_and_reuse_the_cache(
    mock_streamlit, temp_cache_dir, peaks
):
    plain = _heatmap(peaks, temp_cache_dir, "shared")
    with_options = _heatmap(
        None,
        temp_cache_dir,
        "shared",
        color_columns={"QScore": "qscore"},
        layer_column="layer",
        colorbar_editor=False,
    )

    assert with_options._get_cache_config() == plain._get_cache_config()
    assert "qscore" in with_options._prepare_vue_data({})["heatmapData"].columns
    assert with_options._get_component_args()["colorbarEditor"] is False


def test_color_columns_must_be_a_mapping(mock_streamlit, temp_cache_dir, peaks):
    with pytest.raises(TypeError, match="color_columns"):
        _heatmap(peaks, temp_cache_dir, "bad", color_columns=["qscore"])


def test_clustered_heatmap_colorbar_editor_flag(
    mock_streamlit,
    temp_cache_dir,
    sample_quantification_data_complete,
    sample_quantification_metadata,
):
    def build(cache_id, **kwargs):
        return ClusteredHeatmap(
            cache_id=cache_id,
            data=sample_quantification_data_complete,
            metadata=sample_quantification_metadata,
            id_col="feature",
            cache_path=str(temp_cache_dir),
            **kwargs,
        )

    assert "colorbarEditor" not in build("editable")._get_component_args()
    assert (
        build("fixed", colorbar_editor=False)._get_component_args()["colorbarEditor"]
        is False
    )
