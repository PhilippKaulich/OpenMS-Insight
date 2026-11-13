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


def test_link_text():
    assert proforma_text("PEPK") == "PEPK"
    assert proforma_text({"text": "PEPK", "by": "view", "n": 3}) == "PEPK"
    assert proforma_text(None) == ""
