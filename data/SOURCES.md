Data Sources & Licenses

Status: draft terms summary. Re-open the linked official pages and confirm before relying on this summary.
Not legal advice. A team member must open each link, confirm the text still matches, and sign the last column.
Do not ingest a source until its row is signed.

Brand-mapping provenance audit (12 Nov 2026): the current brand sheets have no row-level source references or
access dates. Their source labels are not evidence. Do not load these draft rows until the exact supporting
record/document and date checked are recorded per row.







Source



Used for



Official terms page (read)



License / terms (as stated there)



Verified by / date





openFDA drug labels



Label text for RAG (warnings, drug interactions sections)



https://open.fda.gov/license (also: https://open.fda.gov/terms/)



Content/data on openFDA is public domain under CC0 1.0. The service (API) is offered under the openFDA Terms of Service and FDA website policies. FDA may limit or restrict API access.



MD. Shadman Hasan





DDInter 2.0 (drug–drug interactions)



Interaction table for check_interaction + Verifier



https://ddinter2.scbdd.com/terms/



Data under CC BY-NC-SA 4.0. Download/print allowed for "personal, non-commercial, informational or scholarly use."



MD. Shadman Hasan





Brand→generic sample (team-curated)



Local brand-name resolver



n/a (our own work)



Each row needs a source; verified=false until a pharmacist/mentor reviews it





What this means for PredictRx

openFDA





CC0 → reuse (even commercial) without asking; attribution not required, but we credit it anyway.



Its API response carries a disclaimer: do not rely on openFDA to make decisions regarding medical care; assume all results are unvalidated. Keep that caution visible in the product and pitch (already in docs/PRD.md §5).



openFDA also carries device terminology (GMDN) under a separate license with restrictions. We use drug labels only, so keep device datasets out of the pipeline.



Rate limits / API key: check https://open.fda.gov/apis/authentication before the Day 3 ingest and get a free key.

DDInter





Non-commercial + ShareAlike. Fine for a hackathon prototype and research demo with attribution. It does not cover a paid product.



ShareAlike: data we derive from DDInter (our Interaction rows) should be treated as derived material. If the repo or any export publishes it, it must carry the same license. Simplest rule: do not commit DDInter raw files or exported interaction tables to Git (data/raw/ and data/processed/ are git-ignored); commit only scripts and download instructions.



The DDInter team's own disclaimer: the database is incomplete and contains errors, and the absence of an interaction does not necessarily mean no interactions exist. This matches our rule "no record ≠ safe" — quote it in the pitch.



Business-slide wording (suggested): "Prototype uses DDInter (academic license). Commercial deployment requires permission from the DDInter authors or a licensed interaction source." Consider emailing the DDInter team (contact page on their site) early if the monetization path matters to judging.

Attribution text (put in app footer + README + pitch)





openFDA: "Drug label data: U.S. FDA via openFDA (CC0). Not validated for medical decisions."



DDInter: "Interaction data: DDInter 2.0, licensed CC BY-NC-SA 4.0. Tian Y. et al., Nucleic Acids Res. 2025;53(D1):D1356; Xiong G. et al., Nucleic Acids Res. 2022;50(D1):D1200–D1207 (doi:10.1093/nar/gkab880)."
(Confirm the exact citation and preferred credit on the DDInter site before submission.)

Rules





Record the fetch date and version/ref for every download (DDInter 2.0, last update shown on site: 2024-05-14).



Never commit raw datasets. Commit scripts + download instructions.



Every loaded record stores a license_note (field exists on Interaction and KnowledgeDocument).



If a source's terms forbid something we do, stop and raise it in the daily sync.

Open items for the Lead





Open both official pages, confirm the text above, sign the table.



Get the free openFDA API key; put it in .env (never commit).



Download the DDInter CSV files from its download page into data/raw/ (git-ignored); note date and version here.



Decide whether to contact the DDInter team about commercial use.

