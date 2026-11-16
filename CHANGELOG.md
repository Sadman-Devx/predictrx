# Changelog

## [Unreleased]
- Day 10 (Lead): What-if / Digital Twin (`apps/twin`): `POST /api/twin/` adds one hypothetical drug to a completed run and
  compares the interaction picture (before / after, added findings with evidence, no-record pairs, limitations). Computed
  from the `Interaction` table only (no LLM), so it answers synchronously and always matches the Verifier's data. Same
  request = same scenario (no duplicates); `GET /api/twin/{id}/`, `GET /api/analysis/{id}/twin/` (history). Owner-only,
  audited (`twin_run`, `twin_read`), `no-store`, throttled (`twin`, `twin_read`). Labs/vitals do not change severity.
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