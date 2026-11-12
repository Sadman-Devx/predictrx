from ai.rag.chunking import chunk_document, chunk_section, split_sentences

LABEL = """WARNINGS
Use caution with other drugs that affect the liver.

DRUG INTERACTIONS
""" + ("alpha beta gamma delta " * 100)


def words(text: str) -> int:
    return len(text.split())


def test_chunks_follow_sections_and_size():
    chunks = chunk_document(LABEL)
    assert {c["section"] for c in chunks} == {"WARNINGS", "DRUG INTERACTIONS"}
    assert all(c["token_count"] <= 180 for c in chunks)
    assert len([c for c in chunks if c["section"] == "DRUG INTERACTIONS"]) >= 2


def test_sentences_are_never_cut_and_chunks_overlap():
    body = " ".join(f"Sentence number {i} says something about the same drug." for i in range(40))
    chunks = chunk_section(body, max_words=60, overlap=20)
    assert len(chunks) >= 5
    assert all(words(c) <= 60 for c in chunks)
    assert all(c.startswith("Sentence") and c.endswith("drug.") for c in chunks)  # whole sentences only
    assert split_sentences(chunks[0])[-1] in chunks[1]  # the tail of one chunk reappears in the next
    covered = {s for c in chunks for s in split_sentences(c)}
    assert covered == set(split_sentences(body))  # nothing lost


def test_sentence_without_punctuation_falls_back_to_word_windows():
    chunks = chunk_section("alpha " * 500)
    assert len(chunks) >= 3
    assert all(words(c) <= 180 for c in chunks)


def test_short_sentence_before_a_huge_one_is_not_left_as_a_tiny_chunk():
    chunks = chunk_section("Short lead sentence here. " + "Alpha " * 300)
    assert chunks[0].startswith("Short lead sentence here.")
    assert all(words(c) > 100 for c in chunks)


def test_known_abbreviation_does_not_end_a_sentence():
    parts = split_sentences("Avoid combining with anticoagulants, e.g. Warfarin or heparin. Monitor INR.")
    assert parts == ["Avoid combining with anticoagulants, e.g. Warfarin or heparin.", "Monitor INR."]


def test_semantic_boundary_starts_a_new_chunk_at_topic_change():
    alpha = " ".join(f"Alpha topic sentence number {n} has eight words." for n in ("one", "two", "three"))
    beta = " ".join(f"Beta topic sentence number {n} has eight words." for n in ("one", "two", "three"))
    body = f"{alpha} {beta}"  # 48 words, two topics
    fake_embed = lambda sentences: [[1.0, 0.0] if s.startswith("Alpha") else [0.0, 1.0] for s in sentences]  # noqa: E731

    plain = chunk_section(body, max_words=40, overlap=5)
    semantic = chunk_section(body, max_words=40, overlap=5, embed_fn=fake_embed)

    assert "Beta" in plain[0]  # size-only packing runs on into the second topic
    assert len(semantic) == 2
    assert "Beta" not in semantic[0] and "Alpha" not in semantic[1]  # the topic change is the cut point