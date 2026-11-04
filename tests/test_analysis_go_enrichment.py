"""GO enrichment of a selected set of proteins (no network: annotations given)."""

import pandas as pd
import pytest

pytest.importorskip("mygene")
pytest.importorskip("scipy")

from openms_insight.analysis.enrichment import (  # noqa: E402
    benjamini_hochberg,
    fetch_go_annotations,
    go_enrichment,
    go_enrichment_from_index,
    go_term_index,
    go_term_table,
)


@pytest.fixture
def annotations():
    return pd.DataFrame(
        {
            "query": ["A", "B", "C", "D", "E", "F"],
            "BP_terms": [["x", "y"], ["x"], ["x"], ["y"], ["z"], []],
            "CC_terms": [[], [], [], [], [], []],
            "MF_terms": [["m"], [], [], [], [], []],
        }
    )


def test_selected_set_against_background(annotations):
    result = go_enrichment(
        annotations, ["sp|A|NAME_A", "B", "C"], list("ABCDEF") + ["G"]
    )
    # F and G have no GO term: not counted
    assert (result["fg_count"], result["bg_count"]) == (3, 5)
    assert (result["fg_total"], result["bg_total"]) == (3, 7)
    bp = result["categories"]["BP"]
    top = bp.iloc[0]
    assert top["GO_Term"] == "x"
    assert (top["Count"], top["Background"]) == (3, 3)
    assert top["GeneRatio"] == "3/3" and top["BgRatio"] == "3/5"
    assert top["Proteins"] == "A;B;C"
    assert top["FoldEnrichment"] == pytest.approx(5 / 3)
    assert list(bp["p_adj"]) == sorted(bp["p_adj"])
    assert result["categories"]["CC"].empty


def test_background_includes_foreground(annotations):
    table = go_term_table(annotations, {"A"}, {"B"}, "BP")
    assert set(table["GO_Term"]) == {"x", "y"}
    assert table.loc[table["GO_Term"] == "x", "BgRatio"].item() == "2/2"


def test_benjamini_hochberg_monotone_and_capped():
    adjusted = benjamini_hochberg([0.01, 0.04, 0.03, 0.9])
    assert adjusted[0] == pytest.approx(0.04)
    assert adjusted.max() <= 1.0
    assert len(benjamini_hochberg([])) == 0


def test_fetch_merges_genes_and_skips_not_found():
    class FakeClient:
        def querymany(self, ids, **kwargs):
            assert ids == ["P1", "P2"]
            return [
                {"query": "P1", "go": {"BP": [{"term": "a"}], "MF": {"term": "m"}}},
                {"query": "P1", "go": {"BP": [{"term": "b"}]}},
                {"query": "P2", "notfound": True},
            ]

    result = fetch_go_annotations(
        ["sp|P1|X", "P2", "P1", None], mygene_client=FakeClient()
    )
    assert result["query"].tolist() == ["P1"]
    assert result.loc[0, "BP_terms"] == ["a", "b"]
    assert result.loc[0, "MF_terms"] == ["m"]
    assert fetch_go_annotations([], mygene_client=FakeClient()).empty


def test_term_index_lists_every_protein(annotations):
    index = go_term_index(annotations, ["sp|A|NAME_A", "F", "G"])
    assert sorted(index["accession"].unique().to_list()) == ["A", "F", "G"]
    # F (no terms) and G (not annotated) keep one row without a term
    empty = index.filter(index["term"].is_null())
    assert sorted(empty["accession"].to_list()) == ["F", "G"]
    assert sorted(
        index.filter(index["accession"] == "A")[["category", "term"]].rows()
    ) == [("BP", "x"), ("BP", "y"), ("MF", "m")]


@pytest.mark.parametrize(
    "foreground",
    [["A"], ["sp|A|NAME_A", "B", "C"], ["D", "E", "F"], list("ABCDEFG")],
)
def test_from_index_matches_direct_enrichment(annotations, foreground):
    background = list("ABCDEFG")
    index = go_term_index(annotations, background)
    got = go_enrichment_from_index(index, foreground, background)
    want = go_enrichment(annotations, foreground, background)
    for key in ("fg_total", "bg_total", "fg_count", "bg_count"):
        assert got[key] == want[key]
    for category, table in want["categories"].items():
        pd.testing.assert_frame_equal(
            got["categories"][category], table, check_dtype=False
        )


def test_p_values_are_fishers_exact_test(annotations):
    from scipy.stats import fisher_exact

    table = go_term_table(annotations, {"A", "D"}, set("ABCDE"), "BP")
    # y: both selected proteins, 2 of 5 in the background
    row = table.set_index("GO_Term").loc["y"]
    _, p = fisher_exact([[2, 0], [0, 3]], alternative="greater")
    assert row["p_value"] == pytest.approx(p)
