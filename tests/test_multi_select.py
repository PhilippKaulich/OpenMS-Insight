"""`multi_select`: selecting several entries at once.

The identifier holds the sorted distinct values of the column over the
selected entries (None when nothing is selected). VolcanoPlot and the Table's
check boxes compute it in the browser; Heatmap boxes and lassos, and the
Table's "all rows" box of a paginated table, are applied in Python from the
full data.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from openms_insight import ClusteredHeatmap, Heatmap, StateManager, Table, VolcanoPlot
from openms_insight.core.multi_select import (
    combine,
    normalize_multi_select,
    region_mask,
    selection_values,
    values_in_region,
)
from openms_insight.core.state import _render_state_manager

# -- helpers -----------------------------------------------------------------


def test_selection_values_sorted_distinct_or_none():
    assert selection_values(["b", "a", None, "b"]) == ["a", "b"]
    assert selection_values([np.int64(3), 1, 3]) == [1, 3]
    assert selection_values([]) is None
    assert selection_values([None]) is None


def test_combine_modes():
    assert combine(["a", "b"], ["c"], "add") == ["a", "b", "c"]
    assert combine(["a", "b"], ["b"], "remove") == ["a"]
    assert combine(["a"], ["a"], "remove") is None
    assert combine(["a", "b"], ["c"], "replace") == ["c"]
    assert combine(None, None, "replace") is None


def test_normalize_rejects_pagination_identifier():
    assert normalize_multi_select(None) == {}
    with pytest.raises(ValueError):
        normalize_multi_select({"x_page": "col"})
    with pytest.raises(ValueError):
        normalize_multi_select(["col"])


def test_region_mask_box_and_lasso():
    x = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([0.0, 1.0, 2.0, 3.0])
    box = {"type": "box", "x": [2.5, 0.5], "y": [0.5, 2.5]}
    assert region_mask(x, y, box).tolist() == [False, True, True, False]
    # A triangle containing (1, 1) only
    lasso = {"type": "lasso", "x": [0.5, 2.0, 0.5], "y": [0.5, 1.0, 1.8]}
    assert region_mask(x, y, lasso).tolist() == [False, True, False, False]
    assert region_mask(x, y, {"type": "lasso", "x": [1], "y": [1]}).sum() == 0


def test_values_in_region():
    frame = pl.DataFrame(
        {"x": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 2.0], "acc": ["A", "B", "B"]}
    )
    region = {"type": "box", "x": [0.5, 2.5], "y": [0.5, 2.5]}
    assert values_in_region(frame, "x", "y", "acc", region) == ["B"]
    assert (
        values_in_region(
            frame.lazy(), "x", "y", "acc", {"type": "box", "x": [5, 6], "y": [5, 6]}
        )
        is None
    )


# -- VolcanoPlot ---------------------------------------------------------------


@pytest.fixture
def volcano_data() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "id": [1, 2, 3, 4],
            "log2FC": [2.0, -2.0, 0.1, 3.0],
            "padj": [0.001, 0.01, 0.5, 0.2],
            "name": ["up", "down", "ns", "big but ns"],
            "accession": ["P1", "P2", "P3", "P4"],
        }
    )


def test_volcano_carries_multi_select_column(
    mock_streamlit, temp_cache_dir, volcano_data
):
    plot = VolcanoPlot(
        cache_id="volcano_ms",
        data=volcano_data,
        cache_path=str(temp_cache_dir),
        log2fc_column="log2FC",
        pvalue_column="padj",
        label_column="name",
        multi_select={"proteins": "accession"},
        preset_labels={"up": "Higher in B"},
    )
    payload = plot._prepare_vue_data({})
    assert "accession" in payload["volcanoData"].columns
    args = plot._get_component_args()
    assert args["multiSelect"] == {"proteins": "accession"}
    assert args["presetLabels"] == {"up": "Higher in B"}

    # Restored from the cache
    again = VolcanoPlot(cache_id="volcano_ms", cache_path=str(temp_cache_dir))
    assert again._get_component_args()["multiSelect"] == {"proteins": "accession"}
    assert "multi_select" not in again._config


def test_volcano_without_multi_select_keeps_its_cache_config(
    mock_streamlit, temp_cache_dir, volcano_data
):
    plot = VolcanoPlot(
        cache_id="volcano_plain",
        data=volcano_data,
        cache_path=str(temp_cache_dir),
        log2fc_column="log2FC",
        pvalue_column="padj",
    )
    assert "multi_select" not in plot._get_cache_config()
    assert "multiSelect" not in plot._get_component_args()


# -- Heatmap -------------------------------------------------------------------


@pytest.fixture
def hits() -> pl.LazyFrame:
    n = 30_000
    return pl.LazyFrame(
        {
            "rt": [float(i % 3000) for i in range(n)],
            "mass": [1000.0 + (i * 7919) % 20000 for i in range(n)],
            "score": [float((i * 31) % 997) for i in range(n)],
            "accession": [f"P{i % 400:04d}" for i in range(n)],
            "sample": ["A" if i % 2 else "B" for i in range(n)],
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


def _render_with(state_manager, fn):
    token = _render_state_manager.set(state_manager)
    try:
        return fn()
    finally:
        _render_state_manager.reset(token)


def test_heatmap_box_selects_from_full_data(mock_streamlit, temp_cache_dir, hits):
    plot = _heatmap(
        hits, temp_cache_dir, "ms_box", multi_select={"proteins": "accession"}
    )
    state_manager = StateManager()
    region = {"type": "box", "x": [0.0, 10.0], "y": [0.0, 1e9]}

    changed = _render_with(
        state_manager,
        lambda: plot._handle_event(
            {"type": "multi_select", "region": region, "mode": "replace", "nonce": "1"}
        ),
    )

    full = hits.filter(pl.col("rt") <= 10.0).collect()
    expected = sorted(full["accession"].unique().to_list())
    assert changed
    assert state_manager.get_selection("proteins") == expected
    # More than the shown level holds: the whole data is searched
    shown = plot._prepare_vue_data({})["heatmapData"]
    assert len(shown[shown["rt"] <= 10.0]) < len(full)

    # Every point of the selected proteins is marked
    marks = plot._prepare_vue_data(state_manager.get_all_selections())[
        "multiSelectPoints"
    ]
    assert (
        len(marks["x"])
        == hits.filter(pl.col("accession").is_in(expected)).collect().height
    )


def test_heatmap_shift_adds_and_alt_removes(mock_streamlit, temp_cache_dir, hits):
    plot = _heatmap(
        hits, temp_cache_dir, "ms_modes", multi_select={"proteins": "accession"}
    )
    state_manager = StateManager()
    state_manager.set_selection("proteins", ["P9999"])
    first = {"type": "box", "x": [0.0, 0.5], "y": [0.0, 1e9]}  # rt 0 only

    _render_with(
        state_manager,
        lambda: plot._handle_event(
            {"type": "multi_select", "region": first, "mode": "add", "nonce": "1"}
        ),
    )
    at_zero = sorted(
        hits.filter(pl.col("rt") == 0.0).collect()["accession"].unique().to_list()
    )
    assert state_manager.get_selection("proteins") == sorted(at_zero + ["P9999"])

    _render_with(
        state_manager,
        lambda: plot._handle_event(
            {"type": "multi_select", "region": first, "mode": "remove", "nonce": "2"}
        ),
    )
    assert state_manager.get_selection("proteins") == ["P9999"]

    _render_with(
        state_manager,
        lambda: plot._handle_event(
            {"type": "multi_select", "clear": True, "nonce": "3"}
        ),
    )
    assert state_manager.get_selection("proteins") is None


def test_heatmap_selection_respects_filters(mock_streamlit, temp_cache_dir, hits):
    plot = _heatmap(
        hits,
        temp_cache_dir,
        "ms_filtered",
        filters={"sample": "sample"},
        multi_select={"proteins": "accession"},
    )
    state_manager = StateManager()
    state_manager.set_selection("sample", "A")
    region = {"type": "box", "x": [0.0, 3.0], "y": [0.0, 1e9]}
    _render_with(
        state_manager,
        lambda: plot._handle_event(
            {"type": "multi_select", "region": region, "nonce": "1"}
        ),
    )
    expected = sorted(
        hits.filter((pl.col("rt") <= 3.0) & (pl.col("sample") == "A"))
        .collect()["accession"]
        .unique()
        .to_list()
    )
    assert state_manager.get_selection("proteins") == expected


def test_heatmap_ignores_other_events(mock_streamlit, temp_cache_dir, hits):
    plain = _heatmap(hits, temp_cache_dir, "ms_plain")
    assert plain._handle_event({"type": "multi_select", "region": {}}) is False
    assert "multiSelectPoints" not in plain._prepare_vue_data({})
    assert "multiSelect" not in plain._get_component_args()


def test_heatmap_multi_select_is_a_state_dependency(
    mock_streamlit, temp_cache_dir, hits
):
    plot = _heatmap(
        hits, temp_cache_dir, "ms_deps", multi_select={"proteins": "accession"}
    )
    assert "proteins" in plot.get_state_dependencies()
    again = Heatmap(cache_id="ms_deps", cache_path=str(temp_cache_dir))
    assert again._get_component_args()["multiSelect"] == {"proteins": "accession"}


# -- Table ---------------------------------------------------------------------


@pytest.fixture
def proteins() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "id": list(range(10)),
            "accession": [f"P{i}" for i in range(10)],
            "score": [float(i) for i in range(10)],
            "group": ["a" if i < 5 else "b" for i in range(10)],
        }
    )


def test_table_sends_multi_select_column(mock_streamlit, temp_cache_dir, proteins):
    table = Table(
        cache_id="tbl_ms",
        data=proteins,
        cache_path=str(temp_cache_dir),
        index_field="id",
        column_definitions=[{"field": "score", "title": "Score"}],
        multi_select={"proteins": "accession"},
    )
    assert table._get_component_args()["multiSelect"] == {"proteins": "accession"}
    assert "accession" in table._get_columns_to_select()
    again = Table(cache_id="tbl_ms", cache_path=str(temp_cache_dir))
    assert again._get_component_args()["multiSelect"] == {"proteins": "accession"}
    assert "multi_select" not in again._get_component_args()


def test_table_select_all_rows_passing_filters(
    mock_streamlit, temp_cache_dir, proteins
):
    table = Table(
        cache_id="tbl_all",
        data=proteins,
        cache_path=str(temp_cache_dir),
        index_field="id",
        filters={"group": "group"},
        multi_select={"proteins": "accession"},
    )
    state_manager = StateManager()
    state_manager.set_selection("group", "b")
    state_manager.set_selection("proteins", ["P0"])

    _render_with(
        state_manager,
        lambda: table._handle_event({"type": "multi_select_all", "mode": "add"}),
    )
    assert state_manager.get_selection("proteins") == [
        "P0",
        "P5",
        "P6",
        "P7",
        "P8",
        "P9",
    ]

    _render_with(
        state_manager,
        lambda: table._handle_event({"type": "multi_select_all", "mode": "remove"}),
    )
    assert state_manager.get_selection("proteins") == ["P0"]


# -- ClusteredHeatmap ----------------------------------------------------------


def test_clustered_heatmap_multi_select_rows(mock_streamlit, temp_cache_dir):
    data = pl.LazyFrame(
        {"Proteoform": ["a", "b", "c"], "s1": [1.0, 2.0, 3.0], "s2": [3.0, 1.0, 2.0]}
    )
    plot = ClusteredHeatmap(
        cache_id="ch_ms",
        data=data,
        id_col="Proteoform",
        cache_path=str(temp_cache_dir),
        row_cluster=False,
        col_cluster=False,
        multi_select={"forms": "Proteoform"},
    )
    assert plot._get_component_args()["multiSelect"] == {"forms": "Proteoform"}
    again = ClusteredHeatmap(cache_id="ch_ms", cache_path=str(temp_cache_dir))
    assert again._get_component_args()["multiSelect"] == {"forms": "Proteoform"}
    with pytest.raises(ValueError):
        ClusteredHeatmap(
            cache_id="ch_bad",
            data=data,
            id_col="Proteoform",
            cache_path=str(temp_cache_dir),
            multi_select={"forms": "s1"},
        )


# -- A multi-selection as a filter ----------------------------------------------


def test_filters_accept_a_multi_selection(mock_streamlit, temp_cache_dir, proteins):
    from openms_insight.preprocessing.filtering import filter_and_collect_cached

    frame, _ = filter_and_collect_cached(
        proteins, {"proteins": "accession"}, {"proteins": ["P2", "P7"]}
    )
    assert frame["accession"].tolist() == ["P2", "P7"]
    # Whole floats from the browser match an integer column
    frame, _ = filter_and_collect_cached(proteins, {"ids": "id"}, {"ids": [1.0, 3.0]})
    assert frame["id"].tolist() == [1, 3]
    frame, _ = filter_and_collect_cached(
        proteins, {"proteins": "accession"}, {"proteins": None}
    )
    assert len(frame) == 0


def test_table_filtered_by_a_multi_selection(mock_streamlit, temp_cache_dir, proteins):
    table = Table(
        cache_id="tbl_filtered_ms",
        data=proteins,
        cache_path=str(temp_cache_dir),
        index_field="id",
        filters={"proteins": "accession"},
    )
    payload = table._prepare_vue_data({"proteins": ["P1", "P4", "P9"]})
    assert sorted(payload["tableData"]["accession"].tolist()) == ["P1", "P4", "P9"]


def test_heatmap_filtered_by_a_multi_selection(mock_streamlit, temp_cache_dir, hits):
    plot = _heatmap(
        hits, temp_cache_dir, "ms_filter_set", filters={"proteins": "accession"}
    )
    shown = plot._prepare_vue_data({"proteins": ["P0001", "P0002"]})["heatmapData"]
    expected = hits.filter(pl.col("accession").is_in(["P0001", "P0002"])).collect()
    assert 0 < len(shown) <= expected.height
    assert set(zip(shown["rt"], shown["mass"], strict=True)) <= set(
        zip(expected["rt"], expected["mass"], strict=True)
    )


def test_volcano_selection_presets_are_optional(
    mock_streamlit, temp_cache_dir, volcano_data
):
    plain = VolcanoPlot(
        cache_id="volcano_no_presets",
        data=volcano_data,
        cache_path=str(temp_cache_dir),
        log2fc_column="log2FC",
        pvalue_column="padj",
        multi_select={"proteins": "accession"},
    )
    assert "selectionPresets" not in plain._get_component_args()
    with_presets = VolcanoPlot(
        cache_id="volcano_presets",
        data=volcano_data,
        cache_path=str(temp_cache_dir),
        log2fc_column="log2FC",
        pvalue_column="padj",
        multi_select={"proteins": "accession"},
        selection_presets=True,
    )
    assert with_presets._get_component_args()["selectionPresets"] is True
    again = VolcanoPlot(cache_id="volcano_presets", cache_path=str(temp_cache_dir))
    assert again._get_component_args()["selectionPresets"] is True
