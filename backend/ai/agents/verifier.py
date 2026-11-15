"""Verifier agent (step 5).

Re-checks every finding WITHOUT trusting the wording or the numbers the earlier agents produced, then enforces the
output guardrail on the summaries. Independent sources used here:

  * `check_interaction` (MCP, same deterministic tool as step 3) for the drug pair taken from the resolved drugs,
  * the database rows the finding cites: an `interaction` reference must exist AND belong to this exact pair; a
    `chunk` reference must exist, belong to a label of one of the two drugs and really name the other drug.

Verdict per finding (`verification_status`):

  verified    the interaction table lists the pair, its severity equals the finding's, its sources do not disagree,
              and the finding cites at least one valid table record
  conflict    the finding contradicts the data: different severity, "no severity" where the table has one, the
              table's own sources disagree, a cited record that is not about this pair, wrong drug names, or a pair
              that is not among the resolved drugs. Conflicts are shown to the doctor, never hidden.
  unverified  nothing in the table can confirm it: no table record (label-only or "no record"), unconfirmed
              evidence, or the tools were unavailable. "No record" is NEVER verified (and never "safe").

Also done here (rule.md §1, §2):
  * a finding with a severity but no evidence is downgraded to `unknown` / insufficient evidence (violation recorded),
  * every pair of resolved drugs must have exactly one finding: missing or duplicated pairs become violations,
  * summaries: dosing language or a "safe" claim -> replaced by the insufficient-evidence text; a missing disclaimer
    is appended by code; a notice is added to the doctor summaries when findings conflict.

Unverified or conflicting findings get a lower confidence and one short "Verifier: ..." sentence at the end of the
rationale. Nothing is dropped. If the tools are unavailable every finding stays `unverified` and the run carries the
violation `verifier_tools_unavailable`; the evidence checks against the database still run.
"""
import itertools
import logging

from apps.drugs.models import Drug
from apps.knowledge.models import Chunk

from .. import mcp_client
from ..guardrails.output_checks import (DISCLAIMER_FOR, INSUFFICIENT_EVIDENCE_EN, INSUFFICIENT_FOR, SUMMARY_KEYS,
                                        check_output, claims_safety, contains_dosing_language,
                                        findings_missing_evidence)
from ..rag.graph import mentions_drug
from .common import traced, with_period

logger = logging.getLogger(__name__)

KNOWN = ("minor", "moderate", "major")
VALID = KNOWN + ("unknown",)
CONFLICT_CONFIDENCE_CAP = 0.30
UNVERIFIED_CLAIM_CONFIDENCE_CAP = 0.50
MAX_LISTED_VIOLATIONS = 10

CONFLICT_NOTICE_EN = "Verifier: {n} finding(s) conflict with the interaction table. See the finding cards."
CONFLICT_NOTICE_BN = "যাচাইকারী: {n} টি ফলাফল ইন্টারঅ্যাকশন টেবিলের সঙ্গে মেলেনি। ফলাফল কার্ডগুলো দেখুন।"


# ------------------------------------------------------------------------------------------------ small helpers
def _int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _label(severity: str) -> str:
    return severity if severity in KNOWN else "no severity rating"


def _pair_of(finding: dict):
    a, b = _int(finding.get("drug_a_id")), _int(finding.get("drug_b_id"))
    return None if a is None or b is None or a == b else (a, b)


def _append_once(items: list, value: str) -> None:
    if value not in items:
        items.append(value)


# ------------------------------------------------------------------------------------------------ evidence checks
def _evidence_report(evidence, a_id: int, b_id: int, ix_rows: dict, chunk_rows: dict, drugs: dict) -> dict:
    """Which cited records are real and belong to this pair. Pure given the pre-loaded rows."""
    report = {"valid_interaction": 0, "bad_interaction": [], "valid_chunk": 0, "bad_chunk": []}
    canonical = tuple(sorted((a_id, b_id)))
    for e in evidence or []:
        if not isinstance(e, dict):
            continue
        ident = _int(e.get("id"))
        if e.get("type") == "interaction":
            row = ix_rows.get(ident) if ident is not None else None
            if row and (row["drug_a_id"], row["drug_b_id"]) == canonical:
                report["valid_interaction"] += 1
            else:
                report["bad_interaction"].append(e.get("id"))
        elif e.get("type") == "chunk":
            row = chunk_rows.get(ident) if ident is not None else None
            ok = False
            if row and row.get("document__drug_id") in (a_id, b_id):
                other = drugs.get(b_id if row["document__drug_id"] == a_id else a_id)
                ok = other is not None and mentions_drug(row.get("text") or "", other)
            if ok:
                report["valid_chunk"] += 1
            else:
                report["bad_chunk"].append(e.get("id"))
    return report


def _load_evidence_rows(findings: list):
    """One query per evidence type for the whole run."""
    from apps.drugs.models import Interaction

    ix_ids, chunk_ids = set(), set()
    for f in findings:
        for e in f.get("evidence") or []:
            ident = _int(e.get("id")) if isinstance(e, dict) else None
            if ident is None:
                continue
            if e.get("type") == "interaction":
                ix_ids.add(ident)
            elif e.get("type") == "chunk":
                chunk_ids.add(ident)
    ix_rows = {r["id"]: r for r in Interaction.objects.filter(pk__in=ix_ids).values("id", "drug_a_id", "drug_b_id")} \
        if ix_ids else {}
    chunk_rows = {r["id"]: r for r in Chunk.objects.filter(pk__in=chunk_ids).values(
        "id", "text", "document__drug_id")} if chunk_ids else {}
    return ix_rows, chunk_rows


# ------------------------------------------------------------------------------------------------ the verdict
def judge(*, severity: str, pair_ok: bool = True, names_ok: bool = True, table, ev: dict):
    """(status, reason_code, sentence). `table` is the check_interaction answer, or None when the tool was unavailable.

    `sentence` is a short English line for the end of the rationale ('' when nothing needs saying).
    """
    claims = severity in KNOWN
    if not pair_ok:
        return "conflict", "pair_not_resolved", "Verifier: conflict. This pair is not among the resolved drugs of this run."
    if not names_ok:
        return "conflict", "drug_name_mismatch", "Verifier: conflict. The drug names in this finding do not match the drug records."
    if table is None:
        return "unverified", "tools_unavailable", ""
    if ev.get("bad_interaction"):
        return "conflict", "evidence_interaction_mismatch", \
            "Verifier: conflict. A cited interaction record does not belong to this drug pair."

    if table.get("status") == "found":
        table_sev = table.get("severity") if table.get("severity") in VALID else "unknown"
        if table.get("severity_conflict"):
            return "conflict", "sources_disagree", \
                "Verifier: conflict. The interaction sources disagree on the severity of this pair."
        if severity != table_sev:
            return "conflict", "severity_mismatch", \
                f"Verifier: conflict. This finding states {_label(severity)} but the interaction table lists {_label(table_sev)}."
        if not ev.get("valid_interaction"):
            return "unverified", "record_not_cited", \
                "Verifier: unverified. The cited evidence could not be confirmed against the interaction table." if claims else ""
        if ev.get("bad_chunk"):
            return "unverified", "chunk_reference_invalid", \
                "Verifier: unverified. A cited label passage could not be confirmed to name both drugs."
        return "verified", "table_match", ""

    # no record in the table for this pair
    if claims:
        return "unverified", "not_in_table", \
            "Verifier: unverified. The interaction table has no record for this pair, so this severity could not be confirmed."
    return "unverified", "no_table_record", ""


# ------------------------------------------------------------------------------------------------ summaries
def _before_disclaimer(text: str, disclaimer: str, line: str) -> str:
    return text.replace(disclaimer, f"{line}\n\n{disclaimer}", 1) if disclaimer in text else f"{text.rstrip()}\n\n{line}"


def enforce_summaries(summaries: dict, conflicts: int):
    """-> (summaries, actions, violations). Never raises; repairs by code, never by asking a model."""
    out, actions, found = dict(summaries or {}), [], []
    keys = [k for k in SUMMARY_KEYS if isinstance(out.get(k), str) and out[k].strip()]
    if not keys:
        return out, actions, ["summaries_missing"]

    if conflicts:
        for key, line in (("doctor_en", CONFLICT_NOTICE_EN), ("doctor_bn", CONFLICT_NOTICE_BN)):
            if key in keys:
                out[key] = _before_disclaimer(out[key], DISCLAIMER_FOR[key], line.format(n=conflicts))
        _append_once(actions, "conflict_notice_added")

    text = " ".join(out[k] for k in keys)
    replace = False
    if contains_dosing_language(text):
        _append_once(found, "dosing_language")
        replace = True
    if claims_safety(text):
        _append_once(found, "safety_claim")
        replace = True
    if replace:
        for key in keys:
            out[key] = f"{INSUFFICIENT_FOR[key]}\n\n{DISCLAIMER_FOR[key]}"
        _append_once(actions, "replaced_with_insufficient_evidence")

    for key in keys:
        if DISCLAIMER_FOR[key] not in out[key]:
            _append_once(found, f"disclaimer_missing:{key}")
            out[key] = f"{out[key].rstrip()}\n\n{DISCLAIMER_FOR[key]}"
            _append_once(actions, f"disclaimer_added:{key}")
    return out, actions, found


# ------------------------------------------------------------------------------------------------ node
def run(state: dict) -> dict:
    trace: list = []
    findings_in = list(state.get("findings") or [])
    resolved = state.get("resolved_drugs") or []
    names = {_int(d.get("drug_id")): str(d.get("generic") or "") for d in resolved if _int(d.get("drug_id")) is not None}

    with traced(trace, "verifier", 5, f"{len(findings_in)} findings, {len(names)} resolved drugs") as t:
        violations: list = []
        pairs = [_pair_of(f) for f in findings_in]
        pair_ok = [p is not None and p[0] in names and p[1] in names for p in pairs]

        # 1) the interaction table, asked again, for the pair taken from the RESOLVED drugs (not from the finding text)
        calls, call_for = [], {}
        for i, p in enumerate(pairs):
            if pair_ok[i]:
                call_for[i] = len(calls)
                calls.append(("check_interaction", {"drug_a": names[p[0]], "drug_b": names[p[1]]}))
        tools_ok, transport, note, answers = True, "none", "", []
        if calls:
            try:
                batch = mcp_client.call_tools(calls)
                transport, note, answers = batch.transport, batch.note, batch.results
            except mcp_client.ToolCallError as exc:
                tools_ok, transport, note = False, "unavailable", str(exc)[:200]
                _append_once(violations, "verifier_tools_unavailable")
        t["tool_calls"].append({"tool": "transport", "transport": transport, "note": note})

        # 2) the records the findings cite
        ix_rows, chunk_rows = _load_evidence_rows(findings_in)
        drugs = Drug.objects.in_bulk(list(names)) if names else {}

        # 3) verdicts
        missing_evidence = findings_missing_evidence(findings_in)
        if missing_evidence:
            _append_once(violations, f"missing_evidence:{missing_evidence}")

        findings_out, counts = [], {"verified": 0, "unverified": 0, "conflict": 0}
        for i, f in enumerate(findings_in):
            severity = f.get("severity") if f.get("severity") in VALID else "unknown"
            p = pairs[i]
            table = (answers[call_for[i]] if tools_ok and i in call_for and call_for[i] < len(answers) else None)
            if pair_ok[i]:
                ev = _evidence_report(f.get("evidence"), p[0], p[1], ix_rows, chunk_rows, drugs)
                names_ok = all(not f.get(key) or str(f[key]).strip().lower() == names[p[idx]].lower()
                               for idx, key in enumerate(("drug_a", "drug_b")))
            else:
                ev, names_ok = {}, True
            status, code, sentence = judge(severity=severity, pair_ok=pair_ok[i], names_ok=names_ok, table=table, ev=ev)

            new = dict(f)
            if i in missing_evidence:
                # rule: no warning without a source -> insufficient evidence, and the violation stays on record
                new.update(severity="unknown", rationale=INSUFFICIENT_EVIDENCE_EN, confidence=0.0)
                status, code = "unverified", "missing_evidence"
            else:
                new["severity"] = severity
                if sentence and sentence not in str(new.get("rationale") or ""):
                    new["rationale"] = f"{with_period(str(new.get('rationale') or '').strip())} {sentence}".strip()
                confidence = _float(new.get("confidence"))
                if status == "conflict":
                    new["confidence"] = round(min(confidence, CONFLICT_CONFIDENCE_CAP), 2)
                elif status == "unverified" and severity in KNOWN:
                    new["confidence"] = round(min(confidence, UNVERIFIED_CLAIM_CONFIDENCE_CAP), 2)
            new["verification_status"] = status
            counts[status] += 1
            findings_out.append(new)

            t["tool_calls"].append({
                "tool": "verify_finding",
                "pair": [names.get(p[0]) if p else None, names.get(p[1]) if p else None],
                "claimed_severity": severity,
                "table": {"status": (table or {}).get("status", "unavailable"), "severity": (table or {}).get("severity"),
                          "severity_conflict": bool((table or {}).get("severity_conflict"))},
                "evidence": {k: (v if isinstance(v, int) else len(v)) for k, v in ev.items()},
                "verdict": status, "reason": code,
            })

        # 4) coverage: one finding per pair of resolved drugs, no more, no fewer
        expected = {tuple(sorted(c)) for c in itertools.combinations(sorted(names), 2)}
        seen: dict = {}
        for i, p in enumerate(pairs):
            if pair_ok[i]:
                seen[tuple(sorted(p))] = seen.get(tuple(sorted(p)), 0) + 1
        for a, b in sorted(expected - set(seen))[:MAX_LISTED_VIOLATIONS]:
            _append_once(violations, f"missing_pair:{names[a]}+{names[b]}")
        for (a, b), n in sorted(seen.items()):
            if n > 1:
                _append_once(violations, f"duplicate_pair:{names[a]}+{names[b]}")

        # 5) summaries
        summaries, actions, summary_found = enforce_summaries(state.get("summaries"), counts["conflict"])
        for v in summary_found:
            _append_once(violations, v)
        text = " ".join(str(summaries.get(k) or "") for k in SUMMARY_KEYS)
        for v in check_output(summary_text=text, findings=findings_out, summaries=summaries):
            _append_once(violations, v)
        violations = list(dict.fromkeys(list(state.get("violations") or []) + violations))
        t["tool_calls"].append({"tool": "summary_guardrail", "actions": actions})

        t["output_summary"] = (
            f"{len(findings_out)} findings: verified={counts['verified']} unverified={counts['unverified']} "
            f"conflict={counts['conflict']}; violations={violations or 'none'}; tools via {transport}"
        )
    return {"findings": findings_out, "summaries": summaries, "violations": violations, "trace": trace}