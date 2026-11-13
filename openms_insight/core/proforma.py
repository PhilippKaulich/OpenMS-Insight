"""Read a ProForma 2.0 proteoform with OpenMS's own parser (pyOpenMS).

``read_proforma(text)`` returns what a sequence view shows: the residues, the
global fixed modifications, and every modification as a span of residues with
its mass shift. A span of one residue is a localized modification; a longer
span is a modification somewhere in it: an ambiguous range (``(EVTS)[+79.97]``)
or an unlocalized one (``[+42.0106]?SEQ``, ``[Phospho]^2?SEQ``), which may sit
anywhere in the sequence. Names, Unimod/PSI-MOD accessions, formulas and mass
shifts are read; of alternatives (``[Oxidation|+15.995]``) the first that has
a mass counts. Position groups (``#g1``), labile modifications (``{...}``),
cross-links and charged or chimeric proteoforms are refused with a message.

Needs pyopenms (``ProForma`` in pyOpenMS 3.6 or later).
"""

from __future__ import annotations

import json
from typing import Any


class ProFormaReadError(ValueError):
    """A ProForma the view cannot show, with a message for the user."""


def available() -> bool:
    """Whether the installed pyopenms has a ProForma parser."""
    try:
        import pyopenms
    except ImportError:
        return False
    return hasattr(pyopenms, "ProForma")


def _db():
    from pyopenms import ModificationsDB

    return ModificationsDB()


def _named_mass(name: str) -> tuple[float, str] | None:
    """Mass shift and id of a modification name or accession, or None."""
    try:
        mod = _db().getModification(name)
    except Exception:  # pragma: no cover - unknown names raise in pyOpenMS
        return None
    if mod is None:
        return None
    mod_id = mod.getId()
    mod_id = mod_id.decode() if isinstance(mod_id, bytes) else str(mod_id)
    return float(mod.getDiffMonoMass()), mod_id or name


def _tag_mass(tags: list[dict[str, Any]]) -> tuple[float, str | None]:
    """Mass shift and name of one modification (its alternatives in order)."""
    for entry in tags:
        if "label" in entry:
            raise ProFormaReadError(
                "Position groups (#g1) are not supported yet: give the "
                "modification on one residue or as a range, (EVTS)[+79.97]"
            )
        tag = entry.get("tag", {})
        kind, value = tag.get("type"), tag.get("value", {})
        if kind == "mass_delta":
            return float(value["mass"]), None
        if kind == "named_mod":
            found = _named_mass(value["name"])
            if found:
                return found[0], value["name"]
        elif kind == "cv_accession":
            database = {"UNIMOD": "UNIMOD", "MOD": "MOD"}.get(
                value.get("database", "").upper()
            )
            if database:
                found = _named_mass(f"{database}:{value['accession']}")
                if found:
                    return found[0], found[1]
        elif kind == "formula":
            from pyopenms import EmpiricalFormula

            formula = value["formula_string"]
            return float(
                EmpiricalFormula(formula).getMonoWeight()
            ), f"Formula:{formula}"

    def describe(entry: dict[str, Any]) -> str:
        value = entry.get("tag", {}).get("value", {})
        if "accession" in value:
            return f"{value.get('database', '')}:{value['accession']}"
        return str(
            value.get("name")
            or value.get("formula_string")
            or value.get("text")
            or value
        )

    names = " | ".join(describe(t) for t in tags)
    raise ProFormaReadError(
        f"Cannot find the mass of [{names}]: give it as a mass, e.g. [+79.9663]"
    )


def _library_id(
    name: str, site: str, ids: list[str], residue: str | None = None
) -> str | None:
    """Library id of ``name`` at a site, as the view's dialog looks it up."""
    lower = {i.lower(): i for i in ids}
    if site in ("N-term", "C-term"):
        candidates = [
            f"{name} ({site})",
            f"{name} (Protein {site})",
            f"{name} ({site} {residue or ''})",
        ]
    else:
        candidates = [f"{name} ({site})"]
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return lower.get(name.lower())


def read_proforma(
    text: str,
    fixed_library: list[str] | None = None,
    variable_library: list[str] | None = None,
) -> dict[str, Any]:
    """The residues and modifications of a ProForma 2.0 proteoform.

    Args:
        text: ProForma, or a plain sequence of one-letter codes.
        fixed_library: Ids of the fixed modifications the view offers
            (``'Carbamidomethyl (C)'``); global modifications are given as
            these ids.
        variable_library: Ids of the variable modifications; a named
            modification on one residue is labelled with its id there.

    Returns:
        ``sequence`` (str), ``fixed_ids`` (list of library ids) and
        ``modifications``: dicts with ``start`` and ``end`` (0-based residues,
        inclusive; -1 the N-terminus, the sequence length the C-terminus),
        ``mass`` and ``label``.

    Raises:
        ProFormaReadError: the text cannot be read or shown.
        ImportError: pyopenms has no ProForma parser.
    """
    from pyopenms import ProForma

    text = "".join(text.split())
    if not text:
        return {"sequence": "", "fixed_ids": [], "modifications": []}
    try:
        data = json.loads(ProForma.toJSON(ProForma.parse(text)))
    except Exception as e:
        message = str(e).split("\n")[0]
        raise ProFormaReadError(f"Not a ProForma proteoform: {message}") from e
    if data.get("labile_mods"):
        raise ProFormaReadError("Labile modifications ({...}) are not supported yet")

    residues: list[str] = []
    spans: list[tuple[int, int, list]] = []
    for element in data["sequence"]:
        value = element["value"]
        if element["type"] == "modified_range":
            first = len(residues)
            for inner in value["elements"]:
                residues.append(inner["amino_acid"])
                for tags in inner.get("modifications") or []:
                    spans.append((len(residues) - 1, len(residues) - 1, tags))
            for tags in value.get("modifications") or []:
                spans.append((first, len(residues) - 1, tags))
        else:
            residues.append(value["amino_acid"])
            for tags in value.get("modifications") or []:
                spans.append((len(residues) - 1, len(residues) - 1, tags))
    sequence = "".join(residues)
    if not sequence:
        raise ProFormaReadError("No residues")
    if "X" in sequence or "B" in sequence or "Z" in sequence or "J" in sequence:
        raise ProFormaReadError(
            "Ambiguous residues and mass gaps (X, B, Z, J) are not supported yet"
        )
    for tags in data.get("n_term_mods") or []:
        spans.append((-1, -1, tags))
    for tags in data.get("c_term_mods") or []:
        spans.append((len(sequence), len(sequence), tags))
    for unlocalized in data.get("unlocalised_mods") or []:
        for tags in unlocalized.get("modifications") or []:
            for _ in range(int(unlocalized.get("occurrence") or 1)):
                spans.append((0, len(sequence) - 1, tags))

    variable_ids = variable_library or []
    modifications = []
    for start, end, tags in spans:
        mass, name = _tag_mass(tags)
        label = name or f"{mass:+.4f}"
        if name and start == end:
            site = (
                "N-term"
                if start < 0
                else "C-term"
                if start >= len(sequence)
                else sequence[start]
            )
            residue = sequence[0] if start < 0 else sequence[-1]
            label = _library_id(name, site, variable_ids, residue) or name
        modifications.append({"start": start, "end": end, "mass": mass, "label": label})

    fixed_ids: list[str] = []
    for glob in data.get("global_mods") or []:
        value = glob["value"]
        if glob["type"] != "global_modification":
            raise ProFormaReadError("Isotope labels (<13C>) are not supported yet")
        tag = value["modification"][0].get("tag", {})
        name = tag.get("value", {}).get("name")
        if not name:
            raise ProFormaReadError(
                "Give a fixed modification by name: <[Carbamidomethyl]@C>"
            )
        for site in value.get("locations") or []:
            site = {"N-term": "N-term", "C-term": "C-term"}.get(site, site)
            residue = sequence[0] if site == "N-term" else sequence[-1]
            found = _library_id(name, site, fixed_library or [], residue)
            if found is None:
                raise ProFormaReadError(f"Unknown fixed modification {name} on {site}")
            if found not in fixed_ids:
                fixed_ids.append(found)
    return {
        "sequence": sequence,
        "fixed_ids": fixed_ids,
        "modifications": modifications,
    }
