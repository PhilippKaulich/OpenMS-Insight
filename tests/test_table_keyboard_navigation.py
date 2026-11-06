"""Table keyboard navigation: a display option that never touches the cache."""

import json
from pathlib import Path

import polars as pl
import pytest

from openms_insight import Table

# input_config_hash of the table built by _table() with openms-insight 0.6.0,
# before the option existed. A cache written by that release is reused as is.
HASH_0_6_0 = "630cd4b35ef300d394ac4ffffcca909f28e41fc1e6d564c0b8c8b6cdc8c80ce0"


@pytest.fixture
def scans() -> pl.LazyFrame:
    return pl.LazyFrame(
        {"id": [1, 2, 3], "scan": [10, 20, 30], "mz": [100.5, 200.25, 300.125]}
    )


def _table(cache_path: Path, data: pl.LazyFrame, **kwargs) -> Table:
    return Table(
        cache_id="keys",
        data=data,
        cache_path=str(cache_path),
        interactivity={"spectrum": "scan"},
        index_field="id",
        page_size=20,
        **kwargs,
    )


def _manifest(cache_path: Path) -> dict:
    return json.loads((cache_path / "keys" / "manifest.json").read_text())


class TestArgs:
    def test_on_by_default(self, mock_streamlit, temp_cache_dir: Path, scans):
        # Vue treats a missing value as on, so the default sends nothing
        assert (
            "keyboardNavigation"
            not in _table(temp_cache_dir, scans)._get_component_args()
        )

    def test_turned_off(self, mock_streamlit, temp_cache_dir: Path, scans):
        args = _table(
            temp_cache_dir, scans, keyboard_navigation=False
        )._get_component_args()
        assert args["keyboardNavigation"] is False

    def test_not_an_extra_option(self, mock_streamlit, temp_cache_dir: Path, scans):
        table = _table(temp_cache_dir, scans, keyboard_navigation=False)
        assert "keyboard_navigation" not in table._config
        assert "keyboard_navigation" not in table._get_component_args()


class TestCache:
    @pytest.mark.parametrize("value", [True, False])
    def test_config_and_hash_unchanged(
        self, mock_streamlit, temp_cache_dir: Path, scans, value
    ):
        plain = _table(temp_cache_dir / "plain", scans)
        table = _table(temp_cache_dir / "set", scans, keyboard_navigation=value)
        assert "keyboard_navigation" not in table._get_cache_config()
        assert table._get_cache_config() == plain._get_cache_config()
        assert table._compute_config_hash() == plain._compute_config_hash()
        assert _manifest(temp_cache_dir / "set")["input_config_hash"] == HASH_0_6_0
        assert (
            _manifest(temp_cache_dir / "set")["config_hash"]
            == _manifest(temp_cache_dir / "plain")["config_hash"]
        )

    def test_existing_cache_is_reused(
        self, mock_streamlit, temp_cache_dir: Path, scans
    ):
        _table(temp_cache_dir, scans)
        generation = _manifest(temp_cache_dir)["cache_generation"]
        # Turning the option off on a table whose cache exists does not rebuild it
        table = _table(temp_cache_dir, scans, keyboard_navigation=False)
        assert _manifest(temp_cache_dir)["cache_generation"] == generation
        assert table._get_component_args()["keyboardNavigation"] is False

    def test_reconstruction_from_cache(
        self, mock_streamlit, temp_cache_dir: Path, scans
    ):
        _table(temp_cache_dir, scans)
        restored = Table(
            cache_id="keys", cache_path=str(temp_cache_dir), keyboard_navigation=False
        )
        assert restored._get_component_args()["keyboardNavigation"] is False
        assert (
            "keyboardNavigation"
            not in Table(
                cache_id="keys", cache_path=str(temp_cache_dir)
            )._get_component_args()
        )
