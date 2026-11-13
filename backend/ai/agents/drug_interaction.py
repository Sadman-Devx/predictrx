"""Drug Interaction agent (step 3).

For every pair of distinct resolved drugs:
  1. `check_interaction` over MCP (one SSE session for all pairs) -> the interaction table answer,
  2. label passages from RAG (vector + graph); only passages that name BOTH drugs may be cited.

Facts come only from those two sources; this agent writes no medical statement of its own. Severity comes ONLY
from the interaction table. Outcomes per pair:

  record      table has a record      -> severity from the table, evidence = interaction row (+ label passages)
  label_only  no record, but a label names the other drug -> severity `unknown`, evidence = the passages
  no_record   nothing found           -> severity `unknown`, no evidence, "this does not mean safe"

A pair is never reported as safe. A severity is never emitted without evidence (the runner and the model enforce
the same rule; this agent already follows it). Confidence reflects the KIND of evidence, it is not a probability:

  record with severity 0.80  (+0.10 if a label passage also names the pair, -0.20 if sources disagree)
  record without severity 0.30 · label_only 0.35 · no_record 0.00

Every finding: {drug_a_id, drug_b_id, drug_a, drug_b, severity, rationale, confidence, verification_status,
evidence, pair_status, severity_conflict}. `verification_status` stays `unverified` until the Verifier runs.
"""
import itertools
import logging
import time

from apps.drugs.models import Drug, Interaction
from apps.drugs.services import NO_RECORD_NOTE, SEVERITY_RANK

from .. import mcp_client
from ..config import setting
from ..guardrails.output_checks import INSUFFICIENT_EVIDENCE_EN, contains_dosing_language
from ..rag import embeddings
from ..rag.graph import chunks_linking, mentions_drug
from ..rag.retriever import DEFAULT_K, RetrievedChunk, retrieve_for_pair
from .common import ellipsize, traced, with_period

logger = logging.getLogger(__name__)

MAX_CHUNKS_PER_FINDING = 2
CHUNK_EXCERPT_CHARS = 500
SOURCE_TEXT_CHARS = 300
VALID_SEVERITIES = {"minor", "moderate", "major", "unknown"}
SOURCE_NAMES = {"ddinter": "DDInter 2.0", "openfda_label": "openFDA label"}

CONF_RECORD = 0.80
CONF_LABEL_BONUS = 0.10
CONF_CONFLICT_PENALTY = 0.20
CONF_RECORD_NO_SEVERITY = 0.30
CONF_LABEL_ONLY = 0.35


def _src(name) -> str:
    return SOURCE_NAMES.get(name, str(name or "source"))


# ------------------------------------------------------------------------------------------------ label search
class _LabelSearch:
    """RAG for pairs, with a time budget. Vector search needs the local embedding server; the graph part only needs
    the database, so when vector search is unavailable or the budget is spent the remaining pairs use the graph."""

    def __init__(self, drug_ids: list):
        self.drugs = Drug.objects.in_bulk(drug_ids)
        self.vector = embeddings.is_configured()
        self.deadline = time.monotonic() + float(setting("AI_RAG_BUDGET_SECONDS", 20.0))
        self.vector_pairs = 0
        self.graph_pairs = 0
        self.warnings: list = []
        if not self.vector:
            self._note("embeddings not configured: label search uses the graph only")

    def _note(self, text: str) -> None:
        if text not in self.warnings and len(self.warnings) < 5:
            self.warnings.append(text[:200])

    def find(self, a_id: int, b_id: int):
        a, b = self.drugs.get(a_id), self.drugs.get(b_id)
        if a is None or b is None:
            return [], "none"
        if self.vector and time.monotonic() >= self.deadline:
            self.vector = False
            self._note("vector search budget spent: remaining pairs use the graph only")
        if self.vector:
            result = retrieve_for_pair(a, b, k=DEFAULT_K)
            self.vector_pairs += 1
            for w in result.warnings:
                self._note(w)
                if w.startswith("vector search unavailable"):  # message set by ai/rag/retriever.py
                    self.vector = False
            return result.evidence_chunks, result.mode
        self.graph_pairs += 1
        return self._graph_only(a, b), "graph_only"

    @staticmethod
    def _graph_only(a: Drug, b: Drug) -> list:
        out = []
        for chunk in chunks_linking(a.id, b.id, limit=DEFAULT_K * 2):
            owner = chunk.document.drug_id
            if owner not in (a.id, b.id):
                continue
            other = b if owner == a.id else a
            if not mentions_drug(chunk.text, other):
                continue
            out.append(RetrievedChunk(
                chunk_id=chunk.id, document_id=chunk.document_id,
                drug=chunk.document.drug.generic_name if chunk.document.drug_id else "",
                section=chunk.section, text=chunk.text, source=chunk.document.source,
                source_url=chunk.document.source_url, license_note=chunk.document.license_note,
                distance=None, via=["graph"], supports_pair=True,
            ))
        return out

    def summary(self) -> dict:
        return {"tool": "rag", "vector_pairs": self.vector_pairs, "graph_pairs": self.graph_pairs,
                "warnings": list(self.warnings)}


# ------------------------------------------------------------------------------------------------ text helpers
def _source_text(text) -> str:
    """Mechanism / management text copied from the source table. Dropped (not edited) if it reads like dosing."""
    cleaned = ellipsize(text or "", SOURCE_TEXT_CHARS)
    return "" if not cleaned or contains_dosing_language(cleaned) else cleaned


def _label_sentences(a: str, b: str, chunks: list) -> str:
    parts, seen = [], set()
    for c in chunks:
        key = (c.drug, c.section)
        if key in seen:
            continue
        seen.add(key)
        other = b if c.drug == a else a
        parts.append(f"the {c.drug} label ({(c.section or 'general').lower()}) mentions {other}")
    return with_period("; ".join(parts).capitalize()) if parts else ""


def _rationale(a: str, b: str, *, pair_status: str, records: list, conflict: bool, chunks: list, reason: str) -> str:
    parts: list = []
    if pair_status == "record":
        primary = records[0]
        sev = primary.get("severity")
        if sev in ("minor", "moderate", "major"):
            parts.append(f"{_src(primary.get('source'))} lists a {sev} interaction between {a} and {b}.")
        else:
            parts.append(f"{_src(primary.get('source'))} has a record for {a} and {b} but no severity rating.")
        mech = _source_text(primary.get("mechanism"))
        if mech:
            parts.append(f"Mechanism (from source): {with_period(mech)}")
        mgmt = _source_text(primary.get("management"))
        if mgmt:
            parts.append(f"Management note (from source): {with_period(mgmt)}")
        if conflict:
            levels = "; ".join(f"{_src(r.get('source'))}: {r.get('severity')}" for r in records)
            parts.append(f"Sources disagree on severity ({levels}).")
        label = _label_sentences(a, b, chunks)
        if label:
            parts.append(f"Also, {label[0].lower() + label[1:]}")
    elif pair_status == "record_unreferenced":
        parts.append(f"{INSUFFICIENT_EVIDENCE_EN} A record exists but could not be referenced as evidence.")
    elif pair_status == "label_only":
        parts.append("No interaction record found in the interaction table.")
        parts.append(_label_sentences(a, b, chunks))
        parts.append("No severity can be assigned from label text alone. This does not mean the combination is safe.")
    else:
        if reason == "drug_not_found":
            parts.append("A drug name was not found in the interaction table.")
        parts.append(NO_RECORD_NOTE)
    text = " ".join(p for p in parts if p)
    # Safety net: the runner blanks a rationale that reads like dosing; never hand it one.
    return INSUFFICIENT_EVIDENCE_EN if contains_dosing_language(text) else text


# ------------------------------------------------------------------------------------------------ one pair
def _interaction_ids(drug_ids: list) -> dict:
    rows = Interaction.objects.filter(drug_a_id__in=drug_ids, drug_b_id__in=drug_ids).values(
        "id", "drug_a_id", "drug_b_id", "source")
    return {(r["drug_a_id"], r["drug_b_id"], r["source"]): r["id"] for r in rows}


def _build(a: dict, b: dict, result: dict, ix_ids: dict, labels: _LabelSearch):
    a_id, b_id = a["drug_id"], b["drug_id"]  # callers sort by id, so (a_id, b_id) is the table's canonical order
    name_a, name_b = a["generic"], b["generic"]
    chunks, mode = labels.find(a_id, b_id)
    chunks = chunks[:MAX_CHUNKS_PER_FINDING]
    chunk_evidence = [c.as_evidence() for c in chunks]

    records: list = []
    ix_evidence: list = []
    severity, conflict, reason, pair_status = "unknown", False, "", "no_record"
    if result.get("status") == "found":
        records = [result] + list(result.get("other_records") or [])
        for rec in records:
            ix_id = ix_ids.get((a_id, b_id, rec.get("source")))
            if ix_id is not None:
                ix_evidence.append({"type": "interaction", "id": ix_id, "source": str(rec.get("source", ""))})
        if ix_evidence:
            pair_status = "record"
            severity = result.get("severity") if result.get("severity") in VALID_SEVERITIES else "unknown"
            conflict = bool(result.get("severity_conflict"))
        else:
            pair_status = "record_unreferenced"  # cannot cite the row: no severity (rule: no warning without a source)
    else:
        reason = str(result.get("reason", ""))
        if chunks:
            pair_status = "label_only"

    evidence = ix_evidence + chunk_evidence
    if severity != "unknown" and not evidence:
        severity = "unknown"

    if pair_status == "record" and severity != "unknown":
        conf = CONF_RECORD + (CONF_LABEL_BONUS if chunks else 0) - (CONF_CONFLICT_PENALTY if conflict else 0)
    elif pair_status == "record":
        conf = CONF_RECORD_NO_SEVERITY
    elif pair_status == "label_only":
        conf = CONF_LABEL_ONLY
    else:
        conf = 0.0

    finding = {
        "drug_a_id": a_id, "drug_b_id": b_id, "drug_a": name_a, "drug_b": name_b,
        "severity": severity,
        "rationale": _rationale(name_a, name_b, pair_status=pair_status, records=records, conflict=conflict,
                                chunks=chunks, reason=reason),
        "confidence": round(max(0.0, min(1.0, conf)), 2),
        "verification_status": "unverified",
        "evidence": evidence,
        "pair_status": pair_status,
        "severity_conflict": conflict,
    }
    call_ref = {
        "tool": "check_interaction", "args": {"drug_a": name_a, "drug_b": name_b},
        "result": {"status": result.get("status"), "severity": result.get("severity"),
                   "source": result.get("source"), "interaction_ids": [e["id"] for e in ix_evidence]},
        "label_chunks": [c.chunk_id for c in chunks], "label_mode": mode,
    }
    chunk_rows = [{"pair": [name_a, name_b], "chunk_id": c.chunk_id, "document_id": c.document_id, "drug": c.drug,
                   "section": c.section, "source": c.source, "via": list(c.via), "distance": c.distance,
                   "text": ellipsize(c.text, CHUNK_EXCERPT_CHARS)} for c in chunks]
    return finding, chunk_rows, call_ref


# ------------------------------------------------------------------------------------------------ node
def run(state: dict) -> dict:
    trace: list = []
    drugs = sorted(state.get("resolved_drugs") or [], key=lambda d: d["drug_id"])
    pairs = list(itertools.combinations(drugs, 2))
    with traced(trace, "drug_interaction", 3, f"{len(drugs)} drugs, {len(pairs)} pairs") as t:
        if not pairs:
            t["output_summary"] = "fewer than two resolved drugs: nothing to check"
            return {"findings": [], "retrieved_chunks": [], "trace": trace}

        # ToolCallError is NOT caught here: without the interaction table there is no honest finding to make,
        # so the run fails visibly (runner -> status `failed`) instead of reporting "no record" for everything.
        batch = mcp_client.call_tools(
            [("check_interaction", {"drug_a": a["generic"], "drug_b": b["generic"]}) for a, b in pairs])
        t["tool_calls"].append({"tool": "transport", "transport": batch.transport, "note": batch.note})

        drug_ids = [d["drug_id"] for d in drugs]
        ix_ids = _interaction_ids(drug_ids)
        labels = _LabelSearch(drug_ids)

        findings, chunk_rows = [], []
        for (a, b), result in zip(pairs, batch.results):
            finding, rows, call_ref = _build(a, b, result, ix_ids, labels)
            findings.append(finding)
            chunk_rows.extend(rows)
            t["tool_calls"].append(call_ref)
        t["tool_calls"].append(labels.summary())

        findings.sort(key=lambda f: (-SEVERITY_RANK.get(f["severity"], 0), f["drug_a"], f["drug_b"]))
        status_counts = {k: sum(1 for f in findings if f["pair_status"] == k)
                         for k in ("record", "label_only", "no_record", "record_unreferenced")}
        t["output_summary"] = (
            f"{len(pairs)} pairs checked via {batch.transport}: record={status_counts['record']} "
            f"label_only={status_counts['label_only']} no_record={status_counts['no_record']} "
            f"unreferenced={status_counts['record_unreferenced']}; label search vector={labels.vector_pairs} "
            f"graph={labels.graph_pairs}"
        )
    return {"findings": findings, "retrieved_chunks": chunk_rows, "trace": trace}