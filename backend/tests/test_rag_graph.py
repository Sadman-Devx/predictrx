"""Graph edges, pair retrieval and indexing. The corpus below is synthetic (NOT real label text)."""
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.utils import timezone

from ai.rag import graph, indexer, retriever
from ai.rag.embeddings import EmbeddingError
from apps.drugs.models import Drug
from apps.knowledge.models import Chunk, GraphEdge, KnowledgeDocument


def one_hot(i: int) -> list[float]:
    vec = [0.0] * settings.EMBEDDING_DIM
    vec[i] = 1.0
    return vec


@pytest.fixture
def corpus(db):
    warfarin = Drug.objects.create(generic_name="warfarin")
    aspirin = Drug.objects.create(generic_name="aspirin", aliases=["acetylsalicylic acid"])
    digoxin = Drug.objects.create(generic_name="digoxin")

    def document(drug, n):
        return KnowledgeDocument.objects.create(
            source="openfda_label", drug=drug, title=f"{drug.generic_name} synthetic label",
            fetched_at=timezone.now(), content_hash=f"synthetic-{n}", license_note="synthetic test data")

    doc_w, doc_a = document(warfarin, 1), document(aspirin, 2)
    c1 = Chunk.objects.create(document=doc_w, section="DRUG INTERACTIONS",
                              text="Acetylsalicylic acid may increase the risk of bleeding with warfarin.")
    c2 = Chunk.objects.create(document=doc_w, section="WARNINGS",
                              text="Warfarin can cause major or fatal bleeding. Monitor INR regularly.")
    c3 = Chunk.objects.create(document=doc_a, section="WARNINGS",
                              text="Aspirin increases bleeding risk. Concomitant warfarin use needs caution.")
    c4 = Chunk.objects.create(document=doc_a, section="CONTRAINDICATIONS",
                              text="Do not use with hypersensitivity. Digoxin is listed here for the test.")
    return SimpleNamespace(warfarin=warfarin, aspirin=aspirin, digoxin=digoxin, c1=c1, c2=c2, c3=c3, c4=c4)


def test_find_mentions_uses_names_and_aliases_as_whole_words(corpus):
    index = graph.build_name_index()
    found = graph.find_mentions("Acetylsalicylic acid and WARFARIN; not warfarinish.", index)
    assert found == {corpus.aspirin.id, corpus.warfarin.id}
    assert graph.mentions_drug(corpus.c1.text, corpus.aspirin)  # via the alias
    assert not graph.mentions_drug(corpus.c2.text, corpus.aspirin)


def test_rebuild_edges_builds_mention_and_pair_edges_and_is_idempotent(corpus):
    stats = graph.rebuild_edges()
    assert stats["documents"] == 2 and stats["chunks"] == 4
    assert stats["mention_edges"] == 3  # c1 -> aspirin, c3 -> warfarin, c4 -> digoxin (own drug is never a target)
    assert stats["pair_edges"] == 2
    assert GraphEdge.objects.filter(relation=graph.REL_INTERACTS, src_id=corpus.warfarin.id,
                                    dst_id=corpus.aspirin.id, chunk=corpus.c1).exists()
    assert GraphEdge.objects.filter(relation=graph.REL_CONTRAINDICATED, src_id=corpus.aspirin.id,
                                    dst_id=corpus.digoxin.id, chunk=corpus.c4).exists()
    assert GraphEdge.objects.count() == 5

    graph.rebuild_edges()
    assert GraphEdge.objects.count() == 5  # rebuilt, not duplicated


def test_chunks_linking_works_in_both_directions_and_ranks_by_section(corpus):
    graph.rebuild_edges()
    expected = [corpus.c1.id, corpus.c3.id]  # DRUG INTERACTIONS before WARNINGS; c2 and c4 do not link the pair
    assert [c.id for c in graph.chunks_linking(corpus.warfarin.id, corpus.aspirin.id)] == expected
    assert [c.id for c in graph.chunks_linking(corpus.aspirin.id, corpus.warfarin.id)] == expected


def test_pair_retrieval_falls_back_to_graph_when_embeddings_are_down(corpus, monkeypatch):
    graph.rebuild_edges()

    def down(text):
        raise EmbeddingError("ollama down")

    monkeypatch.setattr(retriever, "embed_query", down)
    result = retriever.retrieve_for_pair("warfarin", "acetylsalicylic acid")  # alias resolves to aspirin
    assert result.mode == "graph_only"
    assert [c.chunk_id for c in result.chunks] == [corpus.c1.id, corpus.c3.id]
    assert all(c.supports_pair and c.via == ["graph"] for c in result.chunks)
    assert any("graph only" in w for w in result.warnings)


def test_pair_retrieval_hybrid_marks_only_passages_naming_both_drugs_as_citable(corpus, monkeypatch):
    graph.rebuild_edges()
    for chunk, i in ((corpus.c1, 0), (corpus.c2, 1), (corpus.c3, 2), (corpus.c4, 3)):
        Chunk.objects.filter(pk=chunk.pk).update(embedding=one_hot(i))
    monkeypatch.setattr(retriever, "embed_query", lambda text: one_hot(0))

    result = retriever.retrieve_for_pair("warfarin", "aspirin", k=5)

    assert result.mode == "hybrid"
    assert [c.chunk_id for c in result.evidence_chunks] == [corpus.c1.id, corpus.c3.id]
    assert [c.chunk_id for c in result.chunks] == [corpus.c1.id, corpus.c3.id, corpus.c4.id, corpus.c2.id]
    best = result.chunks[0]
    assert best.via == ["vector", "graph"] and best.distance == pytest.approx(0.0, abs=1e-6)
    assert best.as_evidence() == {"type": "chunk", "id": corpus.c1.id, "source": "openfda_label"}
    assert not result.chunks[2].supports_pair  # c4 / c2: label context only, must not be cited


def test_unknown_drug_gives_no_chunks_instead_of_a_guess(corpus):
    result = retriever.retrieve_for_pair("warfarin", "nonexistentium")
    assert result.mode == "none" and result.chunks == [] and result.warnings


def test_index_pending_embeds_only_missing_chunks_and_writes_prefixes(corpus, monkeypatch):
    monkeypatch.setattr(indexer, "embed_texts", lambda texts: [one_hot(0) for _ in texts])

    first = indexer.index_pending(batch_size=2, context_mode="template")
    assert first.pending_before == 4 and first.chunks_embedded == 4 and first.prefixes_generated == 4
    assert Chunk.objects.filter(embedding__isnull=True).count() == 0
    prefix = Chunk.objects.get(pk=corpus.c1.pk).context_prefix
    assert prefix.startswith("Source: openfda_label. Drug: warfarin. Section: DRUG INTERACTIONS.")

    second = indexer.index_pending(batch_size=2, context_mode="template")
    assert second.pending_before == 0 and second.chunks_embedded == 0