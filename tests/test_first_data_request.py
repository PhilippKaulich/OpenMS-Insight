"""A view whose first data was lost still asks Python for it.

Python records data as sent when it hands it to Streamlit. When a rerun starts
before the message reaches the browser, the message is dropped, and the next
runs send only the hash. The view then finds no data for that hash and sets
``requestData``. App.vue skips sending state before a view's first render (to
save reruns); a data request must pass that check, or the view never renders
and shows "Loading..." for good.
"""

import re
from pathlib import Path

APP = Path(__file__).parents[1] / "js-component/src/App.vue"


def test_data_request_is_sent_before_the_first_render():
    source = APP.read_text(encoding="utf-8")
    guard = re.search(
        r"if \((streamlitDataStore\.renderData === null[^)]*)\) return", source
    )
    assert guard, "the first-render guard in sendStateToStreamlit was not found"
    assert "!streamlitDataStore.requestData" in guard.group(1)
