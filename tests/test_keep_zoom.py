"""keep_zoom on the spectrum plots: a render-time option passed to Vue, not part of the cache."""

import json

import polars as pl
import pytest

from openms_insight import DeconvolvedSpectrum, LinePlot, MirrorPlot


@pytest.fixture
def spectra() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "scan": [1, 1, 2, 2],
            "mz": [100.0, 200.0, 150.0, 250.0],
            "intensity": [10.0, 20.0, 30.0, 40.0],
        }
    )


def _lineplot(request, cache_dir, cache_id, **kwargs):
    return LinePlot(
        cache_id=cache_id,
        data=request.getfixturevalue("spectra"),
        filters={"spectrum": "scan"},
        x_column="mz",
        y_column="intensity",
        cache_path=str(cache_dir),
        **kwargs,
    )


def _mirror(request, cache_dir, cache_id, **kwargs):
    return MirrorPlot(
        cache_id=cache_id,
        data=request.getfixturevalue("spectra"),
        filters_top={"spectrum": "scan"},
        filters_bottom={"spectrum": "scan"},
        x_column="mz",
        y_column="intensity",
        cache_path=str(cache_dir),
        **kwargs,
    )


def _deconvolved(request, cache_dir, cache_id, **kwargs):
    return DeconvolvedSpectrum(
        cache_id=cache_id,
        data=request.getfixturevalue("sample_deconvolved_spectra"),
        filters={"scan": "scan_idx"},
        view="annotated",
        cache_path=str(cache_dir),
        **kwargs,
    )


BUILDERS = pytest.mark.parametrize(
    "build",
    [_lineplot, _mirror, _deconvolved],
    ids=["LinePlot", "MirrorPlot", "DeconvolvedSpectrum"],
)


@BUILDERS
def test_off_by_default(mock_streamlit, temp_cache_dir, request, build):
    args = build(request, temp_cache_dir, "kz")._get_component_args()
    assert args["keepZoom"] is False


@BUILDERS
def test_true_is_passed_to_vue(mock_streamlit, temp_cache_dir, request, build):
    args = build(request, temp_cache_dir, "kz", keep_zoom=True)._get_component_args()
    assert args["keepZoom"] is True


@BUILDERS
@pytest.mark.parametrize("value", [1, "yes", None])
def test_rejects_non_bool(mock_streamlit, temp_cache_dir, request, build, value):
    with pytest.raises(ValueError, match="keep_zoom"):
        build(request, temp_cache_dir, "kz", keep_zoom=value)


@BUILDERS
def test_not_part_of_the_cache(mock_streamlit, temp_cache_dir, request, build):
    off = build(request, temp_cache_dir, "same")
    with open(off._get_manifest_path()) as f:
        before = json.load(f)
    on = build(request, temp_cache_dir, "same", keep_zoom=True)
    with open(on._get_manifest_path()) as f:
        after = json.load(f)
    assert before == after
    assert "keep_zoom" not in json.dumps(after)
