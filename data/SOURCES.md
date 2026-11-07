# Data Sources & Licenses

Fill this in on **Day 2** (roadmap). Do not ingest a source until its row is complete.
Every loaded record stores a `license_note`; attribution text goes in the app footer / README.

| Source | What we use it for | Access | License / terms (VERIFY on the official site) | Attribution text | Verified by / date |
|---|---|---|---|---|---|
| openFDA drug labels | Label text for RAG (warnings, interactions) | Official API; free key recommended | TODO — read openFDA terms. Its own disclaimer says not to rely on it for medical-care decisions. | TODO | |
| DDInter (drug–drug interactions) | Interaction table for `check_interaction` + Verifier | Downloadable files from the DDInter site | TODO — reported as non-commercial (CC BY-NC-SA 4.0). Confirm on the DDInter site. Prototype use only. | TODO | |
| Brand→generic sample (team-curated) | Local brand-name resolver | Built by the team | Own work; each row needs a `source`; `verified=false` until a pharmacist/mentor reviews it | n/a | |

## Rules
- Record the date each source was fetched and the version/ref.
- Never commit raw datasets (`data/raw/` is git-ignored); commit the scripts and download instructions.
- If a source's terms forbid something we do, stop and raise it in the daily sync.
