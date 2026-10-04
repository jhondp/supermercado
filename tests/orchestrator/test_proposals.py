from orchestrator_samples import HEAD, PROPOSALS
from supermercado.orchestrator.proposals import parse_proposals
from supermercado.pipeline.propose import MARKER


def test_candidates_are_grouped_by_item_and_store_in_file_order() -> None:
    section = parse_proposals(f"{HEAD}\n{PROPOSALS}")
    assert list(section.candidates) == [
        ("rice", "jumbo"),
        ("rice", "acuenta"),
        ("spaghetti", "jumbo"),
    ]
    assert [c.sku for c in section.candidates[("rice", "jumbo")]] == ["100", "101"]
    assert section.week == "2026-W40"
    assert section.malformed == 0
    assert section.total == 4


def test_candidate_fields_are_parsed_from_the_entry_and_its_note() -> None:
    section = parse_proposals(PROPOSALS)
    first = section.candidates[("rice", "jumbo")][1]
    assert first.item_id == "rice"
    assert first.store == "jumbo"
    assert first.size == 1.0
    assert first.name == "Arroz Dos 1 kg"
    assert first.brand == "Marca B"
    assert first.price == 1050
    assert first.unit_price == 1050
    assert first.unit == "kg"
    assert first.url == "https://www.jumbo.cl/arroz-dos/p"


def test_note_without_url_or_brand_still_parses() -> None:
    text = (
        f"{MARKER}\n# rice:\n"
        '#   acuenta: { sku: "200", size: 1, approved: 2026-10-04 }  # Arroz | $850 -> $850/kg\n'
    )
    (candidate,) = parse_proposals(text).candidates[("rice", "acuenta")]
    assert candidate.name == "Arroz"
    assert candidate.brand is None
    assert candidate.url is None
    assert candidate.price == 850


def test_malformed_lines_are_skipped_and_counted() -> None:
    text = (
        f"{MARKER}\n# week: 2026-W40\n"
        '#   jumbo: { sku: "1", size: 1, approved: 2026-10-04 }  # before any item | $1 -> $1/kg\n'
        "# rice:\n"
        "#   jumbo: { sku: 100, size: 1 }  # unquoted and incomplete\n"
        '#   jumbo: { sku: "100", size: abc, approved: 2026-10-04 }  # A | $1 -> $1/kg\n'
        "#   garbage line\n"
        '#   jumbo: { sku: "102", size: 1, approved: 2026-10-04 }  # Ok | B | $900 -> $900/kg\n'
    )
    section = parse_proposals(text)
    assert section.malformed == 4
    assert [c.sku for c in section.candidates[("rice", "jumbo")]] == ["102"]


def test_lider_manual_note_is_not_an_item_or_malformed() -> None:
    section = parse_proposals(PROPOSALS)
    assert all(store != "lider" for _, store in section.candidates)
    assert all(item != "lider" for item, _ in section.candidates)
    assert section.malformed == 0


def test_head_comments_are_ignored_and_missing_section_is_empty() -> None:
    section = parse_proposals(HEAD)
    assert section.candidates == {}
    assert section.week is None
    assert section.total == 0
