"""Residues between the masses of a sequence tag (openms_insight.core.tag_ladder)."""

from itertools import accumulate

from openms_insight.core.tag_ladder import RESIDUE_MASSES, ladder_steps


def _masses(start, residues):
    return [start] + [
        start + m for m in accumulate(RESIDUE_MASSES[r] for r in residues)
    ]


def _labels(masses, sequence):
    steps = ladder_steps(masses, sequence)
    return None if steps is None else [sequence[a:b] for a, b in steps]


def test_one_residue_per_gap_reads_backwards():
    # A C-terminal tag: masses rise from the C-terminus, so the gaps read SNEDY
    sequence = "YDENS"
    masses = _masses(1349.81, sequence[::-1])
    assert _labels(masses, sequence) == ["S", "N", "E", "D", "Y"]
    # Descending masses of an N-terminal tag also read it backwards
    assert _labels(masses[::-1], sequence[::-1]) == ["Y", "D", "E", "N", "S"]


def test_one_residue_per_gap_forwards_when_masses_say_so():
    masses = _masses(3607.11, "AGL")
    assert _labels(masses, "AGL") == ["A", "G", "L"]


def test_isobaric_tag_keeps_backward_reading():
    # Q and K differ by 0.036 Da: no clear direction, the usual reading stays
    masses = _masses(4749.59, "QLK")
    assert _labels(masses, "QLK") == ["K", "L", "Q"]


def test_gaps_with_several_residues():
    # The long tag of a proteoform: fragments missing between some masses
    sequence = "TLKVGLNGFGSVVDLTVRLEKWYDNETGYSN"
    rev = sequence[::-1]
    cuts = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 20, 21, 31]
    prefix = [0.0] + list(accumulate(RESIDUE_MASSES[r] for r in rev))
    masses = [1235.77 + prefix[c] for c in cuts]
    labels = _labels(masses, sequence)
    assert labels == [rev[a:b][::-1] for a, b in zip(cuts, cuts[1:], strict=False)]
    assert "".join(reversed(labels)) == sequence


def test_gap_off_by_an_isotope_still_placed():
    sequence = "PAFVSGKALKDAV"
    masses = _masses(8098.37, sequence)
    masses = [masses[0], masses[7] + 0.08, masses[12] - 1.0, masses[13]]
    assert _labels(masses, sequence) == ["PAFVSGK", "ALKDA", "V"]


def test_residues_that_do_not_account_for_the_gaps():
    assert _labels([1000.0, 1100.0, 1500.0], "GGGGGGGG") is None
    assert _labels([1000.0], "G") is None
    assert _labels([1000.0, 1057.02], "") is None


def test_unknown_residue_one_per_gap_falls_back_to_backwards():
    assert _labels([1000.0, 1100.0, 1200.0], "XB") == ["B", "X"]
