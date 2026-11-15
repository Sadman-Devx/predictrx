"""Manual check of the Verifier: feed it honest and deliberately WRONG findings and see what it says.

    python manage.py verify_demo warfarin aspirin
    python manage.py verify_demo warfarin aspirin --transport direct

Steps: the Drug Interaction and Advisory agents produce honest findings/summaries for the pair, then the Verifier is
run on six variants of them. Nothing is written to the database; use drugs that exist in your loaded data.

    1 honest              nothing tampered                              -> no conflict, no violation
    2 wrong severity      severity changed                              -> conflict
    3 fabricated evidence cites an interaction record that is not real  -> conflict
    4 claim, no evidence  severity but empty evidence                   -> downgraded to unknown + violation
    5 dropped pair        the finding is missing                        -> missing_pair violation
    6 bad summaries       dosing language, no disclaimer                -> replaced + disclaimer added + violation
"""
import copy
import os

from django.core.management.base import BaseCommand, CommandError

from ai.agents import advisory, drug_interaction, verifier
from ai.guardrails.output_checks import DISCLAIMER_EN, contains_dosing_language
from apps.drugs import services
from apps.drugs.models import Drug


def _drug(name: str):
    result = services.resolve_brand(name.strip())
    drug = None
    if result.get("status") == "resolved":
        drug = Drug.objects.filter(generic_name=str(result.get("generic", "")).lower()).first()
    return drug or Drug.objects.filter(generic_name=name.strip().lower()).first()


class Command(BaseCommand):
    help = "Run the Verifier on honest and tampered findings for two drugs. Writes nothing to the database."

    def add_arguments(self, parser):
        parser.add_argument("drug_a")
        parser.add_argument("drug_b")
        parser.add_argument("--transport", choices=["mcp", "mcp_only", "direct"], default=None)

    def _run(self, base: dict, findings: list, summaries: dict) -> dict:
        return verifier.run({**base, "findings": copy.deepcopy(findings), "summaries": dict(summaries), "trace": []})

    def _show(self, title: str, expect: str, result: dict, ok: bool) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{title}"))
        self.stdout.write(f"expect: {expect}")
        for f in result["findings"]:
            self.stdout.write(f"  {f.get('drug_a')} + {f.get('drug_b')}: severity={f.get('severity')} "
                              f"status={f.get('verification_status')} confidence={f.get('confidence')}")
            self.stdout.write(f"    {f.get('rationale')}")
        if not result["findings"]:
            self.stdout.write("  (no findings)")
        self.stdout.write(f"  violations: {result['violations'] or 'none'}")
        self.stdout.write((self.style.SUCCESS("PASS") if ok else self.style.ERROR("FAIL")) + f"  {title}")

    def handle(self, *args, **opts):
        if opts["transport"]:
            os.environ["AI_TOOL_TRANSPORT"] = opts["transport"]
        a, b = _drug(opts["drug_a"]), _drug(opts["drug_b"])
        if a is None or b is None or a.id == b.id:
            raise CommandError("Both names must resolve to two different drugs that exist in the database.")

        resolved = [{"drug_id": d.id, "generic": d.generic_name, "medication_ids": [i], "labels": [d.generic_name],
                     "crosschecks": ["agree"]} for i, d in enumerate(sorted((a, b), key=lambda x: x.id), start=1)]
        base = {"resolved_drugs": resolved, "gaps": [], "patient_context": {}, "trace": []}
        try:
            found = drug_interaction.run(base)
            summaries = advisory.run({**base, **found})["summaries"]
        except Exception as exc:  # noqa: BLE001 — manual tool: show the real reason
            raise CommandError(f"Could not build honest findings ({exc.__class__.__name__}): {exc}") from exc
        honest = found["findings"]
        if len(honest) != 1:
            raise CommandError("Expected exactly one pair.")
        self.stdout.write(f"honest finding: severity={honest[0]['severity']} pair_status={honest[0]['pair_status']} "
                          f"evidence={honest[0]['evidence']}")

        statuses = lambda r: [f["verification_status"] for f in r["findings"]]  # noqa: E731
        has = lambda r, prefix: any(v.startswith(prefix) for v in r["violations"])  # noqa: E731

        r1 = self._run(base, honest, summaries)
        self._show("1 honest", "no conflict, no missing_evidence/missing_pair", r1,
                   "conflict" not in statuses(r1) and not has(r1, "missing_"))

        wrong = copy.deepcopy(honest)
        wrong[0]["severity"] = "minor" if wrong[0]["severity"] == "major" else "major"
        if honest[0]["severity"] == "unknown":  # no table record to contradict: cite a record that is not real
            wrong[0]["evidence"] = [{"type": "interaction", "id": 999999999, "source": "ddinter"}]
        r2 = self._run(base, wrong, summaries)
        self._show("2 wrong severity", "status conflict", r2, statuses(r2) == ["conflict"])

        fake = copy.deepcopy(honest)
        fake[0].update(severity="major", evidence=[{"type": "interaction", "id": 999999999, "source": "ddinter"}])
        r3 = self._run(base, fake, summaries)
        self._show("3 fabricated evidence", "status conflict", r3, statuses(r3) == ["conflict"])

        bare = copy.deepcopy(honest)
        bare[0].update(severity="major", evidence=[])
        r4 = self._run(base, bare, summaries)
        self._show("4 claim without evidence", "severity unknown, unverified, violation missing_evidence", r4,
                   [f["severity"] for f in r4["findings"]] == ["unknown"] and statuses(r4) == ["unverified"]
                   and has(r4, "missing_evidence"))

        r5 = self._run(base, [], summaries)
        self._show("5 dropped pair", "violation missing_pair", r5, has(r5, "missing_pair"))

        bad = {**summaries, "doctor_en": "Increase the dose of the first medicine twice daily."}
        r6 = self._run(base, honest, bad)
        en = r6["summaries"]["doctor_en"]
        self._show("6 bad summaries", "dosing replaced, disclaimer present, violation dosing_language", r6,
                   "dosing_language" in r6["violations"] and not contains_dosing_language(en) and DISCLAIMER_EN in en)