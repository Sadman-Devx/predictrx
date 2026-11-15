from ai.guardrails.output_checks import (DISCLAIMER_BN, DISCLAIMER_EN, check_output, claims_safety,
                                         contains_dosing_language, findings_missing_evidence, missing_disclaimers)
from ai.guardrails.pii import contains_pii, redact


def test_redacts_email_phone_and_id():
    r = redact("Contact a@b.com or 01712345678 or +8801812345678, NID 1234567890123")
    assert "a@b.com" not in r.text
    assert "01712345678" not in r.text
    assert "1234567890123" not in r.text
    assert r.counts["EMAIL"] == 1 and r.counts["PHONE"] == 2 and r.counts["ID"] == 1


def test_redacts_bangla_digit_phone():
    r = redact("ফোন ০১৭১২৩৪৫৬৭৮")
    assert "০১৭১২৩৪৫৬৭৮" not in r.text and r.counts == {"PHONE": 1}


def test_redacts_labelled_name_honorific_address_and_dob():
    r = redact("Name: Rahim Uddin\nage 70. Dr. Rahman advised rest.\nAddress: House 12, Road 5, Dhanmondi\nDOB: 12/03/1950")
    for leaked in ("Rahim", "Uddin", "Rahman", "Dhanmondi", "1950"):
        assert leaked not in r.text
    assert r.counts == {"NAME": 2, "ADDRESS": 1, "DOB": 1}
    assert "age 70" in r.text  # clinical context is kept


def test_redacts_bangla_labelled_name_and_address():
    r = redact("নাম: রহিম উদ্দিন\nঠিকানা: ঢাকা ১২")
    assert "রহিম" not in r.text and "ঢাকা" not in r.text
    assert r.counts == {"NAME": 1, "ADDRESS": 1}


def test_clinical_text_and_drug_names_are_not_redacted():
    text = "Warfarin with aspirin, INR 2.5, ALT 40, Tab Napa 500. Drug name: Napa. NID verified."
    assert redact(text).text == text and not contains_pii(text)


def test_redaction_is_stable_so_counts_do_not_inflate():
    once = redact("Name: Rahim Uddin; Dr. Rahman; Address: House 12; 01712345678; DOB: 12/03/1950; a@b.com")
    twice = redact(once.text)
    assert twice.text == once.text and twice.counts == {}


def test_dosing_language_detected():
    assert contains_dosing_language("Take 500 mg twice daily")
    assert contains_dosing_language("You should stop taking this medicine")
    assert not contains_dosing_language("Please discuss this combination with your doctor.")


def test_finding_without_evidence_is_flagged():
    findings = [{"severity": "major", "evidence": []}, {"severity": "unknown", "evidence": []},
                {"severity": "minor", "evidence": [{"type": "interaction", "id": 1}]}]
    assert findings_missing_evidence(findings) == [0]
    assert "dosing_language" in check_output(summary_text="Increase the dose", findings=[])


def test_safe_claim_only_allowed_inside_a_negation():
    assert claims_safety("These two medicines are safe together.")
    assert claims_safety("ওষুধগুলো একসাথে নিরাপদ।")
    assert not claims_safety("No record does not mean a combination is safe.")
    assert not claims_safety("রেকর্ড না থাকা মানে সংমিশ্রণটি নিরাপদ, তা নয়।")


def test_missing_disclaimer_is_reported():
    summaries = {"doctor_en": "text", "doctor_bn": f"text {DISCLAIMER_BN}", "patient_card_bn": ""}
    assert missing_disclaimers(summaries) == ["doctor_en"]
    problems = check_output(summary_text="ok", findings=[], summaries={"doctor_en": f"ok {DISCLAIMER_EN}",
                                                                        "doctor_bn": "ok"})
    assert problems == ["disclaimer_missing:doctor_bn"]