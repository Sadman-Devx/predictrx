# Congress knowledge-base checklist

**Audit status:** Findings reviewed by two people: Md. Shadman Hasan and Sraya Gharami, 2026-11-17
(verification confirmed by the project owner). This confirms the checklist audit, not completion of every
submission requirement. Boxes below remain unchecked wherever a deliverable or external check is still
outstanding or lacks evidence.

## Submission links and presentation

- [ ] **3-minute video with five required segments** — no video link or script is recorded in this repository.
  Record and upload the real demo, then add its URL to the portal.
- [ ] **Public GitHub repository and README** — [README.md](../README.md) exists; confirm repository visibility,
  submitted URL, and that the README renders correctly on GitHub.
- [ ] **Live demo URL and run owner** — [deploy/README.md](../deploy/README.md) documents a quick-tunnel setup,
  but its final URL, operator, and fallback recording are still blank.
- [ ] **Figma link** — [design/Figma Link/figmadesign.md](../design/Figma%20Link/figmadesign.md) records a link;
  confirm it opens for judges and points to the final design.
- [ ] **At least three supporting links** — collect and verify the required links; none are recorded in the
  submission pack.

## Portal and team facts

- [ ] **Portal form fields and character minimums** — `submission/form-fields.md` is not present. Prepare and
  check the token-optimization (>=50 characters), AI-DLC (>=100), and other-notes (>=80) fields against the
  live portal.
- [ ] **Team size, female-member field, and NRB/mentor contribution** — confirm each against the actual team
  and record only real contributions. Do not infer or invent these claims.
- [ ] **Active deadline confirmed** — `submission/README.md` says the target is 20 Nov 2026 and warns that the
  preliminary-round date in the KB may be stale; confirm the current portal deadline.

## Product, evidence, and documentation

- [ ] **Stack and AI tools documented** — [README.md](../README.md), `docs/`, and
  [mcp-server/README.md](../mcp-server/README.md) document major components. Verify the final list includes
  the actual LLM, contextual/semantic/graph RAG, LangGraph, Ollama, n8n, and the AI coding tool actually used.
- [ ] **MCP requirement** — [mcp-server/README.md](../mcp-server/README.md) documents the custom SSE server and
  an optional external PubMed MCP utility. Confirm the custom server works and describe the external utility
  accurately as research-only.
- [ ] **Data lifecycle** — [data/pipeline/README.md](../data/pipeline/README.md) documents ingest, parse,
  clean, store, indexing, and analytics. Verify the described commands against the final environment.
- [ ] **Cloudflare Tunnel** — [deploy/README.md](../deploy/README.md) has setup instructions; fill in the
  actual tunnel type, final URL, judging-time operator, and fallback.
- [ ] **One-page summary** — `submission/summary-1page.md` is not present. Prepare it from verified project
  facts and the judging criteria.
- [ ] **Working prototype and Bangla localization** — code is present, but a reproducible end-to-end demo,
  device/browser QA, and language review are not evidenced by this checklist. Run and record them.
- [ ] **Measured outcomes** — no KPI result is supported by a pharmacist-reviewed independent evaluation set.
  `data/fixtures/eval_cases.csv` currently contains draft, unreviewed `dev` candidates only; do not report
  metrics from them.
- [ ] **Data sources, licensing, AI tools, and contributions** — [data/SOURCES.md](../data/SOURCES.md) is
  explicitly a draft terms summary. Recheck official terms, record real AI-tool use and contributions, and
  obtain any required sign-off.
- [ ] **Brand mapping safety** — `data/brands/brand_mapping.csv` remains unverified and must not be loaded.
  Review [brand_mapping_review.csv](../data/brands/brand_mapping_review.csv), add row-level primary evidence,
  then obtain pharmacist/mentor review before marking any row verified.

## Remaining actions before any item can be ticked

1. Prepare the missing summary, video script/link, and portal text; confirm the deadline and team fields.
2. Verify each external link, demo access, tunnel operator, and fallback from a second person's account.
3. Recheck source terms and runtime/UX claims; do not treat code presence as clinical or production validation.
4. For each requirement completed later, attach its evidence and record both reviewers and the verification date.
