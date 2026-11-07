"""Your own peak labels on the spectrum views: argument plumbing and caches.

The labels themselves live in the browser (usePeakLabels.ts); Python only
switches the "Label peaks" button on or off.
"""

import json

import pytest
from component_cases import COMPONENT_CASES, build_kwargs

from openms_insight import LinePlot, MirrorPlot

# MirrorPlot is not in COMPONENT_CASES; it is tested on its own below
LABEL_CLASSES = (LinePlot,)
LABEL_CASES = [case for case in COMPONENT_CASES if case[0] in LABEL_CLASSES]
LABEL_IDS = [case[0].__name__ for case in LABEL_CASES]
OTHER_CASES = [case for case in COMPONENT_CASES if case[0] not in LABEL_CLASSES]
OTHER_IDS = [case[0].__name__ for case in OTHER_CASES]


@pytest.fixture
def make(mock_streamlit, temp_cache_dir, request):
    def _make(case, cache_id="labels", **overrides):
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


def test_every_label_component_is_covered():
    assert {case[0] for case in LABEL_CASES} == set(LABEL_CLASSES)


@pytest.mark.parametrize("case", LABEL_CASES, ids=LABEL_IDS)
def test_peak_labels_on_by_default(make, case):
    assert make(case)._get_component_args()["peakLabels"] is True


@pytest.mark.parametrize("case", LABEL_CASES, ids=LABEL_IDS)
def test_peak_labels_false_switches_it_off(make, case):
    assert make(case, peak_labels=False)._get_component_args()["peakLabels"] is False


@pytest.mark.parametrize("case", LABEL_CASES, ids=LABEL_IDS)
@pytest.mark.parametrize("value", ["yes", 1, 0, None])
def test_invalid_peak_labels_raises(make, case, value):
    with pytest.raises(ValueError, match="peak_labels must be True or False"):
        make(case, peak_labels=value)


@pytest.mark.parametrize("case", LABEL_CASES, ids=LABEL_IDS)
def test_peak_labels_do_not_touch_the_cache(make, case):
    on = make(case, cache_id="reuse")
    with open(on._get_manifest_path()) as f:
        manifest = json.load(f)
    off = make(case, cache_id="reuse", peak_labels=False)
    with open(off._get_manifest_path()) as f:
        assert json.load(f)["cache_generation"] == manifest["cache_generation"]
    assert "peak_labels" not in on._get_cache_config()
    assert on._compute_config_hash() == off._compute_config_hash()


@pytest.mark.parametrize("case", OTHER_CASES, ids=OTHER_IDS)
def test_other_components_send_nothing(make, case):
    assert "peakLabels" not in make(case)._get_component_args()


def _mirror(temp_cache_dir, data, **overrides):
    options = {
        "cache_id": "labels",
        "data": data,
        "cache_path": str(temp_cache_dir),
        "filters_top": {"spectrum_top": "scan_id"},
        "filters_bottom": {"spectrum_bottom": "scan_id"},
        "interactivity": {"selected_peak": "peak_id"},
        "x_column": "mass",
        "y_column": "intensity",
    }
    options.update(overrides)
    return MirrorPlot(**options)


def test_mirror_plot_peak_labels(mock_streamlit, temp_cache_dir, sample_lineplot_data):
    on = _mirror(temp_cache_dir, sample_lineplot_data, cache_id="on")
    assert on._get_component_args()["peakLabels"] is True
    off = _mirror(
        temp_cache_dir, sample_lineplot_data, cache_id="off", peak_labels=False
    )
    assert off._get_component_args()["peakLabels"] is False
    assert "peak_labels" not in on._get_cache_config()
    assert on._compute_config_hash() == off._compute_config_hash()
    with pytest.raises(ValueError, match="peak_labels must be True or False"):
        _mirror(temp_cache_dir, sample_lineplot_data, cache_id="bad", peak_labels="on")


def test_mirror_plot_peak_labels_when_loading_by_cache_id(
    mock_streamlit, temp_cache_dir, sample_lineplot_data
):
    _mirror(temp_cache_dir, sample_lineplot_data, cache_id="load")
    loaded = MirrorPlot(
        cache_id="load", cache_path=str(temp_cache_dir), peak_labels=False
    )
    assert loaded._get_component_args()["peakLabels"] is False
