"""Embedding client and contextual-prefix tests. No Ollama, no network: the HTTP call and the LLM are replaced."""
import pytest

from ai.rag import contextual, embeddings
from ai.rag.contextual import context_prefix, embedding_text, generate_context_prefix
from ai.rag.embeddings import EmbeddingDimensionError, EmbeddingNotConfigured

ARGS = {"drug_name": "warfarin", "section": "DRUG INTERACTIONS", "source": "openfda_label", "text": "some passage"}


def test_embed_requires_a_configured_model(settings):
    settings.EMBEDDING_MODEL = ""
    with pytest.raises(EmbeddingNotConfigured):
        embeddings.embed_texts(["x"])


def test_embed_texts_sends_batches_in_order(settings, monkeypatch):
    settings.EMBEDDING_MODEL, settings.EMBEDDING_DIM, settings.EMBEDDING_BATCH_SIZE = "dummy", 2, 2
    calls = []

    def fake_post(batch):
        calls.append(list(batch))
        return {"embeddings": [[1.0, 0.0] for _ in batch]}

    monkeypatch.setattr(embeddings, "_post", fake_post)
    out = embeddings.embed_texts(["a", "b", "c"])
    assert len(out) == 3
    assert calls == [["a", "b"], ["c"]]


def test_embed_texts_rejects_wrong_dimension(settings, monkeypatch):
    settings.EMBEDDING_MODEL, settings.EMBEDDING_DIM = "dummy", 3
    monkeypatch.setattr(embeddings, "_post", lambda batch: {"embeddings": [[0.1, 0.2] for _ in batch]})
    with pytest.raises(EmbeddingDimensionError):
        embeddings.embed_texts(["x"])


def test_embed_texts_rejects_blank_text(settings):
    settings.EMBEDDING_MODEL = "dummy"
    with pytest.raises(ValueError):
        embeddings.embed_texts(["  "])


def test_template_prefix_is_the_default(settings):
    settings.RAG_CONTEXT_MODE = "template"
    assert generate_context_prefix(**ARGS) == context_prefix(drug_name="warfarin", section="DRUG INTERACTIONS",
                                                             source="openfda_label")


def test_model_failure_falls_back_to_the_template(settings, monkeypatch):
    settings.RAG_CONTEXT_MODE = "local"

    def boom(prompt, **kwargs):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(contextual, "local_complete", boom)
    template = context_prefix(drug_name="warfarin", section="DRUG INTERACTIONS", source="openfda_label")
    assert generate_context_prefix(**ARGS) == template


def test_model_sentence_comes_after_the_template(settings, monkeypatch):
    settings.RAG_CONTEXT_MODE = "local"
    monkeypatch.setattr(contextual, "local_complete", lambda prompt, **kw: '  "Describes bleeding risk."  ')
    template = context_prefix(drug_name="warfarin", section="DRUG INTERACTIONS", source="openfda_label")
    prefix = generate_context_prefix(**ARGS)
    assert prefix.startswith(template) and prefix.endswith("Describes bleeding risk.")


def test_embedding_text_puts_the_prefix_first():
    assert embedding_text("PREFIX", "body") == "PREFIX\n\nbody"
    assert embedding_text("", "body") == "body"