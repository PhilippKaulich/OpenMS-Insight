"""Table `on_row_action`: a button per row hands the row to a handler."""

from __future__ import annotations

import polars as pl

from openms_insight import Table


def _table(cache_dir, cache_id, **kwargs):
    return Table(
        cache_id=cache_id,
        data=pl.LazyFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]}),
        cache_path=str(cache_dir),
        index_field="id",
        pagination=False,
        **kwargs,
    )


def test_no_actions_by_default(mock_streamlit, temp_cache_dir):
    assert "rowActions" not in _table(temp_cache_dir, "plain")._get_component_args()


def test_actions_reach_args_without_their_handlers(mock_streamlit, temp_cache_dir):
    table = _table(temp_cache_dir, "actions")
    table.on_row_action(
        "open", lambda row: True, icon="mdi-puzzle-outline", label="Open"
    )
    table.on_row_action("copy", lambda row: False)

    assert table._get_component_args()["rowActions"] == [
        {"id": "open", "icon": "mdi-puzzle-outline", "label": "Open"},
        {"id": "copy", "icon": "mdi-open-in-new", "label": ""},
    ]


def test_none_removes_the_action(mock_streamlit, temp_cache_dir):
    table = _table(temp_cache_dir, "removed")
    table.on_row_action("open", lambda row: True).on_row_action("open", None)

    assert "rowActions" not in table._get_component_args()


def test_actions_are_not_cached(mock_streamlit, temp_cache_dir):
    _table(temp_cache_dir, "cached").on_row_action("open", lambda row: True)

    reloaded = Table(cache_id="cached", cache_path=str(temp_cache_dir))
    assert "rowActions" not in reloaded._get_component_args()


def test_event_calls_the_handler_with_the_row(mock_streamlit, temp_cache_dir):
    seen = []
    table = _table(temp_cache_dir, "event")
    table.on_row_action("open", lambda row: seen.append(row) or True)

    assert table._handle_event(
        {"type": "row_action", "id": "open", "row": {"id": 2, "name": "b"}}
    )
    assert seen == [{"id": 2, "name": "b"}]


def test_handler_result_decides_the_rerun(mock_streamlit, temp_cache_dir):
    table = _table(temp_cache_dir, "rerun")
    table.on_row_action("open", lambda row: None)

    assert not table._handle_event(
        {"type": "row_action", "id": "open", "row": {"id": 1}}
    )


def test_unknown_action_or_bad_row_is_ignored(mock_streamlit, temp_cache_dir):
    seen = []
    table = _table(temp_cache_dir, "ignored")
    table.on_row_action("open", lambda row: seen.append(row) or True)

    assert not table._handle_event(
        {"type": "row_action", "id": "other", "row": {"id": 1}}
    )
    assert not table._handle_event({"type": "row_action", "id": "open", "row": [1]})
    assert seen == []
