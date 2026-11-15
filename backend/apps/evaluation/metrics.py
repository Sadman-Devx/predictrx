"""Pure evaluation maths: no Django, no database, no network. Everything here is unit-testable on its own.

Definitions (state them next to every number in the pitch, with n):

  Label (independent reviewer)   none | minor | moderate | major
  Prediction (PredictRx)         unknown | minor | moderate | major     ("unknown" = no cited evidence, never "safe")

  Detection (does the system flag a pair the reviewer says interacts?)
      TP  reviewer: minor/moderate/major   system: any severity
      FN  reviewer: minor/moderate/major   system: unknown        (a missed pair, or "insufficient evidence")
      FP  reviewer: none                   system: any severity
      TN  reviewer: none                   system: unknown
      recall = TP / (TP + FN)        precision = TP / (TP + FP)

  A rate with an empty denominator is `None` (not 0, not 1): "not measurable" is different from "bad".
  Every rate ships with a 95% Wilson interval, because the sets are small and a bare percentage over-states certainty.
"""
import hashlib
import math
from collections import Counter

POSITIVE = ("minor", "moderate", "major")
EXPECTED = ("none",) + POSITIVE
PREDICTED = ("unknown",) + POSITIVE
_RANK = {"none": 0, "unknown": 0, "minor": 1, "moderate": 2, "major": 3}
Z95 = 1.96


# ------------------------------------------------------------------------------------------------ rates
def ratio(k: int, n: int):
    return None if not n else round(k / n, 4)


def wilson(k: int, n: int, z: float = Z95):
    """95% Wilson score interval for k successes in n trials, or None when n == 0."""
    if not n:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def rate(k: int, n: int) -> dict:
    return {"k": k, "n": n, "value": ratio(k, n), "ci95": wilson(k, n)}


def format_rate(r) -> str:
    if not r or r.get("value") is None:
        return f"not measurable (n={(r or {}).get('n', 0)})"
    lo, hi = r["ci95"]
    return f"{r['value']:.1%}  ({r['k']}/{r['n']}, 95% CI {lo:.0%}-{hi:.0%})"


def fingerprint(rows) -> str:
    """Order-independent hash of a labelled set: two runs with the same fingerprint used the same cases."""
    digest = hashlib.sha256()
    for line in sorted("|".join(str(part) for part in row) for row in rows):
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


# ------------------------------------------------------------------------------------------------ detection
def detection_metrics(outcomes) -> dict:
    """outcomes: iterable of (expected, predicted). Raises ValueError on a label that is not in the vocabulary."""
    outcomes = list(outcomes)
    confusion = {e: {p: 0 for p in PREDICTED} for e in EXPECTED}
    for expected, predicted in outcomes:
        if expected not in EXPECTED:
            raise ValueError(f"expected severity {expected!r} is not one of {EXPECTED}")
        if predicted not in PREDICTED:
            raise ValueError(f"predicted severity {predicted!r} is not one of {PREDICTED}")
        confusion[expected][predicted] += 1

    tp = sum(confusion[e][p] for e in POSITIVE for p in POSITIVE)
    fn = sum(confusion[e]["unknown"] for e in POSITIVE)
    fp = sum(confusion["none"][p] for p in POSITIVE)
    tn = confusion["none"]["unknown"]

    precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
    f1 = None if precision is None or recall is None or (precision + recall) == 0 \
        else round(2 * precision * recall / (precision + recall), 4)

    per_severity = {}
    for sev in POSITIVE:
        n_expected = sum(confusion[sev].values())
        n_predicted = sum(confusion[e][sev] for e in EXPECTED)
        per_severity[sev] = {
            "n_expected": n_expected,
            "detected": rate(n_expected - confusion[sev]["unknown"], n_expected),  # flagged at all, any severity
            "exact": rate(confusion[sev][sev], n_expected),  # flagged with exactly this severity
            "n_predicted": n_predicted,
            "precision_exact": rate(confusion[sev][sev], n_predicted),
        }

    exact_among_detected = sum(confusion[s][s] for s in POSITIVE)
    undercalled = sum(confusion[e][p] for e in POSITIVE for p in POSITIVE if _RANK[p] < _RANK[e])
    overcalled = sum(confusion[e][p] for e in POSITIVE for p in POSITIVE if _RANK[p] > _RANK[e])
    n_major = sum(confusion["major"].values())
    major_not_major = n_major - confusion["major"]["major"]

    return {
        "n": len(outcomes),
        "positives": tp + fn,
        "negatives": fp + tn,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "recall": rate(tp, tp + fn),
        "precision": rate(tp, tp + fp),
        "specificity": rate(tn, tn + fp),
        "f1": f1,
        "severity_agreement": rate(exact_among_detected, tp),  # among detected pairs: same severity as the reviewer
        "undercalled": undercalled,  # flagged, but lower than the reviewer's severity (the risky direction)
        "overcalled": overcalled,
        "major_not_called_major": rate(major_not_major, n_major),  # reviewer: major, system: lower or unknown
        "per_severity": per_severity,
        "confusion": confusion,  # confusion[expected][predicted]
    }


# ------------------------------------------------------------------------------------------------ brand resolution
def brand_metrics(rows) -> dict:
    """rows: dicts {expected, status, generic, match_type}. `expected` is a generic name or "unresolved"
    (a brand that is NOT in the mapping and must therefore come back unresolved).

    correct_resolved    resolved to the reviewer's generic
    wrong_resolution    resolved to a DIFFERENT generic (the dangerous outcome: a silent wrong match)
    missed              left unresolved although the reviewer knows the generic (honest, but a coverage gap)
    correct_abstention  left unresolved and the reviewer agrees it should be
    """
    rows = list(rows)
    count = Counter()
    by_match_type: dict = {}
    for row in rows:
        expected = str(row.get("expected") or "unresolved").strip().lower()
        known = expected != "unresolved"
        resolved = row.get("status") == "resolved"
        got = str(row.get("generic") or "").strip().lower()
        match_type = str(row.get("match_type") or "none")
        count["known"] += known
        if resolved:
            ok = known and got == expected
            count["correct_resolved" if ok else "wrong_resolution"] += 1
            bucket = by_match_type.setdefault(match_type, {"correct": 0, "wrong": 0})
            bucket["correct" if ok else "wrong"] += 1
            if match_type == "exact":
                count["exact_lookup"] += 1
        else:
            count["missed" if known else "correct_abstention"] += 1

    n = len(rows)
    resolved_total = count["correct_resolved"] + count["wrong_resolution"]
    return {
        "n": n,
        "known_n": count["known"],
        "unresolvable_n": n - count["known"],
        "correct_resolved": count["correct_resolved"],
        "wrong_resolution": count["wrong_resolution"],
        "missed": count["missed"],
        "correct_abstention": count["correct_abstention"],
        "accuracy": rate(count["correct_resolved"] + count["correct_abstention"], n),
        "resolved_precision": rate(count["correct_resolved"], resolved_total),
        "coverage_of_known": rate(count["correct_resolved"], count["known"]),
        "wrong_resolution_rate": rate(count["wrong_resolution"], n),
        "by_match_type": by_match_type,
        # Circularity indicator: how much of the set was answered by a plain lookup of a row we loaded ourselves.
        "exact_lookup_share": rate(count["exact_lookup"], n),
    }