"""Heatmap `hover_column` and `highlight`.

`highlight` rings the points whose column holds an identifier's selected value,
whichever component made the selection. The points come from the full data, so a
point the shown level dropped is still marked, and a filtered-out point is not.
"""

from __future__ import annotations

import polars as pl
import pytest

from openms_insight import Heatmap


@pytest.fixture
def hits() -> pl.LazyFrame:
    n = 30_000
    return pl.LazyFrame(
        {
            "rt": [float(i % 3000) for i in range(n)],
            "mass": [1000.0 + (i * 7919) % 20000 for i in range(n)],
            "score": [float((i * 31) % 997) for i in range(n)],
            "hit_id": list(range(n)),
            "group": [i % 50 for i in range(n)],
            "sample": ["A" if i % 2 else "B" for i in range(n)],
            "label": [f"hit {i}" for i in range(n)],
        }
    )


def _heatmap(data, cache_dir, cache_id, **kwargs):
    return Heatmap(
        cache_id=cache_id,
        data=data,
        cache_path=str(cache_dir),
        x_column="rt",
        y_column="mass",
        intensity_column="score",
        min_points=1000,
        **kwargs,
    )


def test_hover_column_reaches_payload_and_args(mock_streamlit, temp_cache_dir, hits):
    plot = _heatmap(hits, temp_cache_dir, "hover", hover_column="label")

    assert "label" in plot._prepare_vue_data({})["heatmapData"].columns
    zoomed = plot._prepare_vue_data(
        {"heatmap_zoom": {"xRange": [100.0, 200.0], "yRange": [1000.0, 5000.0]}}
    )
    assert "label" in zoomed["heatmapData"].columns
    assert plot._get_component_args()["hoverColumn"] == "label"


def test_no_highlight_configured_sends_nothing(mock_streamlit, temp_cache_dir, hits):
    plot = _heatmap(hits, temp_cache_dir, "plain")

    assert "highlightPoints" not in plot._prepare_vue_data({})
    assert "highlight" not in plot._get_component_args()


def test_selected_point_is_marked_even_when_downsampled_away(
    mock_streamlit, temp_cache_dir, hits
):
    plot = _heatmap(hits, temp_cache_dir, "ring", highlight={"hit": "hit_id"})
    shown = set(plot._prepare_vue_data({})["heatmapData"]["rt"].index)
    assert len(shown) < 30_000

    # A low-scoring hit the smallest level drops
    hit = 997  # score 0
    payload = plot._prepare_vue_data({"hit": hit})

    assert payload["highlightPoints"] == {
        "x": [float(hit % 3000)],
        "y": [1000.0 + (hit * 7919) % 20000],
    }


def test_nothing_selected_marks_nothing(mock_streamlit, temp_cache_dir, hits):
    plot = _heatmap(hits, temp_cache_dir, "ring_none", highlight={"hit": "hit_id"})

    assert plot._prepare_vue_data({"hit": None})["highlightPoints"] == {
        "x": [],
        "y": [],
    }
    assert plot._prepare_vue_data({})["highlightPoints"] == {"x": [], "y": []}


def test_selection_change_changes_hash(mock_streamlit, temp_cache_dir, hits):
    plot = _heatmap(hits, temp_cache_dir, "ring_hash", highlight={"hit": "hit_id"})

    hashes = {plot._prepare_vue_data({"hit": h})["_hash"] for h in (None, 3, 4)}

    assert len(hashes) == 3


def test_group_selection_marks_every_point_of_it(mock_streamlit, temp_cache_dir, hits):
    plot = _heatmap(hits, temp_cache_dir, "ring_group", highlight={"group": "group"})

    payload = plot._prepare_vue_data({"group": 7})

    assert len(payload["highlightPoints"]["x"]) == 30_000 // 50


def test_filtered_out_points_are_not_marked(mock_streamlit, temp_cache_dir, hits):
    plot = _heatmap(
        hits,
        temp_cache_dir,
        "ring_filtered",
        filters={"sample": "sample"},
        highlight={"group": "group"},
    )

    payload = plot._prepare_vue_data({"group": 7, "sample": "A"})

    # Group 7 holds only odd ids, all of sample A; group 8 only sample B
    assert len(payload["highlightPoints"]["x"]) == 600
    assert (
        plot._prepare_vue_data({"group": 8, "sample": "A"})["highlightPoints"]["x"]
        == []
    )


def test_highlight_identifiers_are_state_dependencies(
    mock_streamlit, temp_cache_dir, hits
):
    plot = _heatmap(hits, temp_cache_dir, "ring_deps", highlight={"hit": "hit_id"})

    assert "hit" in plot.get_state_dependencies()
    assert plot._get_component_args()["highlight"] == {"hit": "hit_id"}


def test_config_survives_cache_reload(mock_streamlit, temp_cache_dir, hits):
    _heatmap(
        hits,
        temp_cache_dir,
        "ring_reload",
        hover_column="label",
        highlight={"hit": "hit_id"},
    )

    reloaded = Heatmap(cache_id="ring_reload", cache_path=str(temp_cache_dir))

    assert reloaded._get_component_args()["hoverColumn"] == "label"
    assert reloaded._prepare_vue_data({"hit": 5})["highlightPoints"]["x"] == [5.0]


def test_on_select_reaches_args_and_survives_reload(
    mock_streamlit, temp_cache_dir, hits
):
    _heatmap(
        hits,
        temp_cache_dir,
        "on_select",
        interactivity={"hit": "hit_id"},
        on_select={"peak": None},
    )

    reloaded = Heatmap(cache_id="on_select", cache_path=str(temp_cache_dir))

    assert reloaded._get_component_args()["onSelect"] == {"peak": None}
