"""Heatmap `color_columns`, `layer_column` and `colorbar_editor`.

The toolbar of a heatmap offers further columns to color by, layers to show or
hide, and the colorbar below the plot opens an editor. Python only has to send
the columns and say which they are; the plot does the rest in the browser.
These options are render-time: a cache built without them is reused.

The columns are the caller's own: nothing here knows what they mean, so the
data below is deliberately not mass spectrometry.
"""

from __future__ import annotations

import polars as pl
import pytest

from openms_insight import ClusteredHeatmap, Heatmap


@pytest.fixture
def peaks() -> pl.LazyFrame:
    """Readings of weather stations: position, rainfall and two more values."""
    n = 20_000
    return pl.LazyFrame(
        {
            "longitude": [float(i % 2000) for i in range(n)],
            "latitude": [1000.0 + (i * 7919) % 30000 for i in range(n)],
            "rainfall": [float(1 + (i * 31) % 997) for i in range(n)],
            "temperature": [((i * 13) % 100) / 100 for i in range(n)],
            "sunny_days": [(i * 7) % 60 for i in range(n)],
            "network": ["Airport" if i % 20 == 0 else "Volunteer" for i in range(n)],
        }
    )


def _heatmap(data, cache_dir, cache_id, **kwargs):
    return Heatmap(
        cache_id=cache_id,
        data=data,
        cache_path=str(cache_dir),
        x_column="longitude",
        y_column="latitude",
        intensity_column="rainfall",
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
        color_columns={"Temperature": "temperature", "Sunny days": "sunny_days"},
        layer_column="network",
    )

    for state in (
        {},
        {"heatmap_zoom": {"xRange": [100.0, 400.0], "yRange": [1000.0, 9000.0]}},
    ):
        columns = plot._prepare_vue_data(state)["heatmapData"].columns
        assert {"temperature", "sunny_days", "network"} <= set(columns)

    args = plot._get_component_args()
    assert args["colorColumns"] == {
        "Temperature": "temperature",
        "Sunny days": "sunny_days",
    }
    assert args["layerColumn"] == "network"
    assert "colorbarEditor" not in args


def test_without_options_nothing_extra_is_sent(mock_streamlit, temp_cache_dir, peaks):
    plot = _heatmap(peaks, temp_cache_dir, "plain")

    columns = set(plot._prepare_vue_data({})["heatmapData"].columns)
    assert not {"temperature", "sunny_days", "network"} & columns
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
        color_columns={"Temperature": "temperature"},
        layer_column="network",
        colorbar_editor=False,
    )

    assert with_options._get_cache_config() == plain._get_cache_config()
    assert "temperature" in with_options._prepare_vue_data({})["heatmapData"].columns
    assert with_options._get_component_args()["colorbarEditor"] is False


def test_color_columns_must_be_a_mapping(mock_streamlit, temp_cache_dir, peaks):
    with pytest.raises(TypeError, match="color_columns"):
        _heatmap(peaks, temp_cache_dir, "bad", color_columns=["temperature"])


def test_columns_must_exist(mock_streamlit, temp_cache_dir, peaks):
    with pytest.raises(ValueError, match=r"color_columns\['Humidity'\]='humidity'"):
        _heatmap(
            peaks, temp_cache_dir, "missing", color_columns={"Humidity": "humidity"}
        )
    with pytest.raises(ValueError, match="layer_column='region'"):
        _heatmap(peaks, temp_cache_dir, "missing-layer", layer_column="region")


def test_columns_are_checked_in_a_parquet_file(mock_streamlit, temp_cache_dir, peaks):
    path = temp_cache_dir / "stations.parquet"
    peaks.collect().write_parquet(path)
    with pytest.raises(ValueError, match="layer_column='region'"):
        Heatmap(
            cache_id="from-file",
            data_path=str(path),
            cache_path=str(temp_cache_dir),
            x_column="longitude",
            y_column="latitude",
            intensity_column="rainfall",
            layer_column="region",
        )


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
