from ai.rag.chunking import chunk_document

LABEL = """WARNINGS
Use caution with other drugs that affect the liver.

DRUG INTERACTIONS
""" + ("alpha beta gamma delta " * 100)


def test_chunks_follow_sections_and_size():
    chunks = chunk_document(LABEL)
    assert {c["section"] for c in chunks} == {"WARNINGS", "DRUG INTERACTIONS"}
    assert all(c["token_count"] <= 180 for c in chunks)
    assert len([c for c in chunks if c["section"] == "DRUG INTERACTIONS"]) >= 2
