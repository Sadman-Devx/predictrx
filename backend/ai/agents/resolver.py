"""Resolver agent (step 1).

Every medication in a run was already linked to a Drug before the run started (the API refuses unresolved or
unconfirmed medications). The Resolver therefore does NOT re-decide that link: the person's choice wins. It

  * groups medications by drug (two brands of one generic = one drug),
  * cross-checks each medication against the `resolve_brand` MCP tool and records agree / disagree / unresolved,
  * turns anything without a drug link into an explicit GAP with candidate suggestions (never auto-applied).

Output: resolved_drugs [{drug_id, generic, medication_ids, labels, crosschecks}], gaps [medication dict + reason].
"""
from .. import mcp_client
from ..guardrails.pii import redact
from .common import med_label, traced


def _crosscheck(generic: str, result) -> str:
    if not isinstance(result, dict) or result.get("status") != "resolved":
        return "unresolved"
    names = {str(result.get("generic", "")).lower(), *(str(a).lower() for a in result.get("aliases") or [])}
    return "agree" if generic in names else "disagree"


def _compact(result) -> dict:
    if not isinstance(result, dict):
        return {}
    keys = ("status", "generic", "match_type", "confidence", "verified", "reason")
    return {k: result[k] for k in keys if k in result}


def run(state: dict) -> dict:
    trace: list = []
    meds = list(state.get("medications") or [])
    with traced(trace, "resolver", 1, f"{len(meds)} medications") as t:
        queries = []  # (index of medication, tool arguments)
        for i, m in enumerate(meds):
            name = (m.get("brand_name") or m.get("raw_text") or "").strip()
            if not name:
                continue
            args = {"brand": name}
            if m.get("strength"):
                args["strength"] = str(m["strength"])
            queries.append((i, args))

        results: dict = {}
        transport, note = "none", ""
        if queries:
            try:
                batch = mcp_client.call_tools([("resolve_brand", a) for _, a in queries])
                results = {i: r for (i, _), r in zip(queries, batch.results)}
                transport, note = batch.transport, batch.note
            except mcp_client.ToolCallError as exc:
                # The saved drug links still stand; only the cross-check is lost, and the trace says so.
                transport, note = "unavailable", str(exc)[:200]

        t["tool_calls"].append({"tool": "transport", "transport": transport, "note": note})
        for i, args in queries:
            if i in results:
                t["tool_calls"].append({
                    "tool": "resolve_brand",
                    "args": {"brand": redact(args["brand"]).text, **({"strength": args["strength"]} if "strength" in args else {})},
                    "result": _compact(results[i]),
                })

        by_drug: dict = {}
        gaps: list = []
        counts = {"agree": 0, "disagree": 0, "unresolved": 0, "unavailable": 0}
        for i, m in enumerate(meds):
            generic = str(m.get("generic_name") or "").strip().lower()
            drug_id = m.get("drug_id")
            result = results.get(i)
            if not drug_id or not generic:
                candidates: list = []
                if isinstance(result, dict):
                    if result.get("status") == "resolved":
                        candidates = [result.get("generic")]  # a suggestion for the person, never applied here
                    else:
                        candidates = list(result.get("candidates") or [])
                gaps.append({**m, "reason": "needs_user_selection", "candidates": [c for c in candidates if c]})
                continue
            check = "unavailable" if i not in results else _crosscheck(generic, result)
            counts[check] += 1
            entry = by_drug.setdefault(drug_id, {"drug_id": drug_id, "generic": generic, "medication_ids": [],
                                                 "labels": [], "crosschecks": []})
            entry["medication_ids"].append(m.get("medication_id"))
            entry["labels"].append(med_label(m))
            entry["crosschecks"].append(check)

        resolved = sorted(by_drug.values(), key=lambda d: d["drug_id"])
        t["output_summary"] = (
            f"{len(resolved)} distinct drugs from {len(meds)} medications; gaps={len(gaps)}; "
            f"crosscheck agree={counts['agree']} disagree={counts['disagree']} "
            f"unresolved={counts['unresolved']} unavailable={counts['unavailable']}; tools via {transport}"
        )
    return {"resolved_drugs": resolved, "gaps": gaps, "trace": trace}