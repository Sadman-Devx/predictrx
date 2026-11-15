"""Evaluation services (business logic; views, tasks and commands stay thin).

Rules this module enforces (docs/rule.md §2, backend-design §8):
  * The test set must be INDEPENDENT of what the system retrieves from. A row whose source note names DDInter or
    openFDA is refused for the test split (grading DDInter against DDInter is circular).
  * Dev and test never share a pair (unique canonical pair) and an existing case is never re-labelled or moved by a
    reload: a split that could change after the fact is a split you can tune on.
  * The system is graded through the SAME decision code the Drug Interaction agent uses (`drug_interaction._build`),
    not through a re-implementation, so the eval cannot drift away from what the product does.
  * Numbers are never made up: a run that cannot finish ends `failed` with a code and stores no metrics.
  * The test split is "reported once": every extra run is counted and labelled in the run's config.
"""
import csv
import hashlib
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from apps.drugs import services as drug_services
from apps.drugs.models import BrandMapping, Drug, Interaction

from . import metrics
from .models import EvalCase, EvalRun

logger = logging.getLogger(__name__)

EXPECTED = metrics.EXPECTED
SPLITS = ("dev", "test")
DEFAULT_SEED = "predictrx-eval-v1"
DEFAULT_TEST_FRACTION = 0.5
MIN_CASES_WARN = 30  # below this, say loudly that the set is small
MIN_PER_SEVERITY_WARN = 5
CALL_CHUNK = 50  # tool calls per MCP session (keeps one session far below the MCP timeout)
STUCK_MINUTES = 30  # a queued/running eval older than this lost its worker: fail it so a new one can start
MIN_RATIONALE_LEN = 10
CIRCULAR_SOURCES = ("ddinter", "openfda")  # data the system retrieves from: not independent
MAX_DEV_DETAILS = 200

EVAL_CASE_COLUMNS = ("drug_a", "drug_b", "expected_severity", "rationale_ref")
EVAL_BRAND_COLUMNS = ("brand_name", "expected_generic")


class EvalRequestError(APIException):
    """Client-fixable problem. Shape: {"error": {"code": <specific>, "message": ..., "details": {...}}}."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "bad_request"

    def __init__(self, code: str, message: str, *, http_status: int | None = None, **extra):
        super().__init__(detail={"detail": message, "code": code, **extra})
        if http_status:
            self.status_code = http_status


# ------------------------------------------------------------------------------------------------ CSV input
def read_csv_rows(path, required: tuple):
    """Yield (line_number, row) with lower-cased headers and stripped values. Raises ValueError on missing columns."""
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
        missing = [c for c in required if c not in headers]
        if missing:
            raise ValueError(f"Missing column(s): {', '.join(missing)}. Found: {', '.join(h for h in headers if h) or 'none'}")
        reader.fieldnames = headers
        for line_no, row in enumerate(reader, start=2):
            yield line_no, {k: (v or "").strip() for k, v in row.items() if k and isinstance(v, (str, type(None)))}


def _norm_name(value) -> str:
    return " ".join(str(value or "").strip().lower().split())


def assign_split(generic_a: str, generic_b: str, *, test_fraction: float = DEFAULT_TEST_FRACTION,
                 seed: str = DEFAULT_SEED) -> str:
    """Deterministic, order-independent split for a pair (hash of the two generic NAMES, so it is the same on
    every machine and database). Pure: the same pair + seed + fraction always gives the same answer."""
    first, second = sorted((generic_a, generic_b))
    digest = hashlib.sha256(f"{seed}|{first}|{second}".encode("utf-8")).hexdigest()
    return "test" if int(digest[:8], 16) / 0xFFFFFFFF < test_fraction else "dev"


# ------------------------------------------------------------------------------------------------ loading the eval set
@dataclass
class LoadReport:
    dry_run: bool = False
    rows_read: int = 0
    created: int = 0
    created_by_split: Counter = field(default_factory=Counter)
    skipped: Counter = field(default_factory=Counter)
    skipped_lines: dict = field(default_factory=dict)  # reason -> first line numbers
    created_drugs: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def skip(self, line: int, reason: str) -> None:
        self.skipped[reason] += 1
        lines = self.skipped_lines.setdefault(reason, [])
        if len(lines) < 10:
            lines.append(line)

    @property
    def skipped_total(self) -> int:
        return sum(self.skipped.values())


def _generic_drug(name: str, *, cache: dict, create_missing: bool, dry_run: bool, report: LoadReport):
    """-> (Drug | None, reason | None, planned). Only an exact generic name or alias is accepted: a brand name or a
    typo-level match would put a guess into the reviewer's label."""
    if name in cache:
        return cache[name]
    res = drug_services.resolve_brand(name)
    drug, reason, planned = None, None, False
    if res.get("status") == "resolved":
        if res.get("match_type") == "generic":
            drug = Drug.objects.filter(generic_name=res["generic"]).first()
            reason = None if drug else "drug_not_in_database"
        elif res.get("match_type") == "exact":
            reason = "brand_name_not_allowed"  # labels are about generics; resolve the brand first
        else:
            reason = "not_an_exact_generic_name"
    elif res.get("reason") == "no_match":
        if create_missing:
            planned = dry_run
            if not dry_run:
                drug = Drug.objects.create(generic_name=name, external_ids={"created_by": "load_eval_cases"})
            report.created_drugs.append(name)
        else:
            reason = "drug_not_in_database"
    else:
        reason = f"unresolved_{res.get('reason', 'unknown')}"
    cache[name] = (drug, reason, planned)
    return cache[name]


def load_eval_cases(rows, *, test_fraction: float = DEFAULT_TEST_FRACTION, seed: str = DEFAULT_SEED,
                    dry_run: bool = False, allow_unreviewed: bool = False, allow_circular_dev: bool = False,
                    create_missing_drugs: bool = False) -> LoadReport:
    """rows: iterable of (line_number, dict). Optional columns: reviewed_by, split (dev|test).

    Every refused row is counted with a reason (nothing is dropped silently). Existing cases are never changed.
    Drugs that are not in the database are refused unless `create_missing_drugs`: refusing them hides coverage
    gaps (the system genuinely cannot answer for a drug it does not know), so the report says how many there were.
    """
    report = LoadReport(dry_run=dry_run)
    test_reported = EvalRun.objects.filter(kind="pairs", split="test", status="completed").exists()
    cache: dict = {}
    seen_in_file: set = set()
    to_create: list = []

    with transaction.atomic():
        for line, row in rows:
            report.rows_read += 1
            name_a, name_b = _norm_name(row.get("drug_a")), _norm_name(row.get("drug_b"))
            if not name_a or not name_b:
                report.skip(line, "missing_drug_name")
                continue
            if name_a == name_b:
                report.skip(line, "same_drug")
                continue

            expected = (row.get("expected_severity") or "").strip().lower()
            if expected not in EXPECTED:
                report.skip(line, "invalid_expected_severity")
                continue
            rationale = (row.get("rationale_ref") or "").strip()
            reviewer = (row.get("reviewed_by") or "").strip()
            if len(rationale) < MIN_RATIONALE_LEN:
                report.skip(line, "missing_rationale_ref")
                continue
            if len(rationale) > 300 or len(reviewer) > 100:
                report.skip(line, "text_too_long")
                continue
            if not reviewer and not allow_unreviewed:
                report.skip(line, "missing_reviewer")
                continue

            requested = (row.get("split") or "").strip().lower()
            if requested not in ("", *SPLITS):
                report.skip(line, "invalid_split")
                continue
            circular = any(word in f"{rationale} {reviewer}".lower() for word in CIRCULAR_SOURCES)
            if circular and (not allow_circular_dev or requested == "test"):
                report.skip(line, "circular_source")  # DDInter/openFDA-based label: not independent
                continue

            drug_a, reason_a, planned_a = _generic_drug(name_a, cache=cache, create_missing=create_missing_drugs,
                                                        dry_run=dry_run, report=report)
            drug_b, reason_b, planned_b = _generic_drug(name_b, cache=cache, create_missing=create_missing_drugs,
                                                        dry_run=dry_run, report=report)
            if reason_a or reason_b:
                report.skip(line, reason_a or reason_b)
                continue

            generic_a = drug_a.generic_name if drug_a else name_a
            generic_b = drug_b.generic_name if drug_b else name_b
            pair_key = tuple(sorted((generic_a, generic_b)))
            if pair_key in seen_in_file:
                report.skip(line, "duplicate_pair_in_file")
                continue
            seen_in_file.add(pair_key)

            split = "dev" if circular else (requested or assign_split(generic_a, generic_b, test_fraction=test_fraction,
                                                                      seed=seed))
            if planned_a or planned_b:  # dry run + drug that would be created: nothing to compare in the database
                report.created += 1
                report.created_by_split[split] += 1
                continue

            low, high = Interaction.canonical(drug_a.id, drug_b.id)
            existing = EvalCase.objects.filter(drug_a_id=low, drug_b_id=high).first()
            if existing is not None:
                report.skip(line, "already_loaded" if existing.expected_severity == expected
                            else "conflicts_with_existing_label")
                continue

            to_create.append(EvalCase(drug_a_id=low, drug_b_id=high, expected_severity=expected,
                                      rationale_ref=rationale, reviewed_by=reviewer, split=split))
            report.created += 1
            report.created_by_split[split] += 1

        if to_create and not dry_run:
            EvalCase.objects.bulk_create(to_create)
        if report.created_drugs and not dry_run:
            drug_services.invalidate_cache()  # bulk lookups must see the new drugs at once

    if report.created_drugs:
        report.notes.append(
            f"{len(report.created_drugs)} drug(s) were not in the database and were "
            f"{'WOULD BE ' if dry_run else ''}created for this set. Review them: a typo becomes a junk drug.")
    if report.created_by_split.get("test") and test_reported and not dry_run:
        report.notes.append("A test run already exists. The test set changed, so earlier test numbers describe a "
                            "different set (compare the fingerprint of each run).")
    return report


# ------------------------------------------------------------------------------------------------ describing the set
def split_warnings(split: str, n: int, by_severity: dict) -> list:
    warnings = []
    if n == 0:
        return [f"{split}: no cases."]
    if n < MIN_CASES_WARN:
        warnings.append(f"{split}: only {n} cases (< {MIN_CASES_WARN}). Read the confidence intervals, not the point values.")
    thin = [s for s in metrics.POSITIVE if by_severity.get(s, 0) < MIN_PER_SEVERITY_WARN]
    if thin:
        warnings.append(f"{split}: fewer than {MIN_PER_SEVERITY_WARN} cases labelled {', '.join(thin)}: "
                        "per-severity numbers are not reliable.")
    if by_severity.get("none", 0) == 0:
        warnings.append(f"{split}: no cases labelled 'none'. Precision is not measurable without pairs the reviewer "
                        "says do not interact.")
    return warnings


def describe_set() -> dict:
    """Case counts per split and per expected severity, plus warnings about size and balance."""
    out: dict = {"warnings": []}
    for split in SPLITS:
        counts = dict(EvalCase.objects.filter(split=split).values_list("expected_severity").annotate(n=Count("id")))
        by_severity = {s: counts.get(s, 0) for s in EXPECTED}
        out[split] = {"n": sum(by_severity.values()), "by_expected_severity": by_severity,
                      "unreviewed": EvalCase.objects.filter(split=split, reviewed_by="").count()}
        out["warnings"].extend(split_warnings(split, out[split]["n"], by_severity))
    return out


# ------------------------------------------------------------------------------------------------ prediction
@dataclass(frozen=True)
class Prediction:
    severity: str  # minor | moderate | major | unknown
    pair_status: str  # record | label_only | no_record | record_unreferenced
    cited: bool


class _NoLabels:
    """Stand-in for the RAG label search. Severity comes ONLY from the interaction table (agent docstring), so
    label passages cannot change a prediction here: skipping them keeps the eval fast and independent of Ollama."""

    def find(self, a_id: int, b_id: int):
        return [], "none"


def predict_cases(cases: list) -> tuple[list, dict]:
    """Grade the system on `cases` (EvalCase rows with drug_a / drug_b loaded) -> (predictions, config).

    Goes through `mcp_client.call_tools` exactly like the agent (MCP over SSE, or the same functions directly; the
    transport really used is recorded). `ToolCallError` is NOT caught: without the table there is nothing honest to
    report, so the run fails visibly.
    """
    from ai import mcp_client  # lazy: keeps this module importable in light environments
    from ai.agents import drug_interaction

    calls = [("check_interaction", {"drug_a": c.drug_a.generic_name, "drug_b": c.drug_b.generic_name}) for c in cases]
    results, transports, notes = [], set(), []
    for start in range(0, len(calls), CALL_CHUNK):
        batch = mcp_client.call_tools(calls[start:start + CALL_CHUNK])
        results.extend(batch.results)
        transports.add(batch.transport)
        if batch.note and batch.note not in notes:
            notes.append(batch.note)

    drug_ids = sorted({i for c in cases for i in (c.drug_a_id, c.drug_b_id)})
    ix_ids = drug_interaction._interaction_ids(drug_ids)  # noqa: SLF001 — same citation lookup the agent uses
    labels = _NoLabels()
    predictions = []
    for case, result in zip(cases, results):
        a = {"drug_id": case.drug_a_id, "generic": case.drug_a.generic_name}  # canonical order: a.id < b.id
        b = {"drug_id": case.drug_b_id, "generic": case.drug_b.generic_name}
        finding, _chunks, _call = drug_interaction._build(a, b, result, ix_ids, labels)  # noqa: SLF001
        predictions.append(Prediction(finding["severity"], finding["pair_status"], bool(finding["evidence"])))

    config = {
        "predictor": "drug_interaction._build over check_interaction (the product's own decision code)",
        "transports": sorted(transports),
        "transport_notes": notes[:3],
        "label_search": "not used: severity comes only from the interaction table",
        "interaction_rows_by_source": dict(Interaction.objects.values_list("source").annotate(n=Count("id"))),
    }
    return predictions, config


# ------------------------------------------------------------------------------------------------ run bookkeeping
def fail_stale_runs() -> int:
    cutoff = timezone.now() - timedelta(minutes=STUCK_MINUTES)
    return EvalRun.objects.filter(status__in=["queued", "running"], created_at__lt=cutoff).update(
        status="failed", error_code="timeout", finished_at=timezone.now())


def start_run(*, split: str, user=None) -> EvalRun:
    """Create a queued pair-evaluation. One at a time: a second click while one is running is a 409, not a duplicate.
    (Admin-only endpoint; two admins clicking in the same millisecond is accepted as a very small risk.)"""
    if split not in SPLITS:
        raise EvalRequestError("invalid_split", "split must be 'dev' or 'test'.")
    fail_stale_runs()
    if EvalRun.objects.filter(kind="pairs", status__in=["queued", "running"]).exists():
        raise EvalRequestError("eval_in_progress", "An evaluation is already queued or running.",
                               http_status=status.HTTP_409_CONFLICT)
    n = EvalCase.objects.filter(split=split).count()
    if n == 0:
        raise EvalRequestError("no_eval_cases", f"The {split} split has no cases. Load the reviewed set first.")
    return EvalRun.objects.create(kind="pairs", split=split, status="queued", n_cases=n, created_by=user,
                                  config={"split": split})


def enqueue(run_id: int) -> None:
    """Call after the transaction commits (transaction.on_commit), so the worker can never see a run that is not there yet."""
    from .tasks import run_evaluation

    try:
        run_evaluation.delay(run_id)
    except Exception:  # noqa: BLE001 — broker outage: fail visibly instead of leaving a run 'queued' forever
        logger.exception("could not enqueue eval run %s", run_id)
        EvalRun.objects.filter(pk=run_id, status="queued").update(status="failed", error_code="enqueue_failed",
                                                                 finished_at=timezone.now())


def case_fingerprint(cases) -> str:
    return metrics.fingerprint(
        (c.drug_a.generic_name, c.drug_b.generic_name, c.expected_severity, c.split) for c in cases)


# ------------------------------------------------------------------------------------------------ brand resolution eval
def run_brand_eval(rows, *, user=None) -> tuple[EvalRun, list]:
    """Grade `resolve_brand` on a held-out list. rows: iterable of (line, dict) with brand_name, expected_generic and
    optional strength / reviewed_by. -> (completed EvalRun, error list). The error list is for the person at the
    console only and is NOT stored: fixing the mapping until the held-out list passes would be tuning on it."""
    started = timezone.now()
    outcomes, errors, unreviewed, keys = [], [], 0, []
    for line, row in rows:
        brand = (row.get("brand_name") or "").strip()
        if not brand:
            continue
        expected = _norm_name(row.get("expected_generic")) or "unresolved"
        res = drug_services.resolve_brand(brand, (row.get("strength") or "").strip() or None)
        outcome = {"expected": expected, "status": res.get("status"), "generic": res.get("generic"),
                   "match_type": res.get("match_type")}
        outcomes.append(outcome)
        keys.append((brand.lower(), (row.get("strength") or "").strip().lower(), expected))
        unreviewed += 0 if (row.get("reviewed_by") or "").strip() else 1
        got = (res.get("generic") or "unresolved") if res.get("status") == "resolved" else "unresolved"
        if got != expected:
            errors.append({"line": line, "brand": brand, "expected": expected, "got": got,
                           "reason": res.get("reason") or res.get("match_type")})
    if not outcomes:
        raise EvalRequestError("no_eval_cases", "The brand list has no usable rows.")

    result = metrics.brand_metrics(outcomes)
    caveats = []
    if len(outcomes) < MIN_CASES_WARN:
        caveats.append(f"Only {len(outcomes)} brands: read the confidence intervals.")
    if result["unresolvable_n"] == 0:
        caveats.append("No brand labelled 'unresolved': a wrong silent match on unknown brands is not measured.")
    share = result["exact_lookup_share"]["value"]
    if share is not None and share > 0.5:
        caveats.append("Most brands were answered by an exact lookup of a row we loaded ourselves: the held-out "
                       "list may overlap the mapping, so accuracy is optimistic.")
    if unreviewed:
        caveats.append(f"{unreviewed} row(s) have no reviewer.")
    run = EvalRun.objects.create(
        kind="brands", split="", status="completed", n_cases=len(outcomes), metrics=result, created_by=user,
        fingerprint=metrics.fingerprint(keys), started_at=started, finished_at=timezone.now(),
        config={"resolver": "apps.drugs.services.resolve_brand",
                "brand_mappings_total": BrandMapping.objects.count(),
                "brand_mappings_verified": BrandMapping.objects.filter(verified=True).count(),
                "caveats": caveats})
    return run, errors