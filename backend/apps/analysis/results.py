"""Read side of an AnalysisRun: pipeline progress, finding ordering, evidence details, frozen input labels.

Kept separate from services.py (which STARTS runs) so the two concerns do not grow into one file.

Rules enforced here (docs/rule.md):
  * A partial run is never final: callers only build a result context for `completed` runs.
  * Evidence is never invented: an evidence reference whose record no longer exists is returned with
    `available: false` instead of being dropped or guessed.
  * Everything about WHAT was analysed comes from `AnalysisRun.input_snapshot`, so an old run stays explainable
    after the patient's medication list changes.
  * No N+1: evidence records are loaded with one query per evidence type.
"""
from apps.drugs.models import Interaction
from apps.knowledge.models import Chunk

from .models import AgentTrace, RiskFinding, RiskSummary

PIPELINE_STEPS: list[str] = [key for key, _label in AgentTrace.AGENTS]  # resolver -> ... -> verifier
SEVERITY_RANK = {"major": 0, "moderate": 1, "minor": 2, "unknown": 3}
FINAL_STATUSES = ("completed", "failed")
# Failures that happen before any agent starts: no step should be shown as "failed" for them.
NO_STEP_FAILURES = {"enqueue_failed", "pipeline_unavailable"}


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


# ------------------------------------------------------------------------------------------------ evidence
def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def evidence_index(findings: list[RiskFinding]) -> dict[tuple[str, int], dict]:
    """One query per evidence type for ALL findings of a run: {(type, id): details}."""
    wanted: dict[str, set[int]] = {"interaction": set(), "chunk": set()}
    for f in findings:
        for e in f.evidence or []:
            if isinstance(e, dict) and e.get("type") in wanted and _int_or_none(e.get("id")) is not None:
                wanted[e["type"]].add(int(e["id"]))

    index: dict[tuple[str, int], dict] = {}
    if wanted["interaction"]:
        rows = Interaction.objects.filter(pk__in=wanted["interaction"]).values(
            "id", "source", "source_ref", "license_note")
        for r in rows:
            index[("interaction", r["id"])] = {
                "label": f"{r['source']} record #{r['id']}", "section": "",
                "source_ref": r["source_ref"], "license_note": r["license_note"], "url": "",
            }
    if wanted["chunk"]:
        rows = Chunk.objects.filter(pk__in=wanted["chunk"]).values(
            "id", "section", "document__title", "document__source_url", "document__license_note")
        for r in rows:
            index[("chunk", r["id"])] = {
                "label": r["document__title"], "section": r["section"], "source_ref": "",
                "license_note": r["document__license_note"], "url": r["document__source_url"],
            }
    return index


def evidence_items(finding: RiskFinding, index: dict) -> list[dict]:
    items = []
    for e in finding.evidence or []:
        if not isinstance(e, dict):
            continue
        ident = _int_or_none(e.get("id"))
        detail = index.get((e.get("type"), ident)) if ident is not None else None
        items.append({
            "type": str(e.get("type", "")),
            "id": ident,
            "source": str(e.get("source", "")),
            "label": detail["label"] if detail else "",
            "section": detail["section"] if detail else "",
            "source_ref": detail["source_ref"] if detail else "",
            "license_note": detail["license_note"] if detail else "",
            "url": detail["url"] if detail else "",
            "available": detail is not None,  # false = the record was removed by a data reload; say so, don't hide it
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