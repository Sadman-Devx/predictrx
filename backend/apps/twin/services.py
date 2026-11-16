"""What-if (Digital Twin) service: "if drug X is added to this run, how does the interaction picture change?"

This is a SIMULATION FOR EXPLORATION, never a prediction and never advice. It is computed synchronously because it is
a pure database read (no LLM, no network): the only data it uses is the same `Interaction` table the Verifier checks
against, so the simulation and the main analysis can never disagree about what the table says.

Rules enforced here (docs/rule.md):
  * No warning without a source: every added finding carries the interaction rows it came from as `evidence`.
  * "No record" is never "safe": a pair without a record is returned in `no_record_pairs` with the standard note.
  * Nothing is guessed: severity comes ONLY from the table; the text is a deterministic template + the table's own
    mechanism / management text, and that text is dropped if it contains dosing language or a "safe" claim.
  * Runs are snapshots: the base drug list is read from `AnalysisRun.input_snapshot`, never from the live medication
    list, so an old run stays explainable. The base run is never changed; a scenario is a new row.
  * Ownership is derived from the authenticated user. A foreign run / scenario is a plain 404.
  * Labs and vitals do NOT change any severity here (there is no sourced rule for it); the response says so in
    `limitations` instead of implying otherwise.
  * Confidence values mirror ai/agents/drug_interaction.py (the kind of evidence, not a probability) and ship with
    their basis (`confidence_basis`).
"""
import logging
from collections import defaultdict
from types import SimpleNamespace

from django.conf import settings
from django.db.models import Q
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound

from ai.guardrails.output_checks import (DISCLAIMER_BN, DISCLAIMER_EN, INSUFFICIENT_EVIDENCE_EN, check_output,
                                         claims_safety, contains_dosing_language)
from apps.analysis import results
from apps.analysis.models import AnalysisRun
from apps.drugs.models import Drug, Interaction
from apps.drugs.services import NO_RECORD_NOTE, SEVERITY_RANK, lookup_drug

from .models import TwinScenario

logger = logging.getLogger(__name__)

RESULT_VERSION = 1
SEVERITIES = ("major", "moderate", "minor", "unknown")
SOURCE_NAMES = {"ddinter": "DDInter 2.0", "openfda_label": "openFDA label"}

# Same meaning as in ai/agents/drug_interaction.py. Kept here (not imported) so this module does not pull in the
# MCP / embedding stack just to read a table.
CONF_RECORD = 0.80
CONF_RECORD_NO_SEVERITY = 0.30
CONF_CONFLICT_PENALTY = 0.20

MAX_TEXT_CHARS = 300
MAX_SCENARIOS_LISTED = 20

# Wording for Bangla strings is pending clinician / mentor sign-off (docs/design.md, "Clinical wording review status").
SIMULATION_NOTE_EN = ("Simulation for exploration. It only re-reads the interaction table for the added drug. "
                      "It is not a prediction and not medical advice.")
SIMULATION_NOTE_BN = "এটি অনুসন্ধানের জন্য একটি সিমুলেশন। এটি কোনো পূর্বাভাস বা চিকিৎসা পরামর্শ নয়।"

BASE_LIMITATIONS = ["interaction_table_only", "labs_vitals_not_used", "label_passages_not_searched"]


class TwinRequestError(APIException):
    """Client-fixable problem. Shape: {"error": {"code": <specific>, "message": ..., "details": {...}}}."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "bad_request"

    def __init__(self, code: str, message: str, *, http_status: int | None = None, **extra):
        super().__init__(detail={"detail": message, "code": code, **extra})
        if http_status:
            self.status_code = http_status


# ------------------------------------------------------------------------------------------------ ownership
def get_owned_run(user, run_id: int) -> AnalysisRun:
    """A foreign (or missing) run is a plain 404: the existence of other doctors' runs is not leaked."""
    run = AnalysisRun.objects.select_related("patient").filter(pk=run_id, patient__owner=user).first()
    if run is None:
        raise NotFound()
    return run


def get_owned_scenario(user, pk: int) -> TwinScenario:
    scenario = (TwinScenario.objects.select_related("patient", "hypothetical_drug")
                .filter(pk=pk, patient__owner=user).first())
    if scenario is None:
        raise NotFound()
    return scenario


def resolve_hypothetical_drug(*, drug_id: int | None = None, generic_name: str | None = None) -> Drug:
    """The drug to add. By id, or by generic name / alias (exact match). Brand names are NOT guessed here: the UI
    resolves them first through /api/medications/resolve/ or /api/drugs/search/."""
    drug = None
    if drug_id is not None:
        drug = Drug.objects.filter(pk=drug_id).first()
    elif generic_name:
        found = lookup_drug(generic_name)
        if found.get("status") == "found":
            drug = Drug.objects.filter(generic_name=found["generic_name"]).first()
    if drug is None:
        raise TwinRequestError("drug_not_found",
                               "This drug is not in the database. Pick a generic name from the drug search.")
    return drug


# ------------------------------------------------------------------------------------------------ small helpers
def _ref(drug: Drug) -> dict:
    return {"id": drug.id, "generic_name": drug.generic_name}


def _clean_text(text) -> str:
    """Table text (mechanism / management) that is safe to show: truncated first, then checked, so a cut can never
    leave a half sentence that passes the check but would not have passed whole."""
    value = " ".join(str(text or "").split())
    if len(value) > MAX_TEXT_CHARS:
        value = value[: MAX_TEXT_CHARS - 1].rstrip() + "…"
    if not value or contains_dosing_language(value) or claims_safety(value):
        return ""
    return value


def _picture(severities: list[str]) -> dict:
    """Severity picture of a list of findings. `highest_severity` is None when nothing has a known severity."""
    counts = {s: 0 for s in SEVERITIES}
    for s in severities:
        counts[s if s in counts else "unknown"] += 1
    known = [s for s in severities if s in SEVERITY_RANK and s != "unknown"]
    highest = max(known, key=lambda s: SEVERITY_RANK[s]) if known else None
    return {"highest_severity": highest, "counts": counts, "total": len(severities)}


def _finding_for_pair(new_drug: Drug, other: Drug, rows: list[Interaction], names: dict) -> dict:
    """One added finding built ONLY from the interaction rows of the pair. Several sources: the most severe is the
    primary; if they disagree on severity the finding is a `conflict` (shown, never hidden)."""
    rows = sorted(rows, key=lambda r: (-SEVERITY_RANK.get(r.severity, 0), r.source, r.id))
    primary = rows[0]
    known = {r.severity for r in rows if r.severity != "unknown"}
    conflict = len(known) > 1
    a, b = sorted((new_drug, other), key=lambda d: d.id)  # same canonical order as analysis findings
    source = SOURCE_NAMES.get(primary.source, primary.source or "The interaction source")

    if primary.severity == "unknown":
        sentence = f"{source} has an interaction record for {a.generic_name} and {b.generic_name} without a severity rating."
        confidence, verification = CONF_RECORD_NO_SEVERITY, "unverified"
    else:
        sentence = f"{source} lists a {primary.severity} interaction between {a.generic_name} and {b.generic_name}."
        confidence, verification = CONF_RECORD, "verified"
    if conflict:
        sentence += " Sources disagree on the severity; every record is cited."
        confidence, verification = max(0.0, confidence - CONF_CONFLICT_PENALTY), "conflict"

    mechanism = _clean_text(primary.mechanism)
    rationale = f"{sentence} Mechanism noted: {mechanism}" if mechanism else sentence
    return {
        "drug_a": _ref(a),
        "drug_b": _ref(b),
        "entered_names_a": list(names.get(a.id, [])),
        "entered_names_b": list(names.get(b.id, [])),
        "severity": primary.severity,
        "rationale": rationale,
        "management": _clean_text(primary.management) or None,
        "confidence": round(confidence, 2),
        "verification_status": verification,
        "evidence": [{"type": "interaction", "id": r.id, "source": r.source} for r in rows],
        "pair_status": "record",
        "severity_conflict": conflict,
    }


def _no_record_for_pair(new_drug: Drug, other: Drug, names: dict) -> dict:
    a, b = sorted((new_drug, other), key=lambda d: d.id)
    return {
        "drug_a": _ref(a),
        "drug_b": _ref(b),
        "entered_names_a": list(names.get(a.id, [])),
        "entered_names_b": list(names.get(b.id, [])),
        "pair_status": "no_record",
        "note": NO_RECORD_NOTE,  # "...does not mean the combination is safe."
    }


def _enforce_guardrails(findings: list[dict]) -> list[str]:
    """Output guardrail for the simulation (same rules as the main pipeline): no dosing language, no "safe" claim,
    every severity cited. A failing text is replaced, never shown. Returns the violation codes that fired."""
    violations: set[str] = set()
    for f in findings:
        if contains_dosing_language(f["rationale"]):
            f["rationale"] = INSUFFICIENT_EVIDENCE_EN
            violations.add("dosing_language")
        elif claims_safety(f["rationale"]):
            f["rationale"] = INSUFFICIENT_EVIDENCE_EN
            violations.add("safety_claim")
        if f.get("management") and (contains_dosing_language(f["management"]) or claims_safety(f["management"])):
            f["management"] = None
            violations.add("management_withheld")

    text = " ".join(f"{f['rationale']} {f.get('management') or ''}" for f in findings)
    violations.update(check_output(summary_text=text, findings=findings))  # catches missing_evidence too
    return sorted(violations)


# ------------------------------------------------------------------------------------------------ compute
def compute_result(run: AnalysisRun, drug: Drug) -> dict:
    """The stored part of a scenario. Deterministic: the same run + drug + table gives the same dict, which is what
    lets `run_scenario` recognise a repeated request."""
    snapshot = run.input_snapshot or {}
    base_ids = sorted({int(i) for i in snapshot.get("drug_ids") or []})
    if drug.id in base_ids:
        raise TwinRequestError("drug_already_in_run", "This drug is already part of the base analysis.")
    base_drugs = list(Drug.objects.filter(pk__in=base_ids).order_by("generic_name"))
    if not base_drugs:
        raise TwinRequestError("base_run_has_no_drugs", "The base analysis has no resolved drugs to compare with.")

    names = results.entered_names(run)

    # One query for every (new drug, base drug) pair; rows are stored in canonical order, so match both directions.
    rows = Interaction.objects.filter(
        Q(drug_a_id=drug.id, drug_b_id__in=base_ids) | Q(drug_b_id=drug.id, drug_a_id__in=base_ids)
    )
    by_other: dict[int, list[Interaction]] = defaultdict(list)
    for row in rows:
        by_other[row.drug_b_id if row.drug_a_id == drug.id else row.drug_a_id].append(row)

    added: list[dict] = []
    no_record: list[dict] = []
    for other in base_drugs:
        pair_rows = by_other.get(other.id)
        if pair_rows:
            added.append(_finding_for_pair(drug, other, pair_rows, names))
        else:
            no_record.append(_no_record_for_pair(drug, other, names))
    added.sort(key=lambda f: (-SEVERITY_RANK.get(f["severity"], 0), f["drug_a"]["id"], f["drug_b"]["id"]))

    violations = _enforce_guardrails(added)

    before_severities = list(run.findings.values_list("severity", flat=True))
    # A pair with no record is an `unknown` finding in the main analysis too, so the two pictures stay comparable.
    after_severities = before_severities + [f["severity"] for f in added] + ["unknown"] * len(no_record)
    before, after = _picture(before_severities), _picture(after_severities)

    gaps = results.gap_list(run)
    limitations = list(BASE_LIMITATIONS)
    if gaps:
        limitations.append("unresolved_medications_not_checked")

    return {
        "version": RESULT_VERSION,
        "hypothetical_drug": _ref(drug),
        "base_drugs": [{**_ref(d), "entered_names": list(names.get(d.id, []))} for d in base_drugs],
        "added_findings": added,
        "no_record_pairs": no_record,
        "comparison": {
            "before": before,
            "after": after,
            "highest_severity_changed": before["highest_severity"] != after["highest_severity"],
            "base_findings_count": len(before_severities),
            "new_findings_count": len(added),
            "pairs_checked": len(base_drugs),
        },
        "gaps": gaps,
        "limitations": limitations,
        "guardrail_violations": violations,
    }


def run_scenario(user, *, base_run_id: int, drug_id: int | None = None,
                 generic_name: str | None = None) -> tuple[TwinScenario, bool]:
    """Create (or replay) a what-if scenario. Returns (scenario, created). Call inside `transaction.atomic()`.

    The same request (same base run, same drug, unchanged table) returns the SAME scenario instead of a duplicate row,
    so a double click does not clutter the history. If the interaction table was reloaded in between and the answer
    changed, a new scenario is stored and the old one stays as it was (history is never rewritten).
    """
    run = get_owned_run(user, base_run_id)
    if run.status != "completed":
        raise TwinRequestError("base_run_not_completed",
                               "A what-if scenario needs a completed analysis as its base.",
                               http_status=status.HTTP_409_CONFLICT)

    drug = resolve_hypothetical_drug(drug_id=drug_id, generic_name=generic_name)
    result = compute_result(run, drug)

    latest = (TwinScenario.objects.select_related("patient", "hypothetical_drug")
              .filter(base_run=run, hypothetical_drug=drug).order_by("-id").first())
    if latest is not None and latest.result_json == result:
        return latest, False

    scenario = TwinScenario.objects.create(patient=run.patient, base_run=run, hypothetical_drug=drug,
                                           result_json=result)
    return scenario, True


def list_scenarios(user, run_id: int) -> tuple[AnalysisRun, list[TwinScenario]]:
    run = get_owned_run(user, run_id)
    scenarios = list(TwinScenario.objects.filter(base_run=run).select_related("hypothetical_drug")
                     .order_by("-id")[:MAX_SCENARIOS_LISTED])
    return run, scenarios


# ------------------------------------------------------------------------------------------------ read side
def _disclaimer() -> dict:
    return {"version": settings.DISCLAIMER_VERSION, "text_en": DISCLAIMER_EN, "text_bn": DISCLAIMER_BN}


def scenario_payload(scenario: TwinScenario) -> dict:
    """API shape of a stored scenario. Evidence references are expanded with the same helpers the analysis detail
    uses (label, source_ref, license, `available: false` when a data reload removed the record). A scenario is a
    snapshot: its numbers are as of `created_at`."""
    result = scenario.result_json or {}
    stored = result.get("added_findings") or []

    shims = [SimpleNamespace(evidence=f.get("evidence") or [], verification_status=f.get("verification_status", ""))
             for f in stored]
    index = results.evidence_index(shims)  # one query per evidence type for the whole scenario
    added = [
        {**f, "evidence": results.evidence_items(shim, index), "confidence_basis": results.confidence_basis(shim)}
        for f, shim in zip(stored, shims)
    ]

    return {
        "scenario_id": scenario.id,
        "base_run_id": scenario.base_run_id,
        "patient_id": scenario.patient_id,
        "created_at": scenario.created_at,
        "simulation": True,
        "simulation_note": {"text_en": SIMULATION_NOTE_EN, "text_bn": SIMULATION_NOTE_BN},
        "hypothetical_drug": result.get("hypothetical_drug") or _ref(scenario.hypothetical_drug),
        "base_drugs": result.get("base_drugs") or [],
        "added_findings": added,
        "no_record_pairs": result.get("no_record_pairs") or [],
        "comparison": result.get("comparison") or {},
        "gaps": result.get("gaps") or [],
        "limitations": result.get("limitations") or list(BASE_LIMITATIONS),
        "guardrail_violations": result.get("guardrail_violations") or [],
        "disclaimer_version": settings.DISCLAIMER_VERSION,
        "disclaimer": _disclaimer(),
    }


def scenario_summary(scenario: TwinScenario) -> dict:
    """Compact row for the history list of a run (no findings, no evidence)."""
    comparison = (scenario.result_json or {}).get("comparison") or {}
    return {
        "scenario_id": scenario.id,
        "hypothetical_drug": _ref(scenario.hypothetical_drug),
        "created_at": scenario.created_at,
        "new_findings_count": comparison.get("new_findings_count", 0),
        "highest_severity_after": (comparison.get("after") or {}).get("highest_severity"),
        "highest_severity_changed": bool(comparison.get("highest_severity_changed", False)),
    }
