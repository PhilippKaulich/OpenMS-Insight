"""The measure tool of the 2D plots: argument plumbing and cache compatibility.

MirrorPlot has its own tests in test_mirrorplot_contract.py.
"""

import json

import pytest
from component_cases import COMPONENT_CASES, build_kwargs

from openms_insight import (
    DeconvolvedSpectrum,
    Heatmap,
    LinePlot,
    PCAPlot,
    SeriesPlot,
    VolcanoPlot,
)

MEASURE_CLASSES = (
    LinePlot,
    SeriesPlot,
    DeconvolvedSpectrum,
    Heatmap,
    VolcanoPlot,
    PCAPlot,
)
# Components whose x axis is m/z or mass: they match differences to residues
RESIDUE_CLASSES = (LinePlot, DeconvolvedSpectrum)

MEASURE_CASES = [case for case in COMPONENT_CASES if case[0] in MEASURE_CLASSES]
MEASURE_IDS = [case[0].__name__ for case in MEASURE_CASES]
RESIDUE_CASES = [case for case in COMPONENT_CASES if case[0] in RESIDUE_CLASSES]
RESIDUE_IDS = [case[0].__name__ for case in RESIDUE_CASES]
OTHER_CASES = [case for case in COMPONENT_CASES if case[0] not in MEASURE_CLASSES]
OTHER_IDS = [case[0].__name__ for case in OTHER_CASES]
ARGNAMES = "ComponentClass,data_fixture,extra_kwargs,fixture_kwargs"


def test_every_measure_component_is_covered():
    assert {case[0] for case in MEASURE_CASES} == set(MEASURE_CLASSES)


@pytest.fixture
def make(mock_streamlit, temp_cache_dir, request):
    """Build a component of a case, with overrides."""

    def _make(case, cache_id="measure", **overrides):
        ComponentClass, data_fixture, extra_kwargs, fixture_kwargs = case
        kwargs = build_kwargs(request, extra_kwargs, fixture_kwargs)
        kwargs.update(overrides)
        return ComponentClass(
            cache_id=f"{ComponentClass.__name__}_{cache_id}",
            data=request.getfixturevalue(data_fixture),
            cache_path=str(temp_cache_dir),
            **kwargs,
        )

    return _make


def _manifest(component) -> dict:
    with open(component._get_manifest_path()) as f:
        return json.load(f)


@pytest.mark.parametrize("case", MEASURE_CASES, ids=MEASURE_IDS)
def test_measure_on_by_default(make, case):
    args = make(case)._get_component_args()
    assert args["measure"] is True


@pytest.mark.parametrize("case", MEASURE_CASES, ids=MEASURE_IDS)
def test_measure_false_switches_it_off(make, case):
    args = make(case, measure=False)._get_component_args()
    assert args["measure"] is False
    assert "measureTolerance" not in args
    assert "measureResidues" not in args


@pytest.mark.parametrize("case", MEASURE_CASES, ids=MEASURE_IDS)
@pytest.mark.parametrize("value", ["yes", 1, 0, None])
def test_invalid_measure_raises(make, case, value):
    with pytest.raises(ValueError, match="measure must be True or False"):
        make(case, measure=value)


@pytest.mark.parametrize("case", MEASURE_CASES, ids=MEASURE_IDS)
def test_measure_is_not_part_of_the_cache_config(make, case):
    on = make(case, cache_id="on")
    off = make(case, cache_id="off", measure=False)
    assert not any(key.startswith("measure") for key in on._get_cache_config())
    assert on._compute_config_hash() == off._compute_config_hash()
    assert not any(key.startswith("measure") for key in _manifest(on)["config"])


@pytest.mark.parametrize("case", MEASURE_CASES, ids=MEASURE_IDS)
def test_existing_cache_is_reused_whatever_measure(make, case):
    """A cache built before the tool existed (here: with it off) is reused
    as it is when the tool is on by default, and vice versa: no rebuild."""
    first = make(case, cache_id="reuse", measure=False)
    generation = _manifest(first)["cache_generation"]

    default_on = make(case, cache_id="reuse")
    assert _manifest(default_on)["cache_generation"] == generation
    assert default_on._get_component_args()["measure"] is True

    off_again = make(case, cache_id="reuse", measure=False)
    assert _manifest(off_again)["cache_generation"] == generation
    assert off_again._get_component_args()["measure"] is False


@pytest.mark.parametrize("case", MEASURE_CASES, ids=MEASURE_IDS)
def test_measure_applies_when_loading_by_cache_id(make, case, temp_cache_dir):
    built = make(case, cache_id="load")
    ComponentClass = case[0]
    loaded = ComponentClass(
        cache_id=built._cache_id, cache_path=str(temp_cache_dir), measure=False
    )
    assert loaded._get_component_args()["measure"] is False
    loaded = ComponentClass(cache_id=built._cache_id, cache_path=str(temp_cache_dir))
    assert loaded._get_component_args()["measure"] is True


@pytest.mark.parametrize("case", RESIDUE_CASES, ids=RESIDUE_IDS)
def test_residue_options_reach_vue_without_touching_the_cache(make, case):
    plain = make(case, cache_id="plain")
    args = plain._get_component_args()
    assert args["measureTolerance"] == 0.02
    assert "measureResidues" not in args

    tuned = make(
        case,
        cache_id="tuned",
        measure_tolerance=0.005,
        measure_residues={"M(Oxidation)": 147.0354},
    )
    args = tuned._get_component_args()
    assert args["measureTolerance"] == 0.005
    assert args["measureResidues"] == {"M(Oxidation)": 147.0354}
    assert tuned._compute_config_hash() == plain._compute_config_hash()


@pytest.mark.parametrize("case", RESIDUE_CASES, ids=RESIDUE_IDS)
@pytest.mark.parametrize(
    "overrides",
    [
        {"measure_tolerance": -0.1},
        {"measure_tolerance": float("inf")},
        {"measure_tolerance": "0.02"},
        {"measure_tolerance": True},
        {"measure_residues": [("X", 100.0)]},
        {"measure_residues": {"": 100.0}},
        {"measure_residues": {"X": -1.0}},
        {"measure_residues": {"X": "heavy"}},
    ],
)
def test_invalid_residue_options_raise(make, case, overrides):
    with pytest.raises(ValueError, match="measure_"):
        make(case, **overrides)


@pytest.mark.parametrize("case", OTHER_CASES, ids=OTHER_IDS)
def test_components_without_the_tool_send_nothing(make, case):
    """Plot3D (two clicks in 3D do not pick comparable points),
    ClusteredHeatmap (a categorical matrix) and the non-plot components."""
    args = make(case)._get_component_args()
    assert not any(key.startswith("measure") for key in args)


def test_data_path_plot_keeps_its_cache_when_measure_changes(
    mock_streamlit, temp_cache_dir, sample_lineplot_data, tmp_path
):
    """A plot built in a subprocess (data_path) finds its cache again whatever
    the measure options: they never reach the subprocess or the hash."""
    parquet = tmp_path / "peaks.parquet"
    sample_lineplot_data.collect().write_parquet(parquet)
    options = {
        "cache_id": "measure_path",
        "cache_path": str(temp_cache_dir),
        "data_path": str(parquet),
        "x_column": "mass",
        "y_column": "intensity",
        "x_label": "m/z",
    }
    first = LinePlot(**options)
    manifest = first._get_manifest_path()
    before = manifest.stat().st_mtime_ns

    for overrides in (
        {"measure": False},
        {"measure_residues": {"M(Oxidation)": 147.0354}, "measure_tolerance": 0.01},
        {},
    ):
        again = LinePlot(**options, **overrides)
        assert manifest.stat().st_mtime_ns == before
        assert again._get_component_args()["measure"] is overrides.get("measure", True)
