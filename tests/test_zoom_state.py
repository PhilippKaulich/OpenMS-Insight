"""zoom_identifier: plots keep their zoom in the shared state (core/zoom.py)."""

import json

import polars as pl
import pytest
from component_cases import COMPONENT_CASES, build_kwargs

from openms_insight import Heatmap, MirrorPlot
from openms_insight.core.zoom import normalize_zoom, validate_zoom_identifier, zoom_args

ZOOMABLE = {"LinePlot", "VolcanoPlot", "PCAPlot", "SeriesPlot", "DeconvolvedSpectrum"}
CASES = [c for c in COMPONENT_CASES if c[0].__name__ in ZOOMABLE]
IDS = [c[0].__name__ for c in CASES]
ARGNAMES = "ComponentClass,data_fixture,extra_kwargs,fixture_kwargs"


def _build(request, cache_dir, cls, data_fixture, extra, fixtures, cache_id, **kwargs):
    return cls(
        cache_id=cache_id,
        data=request.getfixturevalue(data_fixture),
        cache_path=str(cache_dir),
        **build_kwargs(request, extra, fixtures),
        **kwargs,
    )


def test_all_zoomable_components_are_covered():
    assert {c[0].__name__ for c in CASES} == ZOOMABLE


@pytest.mark.parametrize(ARGNAMES, CASES, ids=IDS)
def test_off_by_default(
    mock_streamlit,
    temp_cache_dir,
    request,
    ComponentClass,
    data_fixture,
    extra_kwargs,
    fixture_kwargs,
):
    plot = _build(
        request,
        temp_cache_dir,
        ComponentClass,
        data_fixture,
        extra_kwargs,
        fixture_kwargs,
        "zoff",
    )
    assert "zoomIdentifier" not in plot._get_component_args()


@pytest.mark.parametrize(ARGNAMES, CASES, ids=IDS)
def test_identifier_is_passed_to_vue(
    mock_streamlit,
    temp_cache_dir,
    request,
    ComponentClass,
    data_fixture,
    extra_kwargs,
    fixture_kwargs,
):
    plot = _build(
        request,
        temp_cache_dir,
        ComponentClass,
        data_fixture,
        extra_kwargs,
        fixture_kwargs,
        "zon",
        zoom_identifier="zoom@plot",
    )
    assert plot._get_component_args()["zoomIdentifier"] == "zoom@plot"


@pytest.mark.parametrize(ARGNAMES, CASES, ids=IDS)
def test_not_part_of_the_cache(
    mock_streamlit,
    temp_cache_dir,
    request,
    ComponentClass,
    data_fixture,
    extra_kwargs,
    fixture_kwargs,
):
    off = _build(
        request,
        temp_cache_dir,
        ComponentClass,
        data_fixture,
        extra_kwargs,
        fixture_kwargs,
        "same",
    )
    with open(off._get_manifest_path()) as f:
        before = json.load(f)
    on = _build(
        request,
        temp_cache_dir,
        ComponentClass,
        data_fixture,
        extra_kwargs,
        fixture_kwargs,
        "same",
        zoom_identifier="zoom@plot",
    )
    with open(on._get_manifest_path()) as f:
        after = json.load(f)
    assert before == after
    assert "zoom@plot" not in json.dumps(after)


def test_mirror_plot(mock_streamlit, temp_cache_dir):
    data = pl.LazyFrame({"scan": [1, 1], "mz": [100.0, 200.0], "intensity": [1.0, 2.0]})
    plot = MirrorPlot(
        cache_id="mirror_zoom",
        data=data,
        filters_top={"spectrum": "scan"},
        filters_bottom={"spectrum": "scan"},
        x_column="mz",
        y_column="intensity",
        cache_path=str(temp_cache_dir),
        zoom_identifier="zoom@mirror",
    )
    assert plot._get_component_args()["zoomIdentifier"] == "zoom@mirror"


@pytest.mark.parametrize("value", ["", 3, ["zoom"]])
def test_rejects_other_identifiers(value):
    with pytest.raises(ValueError, match="zoom_identifier"):
        validate_zoom_identifier(value)


def test_none_is_no_identifier():
    assert validate_zoom_identifier(None) is None
    assert zoom_args(None) == {}


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ({}, None),
        ({"x": [400, 900]}, {"x": [400.0, 900.0]}),
        ({"x": [900, 400], "y": [0, 5]}, {"x": [400.0, 900.0], "y": [0.0, 5.0]}),
        ({"xRange": [1, 2], "yRange": [-1, -1]}, {"x": [1.0, 2.0]}),
        ({"xRange": [-1, -1], "yRange": [-1, -1]}, None),
        ({"x": [-3.5, 2.0]}, {"x": [-3.5, 2.0]}),
        ({"x": [1, 1]}, None),
        ({"x": ["a", 2]}, None),
        ({"x": [1, float("inf")]}, None),
        ("zoomed", None),
    ],
)
def test_normalize(value, expected):
    assert normalize_zoom(value) == expected


@pytest.fixture
def points() -> pl.LazyFrame:
    rows = {"rt": [], "mz": [], "intensity": []}
    for i in range(50):
        for j in range(20):
            rows["rt"].append(float(i))
            rows["mz"].append(100.0 + 10 * j)
            rows["intensity"].append(float(1 + i * j))
    return pl.LazyFrame(rows)


def _heatmap(points, cache_dir):
    return Heatmap(
        cache_id="hm_zoom",
        data=points,
        cache_path=str(cache_dir),
        x_column="rt",
        y_column="mz",
        intensity_column="intensity",
        zoom_identifier="zoom@peak_map",
    )


def test_heatmap_reads_the_shared_form(mock_streamlit, temp_cache_dir, points):
    plot = _heatmap(points, temp_cache_dir)
    shared = plot._prepare_vue_data(
        {"zoom@peak_map": {"x": [10.0, 20.0], "y": [150.0, 200.0]}}
    )
    legacy = plot._prepare_vue_data(
        {"zoom@peak_map": {"xRange": [10.0, 20.0], "yRange": [150.0, 200.0]}}
    )
    rt = shared["heatmapData"]["rt"]
    mz = shared["heatmapData"]["mz"]
    assert rt.between(10.0, 20.0).all() and mz.between(150.0, 200.0).all()
    assert len(shared["heatmapData"]) == len(legacy["heatmapData"]) > 0


def test_heatmap_axis_left_out_spans_the_data(mock_streamlit, temp_cache_dir, points):
    plot = _heatmap(points, temp_cache_dir)
    payload = plot._prepare_vue_data({"zoom@peak_map": {"x": [10.0, 12.0]}})
    data = payload["heatmapData"]
    assert data["rt"].between(10.0, 12.0).all()
    # Every m/z of those spectra, not an empty y range
    assert data["mz"].min() == 100.0 and data["mz"].max() == 290.0
