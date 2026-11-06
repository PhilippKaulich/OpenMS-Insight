"""The image download format: package default, per-component override, cache.

Every component with an image download sends ``imageFormat`` to its view. The
format is a render-time option: it is read when the component is drawn and is
never part of the cache configuration.
"""

import json

import pytest
from component_cases import COMPONENT_CASES, build_kwargs

import openms_insight
from openms_insight import (
    IMAGE_FORMATS,
    MirrorPlot,
    ProteinStructureView,
    SequenceView,
    Table,
    get_image_format,
    set_image_format,
)
from openms_insight.core import image_format as image_format_module

# Every component of COMPONENT_CASES but Table (which downloads CSV), plus
# the ones that need their own arguments.
IMAGE_CASES = [case for case in COMPONENT_CASES if case[0] is not Table]
IMAGE_CASES += [
    (
        MirrorPlot,
        "sample_lineplot_data",
        {
            "filters_top": {"spectrum_top": "scan_id"},
            "filters_bottom": {"spectrum_bottom": "scan_id"},
            "x_column": "mass",
            "y_column": "intensity",
        },
        {},
    ),
    (
        ProteinStructureView,
        "sample_protein_sequence_data",
        {"filters": {"protein": "hit_index"}, "aa_identifier": "aa"},
        {},
    ),
    (
        SequenceView,
        "sample_sequence_data",
        {"filters": {"identification": "scan_id"}},
        {"peaks_data": "sample_peaks_data"},
    ),
]
IMAGE_IDS = [case[0].__name__ for case in IMAGE_CASES]


@pytest.fixture(autouse=True)
def reset_image_format():
    """Each test starts from, and leaves, the process default 'svg'."""
    image_format_module._process_default = "svg"
    yield
    image_format_module._process_default = "svg"


@pytest.fixture
def make(mock_streamlit, temp_cache_dir, request):
    """Build a component of a case, with overrides."""

    def _make(case, cache_id="image", **overrides):
        ComponentClass, data_fixture, extra_kwargs, fixture_kwargs = case
        kwargs = build_kwargs(request, extra_kwargs, fixture_kwargs)
        kwargs.update(overrides)
        data_argument = "sequence_data" if ComponentClass is SequenceView else "data"
        kwargs[data_argument] = request.getfixturevalue(data_fixture)
        return ComponentClass(
            cache_id=f"{ComponentClass.__name__}_{cache_id}",
            cache_path=str(temp_cache_dir),
            **kwargs,
        )

    return _make


def test_every_component_with_an_image_download_is_covered():
    """All exported components but Table have an image download."""
    components = {
        value
        for name in openms_insight.__all__
        if isinstance(value := getattr(openms_insight, name), type)
        and name not in ("BaseComponent", "StateManager", "CacheMissError")
        and hasattr(value, "_get_component_args")
    }
    assert {case[0] for case in IMAGE_CASES} == components - {Table}


def test_default_is_svg():
    assert get_image_format() == "svg"
    assert IMAGE_FORMATS == ("svg", "png", "jpeg", "webp")


@pytest.mark.parametrize("case", IMAGE_CASES, ids=IMAGE_IDS)
def test_components_send_svg_by_default(make, case):
    assert make(case)._get_component_args()["imageFormat"] == "svg"


@pytest.mark.parametrize("case", IMAGE_CASES, ids=IMAGE_IDS)
@pytest.mark.parametrize("fmt", ["png", "jpeg", "webp", "svg"])
def test_set_image_format_changes_what_every_component_sends(make, case, fmt):
    component = make(case)
    set_image_format(fmt)
    # Read at render time: a component built before the call follows it
    assert component._get_component_args()["imageFormat"] == fmt


@pytest.mark.parametrize("case", IMAGE_CASES, ids=IMAGE_IDS)
def test_component_override_wins(make, case):
    component = make(case, image_format="jpeg")
    assert component._get_component_args()["imageFormat"] == "jpeg"
    set_image_format("png")
    assert component._get_component_args()["imageFormat"] == "jpeg"


@pytest.mark.parametrize("case", IMAGE_CASES, ids=IMAGE_IDS)
@pytest.mark.parametrize("value", ["pdf", "jpg", "", 1, True])
def test_invalid_component_format_raises(make, case, value):
    with pytest.raises(ValueError, match="image_format must be one of"):
        make(case, image_format=value)


@pytest.mark.parametrize("value", ["pdf", "jpg", "", None, 1, ["png"]])
def test_invalid_package_format_raises(value):
    with pytest.raises(ValueError, match="image_format must be one of"):
        set_image_format(value)
    assert get_image_format() == "svg"


def test_format_is_case_insensitive():
    set_image_format("PNG")
    assert get_image_format() == "png"


def _manifest_path(component):
    """SequenceView keeps its own cache layout."""
    name = (
        ".cache_config.json" if isinstance(component, SequenceView) else "manifest.json"
    )
    return component._cache_dir / name


def _config_and_hash(component) -> tuple[dict, str]:
    if isinstance(component, SequenceView):
        return component._get_cache_config(), component._compute_input_config_hash()
    return component._get_cache_config(), component._compute_config_hash()


@pytest.mark.parametrize("case", IMAGE_CASES, ids=IMAGE_IDS)
def test_format_is_not_part_of_the_cache_config(make, case, temp_cache_dir):
    plain = make(case, cache_id="plain")
    png = make(case, cache_id="png", image_format="png")
    plain_config, plain_hash = _config_and_hash(plain)
    png_config, png_hash = _config_and_hash(png)
    assert "image_format" not in plain_config
    assert plain_config == png_config
    assert plain_hash == png_hash
    set_image_format("webp")
    assert _config_and_hash(plain) == (plain_config, plain_hash)

    with open(_manifest_path(png)) as f:
        manifest = json.load(f)
    assert "image_format" not in json.dumps(manifest)


@pytest.mark.parametrize("case", IMAGE_CASES, ids=IMAGE_IDS)
def test_existing_cache_is_reused_whatever_format(make, case, temp_cache_dir):
    first = make(case, cache_id="reuse")
    manifest = _manifest_path(first)
    before = manifest.stat().st_mtime_ns
    for overrides in ({"image_format": "png"}, {"image_format": "webp"}, {}):
        again = make(case, cache_id="reuse", **overrides)
        assert manifest.stat().st_mtime_ns == before
        expected = overrides.get("image_format", "svg")
        assert again._get_component_args()["imageFormat"] == expected


@pytest.mark.parametrize("case", IMAGE_CASES, ids=IMAGE_IDS)
def test_format_applies_when_loading_by_cache_id(make, case, temp_cache_dir):
    built = make(case, cache_id="load")
    ComponentClass = case[0]
    loaded = ComponentClass(
        cache_id=built._cache_id, cache_path=str(temp_cache_dir), image_format="png"
    )
    assert loaded._get_component_args()["imageFormat"] == "png"
    loaded = ComponentClass(cache_id=built._cache_id, cache_path=str(temp_cache_dir))
    assert loaded._get_component_args()["imageFormat"] == "svg"


def test_plot3d_export_format_png_still_downloads_png(make):
    case = next(case for case in IMAGE_CASES if case[0].__name__ == "Plot3D")
    legacy = make(case, cache_id="legacy", export_format="png")
    args = legacy._get_component_args()
    assert args["imageFormat"] == "png"
    assert "exportFormat" not in args
    assert (
        make(
            case, cache_id="both", export_format="png", image_format="webp"
        )._get_component_args()["imageFormat"]
        == "webp"
    )


def test_kept_per_streamlit_session(monkeypatch):
    """In a Streamlit session the default lives in that session's state."""
    sessions = {"a": {}, "b": {}}
    current = {"name": "a"}
    monkeypatch.setattr(
        image_format_module, "_session_state", lambda: sessions[current["name"]]
    )
    set_image_format("png")
    assert get_image_format() == "png"
    current["name"] = "b"
    assert get_image_format() == "svg"
    set_image_format("jpeg")
    current["name"] = "a"
    assert get_image_format() == "png"
    # The process default (scripts, tests) is untouched
    monkeypatch.setattr(image_format_module, "_session_state", lambda: None)
    assert get_image_format() == "svg"
