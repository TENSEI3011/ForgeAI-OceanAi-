from forgeai.ingest import chunk_documents, load_documents
from forgeai.textutil import contains_quote, extract_ids, extract_numbers, fact_in_text, is_refusal

REFUSAL = "I'm sorry, I can't answer that from the documents I have access to."


def test_chunking_keeps_headings_pages_and_rows(tmp_path):
    prose = "## 1. Leave\n\n" + " ".join(f"Sentence number {i} says staff get {i} days." for i in range(60))
    (tmp_path / "policy.md").write_text(prose, encoding="utf-8")
    (tmp_path / "table.csv").write_text("id,price\nX-1,5\nX-2,7\n", encoding="utf-8")
    (tmp_path / "ignored.xyz").write_text("binary", encoding="utf-8")
    docs, skipped = load_documents(tmp_path)
    assert skipped == ["ignored.xyz"]
    chunks = chunk_documents(docs, chunk_size=400, overlap=80)
    prose_chunks = [c for c in chunks if c.source == "policy.md"]
    assert len(prose_chunks) > 3
    assert all(len(c.text) <= 400 + 120 for c in prose_chunks)
    assert all(c.heading == "1. Leave" for c in prose_chunks)
    rows = [c for c in chunks if c.source == "table.csv" and c.row]
    assert [c.text for c in rows] == ["id: X-1 | price: 5", "id: X-2 | price: 7"]
    # the end of the text is never lost
    assert "59 days" in prose_chunks[-1].text


def test_numbers_ids_and_facts():
    assert {"1250.5", "10", "15", "21"} <= extract_numbers("USD 1,250.50 for 10-15 days, twenty-one")
    assert "2040" not in extract_numbers("part HX-2040")
    assert extract_ids("Part ME-1042, a 24-month warranty") == {"me-1042"}
    assert fact_in_text("21 working days", "You get 21 working days of leave.")
    assert not fact_in_text("21 working days", "You get 24 working days of leave.")
    assert fact_in_text("requires manager approval", "It must be approved by your line manager.")


def test_quote_matching_is_tolerant_to_pdf_whitespace_only():
    doc = "Claims must be submitted\nwithin 30 days of the end of the trip."
    assert contains_quote("Claims must be submitted within 30 days of the end of the trip.", doc)
    assert not contains_quote("Claims must be submitted within 45 days of the end of the trip.", doc, 95)


def test_refusal_detection():
    assert is_refusal(REFUSAL, REFUSAL)
    assert is_refusal("The documents don't mention salary credit dates.", REFUSAL)
    # a real answer with a caveat is NOT a refusal
    assert not is_refusal("Annual leave is 21 working days per year for staff with under 5 years of service "
                          "[source: leave_policy.pdf]. Staff with 5 or more years get 24 days, accrued monthly, "
                          "and up to 10 days can be carried forward. The documents do not cover payroll.", REFUSAL)
    # short partial answers with a citation are answers too
    assert not is_refusal("Hot work permits are valid for a maximum of 8 hours [source: ptw.txt]. "
                          "The documents do not specify who countersigns them.", REFUSAL)
    # a refusal plus an uncited pointer is still a refusal
    assert is_refusal(REFUSAL + " Please contact the HR Helpdesk on extension 2210 for help.", REFUSAL)
    # opening with the refusal sentence is a refusal even if a long explanation follows
    assert is_refusal(REFUSAL + " The documents list several parts for other vessel classes, such as the fuel "
                      "injector nozzle set [source: catalogue.csv], but nothing about generators for this ship "
                      "type, its budget ranges or recommended brands for that size of vessel.", REFUSAL)
