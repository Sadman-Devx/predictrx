from ai.graph import build_graph


def test_pipeline_runs_in_order_and_traces_every_agent():
    out = build_graph().invoke({"medications": [{"raw_text": "Napa 500"}]})
    names = [t["agent_name"] for t in out["trace"]]
    assert names == ["resolver", "clinical_notes", "drug_interaction", "advisory", "verifier"]
    assert out["violations"] == []
