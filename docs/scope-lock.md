# Scope & KPI Lock (Day 1 — Lead Dev)

Fill in and commit on Day 1. Changing anything here after 16 Nov needs the whole team's agreement.

## Core (must ship)
- [ ] Brand → generic resolver (curated sample mapping, `unresolved` shown honestly)
- [ ] Prescription scan → human-confirmed medication list
- [ ] Multi-agent pipeline (Resolver, Clinical Notes, Drug Interaction, Advisory, **Verifier**)
- [ ] Evidence-cited findings (no source → "insufficient evidence")
- [ ] PII redaction + disclaimer + output guardrail
- [ ] Measured evaluation on an independent test set
- [ ] Bangla UI (doctor view + patient card)
- [ ] Custom MCP (SSE) + 1 external MCP, documented
- [ ] Live demo URL (Cloudflare Tunnel), 3-minute video, portal form

## Cuttable, in this order (see `roadmap.md` cut order)
1. NRB family view (keep as slide + minimal page)
2. Digital Twin (reduce to one what-if example)
3. Admin reskin
4. Graph RAG depth
5. ESP32 / federated learning / audio → roadmap slide only

## KPIs (fill from REAL runs only; never pre-fill)
| KPI | Target / how measured | Owner | Result (n = ?) |
|---|---|---|---|
| % findings with a cited source | 100% — automated check | Lead | |
| Interaction recall on independent test set | measured on `EvalRun` | Lead + Docs/QA | |
| Precision on the same set | measured on `EvalRun` | Lead + Docs/QA | |
| Brand-resolution accuracy (held-out brands) | measured | Docs/QA | |
| Review time vs. manual lookup | timed, small n, stated as such | Docs/QA | |

## Open questions to settle on Day 1
- [ ] Is 20 Nov the active portal deadline for our round? (KB listed 31 Oct for preliminary)
- [ ] Who is the pharmacist/mentor who reviews the brand sheet and the eval set?
- [ ] Which external public MCP server will we use? (decide by Day 4)
- [ ] Embedding model + dimension (must match `EMBEDDING_DIM`)
- [ ] NRB / mentor contributions — real ones only (for PRD §6 and the portal form)
