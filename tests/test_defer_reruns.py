"""Tests for defer_reruns: components rendered inside it rerun the script once,
after the last of them, instead of each rerunning it as soon as it needs to."""

from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from openms_insight import StateManager, Table, defer_reruns
from openms_insight.rendering.bridge import render_component


class Rerun(Exception):
    """Stands in for Streamlit's RerunException."""


@pytest.fixture
def vue():
    return MagicMock(return_value=None)


@pytest.fixture
def rerun(mock_streamlit, vue):
    rerun = MagicMock(side_effect=Rerun)
    with (
        patch("openms_insight.rendering.bridge.st.session_state", mock_streamlit),
        patch("openms_insight.rendering.bridge.st.rerun", rerun),
        patch(
            "openms_insight.rendering.bridge.get_vue_component_function",
            return_value=vue,
        ),
    ):
        yield rerun


def _tables(temp_cache_dir):
    data = pl.LazyFrame({"id": [0, 1, 2], "scan": [1, 1, 2]})
    common = {"data": data, "cache_path": str(temp_cache_dir), "index_field": "id"}
    return [
        Table(cache_id="scans", interactivity={"scan": "scan"}, **common),
        Table(cache_id="rows", filters={"scan": "scan"}, **common),
    ]


def test_each_component_reruns_without_defer(rerun, temp_cache_dir):
    state = StateManager(session_key="no_defer")
    first, _ = _tables(temp_cache_dir)
    # A first render has no payload cached yet: the component reruns at once
    with pytest.raises(Rerun):
        render_component(first, state, key="scans")
    assert rerun.call_count == 1


def test_one_rerun_after_all_components(rerun, vue, temp_cache_dir):
    state = StateManager(session_key="defer")
    first, second = _tables(temp_cache_dir)
    rendered = []
    with pytest.raises(Rerun):
        with defer_reruns():
            render_component(first, state, key="scans")
            rendered.append("scans")
            render_component(second, state, key="rows")
            rendered.append("rows")
    # Both rendered (the second with the selection the first set), then one rerun
    assert rendered == ["scans", "rows"]
    assert state.get_selection("scan") == 1
    assert rerun.call_count == 1
    # The second table got the rows of the scan the first one selected in the
    # same run, not only after the rerun
    rows_call = vue.call_args_list[1].kwargs
    assert rows_call["key"] == "rows"
    assert rows_call["dataChanged"] is True
    assert list(rows_call["tableData"]["scan"]) == [1, 1]

    # Next run: every payload is cached, nothing asks for a rerun
    with defer_reruns():
        render_component(first, state, key="scans")
        render_component(second, state, key="rows")
    assert rerun.call_count == 1


def test_no_rerun_when_the_block_raises(rerun):
    with pytest.raises(ValueError):
        with defer_reruns():
            from openms_insight.rendering.bridge import _deferred_rerun

            _deferred_rerun.get()[0] = True
            raise ValueError
    rerun.assert_not_called()


def test_data_request_resends_in_a_rerun(rerun, vue, temp_cache_dir):
    """A view that missed its data asks for it; the data goes out with the
    next render, so the bridge reruns instead of waiting for another event."""
    state = StateManager(session_key="request")
    first, _ = _tables(temp_cache_dir)
    with pytest.raises(Rerun):
        render_component(first, state, key="scans")
    render_component(first, state, key="scans")  # sends the data
    render_component(first, state, key="scans")
    assert vue.call_args.kwargs["dataChanged"] is False

    # Streamlit keeps returning the value Vue sent last, request included
    vue.return_value = {"_requestData": 1}
    with pytest.raises(Rerun):
        render_component(first, state, key="scans")
    render_component(first, state, key="scans")
    assert vue.call_args.kwargs["dataChanged"] is True
    # ...and the kept request does not rerun or resend again
    render_component(first, state, key="scans")
    assert vue.call_args.kwargs["dataChanged"] is False

    vue.return_value = {"_requestData": 2}
    with pytest.raises(Rerun):
        render_component(first, state, key="scans")


def test_data_sent_in_a_run_that_reruns_is_sent_again(rerun, vue, temp_cache_dir):
    """Starting a run drops the messages of the previous run that have not been
    delivered, so the data sent in a run that reruns is not counted as sent."""
    state = StateManager(session_key="dropped")
    first, second = _tables(temp_cache_dir)
    with pytest.raises(Rerun):
        with defer_reruns():
            render_component(first, state, key="scans")
            render_component(second, state, key="rows")
    assert vue.call_args.kwargs["dataChanged"] is True

    with defer_reruns():
        render_component(first, state, key="scans")
        render_component(second, state, key="rows")
    assert vue.call_args.kwargs["dataChanged"] is True  # sent again

    with defer_reruns():
        render_component(first, state, key="scans")
        render_component(second, state, key="rows")
    assert vue.call_args.kwargs["dataChanged"] is False


def test_click_is_seen_by_components_rendered_before_it(
    rerun, vue, mock_streamlit, temp_cache_dir
):
    """A click is applied before the block renders: the components rendered
    before the clicked one get the new selection in the same run, and the
    click costs no rerun."""
    state = StateManager(session_key="click")
    scans, rows = _tables(temp_cache_dir)

    def render():
        with defer_reruns():
            render_component(rows, state, key="rows")
            render_component(scans, state, key="scans")

    # Streamlit returns each component's last value on every run
    vue.side_effect = lambda **kwargs: mock_streamlit.get(kwargs["key"])
    mock_streamlit["scans"] = {"id": state.session_id, "counter": 0}
    with pytest.raises(Rerun):
        render()
    render()
    assert state.get_selection("scan") == 1
    reruns = rerun.call_count

    # The user clicks scan 2 in the table rendered last
    mock_streamlit["scans"] = {"id": state.session_id, "counter": 5, "scan": 2}
    render()
    assert state.get_selection("scan") == 2
    assert rerun.call_count == reruns
    rows_call = vue.call_args_list[-2].kwargs
    assert rows_call["key"] == "rows"
    assert list(rows_call["tableData"]["scan"]) == [2]

    # The value Streamlit keeps returning is not applied again: a selection made
    # since (here by Python) stands
    state.set_selection("scan", 1)
    render()
    assert state.get_selection("scan") == 1


def test_view_event_is_applied_once(rerun, vue, temp_cache_dir):
    # Streamlit returns the view's last value on every run: an action it
    # carries is applied for the first of them only
    state = StateManager(session_key="events")
    table, _ = _tables(temp_cache_dir)
    with pytest.raises(Rerun):
        render_component(table, state, key="scans")
    applied = []
    table._handle_event = lambda event: applied.append(event["nonce"]) or True
    vue.return_value = {"counter": 0, "_event": {"type": "x", "nonce": "a"}}
    with pytest.raises(Rerun):
        render_component(table, state, key="scans")
    calls = rerun.call_count
    render_component(table, state, key="scans")
    assert applied == ["a"]
    assert rerun.call_count == calls
    vue.return_value = {"counter": 0, "_event": {"type": "x", "nonce": "b"}}
    with pytest.raises(Rerun):
        render_component(table, state, key="scans")
    assert applied == ["a", "b"]
