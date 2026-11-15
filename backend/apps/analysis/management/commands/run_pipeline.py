"""Manual check of the whole LangGraph pipeline, without a patient, an AnalysisRun or Celery.

    python manage.py run_pipeline warfarin aspirin omeprazole
    python manage.py run_pipeline Napa warfarin aspirin --transport direct
    python manage.py run_pipeline warfarin aspirin --age-band 70-79 --lab "creatinine:1.8:0.6-1.2:mg/dL" --note "CKD stage 3"
    python manage.py run_pipeline warfarin aspirin --json

It calls the SAME code path as the Celery task (runner._invoke_pipeline), so the agents, MCP/direct tool calls and RAG
behave exactly as in a real run. Nothing is written to the database: no RiskFinding, AgentTrace or AuditLog rows.
It also shows what runner.normalize_finding() WOULD store, so a downgraded or malformed finding is visible here.

Use synthetic input only (rule.md §3). Names are redacted the same way the real snapshot is.
"""
import json
import os

from django.core.management.base import BaseCommand, CommandError

from ai.guardrails.output_checks import contains_dosing_language
from ai.guardrails.pii import redact
from apps.analysis import runner
from apps.drugs import services
from apps.drugs.models import Drug


class Command(BaseCommand):
    help = ("Run Resolver -> Clinical Notes -> Drug Interaction -> Advisory -> Verifier on drug names and print the "
            "trace, findings and summaries. Writes nothing to the database.")

    def add_arguments(self, parser):
        parser.add_argument("drugs", nargs="+", help="brand or generic names, e.g. warfarin aspirin Napa")
        parser.add_argument("--transport", choices=["mcp", "mcp_only", "direct"], default=None,
                            help="tool transport for this command only (default: AI_TOOL_TRANSPORT / mcp with fallback)")
        parser.add_argument("--age-band", default=None, help='e.g. "70-79"')
        parser.add_argument("--sex", default=None)
        parser.add_argument("--weight", type=float, default=None, help="weight in kg")
        parser.add_argument("--lab", action="append", default=[],
                            help='"name:value:range:unit", e.g. "creatinine:1.8:0.6-1.2:mg/dL" (repeatable)')
        parser.add_argument("--note", action="append", default=[], help="short synthetic clinical note (repeatable)")
        parser.add_argument("--json", action="store_true", help="print the final state as JSON")

    # ------------------------------------------------------------------------------------------ input
    @staticmethod
    def _medication(position: int, name: str) -> dict:
        """Same shape as apps/analysis/services.build_snapshot()['medications'] entries."""
        clean = redact(name.strip()).text
        drug = None
        result = services.resolve_brand(name.strip())
        if result.get("status") == "resolved":
            drug = Drug.objects.filter(generic_name=str(result.get("generic", "")).lower()).first()
        if drug is None:
            drug = Drug.objects.filter(generic_name=name.strip().lower()).first()
        return {
            "medication_id": position, "raw_text": clean, "brand_name": clean, "strength": None, "frequency": None,
            "drug_id": drug.id if drug else None, "generic_name": drug.generic_name if drug else None,
            "resolution_status": "resolved" if drug else "unresolved", "source": "manual",
        }

    @staticmethod
    def _lab(text: str) -> dict:
        parts = (text.split(":", 3) + ["", "", ""])[:4]
        name, value, ref_range, unit = (p.strip() for p in parts)
        if not name:
            raise CommandError(f"Bad --lab value {text!r}. Use name:value:range:unit")
        return {"test_name": name, "value": value or None, "unit": unit, "ref_range": ref_range}

    # ------------------------------------------------------------------------------------------ output
    def _print_trace(self, trace: list) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("\nAgent trace"))
        for t in sorted(trace, key=lambda x: x.get("step_order", 0)):
            self.stdout.write(f"[{t.get('step_order')}] {t.get('agent_name'):<17} {t.get('latency_ms'):>6} ms  "
                              f"{t.get('output_summary', '')}")
            for call in t.get("tool_calls") or []:
                if call.get("tool") == "transport":
                    note = f"  ({call['note']})" if call.get("note") else ""
                    self.stdout.write(f"      tools via: {call.get('transport')}{note}")
                elif call.get("tool") == "rag":
                    self.stdout.write(f"      rag: vector_pairs={call.get('vector_pairs')} "
                                      f"graph_pairs={call.get('graph_pairs')} warnings={call.get('warnings') or 'none'}")

    def _print_findings(self, findings: list, allowed: set) -> list:
        self.stdout.write(self.style.MIGRATE_HEADING(f"\nFindings ({len(findings)})"))
        stored = []
        for f in findings:
            try:
                n = runner.normalize_finding(f, allowed)
            except runner.MalformedFinding as exc:
                self.stdout.write(self.style.ERROR(f"- {f.get('drug_a')} + {f.get('drug_b')}: MALFORMED ({exc}) "
                                                   f"-> a real run would FAIL"))
                continue
            stored.append(n)
            evidence = ", ".join(f"{e['type']}#{e['id']}({e['source']})" for e in n["evidence"]) or "none"
            self.stdout.write(
                f"- {n['severity'].upper():<8} {f.get('drug_a')} + {f.get('drug_b')}  conf={n['confidence']}  "
                f"verification={n['verification_status']}  pair_status={f.get('pair_status', '-')}")
            self.stdout.write(f"    evidence: {evidence}")
            self.stdout.write(f"    {n['rationale']}")
            if n["severity"] != f.get("severity"):
                self.stdout.write(self.style.WARNING(
                    f"    ! runner would downgrade severity {f.get('severity')} -> {n['severity']}"))
        return stored

    def _print_checks(self, result: dict, stored: list, findings: list, summaries: dict) -> None:
        text = " ".join(str(summaries.get(k, "")) for k in ("doctor_en", "doctor_bn", "patient_card_bn"))
        agents = [t.get("agent_name") for t in result.get("trace") or []]
        checks = [
            ("every stored severity has evidence", all(s["severity"] == "unknown" or s["evidence"] for s in stored)),
            ("all findings can be stored", len(stored) == len(findings)),
            ("no dosing language in summaries", not contains_dosing_language(text)),
            ("trace has all 5 agents",
             all(a in agents for a in ("resolver", "clinical_notes", "drug_interaction", "advisory", "verifier"))),
            ("verifier ran and labelled every finding",
             "verifier" in agents and all(f.get("verification_status") in ("verified", "unverified", "conflict")
                                          for f in findings)),
            ("no output-guardrail violations", not result.get("violations")),
        ]
        self.stdout.write(self.style.MIGRATE_HEADING("\nChecks (informational)"))
        for label, ok in checks:
            self.stdout.write((self.style.SUCCESS("PASS  ") if ok else self.style.ERROR("FAIL  ")) + label)

    # ------------------------------------------------------------------------------------------ entry
    def handle(self, *args, **opts):
        if opts["transport"]:
            os.environ["AI_TOOL_TRANSPORT"] = opts["transport"]  # read by ai.config.setting(); this process only

        meds = [self._medication(i, name) for i, name in enumerate(opts["drugs"], start=1) if name.strip()]
        if not meds:
            raise CommandError("Give at least one drug name.")
        snapshot = {
            "medications": meds,
            "patient_context": {
                "age_band": opts["age_band"], "sex": opts["sex"], "weight_kg": opts["weight"],
                "labs": [self._lab(x) for x in opts["lab"]],
                "notes": [redact(n).text for n in opts["note"]],
            },
        }
        allowed = {m["drug_id"] for m in meds if m["drug_id"]}

        self.stdout.write(self.style.MIGRATE_HEADING("Input"))
        for m in meds:
            state = f"-> {m['generic_name']} (drug #{m['drug_id']})" if m["drug_id"] else "-> UNRESOLVED (will be a gap)"
            self.stdout.write(f"  {m['raw_text']} {state}")

        seen: list = []

        def on_step(state: dict) -> None:
            for name in runner._agents_done(state):
                if name not in seen:
                    seen.append(name)
                    self.stdout.write(self.style.SUCCESS(f"  done: {name}"))

        self.stdout.write(self.style.MIGRATE_HEADING("\nPipeline"))
        try:
            result = runner._invoke_pipeline(snapshot, on_step=on_step)
        except runner.PipelineUnavailable as exc:
            raise CommandError(f"AI package not installed: {exc}. Run: pip install -r requirements/ai.txt") from exc
        except Exception as exc:  # noqa: BLE001 — a manual tool: show the real error type instead of a traceback wall
            raise CommandError(f"Pipeline failed ({exc.__class__.__name__}): {exc}") from exc

        findings = result.get("findings") or []
        summaries = result.get("summaries") or {}
        gaps = result.get("gaps") or []

        if opts["json"]:
            self.stdout.write(json.dumps({
                "resolved_drugs": result.get("resolved_drugs"), "gaps": gaps, "findings": findings,
                "summaries": summaries, "violations": result.get("violations"), "trace": result.get("trace"),
            }, ensure_ascii=False, indent=2, default=str))
            return

        self._print_trace(result.get("trace") or [])
        stored = self._print_findings(findings, allowed)
        if gaps:
            self.stdout.write(self.style.MIGRATE_HEADING("\nGaps (not checked)"))
            for g in gaps:
                self.stdout.write(f"- {g.get('raw_text')}: {g.get('reason')} candidates={g.get('candidates') or 'none'}")
        for key, title in (("doctor_en", "Doctor summary (EN)"), ("doctor_bn", "Doctor summary (BN)"),
                           ("patient_card_bn", "Patient card (BN)")):
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{title}"))
            self.stdout.write(str(summaries.get(key, "")))
        self._print_checks(result, stored, findings, summaries)