# PredictRx — 3-minute demo video (live URL only, no slides)

Everything is screen-recorded from **https://predictrx-assi.malaysiawest.cloudapp.azure.com**. Narration in English; Bangla shown where the product is Bangla-first. Synthetic data only (the "DEMO DATA" badge stays visible). Hard cap 3:00.

## Before you record
- Clean Chrome profile or F11 full-screen (hide profile photo, extensions, taskbar).
- UI in **English** for the main flow; switch to **Bangla** only for the language toggle and the Patient card.
- Pre-run one analysis on demo patient PX-2B5MHGN7 so Results, Agent trace and What-if are ready. Keep a scan ready for the live `/review` pass.
- Record the **auth part separately** (test email + demo Google account, inbox blurred) and cut it in.
- Rehearse once. Record in pieces and join them in an editor.

## Timeline

| Time | Page (live URL) | What you do | What you say |
|---|---|---|---|
| 0:00–0:14 | **/login** | Show the page; click বাংলা and back to English; point at the disclaimer strip | "In Bangladesh, patients take medicines by **brand name**, while interaction databases speak English and generic names. Doctors have little time to cross-check, and families abroad can't see the risk in a parent's medicines. PredictRx closes that gap." |
| 0:14–0:24 | **/register** → email OTP → code | Fill form, show the OTP email, enter code | "It's Bangla-first, with English too. New accounts are **verified by a one-time code** sent to email." |
| 0:24–0:30 | **/login** → Google (G) | Click G, pick the demo account | "Or sign in with Google." |
| 0:30–0:36 | **Dashboard** | Let the DEMO DATA badge and "New analysis" button show | "Everything here is synthetic demo data, and it's decision support, not a diagnosis." |
| 0:36–0:42 | **/patients/1** (patient record) | Click the patient; **scroll straight past the Consent card** to the safety history: severity bars per analysis and the "what changed" comparison; then click **New analysis** | "Each patient has a safety history, and a comparison of what changed between two analyses. Now a new analysis." |
| 0:42–0:58 | **New analysis → /review** | Prescription image beside the drug list; point at "matched" badges and the 100% generic match; on **Paracetamol (unresolved)** choose a generic; tick "I checked this list against the prescription"; click Run | "A vision model reads the prescription, but a **human confirms**. Matched brands show the generic and a match score. An ambiguous name is flagged, not guessed — I choose. Analysis won't start until every drug is resolved and I confirm." |
| 0:58–1:06 | **/analysis/3** (progress) | Let the 6 steps tick | "Six visible steps — upload, OCR, brand to generic, interaction check, guardrail and verify, final report — each with status and time." |
| 1:06–1:16 | **Results (top)** | Stats, severity donut, verification bar; hover Print / PDF | "Fifteen findings for six drugs, split by severity and by verification status. One click makes a sourced PDF for the clinician." |
| 1:16–1:30 | **Findings → Evidence** | Scroll from the top (major → moderate); open Evidence on *aspirin + ciprofloxacin* | "Major first. Every finding shows its source, licence and confidence, with a verified badge — so the claim can be checked." |
| 1:30–1:36 | **An unknown finding** (acetaminophen + ciprofloxacin) | Point at the text | "With no record it says so: **'no interaction record found — this does not mean the combination is safe.'**" |
| 1:36–1:44 | **Patient card** tab → switch UI to Bangla | Scroll the Bangla card and yellow box | "A plain-Bangla card for the patient or caregiver. It never tells anyone to start, stop or change a medicine." |
| 1:44–1:50 | **What-if** tab (back to English) | Show the "simulation for research" banner and the add-a-drug box | "A what-if view re-reads interaction records for an added drug. It's a lookup, not a forecast." |
| 1:50–2:10 | **Agent trace** tab | Scroll the agents and tool calls | "Under the hood: **LangGraph** agents, RAG over openFDA labels in Postgres with pgvector, and a **custom MCP server over SSE** with deterministic tools. The Verifier re-checks through the same tools, independent of the model's wording. PII is redacted before any cloud call; embeddings and sensitive text run locally on Ollama." |
| 2:10–2:20 | **Results (top)** again | Point at the counts | "In this run: 6 drugs, 15 pairs checked, 11 verified against a cited record, and pairs with no record shown as **unknown, never safe**. We claim no accuracy yet." |
| 2:20–2:28 | **Review queue** (পর্যালোচনার তালিকা) | Open "how the order is decided" (conflict → major → overdue follow-up → unverified → moderate …); **click outside the box** so no focus outline shows; point at the patient's flags | "A transparent, **rule-based** review order — no AI ranking. And a patient with no flag is never called safe." |
| 2:28–2:52 | **Trust center** (`/trust`) | Scroll top → bottom without stopping | "The Trust center states how it's protected — the Verifier, no 'safe' for missing records, a dosing guardrail, PII removal, an audit log — what is **still unverified**, and what's only planned: a pharmacist-verified brand list, independent evaluation, licensed data, ESP32 vitals, federated learning." |
| 2:52–3:00 | **/login** (URL visible) | Hold on the address bar | "PredictRx — fewer medication errors, in Bangla, with evidence you can check." |

**Numbers (2:10):** read them from your Results screen when you record (analysis #3: 6 drugs, 15 findings, 2 major, 5 moderate, 1 minor, 7 unknown, 11 verified, 4 unverified). Call it "one synthetic demo run", not accuracy.

## Cut if you run over (in order)
What-if (6 s) → Patient record (6 s) → Review queue (8 s) → Google sign-in (6 s). Keep email OTP.

## Do not film
Patient page **Consent** card at the top (shows "status not available") — scroll past it, Follow-up board (one task only).
## Confirm before recording
I could not see the **Agent trace** tab contents or the top of the **Trust center** in your screenshots. Open both once. If the trace is thin, shorten 1:50–2:10 to 10 s and give the time to Trust center.

## Final checklist
- [ ] Recorded on the live URL
- [ ] Only the synthetic patient; demo accounts only; inbox blurred
- [ ] Disclaimer strip and DEMO DATA badge visible
- [ ] One unknown/unverified case, one major, one moderate, one verified badge visible
- [ ] No accuracy/time-saved claim; no NRB/mentor claim
- [ ] Bangla text checked
- [ ] Uploaded to YouTube, plays logged-out; link in the portal Proof tab
- [ ] Fallback clip saved

## Video link
`[TBD — YouTube URL]`