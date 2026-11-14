"""stepper: previous / next buttons for one filter (core/stepper.py)."""

import json

import polars as pl
import pytest

from openms_insight import Heatmap, LinePlot
from openms_insight.core.stepper import stepper_args, validate_stepper


@pytest.fixture
def spectra() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "scan": [5, 5, 2, 2, 9],
            "mz": [100.0, 200.0, 150.0, 250.0, 300.0],
            "intensity": [10.0, 20.0, 30.0, 40.0, 50.0],
        }
    )


@pytest.fixture
def frames() -> pl.LazyFrame:
    n = 60
    return pl.LazyFrame(
        {
            "frame": [i % 3 + 1 for i in range(n)],
            "mz": [400.0 + i for i in range(n)],
            "im": [0.7 + i / 100 for i in range(n)],
            "intensity": [float(i + 1) for i in range(n)],
        }
    )


def _line(spectra, cache_dir, cache_id="step", **kwargs) -> LinePlot:
    return LinePlot(
        cache_id=cache_id,
        data=spectra,
        filters={"spectrum": "scan"},
        x_column="mz",
        y_column="intensity",
        cache_path=str(cache_dir),
        **kwargs,
    )


def _heatmap(frames, cache_dir, cache_id="frames", **kwargs) -> Heatmap:
    return Heatmap(
        cache_id=cache_id,
        data=frames,
        x_column="mz",
        y_column="im",
        intensity_column="intensity",
        filters={"frame": "frame"},
        categorical_filters=["frame"],
        cache_path=str(cache_dir),
        **kwargs,
    )


def test_off_by_default(mock_streamlit, temp_cache_dir, spectra):
    plot = _line(spectra, temp_cache_dir)
    assert plot._state_args({"spectrum": 5}) == {}


def test_lineplot_steps_through_sorted_values(mock_streamlit, temp_cache_dir, spectra):
    plot = _line(spectra, temp_cache_dir, stepper="spectrum")
    args = plot._state_args({"spectrum": 5})["stepper"]
    assert args == {
        "identifier": "spectrum",
        "label": "spectrum",
        "value": 5,
        "index": 1,
        "count": 3,
        "prev": 2,
        "next": 9,
    }
    first = plot._state_args({"spectrum": 2})["stepper"]
    assert (first["prev"], first["next"], first["index"]) == (None, 5, 0)
    last = plot._state_args({"spectrum": 9})["stepper"]
    assert (last["prev"], last["next"]) == (5, None)


def test_nothing_selected_steps_to_the_first(mock_streamlit, temp_cache_dir, spectra):
    args = _line(spectra, temp_cache_dir, stepper="spectrum")._state_args({})
    assert args["stepper"]["index"] is None
    assert (args["stepper"]["prev"], args["stepper"]["next"]) == (None, 2)


def test_heatmap_frames(mock_streamlit, temp_cache_dir, frames):
    heatmap = _heatmap(frames, temp_cache_dir, stepper="frame")
    args = heatmap._state_args({"frame": 2})["stepper"]
    assert (args["count"], args["index"], args["prev"], args["next"]) == (3, 1, 1, 3)


def test_heatmap_without_categorical_filter(mock_streamlit, temp_cache_dir, frames):
    heatmap = Heatmap(
        cache_id="nocat",
        data=frames,
        x_column="mz",
        y_column="im",
        intensity_column="intensity",
        filters={"frame": "frame"},
        cache_path=str(temp_cache_dir),
        stepper="frame",
    )
    args = heatmap._state_args({"frame": 3})["stepper"]
    assert (args["count"], args["index"], args["prev"], args["next"]) == (3, 2, 2, None)


def test_other_plots_accept_a_stepper(mock_streamlit, temp_cache_dir):
    from openms_insight import MirrorPlot

    data = pl.LazyFrame(
        {
            "scan": [1, 1, 4],
            "mz": [100.0, 200.0, 300.0],
            "intensity": [1.0, 2.0, 3.0],
        }
    )
    mirror = MirrorPlot(
        cache_id="mirror",
        data=data,
        filters_top={"spectrum": "scan"},
        filters_bottom={"spectrum": "scan"},
        x_column="mz",
        y_column="intensity",
        cache_path=str(temp_cache_dir),
        stepper="spectrum",
    )
    args = mirror._state_args({"spectrum": 1})["stepper"]
    assert (args["count"], args["next"]) == (2, 4)


def test_table_has_no_stepper(mock_streamlit, temp_cache_dir, spectra):
    from openms_insight import Table

    with pytest.raises(ValueError, match="stepper"):
        Table(
            cache_id="table",
            data=spectra,
            filters={"spectrum": "scan"},
            cache_path=str(temp_cache_dir),
            stepper="spectrum",
        )


@pytest.mark.parametrize("value", ["scan", "", 3, ["spectrum"]])
def test_rejects_bad_steppers(mock_streamlit, temp_cache_dir, spectra, value):
    with pytest.raises(ValueError, match="stepper"):
        _line(spectra, temp_cache_dir, stepper=value)


def test_values_off_the_list():
    args = stepper_args("f", "f", [1, 3, 5], 4)["stepper"]
    assert (args["index"], args["prev"], args["next"]) == (None, 3, 5)
    args = stepper_args("f", "f", [1, 3, 5], "x")["stepper"]
    assert (args["prev"], args["next"]) == (5, None)
    assert stepper_args("f", "f", [], 1)["stepper"]["count"] == 0
    assert stepper_args(None, "f", [1], 1) == {}
    assert validate_stepper(None, {}) is None


def test_not_part_of_the_cache(mock_streamlit, temp_cache_dir, spectra):
    off = _line(spectra, temp_cache_dir, cache_id="same")
    with open(off._get_manifest_path()) as f:
        before = json.load(f)
    on = _line(spectra, temp_cache_dir, cache_id="same", stepper="spectrum")
    with open(on._get_manifest_path()) as f:
        after = json.load(f)
    assert before == after
    assert "stepper" not in json.dumps(after)


def test_starts_at_the_first_value(mock_streamlit, temp_cache_dir, spectra, frames):
    plot = _line(spectra, temp_cache_dir, stepper="spectrum")
    assert plot.get_initial_selection({}) == {"spectrum": 2}
    assert plot.get_initial_selection({"spectrum": 9}) is None
    assert (
        _line(spectra, temp_cache_dir, cache_id="plain").get_initial_selection({})
        is None
    )
    defaulted = _line(
        spectra,
        temp_cache_dir,
        cache_id="defaulted",
        stepper="spectrum",
        filter_defaults={"spectrum": 9},
    )
    assert defaulted.get_initial_selection({}) is None
    heatmap = _heatmap(frames, temp_cache_dir, stepper="frame")
    assert heatmap.get_initial_selection({}) == {"frame": 1}
