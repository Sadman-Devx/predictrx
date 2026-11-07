from ai.guardrails.output_checks import check_output, contains_dosing_language, findings_missing_evidence
from ai.guardrails.pii import redact


def test_redacts_email_phone_and_id():
    r = redact("Contact a@b.com or 01712345678 or +8801812345678, NID 1234567890123")
    assert "a@b.com" not in r.text
    assert "01712345678" not in r.text
    assert "1234567890123" not in r.text
    assert r.counts["EMAIL"] == 1 and r.counts["PHONE"] == 2 and r.counts["ID"] == 1


def test_dosing_language_detected():
    assert contains_dosing_language("Take 500 mg twice daily")
    assert contains_dosing_language("You should stop taking this medicine")
    assert not contains_dosing_language("Please discuss this combination with your doctor.")


def test_finding_without_evidence_is_flagged():
    findings = [{"severity": "major", "evidence": []}, {"severity": "unknown", "evidence": []},
                {"severity": "minor", "evidence": [{"type": "interaction", "id": 1}]}]
    assert findings_missing_evidence(findings) == [0]
    assert "dosing_language" in check_output(summary_text="Increase the dose", findings=[])
