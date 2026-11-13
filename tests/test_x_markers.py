"""LinePlot x_markers: render-time options passed to Vue, not part of the cache."""

import json

import polars as pl
import pytest

from openms_insight import LinePlot
from openms_insight.core.x_markers import (
    MAX_X_MARKERS,
    validate_x_marker_tolerance,
    validate_x_markers,
    x_marker_args,
)


@pytest.fixture
def spectra() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "scan": [1, 1, 1],
            "mz": [126.1277, 127.1248, 300.0],
            "intensity": [10.0, 20.0, 30.0],
        }
    )


def _plot(spectra, cache_dir, cache_id="markers", **kwargs) -> LinePlot:
    return LinePlot(
        cache_id=cache_id,
        data=spectra,
        x_column="mz",
        y_column="intensity",
        cache_path=str(cache_dir),
        **kwargs,
    )


def test_off_by_default(mock_streamlit, temp_cache_dir, spectra):
    args = _plot(spectra, temp_cache_dir)._get_component_args()
    assert "xMarkers" not in args and "xMarkerTolerance" not in args


def test_dict_sorted_by_x(mock_streamlit, temp_cache_dir, spectra):
    args = _plot(
        spectra,
        temp_cache_dir,
        x_markers={"b": 127.1248, "a": 126.1277},
        x_marker_tolerance=0.003,
    )._get_component_args()
    assert args["xMarkers"] == [
        {"x": 126.1277, "label": "a"},
        {"x": 127.1248, "label": "b"},
    ]
    assert args["xMarkerTolerance"] == 0.003


def test_list_with_colours_and_without_labels():
    markers = validate_x_markers([{"x": 5, "label": " end ", "color": "red"}, {"x": 1}])
    assert markers == [
        {"x": 1.0, "label": ""},
        {"x": 5.0, "label": "end", "color": "red"},
    ]
    assert x_marker_args(markers, None) == {
        "xMarkers": markers,
        "xMarkerTolerance": None,
    }
    assert x_marker_args(None, 1.0) == {}


@pytest.mark.parametrize(
    "markers",
    [
        "TMT10",
        {},
        [],
        {"a": "x"},
        {"a": True},
        {"a": float("nan")},
        {"a": float("inf")},
        {1: 2.0},
        [{"x": 1, "size": 3}],
        [{"label": "no x"}],
        [{"x": 1, "color": ""}],
        [3.0],
        {str(i): float(i) for i in range(MAX_X_MARKERS + 1)},
    ],
)
def test_bad_markers_raise(markers):
    with pytest.raises(ValueError, match="x_markers|x marker"):
        validate_x_markers(markers)


@pytest.mark.parametrize("tolerance", [0, -1, True, "0.01", float("inf")])
def test_bad_tolerances_raise(tolerance):
    with pytest.raises(ValueError, match="x_marker_tolerance"):
        validate_x_marker_tolerance(tolerance)


def test_tolerance_optional():
    assert validate_x_marker_tolerance(None) is None
    assert validate_x_marker_tolerance(2) == 2.0


def test_not_part_of_the_cache(mock_streamlit, temp_cache_dir, spectra):
    off = _plot(spectra, temp_cache_dir, cache_id="same")
    with open(off._get_manifest_path()) as f:
        before = json.load(f)
    on = _plot(
        spectra,
        temp_cache_dir,
        cache_id="same",
        x_markers={"a": 126.1277},
        x_marker_tolerance=0.003,
    )
    with open(on._get_manifest_path()) as f:
        after = json.load(f)
    assert before == after
