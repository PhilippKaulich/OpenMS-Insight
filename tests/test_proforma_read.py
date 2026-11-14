"""ProForma 2.0 read by pyOpenMS for the sequence view (openms_insight.core.proforma)."""

import pytest

pytest.importorskip("pyopenms")

from openms_insight.components.protein_sequence_view import proforma_text  # noqa: E402
from openms_insight.core import proforma  # noqa: E402

if not proforma.available():  # pragma: no cover - older pyopenms
    pytest.skip("pyopenms without ProForma", allow_module_level=True)

LIBRARY = [
    "Carbamidomethyl (C)",
    "Oxidation (M)",
    "Acetyl (N-term)",
    "Acetyl (K)",
    "Phospho (S)",
]


def spans(read):
    return [
        (m["start"], m["end"], round(m["mass"], 3), m["label"])
        for m in read["modifications"]
    ]


def test_plain_sequence():
    read = proforma.read_proforma("MNKT", LIBRARY, LIBRARY)
    assert read == {"sequence": "MNKT", "fixed_ids": [], "modifications": []}


def test_residue_terminal_and_fixed():
    read = proforma.read_proforma(
        "<[Carbamidomethyl]@C>[Acetyl]-PEK[Acetyl]S[UNIMOD:21]C-[Amidated]",
        LIBRARY,
        LIBRARY,
    )
    assert read["sequence"] == "PEKSC"
    assert read["fixed_ids"] == ["Carbamidomethyl (C)"]
    assert spans(read) == [
        (2, 2, 42.011, "Acetyl (K)"),
        (3, 3, 79.966, "Phospho (S)"),
        (-1, -1, 42.011, "Acetyl (N-term)"),
        (5, 5, -0.984, "Amidated"),
    ]


def test_range_and_unlocalized():
    read = proforma.read_proforma("[+42.0106]^2?EM(EVTS)[+79.966]ESPEK")
    assert read["sequence"] == "EMEVTSESPEK"
    assert spans(read) == [
        (2, 5, 79.966, "+79.9660"),
        (0, 10, 42.011, "+42.0106"),
        (0, 10, 42.011, "+42.0106"),
    ]


def test_alternatives_and_formula():
    assert spans(proforma.read_proforma("PEP[Oxidation|+15.995]M")) == [
        (2, 2, 15.995, "Oxidation")
    ]
    assert spans(proforma.read_proforma("PEPT[Formula:HPO3]K")) == [
        (3, 3, 79.966, "Formula:HPO3")
    ]


@pytest.mark.parametrize(
    "text, message",
    [
        ("PEPT[Phospho#g1]S[#g1]K", "Position groups"),
        ("{Glycan:Hex}PEPK", "Labile"),
        ("PEPXK", "mass gaps"),
        ("PEP[Foo]K", r"Cannot find the mass of \[Foo\]"),
        ("PEP[", "Not a ProForma"),
    ],
)
def test_refused_with_a_message(text, message):
    with pytest.raises(proforma.ProFormaReadError, match=message):
        proforma.read_proforma(text)


def test_glycans_info_and_charge():
    assert spans(proforma.read_proforma("PEP[Glycan:Hex]K")) == [
        (2, 2, 162.053, "Glycan:Hex")
    ]
    assert spans(proforma.read_proforma("PEPN[Glycan:HexNAc2Hex3]K")) == [
        (3, 3, 892.317, "Glycan:HexNAc2Hex3")
    ]
    # INFO tags carry no mass: alone they leave no modification
    assert spans(proforma.read_proforma("PEPS[INFO:checked]K")) == []
    assert spans(
        proforma.read_proforma("PEPS[Phospho|INFO:checked]K", LIBRARY, LIBRARY)
    ) == [(3, 3, 79.966, "Phospho (S)")]
    # the charge is read and left out: the view shows the proteoform
    assert proforma.read_proforma("PEPTIDE/2")["sequence"] == "PEPTIDE"


def test_names_resolve_for_their_residue():
    assert spans(
        proforma.read_proforma("PEPY[Phospho]K", LIBRARY, ["Phospho (Y)"])
    ) == [(3, 3, 79.966, "Phospho (Y)")]
    # a PSI-MOD accession without a Unimod entry is named, not shown raw
    assert spans(proforma.read_proforma("PEPM[MOD:00719]K")) == [
        (3, 3, 15.995, "oxidation to L-methionine sulfoxide")
    ]


@pytest.mark.parametrize(
    "text, message",
    [
        ("A//B", "Chimeric or cross-linked"),
        ("PEP[Glycan:Foo]K", r"Cannot find the mass of \[Glycan:Foo\]"),
    ],
)
def test_more_refused_with_a_message(text, message):
    with pytest.raises(proforma.ProFormaReadError, match=message):
        proforma.read_proforma(text)


def test_view_answer_is_not_read_again(mock_streamlit, temp_cache_dir):
    """The app asks, the view answers with by="view": the answer is not read
    again, and further renders with it give the same payload (no rerun)."""
    import polars as pl

    from openms_insight import ProteinSequenceView

    view = ProteinSequenceView(
        cache_id="proforma_round_trip",
        data=pl.LazyFrame(
            {"scan_idx": [0], "masses": [[1.0]], "precursor_mass": [500.0]}
        ),
        filters={"scan": "scan_idx"},
        sequence={"sequence": list("PEPSK")},
        sequence_identifier="sequence",
        proforma_identifier="proforma",
        cache_path=str(temp_cache_dir),
    )
    assert "proforma" in view.get_state_dependencies()
    asked = {"scan": 0, "proforma": {"text": "PEPS[Phospho]K", "by": "app", "n": 1}}
    read = view._prepare_vue_data(asked)["proformaRead"]
    assert read["text"] == "PEPS[Phospho]K" and read["sequence"] == "PEPSK"

    answered = {"scan": 0, "proforma": {"text": "PEPS[Phospho]K", "by": "view", "n": 1}}
    first = view._prepare_vue_data(answered)
    assert "proformaRead" not in first
    assert view._prepare_vue_data(answered)["_hash"] == first["_hash"]
    # a plain string is the app's, and read
    assert "proformaRead" in view._prepare_vue_data({"scan": 0, "proforma": "PEPK"})


def test_link_text():
    assert proforma_text("PEPK") == "PEPK"
    assert proforma_text({"text": "PEPK", "by": "view", "n": 3}) == "PEPK"
    assert proforma_text(None) == ""
