# Changelog

## [Unreleased]
- Day 7: Verifier agent (`ai/agents/verifier.py`): re-checks every finding through `check_interaction` + the cited
  records, labels `verified / unverified / conflict`, downgrades uncited severities, reports missing/duplicate pairs,
  enforces the summary guardrail (dosing, "safe" claims, disclaimers). Guardrails: `claims_safety`, disclaimer checks.
  PII redaction: names, addresses, DOB, labelled IDs, Bangla digits, stable on re-run. LLM router: cloud calls are
  redacted at the door, sensitive text is local-only, optional fallback to Ollama. Manual tools:
  `manage.py verify_demo`, `manage.py run_pipeline`.
- Day 6: LangGraph pipeline (Resolver, Clinical Notes, Drug Interaction, Advisory), `AgentTrace`/`RiskFinding`
  persistence in `apps/analysis/runner.py`, live progress for the pipeline stepper.
- Day 4: `apps/drugs/services.py` (resolve_brand, lookup_drug, check_interaction, search), `/api/medications/resolve/`,
  `/api/drugs/search/`, DB-backed MCP server + SSE test client, `load_brands.py` + sample brand sheet, tests.
- Repo scaffold: backend (Django/DRF), frontend (React/Vite), MCP server skeleton, docs, vitals (roadmap) module.