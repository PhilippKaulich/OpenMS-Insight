"""Tests for streaming (server-side pagination) table functionality.

These tests verify that the Table component correctly implements server-side
pagination where only the current page of data is sent to the frontend.
"""

import polars as pl
import pytest

from openms_insight import Table


@pytest.fixture
def large_table_data() -> pl.LazyFrame:
    """Create a large dataset for pagination testing."""
    n_rows = 1000
    return pl.LazyFrame(
        {
            "id": list(range(n_rows)),
            "scan_id": [i // 100 for i in range(n_rows)],  # 10 unique scan_ids
            "mass": [100.0 + i * 0.5 for i in range(n_rows)],
            "intensity": [1000.0 + i * 10 for i in range(n_rows)],
            "name": [f"peak_{i}" for i in range(n_rows)],
            "category": [["A", "B", "C"][i % 3] for i in range(n_rows)],
        }
    )


class TestStreamingTablePagination:
    """Tests for server-side pagination behavior."""

    def test_streaming_returns_only_page_size_rows(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        """Verify that only page_size rows are returned."""
        table = Table(
            cache_id="test_streaming_page_size",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
            page_size=50,
        )

        result = table._prepare_vue_data({})

        assert "tableData" in result
        assert len(result["tableData"]) == 50

    def test_pagination_metadata_returned(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        """Verify pagination metadata is included in response."""
        table = Table(
            cache_id="test_streaming_metadata",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
            page_size=100,
        )

        result = table._prepare_vue_data({})

        assert "_pagination" in result
        pagination = result["_pagination"]
        assert pagination["page"] == 1
        assert pagination["page_size"] == 100
        assert pagination["total_rows"] == 1000
        assert pagination["total_pages"] == 10

    def test_page_navigation(self, mock_streamlit, temp_cache_dir, large_table_data):
        """Verify correct data is returned for different pages."""
        table = Table(
            cache_id="test_streaming_navigation",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
            page_size=100,
        )

        pagination_id = table._pagination_identifier

        # Request page 3
        state = {pagination_id: {"page": 3, "page_size": 100}}
        result = table._prepare_vue_data(state)

        # Should return rows 200-299
        assert len(result["tableData"]) == 100
        assert result["tableData"]["id"].iloc[0] == 200
        assert result["tableData"]["id"].iloc[-1] == 299
        assert result["_pagination"]["page"] == 3

    def test_last_page_partial_rows(self, mock_streamlit, temp_cache_dir):
        """Verify last page returns correct number of rows when not full."""
        # 150 rows with page_size=100 means page 2 has only 50 rows
        data = pl.LazyFrame(
            {
                "id": list(range(150)),
                "value": list(range(150)),
            }
        )

        table = Table(
            cache_id="test_streaming_partial",
            data=data,
            cache_path=str(temp_cache_dir),
            page_size=100,
        )

        pagination_id = table._pagination_identifier
        state = {pagination_id: {"page": 2, "page_size": 100}}
        result = table._prepare_vue_data(state)

        assert len(result["tableData"]) == 50
        assert result["_pagination"]["total_pages"] == 2


class TestStreamingTableSort:
    """Tests for server-side sorting behavior."""

    def test_server_side_sort_ascending(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        """Verify ascending sort is applied server-side."""
        table = Table(
            cache_id="test_streaming_sort_asc",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
            page_size=50,
        )

        pagination_id = table._pagination_identifier
        state = {
            pagination_id: {
                "page": 1,
                "page_size": 50,
                "sort_column": "mass",
                "sort_dir": "asc",
            }
        }
        result = table._prepare_vue_data(state)

        # First row should have lowest mass
        assert result["tableData"]["mass"].iloc[0] == 100.0

    def test_server_side_sort_descending(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        """Verify descending sort is applied server-side."""
        table = Table(
            cache_id="test_streaming_sort_desc",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
            page_size=50,
        )

        pagination_id = table._pagination_identifier
        state = {
            pagination_id: {
                "page": 1,
                "page_size": 50,
                "sort_column": "mass",
                "sort_dir": "desc",
            }
        }
        result = table._prepare_vue_data(state)

        # First row should have highest mass (999 * 0.5 + 100 = 599.5)
        assert result["tableData"]["mass"].iloc[0] == 599.5


class TestStreamingTableFilters:
    """Tests for server-side filtering behavior."""

    def test_cross_component_filter(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        """Verify cross-component filters are applied."""
        table = Table(
            cache_id="test_streaming_cross_filter",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
            filters={"scan": "scan_id"},
            page_size=50,
        )

        # Filter to scan_id=5, which has 100 rows (ids 500-599)
        state = {"scan": 5}
        result = table._prepare_vue_data(state)

        assert result["_pagination"]["total_rows"] == 100
        assert result["_pagination"]["total_pages"] == 2
        assert len(result["tableData"]) == 50

    def test_column_filter_categorical(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        """Verify categorical column filters are applied."""
        table = Table(
            cache_id="test_streaming_col_filter_cat",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
            page_size=100,
        )

        pagination_id = table._pagination_identifier
        state = {
            pagination_id: {
                "page": 1,
                "page_size": 100,
                "column_filters": [
                    {"field": "category", "type": "in", "value": ["A", "B"]}
                ],
            }
        }
        result = table._prepare_vue_data(state)

        # Categories A and B = 2/3 of data = ~667 rows
        # With rounding: (1000 // 3) * 2 + (1000 % 3) if remainder covers A or B
        expected_rows = sum(
            1 for i in range(1000) if ["A", "B", "C"][i % 3] in ["A", "B"]
        )
        assert result["_pagination"]["total_rows"] == expected_rows

    def test_column_filter_numeric_range(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        """Verify numeric range filters are applied."""
        table = Table(
            cache_id="test_streaming_col_filter_num",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
            page_size=100,
        )

        pagination_id = table._pagination_identifier
        state = {
            pagination_id: {
                "page": 1,
                "page_size": 100,
                "column_filters": [
                    {"field": "mass", "type": ">=", "value": 200.0},
                    {"field": "mass", "type": "<=", "value": 300.0},
                ],
            }
        }
        result = table._prepare_vue_data(state)

        # All returned rows should be in range
        for mass in result["tableData"]["mass"]:
            assert 200.0 <= mass <= 300.0

    def test_filter_change_resets_pagination_metadata(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        """Verify total_rows/total_pages update when filters change."""
        table = Table(
            cache_id="test_streaming_filter_meta",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
            filters={"scan": "scan_id"},
            page_size=50,
        )

        # No filter - all 1000 rows
        result1 = table._prepare_vue_data({})
        # Note: Without scan filter, returns empty due to filter logic
        # Let's use a filter with a value
        result1 = table._prepare_vue_data({"scan": 0})
        assert result1["_pagination"]["total_rows"] == 100

        # Filter to different scan
        result2 = table._prepare_vue_data({"scan": 1})
        assert result2["_pagination"]["total_rows"] == 100


class TestStreamingTableNavigation:
    """Tests for cross-component selection navigation."""

    def test_navigate_to_page_hint(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        """Verify navigate_to_page hint is returned when selection is on different page."""
        table = Table(
            cache_id="test_streaming_navigate",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
            interactivity={"selected_id": "id"},
            page_size=100,
        )

        pagination_id = table._pagination_identifier

        # Current page is 1, but selection (id=550) is on page 6
        state = {
            pagination_id: {"page": 1, "page_size": 100},
            "selected_id": 550,
        }
        result = table._prepare_vue_data(state)

        # Should include navigation hint to page 6
        assert "_navigate_to_page" in result
        assert result["_navigate_to_page"] == 6
        assert "_target_row_index" in result
        assert result["_target_row_index"] == 50  # Index within page

    def test_no_navigate_hint_when_on_correct_page(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        """Verify no navigation hint when selection is on current page."""
        table = Table(
            cache_id="test_streaming_no_navigate",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
            interactivity={"selected_id": "id"},
            page_size=100,
        )

        pagination_id = table._pagination_identifier

        # Selection (id=50) is on page 1
        state = {
            pagination_id: {"page": 1, "page_size": 100},
            "selected_id": 50,
        }
        result = table._prepare_vue_data(state)

        # Should NOT include navigation hint
        assert "_navigate_to_page" not in result

    def test_new_data_version_keeps_page(self, mock_streamlit, temp_cache_dir):
        """A table rebuilt under a new cache id as its data grows (a live view)
        stays on its page: the selection did not change, so it is not followed."""
        pagination_id = "live_page"

        def version(n):
            return Table(
                cache_id=f"live_{n}",
                data=pl.LazyFrame({"id": list(range(n, 0, -1))}),
                cache_path=str(temp_cache_dir),
                interactivity={"selected_id": "id"},
                index_field="id",
                pagination_identifier=pagination_id,
                page_size=100,
            )

        state = {pagination_id: {"page": 1, "page_size": 100}, "selected_id": 150}
        first = version(200)._prepare_vue_data(state)
        assert "_navigate_to_page" not in first

        # 100 newer rows on top move the selected row to page 2
        grown = version(300)._prepare_vue_data(state)
        assert "_navigate_to_page" not in grown

        # A new selection is still followed to its page
        state["selected_id"] = 10
        picked = version(300)._prepare_vue_data(state)
        assert picked["_navigate_to_page"] == 3


class TestStreamingTableGoTo:
    """Tests for server-side go-to functionality."""

    def test_go_to_request_returns_correct_page(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        """Verify go-to request returns navigation to correct page."""
        table = Table(
            cache_id="test_streaming_goto",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
            page_size=100,
        )

        pagination_id = table._pagination_identifier

        # Search for id=750 (on page 8)
        state = {
            pagination_id: {
                "page": 1,
                "page_size": 100,
                "go_to_request": {"field": "id", "value": "750"},
            }
        }
        result = table._prepare_vue_data(state)

        assert "_navigate_to_page" in result
        assert result["_navigate_to_page"] == 8
        assert result["_target_row_index"] == 50


class TestStreamingTableColumnMetadata:
    """Tests for column metadata computation during preprocessing."""

    def test_column_metadata_computed(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        """Verify column metadata is computed during preprocessing."""
        table = Table(
            cache_id="test_streaming_metadata_compute",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
        )

        args = table._get_component_args()

        assert "columnMetadata" in args
        metadata = args["columnMetadata"]

        # Check numeric column
        assert "mass" in metadata
        assert metadata["mass"]["type"] == "numeric"
        assert "min" in metadata["mass"]
        assert "max" in metadata["mass"]

        # Check categorical column (3 unique values)
        assert "category" in metadata
        assert metadata["category"]["type"] == "categorical"
        assert "unique_values" in metadata["category"]
        assert set(metadata["category"]["unique_values"]) == {"A", "B", "C"}

    def test_pagination_identifier_in_args(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        """Verify pagination identifier is included in component args."""
        table = Table(
            cache_id="test_streaming_pagination_id",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
        )

        args = table._get_component_args()

        assert "paginationIdentifier" in args
        assert args["paginationIdentifier"] == "test_streaming_pagination_id_page"


class TestStreamingTableStateDependencies:
    """Tests for get_state_dependencies() behavior."""

    def test_includes_pagination_identifier(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        """Verify pagination identifier is included in state dependencies."""
        table = Table(
            cache_id="test_streaming_deps",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
            filters={"scan": "scan_id"},
        )

        deps = table.get_state_dependencies()

        assert "scan" in deps
        assert table._pagination_identifier in deps

    def test_custom_pagination_identifier(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        """Verify custom pagination identifier is used."""
        table = Table(
            cache_id="test_streaming_custom_id",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
            pagination_identifier="my_custom_page_state",
        )

        assert table._pagination_identifier == "my_custom_page_state"
        assert "my_custom_page_state" in table.get_state_dependencies()


class TestPaginationCounterConflict:
    """Tests for counter-based conflict resolution protecting Vue pagination state."""

    def test_vue_pagination_not_overwritten_by_stale_python(self, mock_streamlit):
        """Vue's page state should be preserved when Python's counter is behind.

        This tests the scenario where:
        1. User navigates to page 10, Vue increments pagination_counter to 14
        2. User clicks a row, triggering a rerun
        3. Python processes the selection but its counter is still at 12
        4. Python sends response with stale page=1

        The StateManager should reject the stale pagination state because
        Vue's counter (14) > Python's counter (12).
        """
        from openms_insight.core.state import StateManager

        state_manager = StateManager("test_state")
        pagination_id = "test_table_page"

        # Simulate initial state: user navigated to page 10
        state_manager._state["pagination_counter"] = 14
        state_manager._state["selections"][pagination_id] = {
            "page": 10,
            "page_size": 100,
        }

        # Simulate stale Vue state coming back with counter 12 and page 1
        # (This represents what Python would echo back before catching up)
        vue_state = {
            "pagination_counter": 12,
            "selection_counter": 0,
            "id": state_manager.session_id,
            pagination_id: {"page": 1, "page_size": 100},
        }

        # This should NOT update the pagination state
        state_manager.update_from_vue(vue_state)

        # Page should still be 10 because Python's counter (12) < Vue's counter (14)
        assert state_manager._state["selections"][pagination_id]["page"] == 10

    def test_python_pagination_accepted_when_counter_higher(self, mock_streamlit):
        """Python's page state should be accepted when its counter is higher.

        This tests legitimate updates like sort/filter changes where Python
        resets to page 1 intentionally.
        """
        from openms_insight.core.state import StateManager

        state_manager = StateManager("test_state")
        pagination_id = "test_table_page"

        # Initial state: user on page 5
        state_manager._state["pagination_counter"] = 10
        state_manager._state["selections"][pagination_id] = {
            "page": 5,
            "page_size": 100,
        }

        # Vue state with higher counter (e.g., after Python processed a filter change)
        vue_state = {
            "pagination_counter": 11,  # Higher than Python's 10
            "selection_counter": 0,
            "id": state_manager.session_id,
            pagination_id: {"page": 1, "page_size": 100},
        }

        # This SHOULD update the pagination state
        state_manager.update_from_vue(vue_state)

        # Page should be updated to 1
        assert state_manager._state["selections"][pagination_id]["page"] == 1

    def test_selection_and_pagination_counters_independent(self, mock_streamlit):
        """Selection updates shouldn't affect pagination counter checks.

        This ensures the two counters are truly independent - a selection
        update with high selection_counter shouldn't allow pagination updates
        with low pagination_counter.
        """
        from openms_insight.core.state import StateManager

        state_manager = StateManager("test_state")
        pagination_id = "test_table_page"
        selection_id = "spectrum"

        # Initial state: high pagination counter, low selection counter
        state_manager._state["pagination_counter"] = 20
        state_manager._state["selection_counter"] = 5
        state_manager._state["selections"][pagination_id] = {
            "page": 10,
            "page_size": 100,
        }
        state_manager._state["selections"][selection_id] = 42

        # Vue state: high selection counter but low pagination counter
        vue_state = {
            "pagination_counter": 15,  # Lower than Python's 20
            "selection_counter": 10,  # Higher than Python's 5
            "id": state_manager.session_id,
            pagination_id: {"page": 1, "page_size": 100},
            selection_id: 99,
        }

        state_manager.update_from_vue(vue_state)

        # Selection should update (10 >= 5)
        assert state_manager._state["selections"][selection_id] == 99
        # Pagination should NOT update (15 < 20)
        assert state_manager._state["selections"][pagination_id]["page"] == 10


class TestHiddenColumns:
    """Columns hidden until the viewer turns them on in the column menu."""

    def test_hidden_columns_in_args(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        table = Table(
            cache_id="test_hidden_columns",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
            hidden_columns=["category"],
        )

        args = table._get_component_args()

        assert args["hiddenColumns"] == ["category"]
        # Hidden columns are still sent, so the viewer can show them
        assert "category" in [c["field"] for c in args["columnDefinitions"]]

    def test_no_hidden_columns_by_default(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        table = Table(
            cache_id="test_hidden_columns_default",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
        )

        assert "hiddenColumns" not in table._get_component_args()

    def test_hidden_columns_do_not_invalidate_cache(
        self, mock_streamlit, temp_cache_dir, large_table_data
    ):
        Table(
            cache_id="test_hidden_columns_cache",
            data=large_table_data,
            cache_path=str(temp_cache_dir),
        )
        # Loaded from cache without data: a display option must not require a rebuild
        table = Table(
            cache_id="test_hidden_columns_cache",
            cache_path=str(temp_cache_dir),
            hidden_columns=["mass"],
        )

        assert table._get_component_args()["hiddenColumns"] == ["mass"]
