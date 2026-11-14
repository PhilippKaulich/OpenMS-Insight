"""SeriesPlot views (view_column) and the "Top n" menu (top_choices)."""

import polars as pl
import pytest

from openms_insight import SeriesPlot


@pytest.fixture
def terms():
    return pl.DataFrame(
        {
            "term": ["a", "b", "c", "d", "e"],
            "score": [5.0, 4.0, 3.0, 2.0, 1.0],
            "category": ["BP", "BP", "BP", "MF", "CC"],
        }
    ).lazy()


def _plot(tmp_path, terms, **kwargs):
    return SeriesPlot(
        cache_id="go",
        cache_path=str(tmp_path),
        data=terms,
        x_column="term",
        y_column="score",
        mode="bars",
        orientation="h",
        **kwargs,
    )


def test_view_and_top_args(tmp_path, terms):
    plot = _plot(
        tmp_path,
        terms,
        view_column="category",
        view_names={"BP": "Biological process", "MF": "Molecular function"},
        view_identifier="go_category",
        view_default="MF",
        top_choices=[1, 2, 5],
        bar_height=24,
        title="{view}: top terms",
    )
    args = plot._get_component_args()
    assert args["viewColumn"] == "category"
    assert args["viewNames"] == [
        ["BP", "Biological process"],
        ["MF", "Molecular function"],
    ]
    assert args["viewIdentifier"] == "go_category"
    assert args["viewDefault"] == "MF"
    assert args["topChoices"] == [1, 2, 5]
    assert args["topDefault"] == 2
    assert args["barHeight"] == 24
    # The view column reaches the browser with the points
    data = plot._prepare_vue_data({})["plotData"]
    assert list(data["category"]) == ["BP", "BP", "BP", "MF", "CC"]


def test_render_time_options_stay_out_of_the_cache(tmp_path, terms):
    config = _plot(
        tmp_path, terms, view_column="category", view_identifier="x", bar_height=20
    )._get_cache_config()
    assert "view_identifier" not in config and "bar_height" not in config
    assert config["view_column"] == "category"
    # Without views or top choices the configuration (and its hash) is unchanged
    plain = _plot(tmp_path, terms)._get_cache_config()
    assert "view_column" not in plain and "top_choices" not in plain


def test_cache_restores_views(tmp_path, terms):
    _plot(tmp_path, terms, view_column="category", top_choices=[2, 3], top_default=3)
    restored = SeriesPlot(cache_id="go", cache_path=str(tmp_path))
    args = restored._get_component_args()
    assert args["viewColumn"] == "category"
    assert args["topChoices"] == [2, 3] and args["topDefault"] == 3


@pytest.mark.parametrize(
    "kwargs",
    [
        {"top_choices": []},
        {"top_choices": [0, 5]},
        {"top_choices": [5, 10], "top_default": 7},
        {"top_default": 5},
        {"view_identifier": "go_category"},
        {"view_column": "missing"},
        {"bar_height": 0},
    ],
)
def test_invalid_options(tmp_path, terms, kwargs):
    with pytest.raises(ValueError):
        _plot(tmp_path, terms, **kwargs)
