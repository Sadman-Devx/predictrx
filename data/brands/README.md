# Brand → generic sheet (owner: Docs/QA)

Fill `brand_mapping.csv` (copy `brand_mapping_template.csv`). Load it with `python data/pipeline/load_brands.py`.
**Do not commit real-looking rows you have not sourced.** Every row must be traceable.

| Column | Required | Meaning |
|---|---|---|
| `brand_name` | yes | the name as printed/used locally, e.g. the box or prescription text |
| `strength` | no | e.g. `500mg` (write it without spaces) |
| `dosage_form` | no | tablet / capsule / syrup … |
| `generic_name` | yes | must already exist in the Drug table (US/openFDA name or a known alias, e.g. `acetaminophen` or `paracetamol`) |
| `source` | **yes** | where the mapping came from (e.g. "printed pack, photo ref 12", "company website <url>, accessed <date>") |
| `verified` | no | `true` ONLY after a pharmacist/mentor reviewed the row (default `false`) |
| `confidence` | yes | 0–1: your confidence in the row; decide a simple rule with the pharmacist and write it here |

Rules: one row per brand+strength+form; combination products (several active ingredients) are **not** supported
yet — leave them out and list them in a separate sheet for later. Rows that fail validation are reported, never skipped silently.