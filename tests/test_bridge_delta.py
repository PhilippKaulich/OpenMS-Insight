"""Tables that grow while data comes in (a live heatmap) are sent as deltas.

Vue holds the rows it was sent last. Python sends where each row of the new
table comes from (a row Vue holds, or one of the new rows) and the new rows;
Vue rebuilds the table from them in the same order, so it equals a full send.
"""

from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

from openms_insight.rendering import bridge


def _rebuild(held: pd.DataFrame, payload: dict, name: str) -> pd.DataFrame:
    """What streamlit-data.ts applyDelta does with a delta payload."""
    added = payload[f"{name}__add"]
    rows = []
    for s, n in payload[f"{name}__src"][["s", "n"]].itertuples(index=False):
        for i in range(n):
            rows.append(held.iloc[s + i] if s >= 0 else added.iloc[-s - 1 + i])
    return pd.DataFrame(rows).reset_index(drop=True)


def _table(rng, n, start=0):
    return pd.DataFrame(
        {
            "rt": np.arange(start, start + n, dtype=float),
            "mass": rng.random(n) * 1e4,
            "intensity": rng.random(n),
        }
    )


COMPONENT = SimpleNamespace(_delta_tables=("heatmapData",))


def _send(state, key, df, data_hash):
    """One render: the payload sent, recorded as sent as the bridge does."""
    with patch("openms_insight.rendering.bridge.st.session_state", state):
        payload = bridge._as_delta(key, COMPONENT, {"heatmapData": df}, data_hash)
        state.setdefault(bridge._SENT_HASH_KEY, {})[key] = data_hash
    return payload


def test_row_sources_point_at_held_rows_and_number_new_ones():
    old = np.array([10, 20, 30], dtype="uint64")
    new = np.array([30, 40, 10, 50, 20], dtype="uint64")
    sources, is_new = bridge._row_sources(old, new)
    assert sources.tolist() == [2, -1, 0, -2, 1]
    assert is_new.tolist() == [False, True, False, True, False]


def test_row_sources_with_nothing_held():
    sources, is_new = bridge._row_sources(
        np.array([], dtype="uint64"), np.array([1, 2], dtype="uint64")
    )
    assert sources.tolist() == [-1, -2]
    assert is_new.all()


def test_source_runs():
    sources = np.array([5, 6, 7, -1, -2, 0, 3, 4, -3], dtype="int32")
    runs = bridge._source_runs(sources)
    assert runs.to_dict("list") == {"s": [5, -1, 0, 3, -3], "n": [3, 2, 1, 2, 1]}
    assert bridge._source_runs(np.arange(1000, dtype="int32")).to_dict("list") == {
        "s": [0],
        "n": [1000],
    }


def test_growing_table_is_sent_as_delta_and_rebuilds_exactly():
    rng = np.random.default_rng(0)
    state = {}
    first = _table(rng, 5000)
    payload = _send(state, "map", first, "h1")
    assert "heatmapData" in payload and "_delta" not in payload

    # Some rows dropped, new ones added, order changed (sorted by intensity)
    second = (
        pd.concat([first.iloc[500:], _table(rng, 800, start=5000)])
        .sort_values("intensity")
        .reset_index(drop=True)
    )
    payload = _send(state, "map", second, "h2")
    assert payload["_delta"] == {"base": "h1", "tables": ["heatmapData"]}
    assert "heatmapData" not in payload
    assert len(payload["heatmapData__add"]) == 800
    pd.testing.assert_frame_equal(_rebuild(first, payload, "heatmapData"), second)


def test_full_send_when_vue_may_hold_other_data():
    rng = np.random.default_rng(1)
    state = {}
    first = _table(rng, 5000)
    _send(state, "map", first, "h1")
    # A data request (or a remounted view) clears the sent hashes and the
    # versions held, as render_component does
    state[bridge._SENT_HASH_KEY].clear()
    state.pop(bridge._HELD_TABLES_KEY)
    payload = _send(state, "map", pd.concat([first, _table(rng, 10, 5000)]), "h2")
    assert "_delta" not in payload and "heatmapData" in payload


def test_delta_builds_on_the_newest_version_when_no_send_is_recorded():
    """Every run that sent data reran, so the sent hash went back to None."""
    rng = np.random.default_rng(6)
    state = {}
    first = _table(rng, 5000)
    _send(state, "map", first, "h1")
    state[bridge._SENT_HASH_KEY]["map"] = None  # what _rerun() does
    second = pd.concat([first, _table(rng, 10, 5000)], ignore_index=True)
    payload = _send(state, "map", second, "h2")
    assert payload["_delta"]["base"] == "h1"
    pd.testing.assert_frame_equal(_rebuild(first, payload, "heatmapData"), second)


def test_full_send_when_most_rows_are_new_or_table_is_small():
    rng = np.random.default_rng(2)
    state = {}
    _send(state, "map", _table(rng, 5000), "h1")
    payload = _send(state, "map", _table(rng, 5000, start=10000), "h2")
    assert "_delta" not in payload

    small = _table(rng, 100)
    _send(state, "small", small, "s1")
    payload = _send(state, "small", pd.concat([small, _table(rng, 5, 100)]), "s2")
    assert "_delta" not in payload


def test_components_without_delta_tables_are_untouched():
    payload = {"heatmapData": pd.DataFrame({"a": [1]})}
    out = bridge._as_delta("k", SimpleNamespace(), payload, "h")
    assert out is payload


def test_after_a_rerun_forgets_the_last_send_the_delta_builds_on_the_one_before():
    """_rerun() puts back the hash sent before, as the last message may be lost.

    Vue keeps the tables of the hash before the current one, so a delta against
    it applies whether or not the last message arrived.
    """
    rng = np.random.default_rng(3)
    state = {}
    first = _table(rng, 5000)
    _send(state, "map", first, "h1")
    second = pd.concat([first, _table(rng, 100, 5000)], ignore_index=True)
    _send(state, "map", second, "h2")
    state[bridge._SENT_HASH_KEY]["map"] = "h1"  # what _rerun() does

    third = pd.concat([second, _table(rng, 100, 6000)], ignore_index=True)
    payload = _send(state, "map", third, "h3")
    assert payload["_delta"]["base"] == "h1"
    assert len(payload["heatmapData__add"]) == 200
    pd.testing.assert_frame_equal(_rebuild(first, payload, "heatmapData"), third)

    # The held versions stay bounded
    for n in range(4, 10):
        _send(state, "map", third.iloc[n:], f"h{n}")
    assert len(state[bridge._HELD_TABLES_KEY]["map"]) == bridge._DELTA_VERSIONS


def test_delta_builds_on_the_data_sent_last_not_the_hash_vue_echoed():
    """Vue's echoed hash can be older than the data it holds; the sent one counts."""
    rng = np.random.default_rng(4)
    state = {}
    first = _table(rng, 5000)
    _send(state, "map", first, "h1")
    second = pd.concat([first, _table(rng, 100, 5000)], ignore_index=True)
    _send(state, "map", second, "h2")
    state[bridge._VUE_ECHOED_HASH_KEY] = {"map": "h1"}  # an echo from before

    third = pd.concat([second, _table(rng, 10, 6000)], ignore_index=True)
    payload = _send(state, "map", third, "h3")
    assert payload["_delta"]["base"] == "h2"
    assert len(payload["heatmapData__add"]) == 10
    pd.testing.assert_frame_equal(_rebuild(second, payload, "heatmapData"), third)


def test_data_sent_again_after_a_rerun_goes_as_a_delta_on_itself():
    """A rerun forgets the last send; sending the same data again costs no rows.

    Vue ignores it when it holds that data, and rebuilds it from the version it
    keeps (or asks for it) otherwise. Data that was sent before, such as the
    view before a zoom, goes the same way.
    """
    rng = np.random.default_rng(5)
    state = {}
    first = _table(rng, 5000)
    _send(state, "map", first, "h1")
    zoomed = _table(rng, 5000, 10000)  # every row new: sent in full
    assert "heatmapData" in _send(state, "map", zoomed, "h2")
    state[bridge._SENT_HASH_KEY]["map"] = "h1"  # what _rerun() does

    payload = _send(state, "map", zoomed, "h2")
    assert payload["_delta"]["base"] == "h2"
    assert len(payload["heatmapData__add"]) == 0
    pd.testing.assert_frame_equal(_rebuild(zoomed, payload, "heatmapData"), zoomed)

    payload = _send(state, "map", first, "h1")  # the zoom undone
    assert payload["_delta"]["base"] == "h1"
    assert len(payload["heatmapData__add"]) == 0


def test_each_run_records_its_own_sent_hashes():
    """A rerun reverts only the hashes sent in the run it ends.

    Streamlit makes a new ``cursors`` dict per run; newer versions clear
    ``widget_ids_this_run`` in place, so that set no longer tells runs apart.
    """
    state = {bridge._SENT_HASH_KEY: {}}
    ctx = SimpleNamespace(cursors={}, widget_ids_this_run=set())
    with (
        patch("openms_insight.rendering.bridge.st.session_state", state),
        patch("streamlit.runtime.scriptrunner.get_script_run_ctx", return_value=ctx),
        patch("openms_insight.rendering.bridge.st.rerun"),
    ):
        bridge._record_sent("map", "h1")
        ctx.cursors = {}  # the next run
        ctx.widget_ids_this_run.clear()
        bridge._record_sent("map", "h2")
        bridge._rerun()
    assert state[bridge._SENT_HASH_KEY]["map"] == "h1"
