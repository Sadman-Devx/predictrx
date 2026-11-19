# PredictRx — 3-minute demo video script

Target length: **3:00** (hard cap). Language: narrate in English with Bangla on-screen captions (or the reverse — pick one and keep it).
Rule: every shot must be a **real run** of the deployed app, on **synthetic data**. No mock-ups, no fabricated numbers.
Before recording: log in as the demo doctor, make sure the "DEMO DATA" badge is visible, and open the agent trace once so it is warm.

| # | Segment | Time | On screen | Narration |
|---|---|---|---|---|
| 1 | Problem & users | 0:00–0:30 | Prescription photo with local brand names; one slide: doctor / caregiver / NRB family | "In Bangladesh, patients take medicines by **brand name** and carry paper prescriptions. Interaction databases speak English and generic names. A busy doctor has no quick, trustworthy way to check a medication list — and an NRB son or daughter abroad can't see risk in a parent's medicines at all. PredictRx closes that gap." |
| 2 | AI solution | 0:30–1:00 | Login page (Bangla/English toggle) → Dashboard → one slide of the pipeline: Resolver → Clinical Notes → Drug Interaction → Advisory → Verifier | "PredictRx is a **Bangla-first, evidence-cited medication-safety assistant**. A multi-agent pipeline resolves brand to generic, checks interactions against public sources, and a **Verifier agent** cross-checks every finding. If there is no source, it says *insufficient evidence* — it never guesses. It is decision support, not a diagnosis." |
| 3 | Live demo / flow | 1:00–2:05 | Scan a **synthetic** prescription → Review & Confirm (edit one drug, show resolve badges) → Run analysis (stepper) → Results (severity cards, evidence chips, verified/unverified/conflict) → Patient card (Bangla) → Family view → What-if | "I upload a synthetic prescription. The model extracts the drugs — and I **confirm** the list; a human is always in the loop. Brand names resolve to generics, unresolved ones are flagged, not guessed. The pipeline runs live. Each finding shows its **mechanism, source and confidence**, plus a verification badge. The patient gets a short Bangla card — no dosing, just 'discuss with your doctor'. With consent, a family member sees a read-only summary. And a what-if: add one more drug and see how the interaction picture changes." |
| 4 | AI approach | 2:05–2:35 | Architecture graphic; agent trace panel showing `mcp_sse` tool calls; one line each: LangGraph, RAG, MCP, Ollama | "Under the hood: **LangGraph** agents, **RAG** over openFDA labels with semantic chunking, contextual prefixes and a graph of drug–interaction links, stored in **Postgres + pgvector**. A **custom MCP server over SSE** exposes `resolve_brand`, `lookup_drug` and `check_interaction` — the Verifier uses the same deterministic tools, independent of the LLM's prose. **PII is redacted** before any cloud call; embeddings run locally on **Ollama**. Data comes through an ingest → parse → clean → store → analytics pipeline, orchestrated with **n8n**, hosted on an Azure VM." |
| 5 | Impact, KPIs, next steps | 2:35–3:00 | KPI slide (only numbers from a recorded eval run — see note) → roadmap slide → closing card with project name + link | "Our goal: **100% of warnings carry a source**. [Insert measured recall / precision / n **only if** the pharmacist-reviewed test set has been run — otherwise say 'we report measured accuracy once our reviewed test set is complete'.] Next: licensed data for commercial use, pharmacist-verified brand mapping, IoT vitals, federated learning across hospitals. PredictRx — fewer medication errors, in Bangla, with evidence you can check." |

## Shot list & checks
- [ ] Record on the **live URL** (not localhost), from a clean browser profile.
- [ ] Use only the synthetic demo patient; no real names, no real prescriptions.
- [ ] Show the disclaimer strip ("Decision support only. Not a diagnosis.") at least once, clearly.
- [ ] Show one **unresolved/unverified** case on purpose — it proves the system is honest.
- [ ] Captions in Bangla + English; check Bangla text for typos.
- [ ] Do not show API keys, `.env`, demo passwords or the database dump.
- [ ] Do not claim any accuracy, time-saved or KPI number that is not backed by a recorded run.
- [ ] Do not claim NRB/mentor contribution unless it really happened.
- [ ] Upload to YouTube (unlisted/public as the portal requires), confirm it plays while logged out, then paste the link into `form-fields.md` and the portal.
- [ ] Keep a **fallback clip** (screen recording of the full demo path) in case the live site is down during judging.

## Video link
`[TBD — YouTube URL]`
