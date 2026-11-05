"""StateManager.clear(): the views take the cleared state.

A view keeps the selections it last had from Python. After clear() (an app
switching its views to another data set) the view's value must not bring the
old selections back.
"""

from openms_insight import StateManager


def _sync(sm: StateManager, **selections) -> dict:
    """Select in Python and return the state a view now holds."""
    for key, value in selections.items():
        sm.set_selection(key, value)
    return sm.get_state_for_vue()


def test_clear_wins_over_view_state(mock_streamlit):
    sm = StateManager(session_key="clear_test")
    view = _sync(sm, scan=6, mass=0)

    sm.clear()
    state = sm.get_state_for_vue()
    assert state["scan"] is None and state["mass"] is None
    assert state["selection_counter"] > view["selection_counter"]

    # The view sends back what it held before it saw the cleared state
    assert sm.update_from_vue(dict(view)) is False
    assert sm.get_selection("scan") is None
    assert sm.get_selection("mass") is None


def test_selection_after_clear_is_taken(mock_streamlit):
    sm = StateManager(session_key="clear_test2")
    _sync(sm, scan=6)
    sm.clear()
    state = sm.get_state_for_vue()

    # The view took the cleared state, then the user selects
    view = dict(state, scan=2, selection_counter=state["selection_counter"] + 1)
    assert sm.update_from_vue(view) is True
    assert sm.get_selection("scan") == 2
