"""Read side of an AnalysisRun: pipeline progress, finding ordering, evidence details, frozen input labels.

Kept separate from services.py (which STARTS runs) so the two concerns do not grow into one file.

Rules enforced here (docs/rule.md):
  * A partial run is never final: callers only build a result context for `completed` runs.
  * Evidence is never invented: an evidence reference whose record no longer exists is returned with
    `available: false` instead of being dropped or guessed.
  * Everything about WHAT was analysed comes from `AnalysisRun.input_snapshot`, so an old run stays explainable
    after the patient's medication list changes.
  * No N+1: evidence records are loaded with one query per evidence type.
  * The evidence "excerpt" is a short VERBATIM passage of the stored source text (never written by a model). A
    sentence that reads like dosing advice, or that calls a combination safe, is never used as an excerpt:
    the same guardrail rules as every other text we show. No usable sentence -> an empty excerpt, not a guess.
"""
import re

from ai.guardrails.output_checks import claims_safety, contains_dosing_language
from apps.drugs.models import Interaction
from apps.knowledge.models import Chunk

from .models import AgentTrace, RiskFinding, RiskSummary

PIPELINE_STEPS: list[str] = [key for key, _label in AgentTrace.AGENTS]  # resolver -> ... -> verifier
SEVERITY_RANK = {"major": 0, "moderate": 1, "minor": 2, "unknown": 3}
FINAL_STATUSES = ("completed", "failed")
# Failures that happen before any agent starts: no step should be shown as "failed" for them.
NO_STEP_FAILURES = {"enqueue_failed", "pipeline_unavailable"}

# Evidence panel ("why are we saying this?"). Keys are the `source` strings stored in RiskFinding.evidence.
SOURCE_NAMES = {"ddinter": "DDInter 2.0", "openfda_label": "openFDA label", "openfda": "openFDA label"}
# Fallback link when a record has no URL of its own (an Interaction row has none): the source's public site.
# Taken from data/SOURCES.md; never a made-up deep link.
SOURCE_HOMEPAGES = {
    "ddinter": "https://ddinter2.scbdd.com/",
    "openfda_label": "https://open.fda.gov/",
    "openfda": "https://open.fda.gov/",
}
EXCERPT_CHARS = 180  # about two lines on a desktop card


# ------------------------------------------------------------------------------------------------ progress
def completed_agents(run) -> list[str]:
    """Agents that finished, in pipeline order. A completed run has, by definition, finished every step."""
    if run.status == "completed":
        return list(PIPELINE_STEPS)
    raw = ((run.model_info or {}).get("progress") or {}).get("completed_agents") or []
    done = set(raw)
    return [a for a in PIPELINE_STEPS if a in done]


def progress_steps(run) -> list[dict]:
    """[{agent, order, status}] with status in done | running | failed | pending (drives the pipeline stepper)."""
    done = set(completed_agents(run))
    error = (run.model_info or {}).get("error")
    marked = False
    steps = []
    for order, agent in enumerate(PIPELINE_STEPS, start=1):
        if agent in done:
            status = "done"
        elif not marked and run.status == "running":
            status, marked = "running", True
        elif not marked and run.status == "failed" and error not in NO_STEP_FAILURES:
            status, marked = "failed", True
        else:
            status = "pending"
        steps.append({"agent": agent, "order": order, "status": status})
    return steps


def current_step(run) -> str | None:
    for step in progress_steps(run):
        if step["status"] in ("running", "failed"):
            return step["agent"]
    return None


# ------------------------------------------------------------------------------------------------ timeline
# The judge-facing view of a run: Photo upload -> OCR -> Brand->Generic -> Interaction check -> Guardrail -> Final report.
# Only the agent-backed stages come from AgentTrace; upload / OCR happen before the run exists and are read from the
# frozen snapshot (a medication with source "scan" can only be analysed after the person confirmed the OCR draft).
TIMELINE_AGENT_STAGES: list[tuple[str, tuple[str, ...]]] = [
    ("resolve", ("resolver",)),
    ("interaction", ("clinical_notes", "drug_interaction")),
    ("guardrail", ("verifier",)),
]
REPORT_AGENT = "advisory"


def _timeline_stage(key: str, status: str, duration_ms: int | None = None, meta: dict | None = None) -> dict:
    """status: done | running | failed | pending | skipped. `meta` holds counts only (the UI words them, in Bangla/English)."""
    return {"key": key, "status": status, "duration_ms": duration_ms, "meta": meta or {}}


def _agent_status(agents: tuple[str, ...], steps: dict[str, str], run_status: str) -> str:
    states = [steps.get(a, "pending") for a in agents]
    if "failed" in states:
        return "failed"
    if all(s == "done" for s in states):
        return "done"
    if "running" in states or "done" in states:
        # A half-finished stage only counts as "running" while the run is. A stopped run never shows a spinner.
        return "running" if run_status == "running" else "pending"
    return "pending"


def trace_timeline(run, traces: list) -> list[dict]:
    """Six stages for the Agent trace timeline: [{key, status, duration_ms, meta}].

    * Statuses are always available (they carry no clinical content) so a polling UI can show live progress.
    * `duration_ms` comes from the stored AgentTrace rows and exists only once the run is completed (the same moment
      the trace rows exist). Upload / OCR have no recorded duration: it is `None`, never estimated.
    * `meta` holds counts only. Resolve counts come from the frozen snapshot; interaction / guardrail counts from the
      stored findings and only for a completed run, so a partial run never looks final.
    * Nothing here says a combination is safe: the guardrail stage reports verification counts, nothing more.
    """
    final = run.status == "completed"
    snapshot_meds = (run.input_snapshot or {}).get("medications", [])
    scan_count = sum(1 for m in snapshot_meds if m.get("source") == "scan")
    steps = {s["agent"]: s["status"] for s in progress_steps(run)}

    latency: dict[str, int] = {}
    for trace in traces:
        latency[trace.agent_name] = latency.get(trace.agent_name, 0) + max(0, trace.latency_ms)

    def took(agents: tuple[str, ...]) -> int | None:
        return sum(latency[a] for a in agents if a in latency) if any(a in latency for a in agents) else None

    counts = {"pairs": 0, "verified": 0, "unverified": 0, "conflict": 0}
    if final:
        for _severity, verification in run.findings.values_list("severity", "verification_status"):
            counts["pairs"] += 1
            if verification in counts:
                counts[verification] += 1
    violations = len(guardrail_violations(run)) if final else 0

    if scan_count:
        stages = [_timeline_stage("photo_upload", "done"),
                  _timeline_stage("ocr", "done", meta={"medicines": scan_count})]
    else:  # typed in by hand: there was no image and no OCR
        stages = [_timeline_stage("photo_upload", "skipped"), _timeline_stage("ocr", "skipped")]

    for key, agents in TIMELINE_AGENT_STAGES:
        status = _agent_status(agents, steps, run.status)
        meta: dict = {}
        if status == "done" and key == "resolve" and snapshot_meds:
            matched = sum(1 for m in snapshot_meds if m.get("drug_id"))
            meta = {"resolved": matched, "total": len(snapshot_meds)}
        elif status == "done" and final and key == "interaction":
            meta = {"pairs": counts["pairs"]}
        elif status == "done" and final and key == "guardrail":
            meta = {"verified": counts["verified"], "unverified": counts["unverified"],
                    "conflict": counts["conflict"], "violations": violations}
        stages.append(_timeline_stage(key, status, took(agents) if status == "done" else None, meta))

    # The final report is final only after the guardrail ran, so it follows the run, not the (earlier) advisory agent.
    if final:
        report = _timeline_stage("report", "done", took((REPORT_AGENT,)))
    elif all(s["status"] in ("done", "skipped") for s in stages):
        report = _timeline_stage("report", {"failed": "failed", "running": "running"}.get(run.status, "pending"))
    else:
        report = _timeline_stage("report", "pending")
    stages.append(report)
    return stages


# ------------------------------------------------------------------------------------------------ frozen input
def snapshot_medications(run) -> list[dict]:
    """What was analysed, exactly as frozen at run time (already PII-redacted). Frequency is left out on purpose."""
    return [
        {
            "medication_id": m.get("medication_id"),
            "raw_text": m.get("raw_text") or "",
            "brand_name": m.get("brand_name") or "",
            "strength": m.get("strength") or "",
            "generic_name": m.get("generic_name"),
            "resolution_status": m.get("resolution_status") or "",
            "source": m.get("source") or "",
        }
        for m in (run.input_snapshot or {}).get("medications", [])
    ]


def entered_names(run) -> dict[int, list[str]]:
    """drug_id -> names as the person entered them (brand/raw text). The UI shows generic + the name as entered."""
    out: dict[int, list[str]] = {}
    for m in (run.input_snapshot or {}).get("medications", []):
        drug_id = m.get("drug_id")
        name = (m.get("brand_name") or m.get("raw_text") or "").strip()
        if not drug_id or not name:
            continue
        names = out.setdefault(drug_id, [])
        if name not in names:
            names.append(name)
    return out


def gap_list(run) -> list[dict]:
    """Medications the pipeline could not resolve: shown as 'not checked', never hidden."""
    meta = (run.model_info or {}).get("result_meta") or {}
    wanted = {i for i in meta.get("gap_medication_ids") or [] if i is not None}
    if not wanted:
        return []
    return [
        {"medication_id": m["medication_id"], "raw_text": m["raw_text"], "brand_name": m["brand_name"],
         "reason": "needs_user_selection"}
        for m in snapshot_medications(run)
        if m["medication_id"] in wanted
    ]


def guardrail_violations(run) -> list[str]:
    meta = (run.model_info or {}).get("result_meta") or {}
    return [str(v) for v in meta.get("violations") or []]


# ------------------------------------------------------------------------------------------------ excerpt
_SENTENCES = re.compile(r"(?<=[.!?।])\s+")


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def _ellipsize(text: str, limit: int) -> str:
    """Collapse whitespace and cut at a word boundary."""
    text = _clean(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:.- ")
    return f"{cut}…"


def _window(sentence: str, terms: list[str], limit: int) -> str:
    """Cut a long sentence to about `limit` characters, keeping the first drug-name mention in view."""
    if len(sentence) <= limit:
        return sentence
    low = sentence.lower()
    positions = [p for p in (low.find(t) for t in terms) if p >= 0]
    first = min(positions) if positions else -1
    start = 0
    if first > limit - 40:  # a plain cut from the start would lose the mention
        start = max(0, first - 40)
        space = sentence.find(" ", start)
        if 0 <= space < first:
            start = space + 1  # begin at a word boundary
    body = _ellipsize(sentence[start:], limit)
    return f"…{body}" if start else body


def build_excerpt(texts: list, terms: list[str], limit: int = EXCERPT_CHARS) -> str:
    """One short verbatim passage from the source text, or "" when no sentence may be shown.

    The sentence that names the most drugs of the pair wins (ties: the earliest). Sentences with dosing language
    or an un-negated "safe" claim are skipped, exactly like the guardrail does for summaries."""
    wanted = [t.strip().lower() for t in terms if t and t.strip()]
    best, best_score = "", -1
    for text in texts:
        for sentence in _SENTENCES.split(_clean(text)):
            if not sentence or contains_dosing_language(sentence) or claims_safety(sentence):
                continue
            score = sum(1 for t in wanted if t in sentence.lower())
            if score > best_score:
                best, best_score = sentence, score
    return _window(best, wanted, limit) if best else ""


def _pair_terms(finding) -> list[str]:
    """Generic names of the finding's two drugs (empty for objects without drugs, e.g. a what-if shim)."""
    terms = []
    for side in ("drug_a", "drug_b"):
        drug = getattr(finding, side, None)
        name = getattr(drug, "generic_name", "") if drug is not None else ""
        if name:
            terms.append(str(name))
    return terms


def _finding_confidence(finding) -> float | None:
    """The stored confidence of the finding (0..1). None when the object carries none (what-if shim)."""
    value = getattr(finding, "confidence", None)
    if value is None:
        return None
    try:
        return round(min(1.0, max(0.0, float(value))), 2)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------ evidence
def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def evidence_index(findings: list[RiskFinding]) -> dict[tuple[str, int], dict]:
    """One query per evidence type for ALL findings of a run: {(type, id): details}.

    `texts` holds the stored source text the excerpt is cut from (interaction: mechanism + management note,
    label passage: the passage). It is loaded by the same two queries as before: no extra query."""
    wanted: dict[str, set[int]] = {"interaction": set(), "chunk": set()}
    for f in findings:
        for e in f.evidence or []:
            if isinstance(e, dict) and e.get("type") in wanted and _int_or_none(e.get("id")) is not None:
                wanted[e["type"]].add(int(e["id"]))

    index: dict[tuple[str, int], dict] = {}
    if wanted["interaction"]:
        rows = Interaction.objects.filter(pk__in=wanted["interaction"]).values(
            "id", "source", "source_ref", "license_note", "mechanism", "management")
        for r in rows:
            index[("interaction", r["id"])] = {
                "label": f"{r['source']} record #{r['id']}", "section": "",
                "source_ref": r["source_ref"], "license_note": r["license_note"], "url": "",
                "texts": [r["mechanism"], r["management"]],
            }
    if wanted["chunk"]:
        rows = Chunk.objects.filter(pk__in=wanted["chunk"]).values(
            "id", "section", "text", "document__title", "document__source_url", "document__license_note")
        for r in rows:
            index[("chunk", r["id"])] = {
                "label": r["document__title"], "section": r["section"], "source_ref": "",
                "license_note": r["document__license_note"], "url": r["document__source_url"],
                "texts": [r["text"]],
            }
    return index


def evidence_items(finding: RiskFinding, index: dict) -> list[dict]:
    """Evidence of one finding, ready for the Evidence panel.

    Besides the record details every item carries:
      source_name  human name of the source ("DDInter 2.0", "openFDA label")
      source_url   the record's own URL, else the source's public site, else ""
      excerpt      short verbatim quote of the stored source text ("" when none may be shown / record is gone)
      confidence   the confidence of THIS finding (0..1). There is no separate per-source score: the value
                   reflects the kind of evidence behind the finding and is not a probability.
    """
    terms = _pair_terms(finding)
    confidence = _finding_confidence(finding)
    items = []
    for e in finding.evidence or []:
        if not isinstance(e, dict):
            continue
        ident = _int_or_none(e.get("id"))
        detail = index.get((e.get("type"), ident)) if ident is not None else None
        raw_source = str(e.get("source", "")).strip()
        key = raw_source.lower()
        url = detail["url"] if detail else ""
        items.append({
            "type": str(e.get("type", "")),
            "id": ident,
            "source": str(e.get("source", "")),
            "label": detail["label"] if detail else "",
            "section": detail["section"] if detail else "",
            "source_ref": detail["source_ref"] if detail else "",
            "license_note": detail["license_note"] if detail else "",
            "url": url,
            "available": detail is not None,  # false = the record was removed by a data reload; say so, don't hide it
            "source_name": SOURCE_NAMES.get(key) or raw_source or "Source",
            "source_url": url or SOURCE_HOMEPAGES.get(key, ""),
            "excerpt": build_excerpt(detail.get("texts", []), terms) if detail else "",
            "confidence": confidence,
        })
    return items


def confidence_basis(finding: RiskFinding) -> dict:
    """A confidence value never travels without its basis (rule.md §5)."""
    sources = sorted({str(e.get("source", "")) for e in finding.evidence or [] if isinstance(e, dict) and e.get("source")})
    return {
        "verification_status": finding.verification_status,
        "evidence_count": len(finding.evidence or []),
        "sources": sources,
    }


# ------------------------------------------------------------------------------------------------ context
def result_context(run) -> dict:
    """Everything the detail serializer needs for a COMPLETED run, loaded with a fixed number of queries."""
    findings = list(run.findings.select_related("drug_a", "drug_b"))
    findings.sort(key=lambda f: (SEVERITY_RANK.get(f.severity, 3), f.id))  # major -> moderate -> minor -> unknown
    return {
        "findings": findings,
        "evidence_index": evidence_index(findings),
        "entered_names": entered_names(run),
        "summary": RiskSummary.objects.filter(run=run).first(),
    }