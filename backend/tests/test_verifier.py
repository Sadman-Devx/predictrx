"""Verifier: verdict rules (pure), summary enforcement (pure) and an end-to-end run against the real tables."""
import pytest

from ai.agents import verifier
from ai.guardrails.output_checks import DISCLAIMER_BN, DISCLAIMER_EN, INSUFFICIENT_EVIDENCE_EN
from tests.factories import DrugFactory, make_interaction


def ev(**kw):
    return {"valid_interaction": 0, "bad_interaction": [], "valid_chunk": 0, "bad_chunk": [], **kw}


def found(severity, **kw):
    return {"status": "found", "severity": severity, **kw}


# ------------------------------------------------------------------------------------------ judge()
def test_verified_only_when_table_agrees_and_record_is_cited():
    assert verifier.judge(severity="major", table=found("major"), ev=ev(valid_interaction=1))[0] == "verified"
    assert verifier.judge(severity="major", table=found("major"), ev=ev())[0] == "unverified"


def test_conflict_when_severity_differs_or_is_understated():
    assert verifier.judge(severity="minor", table=found("major"), ev=ev(valid_interaction=1))[0] == "conflict"
    assert verifier.judge(severity="unknown", table=found("major"), ev=ev(valid_interaction=1))[0] == "conflict"


def test_conflict_when_table_sources_disagree():
    status, code, _ = verifier.judge(severity="major", table=found("major", severity_conflict=True),
                                     ev=ev(valid_interaction=1))
    assert (status, code) == ("conflict", "sources_disagree")


def test_conflict_when_cited_record_is_not_about_this_pair():
    status, code, _ = verifier.judge(severity="major", table=found("major"),
                                     ev=ev(valid_interaction=1, bad_interaction=[99]))
    assert (status, code) == ("conflict", "evidence_interaction_mismatch")


def test_no_record_is_never_verified():
    no_record = {"status": "no_record"}
    assert verifier.judge(severity="unknown", table=no_record, ev=ev())[0] == "unverified"
    assert verifier.judge(severity="major", table=no_record, ev=ev(valid_chunk=1))[0] == "unverified"


def test_tools_down_means_unverified_not_verified():
    assert verifier.judge(severity="major", table=None, ev=ev(valid_interaction=1))[0] == "unverified"


def test_pair_or_names_that_do_not_match_are_conflicts():
    assert verifier.judge(severity="major", pair_ok=False, table=found("major"), ev={})[0] == "conflict"
    assert verifier.judge(severity="major", names_ok=False, table=found("major"), ev=ev())[0] == "conflict"


def test_evidence_report_checks_pair_and_existence():
    rows = {5: {"drug_a_id": 1, "drug_b_id": 2}, 6: {"drug_a_id": 1, "drug_b_id": 3}}
    report = verifier._evidence_report(
        [{"type": "interaction", "id": 5}, {"type": "interaction", "id": 6}, {"type": "interaction", "id": 404},
         {"type": "chunk", "id": 1}], 2, 1, rows, {}, {})
    assert report["valid_interaction"] == 1 and report["bad_interaction"] == [6, 404] and report["bad_chunk"] == [1]


# ------------------------------------------------------------------------------------------ summaries
def good_summaries():
    return {"doctor_en": f"Review. No record does not mean a combination is safe.\n\n{DISCLAIMER_EN}",
            "doctor_bn": f"পর্যালোচনা।\n\n{DISCLAIMER_BN}", "patient_card_bn": f"কার্ড।\n\n{DISCLAIMER_BN}"}


def test_clean_summaries_pass_unchanged():
    out, actions, violations = verifier.enforce_summaries(good_summaries(), 0)
    assert out == good_summaries() and actions == [] and violations == []


def test_dosing_and_safe_claims_are_replaced_and_disclaimer_kept():
    bad = {**good_summaries(), "doctor_en": f"Increase the dose of this medicine.\n\n{DISCLAIMER_EN}"}
    out, actions, violations = verifier.enforce_summaries(bad, 0)
    assert "dosing_language" in violations and out["doctor_en"].startswith(INSUFFICIENT_EVIDENCE_EN)
    assert DISCLAIMER_EN in out["doctor_en"] and DISCLAIMER_BN in out["patient_card_bn"]

    claim = {**good_summaries(), "patient_card_bn": f"ওষুধগুলো একসাথে নিরাপদ।\n\n{DISCLAIMER_BN}"}
    assert "safety_claim" in verifier.enforce_summaries(claim, 0)[2]


def test_missing_disclaimer_is_added_by_code():
    out, actions, violations = verifier.enforce_summaries({**good_summaries(), "doctor_bn": "পর্যালোচনা।"}, 0)
    assert "disclaimer_missing:doctor_bn" in violations and out["doctor_bn"].endswith(DISCLAIMER_BN)


def test_conflict_notice_goes_before_the_disclaimer():
    out, actions, _ = verifier.enforce_summaries(good_summaries(), 2)
    assert "conflict_notice_added" in actions
    assert out["doctor_en"].index("2 finding(s) conflict") < out["doctor_en"].index(DISCLAIMER_EN)


# ------------------------------------------------------------------------------------------ run() on real rows
@pytest.fixture
def pair(db, monkeypatch):
    from apps.drugs import services

    monkeypatch.setenv("AI_TOOL_TRANSPORT", "direct")  # no MCP server needed in the test
    a, b = DrugFactory(generic_name="verifalpha"), DrugFactory(generic_name="verifbeta")
    ix = make_interaction(a, b, severity="major", source="ddinter")
    services.invalidate_cache()
    return a, b, ix


def state(pair, findings, summaries=None):
    a, b, _ = pair
    return {"resolved_drugs": [{"drug_id": d.id, "generic": d.generic_name} for d in (a, b)],
            "findings": findings, "summaries": summaries or good_summaries(), "trace": []}


def finding(pair, **overrides):
    a, b, ix = pair
    lo, hi = sorted((a, b), key=lambda d: d.id)
    base = {"drug_a_id": lo.id, "drug_b_id": hi.id, "drug_a": lo.generic_name, "drug_b": hi.generic_name,
            "severity": "major", "rationale": "Table lists a major interaction.", "confidence": 0.8,
            "verification_status": "unverified", "evidence": [{"type": "interaction", "id": ix.id, "source": "ddinter"}]}
    return {**base, **overrides}


def test_honest_finding_is_verified(pair):
    out = verifier.run(state(pair, [finding(pair)]))
    assert out["findings"][0]["verification_status"] == "verified" and out["violations"] == []
    assert out["trace"][0]["agent_name"] == "verifier" and out["trace"][0]["step_order"] == 5


def test_seeded_wrong_severity_is_flagged(pair):
    out = verifier.run(state(pair, [finding(pair, severity="minor")]))
    f = out["findings"][0]
    assert f["verification_status"] == "conflict" and "Verifier: conflict" in f["rationale"] and f["confidence"] <= 0.3
    assert "conflict with the interaction table" in out["summaries"]["doctor_en"]


def test_fabricated_evidence_is_a_conflict(pair):
    bad = finding(pair, evidence=[{"type": "interaction", "id": 999999999, "source": "ddinter"}])
    assert verifier.run(state(pair, [bad]))["findings"][0]["verification_status"] == "conflict"


def test_severity_without_evidence_is_downgraded_with_a_violation(pair):
    out = verifier.run(state(pair, [finding(pair, evidence=[])]))
    f = out["findings"][0]
    assert f["severity"] == "unknown" and f["verification_status"] == "unverified"
    assert f["rationale"] == INSUFFICIENT_EVIDENCE_EN and any(v.startswith("missing_evidence") for v in out["violations"])


def test_dropped_pair_is_reported(pair):
    out = verifier.run(state(pair, []))
    assert any(v.startswith("missing_pair:") for v in out["violations"])


def test_tools_unavailable_leaves_everything_unverified(pair, monkeypatch):
    from ai import mcp_client

    def boom(calls):
        raise mcp_client.ToolCallError("down")

    monkeypatch.setattr(mcp_client, "call_tools", boom)
    out = verifier.run(state(pair, [finding(pair)]))
    assert out["findings"][0]["verification_status"] == "unverified"
    assert "verifier_tools_unavailable" in out["violations"]