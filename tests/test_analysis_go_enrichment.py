"""GO enrichment of a selected set of proteins (no network: annotations given)."""

import pandas as pd
import pytest

pytest.importorskip("mygene")
pytest.importorskip("scipy")

from openms_insight.analysis.enrichment import (  # noqa: E402
    benjamini_hochberg,
    fetch_go_annotations,
    go_enrichment,
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
