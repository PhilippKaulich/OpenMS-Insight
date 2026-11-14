"""streamlit-data.ts applies the deltas the bridge sends (test_bridge_delta.py).

The store must take ``_delta`` out of the args before anything stores them, try
the tables held now and the ones held before (see previousTables), and ask for
the full data when it holds neither.
"""

from pathlib import Path

STORE = Path(__file__).parents[1] / "js-component/src/stores/streamlit-data.ts"


def test_store_applies_deltas_and_asks_for_data_without_their_base():
    source = STORE.read_text(encoding="utf-8")
    assert "delete newData.args._delta" in source
    assert "applyDelta(" in source
    assert "version.hash === delta.base" in source
    assert "const HELD_VERSIONS = 4" in source  # bridge._DELTA_VERSIONS
    apply_call = source.index("this.applyDelta(")
    assert "this.requestData = true" in source[apply_call : apply_call + 300]
