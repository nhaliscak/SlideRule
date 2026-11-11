"""References that have not been fully checked against a source (the rest were looked up: journal articles in Crossref, books in Open Library, the others by web search; see PROJECT_LOG.md, "Citation check" and the follow-up of 2026-10-30).

calculation id -> [(text that appears in the reference, what is unverified)]. The page flags the matching reference; a test keeps every entry pointing at a reference
that still contains its text, so correcting a citation means deleting its entry here.
"""

UNVERIFIED: dict[str, list[tuple[str, str]]] = {
    "green.lca.gwp_co2_equivalent": [("IPCC AR6", "The values (fossil methane 29.8, non-fossil 27.0, N₂O 273, SF₆ 25 200, and 27.9 without methane oxidation) agree with secondary sources that quote Table 7.15 and Supplementary Table 7.SM.7, but the report itself was not opened, and one source numbers the supplementary table 7.SM.6: check the table number.")],
}


def notes_for(calc_id: str, references: list[str]) -> list[dict]:
    """The unverified notes of a calculation, each with the full reference text it belongs to."""
    out = []
    for fragment, note in UNVERIFIED.get(calc_id, []):
        ref = next((r for r in references if fragment in r), None)
        if ref is not None:
            out.append({"reference": ref, "note": note})
    return out
