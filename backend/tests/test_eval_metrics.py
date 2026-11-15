"""Day 9: evaluation maths and the dev/test split. Pure: no database, no model call, no network."""
import pytest

from apps.evaluation import metrics, services

OUTCOMES = [
    ("major", "major"),      # TP, exact
    ("moderate", "minor"),   # TP, under-called
    ("major", "unknown"),    # FN
    ("none", "unknown"),     # TN
    ("none", "minor"),       # FP
    ("minor", "minor"),      # TP, exact
]


def test_wilson_interval_known_values():
    low, high = metrics.wilson(5, 10)
    assert low == pytest.approx(0.2366, abs=1e-3) and high == pytest.approx(0.7634, abs=1e-3)
    low, high = metrics.wilson(0, 10)
    assert low == 0.0 and high == pytest.approx(0.2775, abs=1e-3)
    assert metrics.wilson(0, 0) is None


def test_rate_with_empty_denominator_is_not_measurable():
    assert metrics.rate(0, 0) == {"k": 0, "n": 0, "value": None, "ci95": None}
    assert "not measurable" in metrics.format_rate(metrics.rate(0, 0))
    assert "75.0%" in metrics.format_rate(metrics.rate(3, 4))


def test_detection_counts_recall_and_precision():
    m = metrics.detection_metrics(OUTCOMES)
    assert (m["tp"], m["fn"], m["fp"], m["tn"]) == (3, 1, 1, 1)
    assert m["n"] == 6 and m["positives"] == 4 and m["negatives"] == 2
    assert m["recall"]["value"] == 0.75 and m["precision"]["value"] == 0.75
    assert m["f1"] == 0.75


def test_detection_severity_agreement_and_direction_of_error():
    m = metrics.detection_metrics(OUTCOMES)
    assert m["severity_agreement"]["k"] == 2 and m["severity_agreement"]["n"] == 3
    assert m["undercalled"] == 1 and m["overcalled"] == 0
    assert m["major_not_called_major"]["k"] == 1 and m["major_not_called_major"]["n"] == 2
    assert m["per_severity"]["major"]["detected"]["k"] == 1 and m["per_severity"]["major"]["detected"]["n"] == 2
    assert m["confusion"]["moderate"]["minor"] == 1


def test_precision_is_not_measurable_without_flags():
    m = metrics.detection_metrics([("none", "unknown")])
    assert m["precision"]["value"] is None
    assert m["recall"]["value"] is None
    assert m["f1"] is None


@pytest.mark.parametrize("bad", [("unknown", "major"), ("major", "none"), ("safe", "minor")])
def test_labels_outside_the_vocabulary_are_rejected(bad):
    with pytest.raises(ValueError):
        metrics.detection_metrics([bad])


def test_brand_metrics_separate_wrong_matches_from_honest_misses():
    rows = [
        {"expected": "paracetamol", "status": "resolved", "generic": "paracetamol", "match_type": "exact"},
        {"expected": "unresolved", "status": "unresolved", "generic": None, "match_type": None},
        {"expected": "metformin", "status": "resolved", "generic": "glimepiride", "match_type": "fuzzy"},
        {"expected": "omeprazole", "status": "unresolved", "generic": None, "match_type": None},
    ]
    m = metrics.brand_metrics(rows)
    assert (m["correct_resolved"], m["wrong_resolution"], m["missed"], m["correct_abstention"]) == (1, 1, 1, 1)
    assert m["accuracy"]["value"] == 0.5
    assert m["resolved_precision"]["value"] == 0.5
    assert m["coverage_of_known"]["k"] == 1 and m["coverage_of_known"]["n"] == 3
    assert m["by_match_type"] == {"exact": {"correct": 1, "wrong": 0}, "fuzzy": {"correct": 0, "wrong": 1}}
    assert m["exact_lookup_share"]["k"] == 1


def test_a_resolved_brand_that_should_stay_unresolved_is_wrong():
    m = metrics.brand_metrics([{"expected": "unresolved", "status": "resolved", "generic": "napa", "match_type": "fuzzy"}])
    assert m["wrong_resolution"] == 1 and m["correct_abstention"] == 0


def test_fingerprint_ignores_order_and_detects_change():
    a = [("x", "y", "major", "test"), ("p", "q", "none", "dev")]
    assert metrics.fingerprint(a) == metrics.fingerprint(list(reversed(a)))
    assert metrics.fingerprint(a) != metrics.fingerprint([("x", "y", "minor", "test"), a[1]])


def test_split_is_stable_and_order_independent():
    assert services.assign_split("warfarin", "aspirin") == services.assign_split("aspirin", "warfarin")
    assert services.assign_split("warfarin", "aspirin") == services.assign_split("warfarin", "aspirin")


def test_split_fraction_edges_and_balance():
    pairs = [(f"drug{i}", f"drug{i + 1000}") for i in range(200)]
    assert {services.assign_split(a, b, test_fraction=0.0) for a, b in pairs} == {"dev"}
    assert {services.assign_split(a, b, test_fraction=1.0) for a, b in pairs} == {"test"}
    in_test = sum(services.assign_split(a, b, test_fraction=0.5) == "test" for a, b in pairs)
    assert 70 <= in_test <= 130


def test_split_warnings_say_when_the_set_is_small_or_has_no_negatives():
    assert services.split_warnings("test", 0, {}) == ["test: no cases."]
    text = " ".join(services.split_warnings("test", 10, {"major": 4, "minor": 3, "moderate": 3, "none": 0}))
    assert "only 10 cases" in text and "labelled minor" in text and "'none'" in text
    ok = services.split_warnings("test", 60, {"major": 15, "minor": 15, "moderate": 15, "none": 15})
    assert ok == []