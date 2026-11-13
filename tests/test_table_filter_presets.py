"""Table option filter_presets: ready-made filters at the top of the filter
dialog, switched on and off by the viewer and applied on the server."""

from pathlib import Path

import polars as pl
import pytest

from openms_insight import Table
from openms_insight.core.filter_presets import (
    normalize_filter_presets,
    preset_expression,
)


@pytest.fixture
def psms() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "row": [0, 1, 2, 3, 4],
            "is_decoy": [False, True, False, None, False],
            "q_value": [0.001, 0.2, 0.03, 0.005, 0.009],
            "charge": [2, 3, 1, 2, 4],
            "protein": ["ALB", "REV_ALB", "KRT1", "TRYP", "KRT9"],
        }
    )


COLUMNS = [
    {"field": "protein", "title": "Protein"},
    {"field": "q_value", "title": "q-value", "sorter": "number"},
    {"field": "charge", "title": "Charge", "sorter": "number"},
]

PRESETS = [
    {
        "label": "Hide decoys",
        "column": "is_decoy",
        "op": "!=",
        "value": True,
        "default": True,
        "help": "Rows matched to reversed sequences",
    },
    {
        "id": "confident",
        "label": "Confident PSMs",
        "filters": [
            {"column": "q_value", "op": "<=", "value": 0.01},
            {"column": "charge", "op": ">=", "value": 2},
        ],
    },
]


def _table(tmp: Path, data: pl.LazyFrame, cache_id: str = "psms", **kwargs) -> Table:
    return Table(
        cache_id=cache_id,
        data=data,
        cache_path=str(tmp),
        column_definitions=COLUMNS,
        index_field="row",
        **kwargs,
    )


def _rows(table: Table, **pagination) -> list[int]:
    state = {table._pagination_identifier: {"page": 1, **pagination}}
    return sorted(table._prepare_vue_data(state)["tableData"]["row"].tolist())


class TestNormalize:
    def test_shorthand_and_defaults(self):
        hide, confident = normalize_filter_presets(PRESETS)
        assert hide == {
            "id": "Hide decoys",
            "label": "Hide decoys",
            "filters": [{"column": "is_decoy", "op": "!=", "value": True}],
            "default": True,
            "help": "Rows matched to reversed sequences",
        }
        assert confident["id"] == "confident"
        assert confident["default"] is False
        assert len(confident["filters"]) == 2

    @pytest.mark.parametrize(
        "presets, message",
        [
            ([{"column": "x"}], "label"),
            ([{"label": "a"}], "column"),
            ([{"label": "a", "column": "x", "op": "~"}], "op"),
            ([{"label": "a", "column": "x", "op": "in", "value": 1}], "list"),
            ([{"label": "a", "filters": []}], "no conditions"),
            ([{"label": "a", "column": "x"}, {"label": "a", "column": "y"}], "id"),
        ],
    )
    def test_invalid(self, presets, message):
        with pytest.raises(ValueError, match=message):
            normalize_filter_presets(presets)

    @pytest.mark.parametrize(
        "condition, kept",
        [
            ({"column": "charge", "op": "==", "value": 2}, [0, 3]),
            ({"column": "charge", "op": "<", "value": 2}, [2]),
            ({"column": "charge", "op": ">", "value": 3}, [4]),
            ({"column": "protein", "op": "in", "value": ["ALB", "TRYP"]}, [0, 3]),
            ({"column": "protein", "op": "not in", "value": ["ALB"]}, [1, 2, 3, 4]),
            # A missing value counts as different from True
            ({"column": "is_decoy", "op": "!=", "value": True}, [0, 2, 3, 4]),
        ],
    )
    def test_conditions(self, psms, condition, kept):
        (preset,) = normalize_filter_presets([{"label": "p", **condition}])
        rows = psms.filter(preset_expression(preset)).collect()["row"].to_list()
        assert rows == kept


class TestTable:
    def test_defaults_apply_until_the_view_switches(
        self, mock_streamlit, temp_cache_dir: Path, psms
    ):
        table = _table(temp_cache_dir, psms, filter_presets=PRESETS)
        result = table._prepare_vue_data({})
        assert sorted(result["tableData"]["row"].tolist()) == [0, 2, 3, 4]
        assert result["_pagination"]["presets"] == {
            "Hide decoys": True,
            "confident": False,
        }
        assert _rows(table, presets={"Hide decoys": False}) == [0, 1, 2, 3, 4]
        assert _rows(table, presets={"confident": True}) == [0, 3, 4]
        assert _rows(table, presets={"Hide decoys": False, "confident": True}) == [
            0,
            3,
            4,
        ]

    def test_presets_combine_with_dialog_filters(
        self, mock_streamlit, temp_cache_dir: Path, psms
    ):
        table = _table(temp_cache_dir, psms, filter_presets=PRESETS)
        filters = [{"field": "charge", "type": ">=", "value": 2}]
        assert _rows(table, column_filters=filters) == [0, 3, 4]

    def test_sent_to_vue(self, mock_streamlit, temp_cache_dir: Path, psms):
        table = _table(temp_cache_dir, psms, filter_presets=PRESETS)
        args = table._get_component_args()
        assert [p["id"] for p in args["filterPresets"]] == ["Hide decoys", "confident"]
        assert "filter_presets" not in args

    def test_export_follows_the_presets(
        self, mock_streamlit, temp_cache_dir: Path, psms
    ):
        table = _table(temp_cache_dir, psms, filter_presets=PRESETS)
        state = {table._pagination_identifier: {"page": 1, "download_request": 1}}
        csv = table._prepare_vue_data(state)["_download"]["csv"]
        assert "REV_ALB" not in csv and "KRT1" in csv

    def test_unset_keeps_config_hash_and_response(
        self, mock_streamlit, temp_cache_dir: Path, psms
    ):
        plain = _table(temp_cache_dir, psms, cache_id="plain")
        assert "filter_presets" not in plain._get_cache_config()
        assert "filterPresets" not in plain._get_component_args()
        assert "presets" not in plain._prepare_vue_data({})["_pagination"]
        assert (
            plain._compute_config_hash()
            == _table(
                temp_cache_dir / "other", psms, cache_id="plain", filter_presets=[]
            )._compute_config_hash()
        )

    def test_survive_reconstruction(self, mock_streamlit, temp_cache_dir: Path, psms):
        _table(temp_cache_dir, psms, cache_id="rebuild", filter_presets=PRESETS)
        restored = Table(cache_id="rebuild", cache_path=str(temp_cache_dir))
        assert len(restored._get_component_args()["filterPresets"]) == 2
        assert _rows(restored) == [0, 2, 3, 4]
