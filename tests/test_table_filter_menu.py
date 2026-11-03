"""Table options search and numeric_filters: the toolbar search box and the
filter dialog's one-sided thresholds, applied on the server."""

from pathlib import Path

import polars as pl
import pytest

from openms_insight import Table


@pytest.fixture
def proteins() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "row": [0, 1, 2, 3, 4],
            "accession": ["P02768", "P04264", "P35527", "Q9Y6K9", "P00761"],
            "gene": ["ALB", "KRT1", "KRT9", None, "TRYP"],
            "description": [
                "Serum albumin",
                "Keratin, type II cytoskeletal 1",
                "Keratin, type I cytoskeletal 9",
                "NF-kappa-B essential modulator (a.k.a. NEMO)",
                "Trypsin",
            ],
            "peptides": [12, 1, 3, 2, 5],
            "replicates": [2, 1, 2, 0, 1],
            "q_value": [0.0001, 0.004, 0.0009, 0.009, 0.0002],
        }
    )


COLUMNS = [
    {"field": "accession", "title": "Accession"},
    {"field": "gene", "title": "Gene"},
    {"field": "description", "title": "Description"},
    {"field": "peptides", "title": "Peptides", "sorter": "number"},
    {"field": "replicates", "title": "Replicates", "sorter": "number"},
    {"field": "q_value", "title": "q-value", "sorter": "number"},
]


def _table(
    tmp: Path, data: pl.LazyFrame, cache_id: str = "proteins", **kwargs
) -> Table:
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


class TestSearch:
    def test_every_word_in_any_text_column_ignoring_case(
        self, mock_streamlit, temp_cache_dir: Path, proteins
    ):
        table = _table(temp_cache_dir, proteins, search=True)
        assert _rows(table, search="keratin") == [1, 2]
        assert _rows(table, search="KERATIN type ii") == [1]
        # Words may sit in different columns
        assert _rows(table, search="krt9 cytoskeletal") == [2]
        assert _rows(table, search="  ") == [0, 1, 2, 3, 4]
        # Numbers are not searched as text by default
        assert _rows(table, search="12") == []

    def test_literal_not_a_pattern(
        self, mock_streamlit, temp_cache_dir: Path, proteins
    ):
        table = _table(temp_cache_dir, proteins, search=True)
        assert _rows(table, search="(a.k.a.") == [3]
        assert _rows(table, search="a.b") == []
        assert _rows(table, search="[") == []

    def test_given_columns_only(self, mock_streamlit, temp_cache_dir: Path, proteins):
        table = _table(temp_cache_dir, proteins, search=["gene"])
        assert _rows(table, search="tryp") == [4]
        # The description is not searched
        assert _rows(table, search="albumin") == []
        assert table._get_component_args()["searchColumns"] == ["gene"]

    def test_without_the_option_the_text_is_ignored(
        self, mock_streamlit, temp_cache_dir: Path, proteins
    ):
        table = _table(temp_cache_dir, proteins)
        assert _rows(table, search="keratin") == [0, 1, 2, 3, 4]

    def test_search_combines_with_dialog_filters_and_counts(
        self, mock_streamlit, temp_cache_dir: Path, proteins
    ):
        table = _table(temp_cache_dir, proteins, search=True, page_size=1)
        state = {
            table._pagination_identifier: {
                "page": 1,
                "search": "keratin",
                "column_filters": [{"field": "peptides", "type": ">=", "value": 2}],
            }
        }
        result = table._prepare_vue_data(state)
        assert result["tableData"]["row"].tolist() == [2]
        assert result["_pagination"]["total_rows"] == 1
        # Echoed, so a view drawn again shows them
        assert result["_pagination"]["search"] == "keratin"
        assert result["_pagination"]["column_filters"][0]["field"] == "peptides"
        # The export honours them too
        assert table.export_data(state)["row"].to_list() == [2]

    def test_args(self, mock_streamlit, temp_cache_dir: Path, proteins):
        table = _table(
            temp_cache_dir,
            proteins,
            search=True,
            search_placeholder="Accession or gene",
        )
        args = table._get_component_args()
        assert args["search"] is True
        assert args["searchColumns"] == ["accession", "gene", "description"]
        assert args["searchPlaceholder"] == "Accession or gene"
        for key in ("search_placeholder", "numeric_filters"):
            assert key not in args


class TestNumericFilters:
    OPTION = {
        "q_value": {
            "op": "<=",
            "suggestions": [{"value": 0.01, "label": "1 % (run)"}, 0.005, 0.001],
        },
        "peptides": {"op": ">=", "suggestions": [2, 3], "default": 2},
    }

    def test_normalised_and_sent_to_vue(
        self, mock_streamlit, temp_cache_dir: Path, proteins
    ):
        table = _table(temp_cache_dir, proteins, numeric_filters=self.OPTION)
        args = table._get_component_args()
        assert args["numericFilters"] == {
            "q_value": {
                "op": "<=",
                "suggestions": [
                    {"value": 0.01, "label": "1 % (run)"},
                    {"value": 0.005},
                    {"value": 0.001},
                ],
            },
            "peptides": {
                "op": ">=",
                "suggestions": [{"value": 2.0}, {"value": 3.0}],
                "default": 2.0,
            },
        }

    def test_default_applies_until_the_view_sends_filters(
        self, mock_streamlit, temp_cache_dir: Path, proteins
    ):
        table = _table(temp_cache_dir, proteins, numeric_filters=self.OPTION)
        # Nothing sent yet: the default threshold peptides >= 2
        result = table._prepare_vue_data({})
        assert sorted(result["tableData"]["row"].tolist()) == [0, 2, 3, 4]
        assert result["_pagination"]["column_filters"] == [
            {"field": "peptides", "type": ">=", "value": 2.0}
        ]
        # The viewer removed it
        assert _rows(table, column_filters=[]) == [0, 1, 2, 3, 4]
        # A threshold of their own
        assert _rows(
            table, column_filters=[{"field": "q_value", "type": "<=", "value": 0.001}]
        ) == [0, 2, 4]
        assert sorted(table.export_data({})["row"].to_list()) == [0, 2, 3, 4]

    def test_few_valued_numbers_carry_their_range(
        self, mock_streamlit, temp_cache_dir: Path, proteins
    ):
        table = _table(temp_cache_dir, proteins)
        meta = table._get_component_args()["columnMetadata"]["replicates"]
        assert meta["type"] == "categorical"
        assert (meta["min"], meta["max"]) == (0.0, 2.0)

    @pytest.mark.parametrize(
        "option, message",
        [
            ({"q": {"op": "<"}}, "op"),
            ({"q": {"op": "<=", "suggestions": [{"label": "x"}]}}, "value"),
        ],
    )
    def test_invalid(self, mock_streamlit, temp_cache_dir: Path, option, message):
        with pytest.raises(ValueError, match=message):
            Table(
                cache_id="bad",
                data=pl.LazyFrame({"q": [0.1]}),
                cache_path=str(temp_cache_dir),
                numeric_filters=option,
            )


class TestCache:
    def test_unset_options_keep_the_config_hash(
        self, mock_streamlit, temp_cache_dir: Path, proteins
    ):
        plain = _table(temp_cache_dir, proteins, cache_id="plain")
        config = plain._get_cache_config()
        for key in ("search", "search_placeholder", "numeric_filters"):
            assert key not in config
        args = plain._get_component_args()
        for key in ("search", "searchColumns", "searchPlaceholder", "numericFilters"):
            assert key not in args
        # Same hash as a table built without knowing of these options
        assert (
            plain._compute_config_hash()
            == _table(
                temp_cache_dir / "other",
                proteins,
                cache_id="plain",
                search=False,
                search_placeholder="",
                numeric_filters={},
            )._compute_config_hash()
        )

    def test_unset_options_leave_the_response_alone(
        self, mock_streamlit, temp_cache_dir: Path, proteins
    ):
        table = _table(temp_cache_dir, proteins)
        pagination = table._prepare_vue_data({})["_pagination"]
        assert "column_filters" not in pagination and "search" not in pagination

    def test_options_survive_reconstruction(
        self, mock_streamlit, temp_cache_dir: Path, proteins
    ):
        _table(
            temp_cache_dir,
            proteins,
            cache_id="rebuild",
            search=["accession", "gene"],
            search_placeholder="Accession or gene",
            numeric_filters={
                "peptides": {"op": ">=", "suggestions": [2], "default": 2}
            },
        )
        restored = Table(cache_id="rebuild", cache_path=str(temp_cache_dir))
        args = restored._get_component_args()
        assert args["searchColumns"] == ["accession", "gene"]
        assert args["searchPlaceholder"] == "Accession or gene"
        assert args["numericFilters"]["peptides"]["default"] == 2.0
        assert _rows(restored, search="krt", column_filters=[]) == [1, 2]
        assert sorted(restored._prepare_vue_data({})["tableData"]["row"].tolist()) == [
            0,
            2,
            3,
            4,
        ]
