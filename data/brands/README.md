# Brand → generic sheet (owner: Docs/QA)

Fill `brand_mapping.csv` (copy `brand_mapping_template.csv`). Load it with `python data/pipeline/load_brands.py`.
**Do not commit real-looking rows you have not sourced.** Every row must be traceable.

| Column | Required | Meaning |
|---|---|---|
| `brand_name` | yes | the name as printed/used locally, e.g. the box or prescription text |
| `strength` | no | e.g. `500mg` (write it without spaces) |
| `dosage_form` | no | tablet / capsule / syrup … |
| `generic_name` | yes | must already exist in the Drug table (US/openFDA name or a known alias, e.g. `acetaminophen` or `paracetamol`) |
| `source` | **yes** | concise source label, such as a regulator registry or manufacturer product information |
| `source_ref` | **yes** | exact URL or stable record/document reference that supports this row |
| `source_accessed` | **yes** | date that reference was checked, in `YYYY-MM-DD` format |
| `verified` | no | `true` ONLY after a pharmacist/mentor reviewed the row (default `false`) |
| `confidence` | yes | 0–1: your confidence in the row; decide a simple rule with the pharmacist and write it here |

Rules: one row per brand+strength+form; combination products (several active ingredients) are **not** supported
yet — leave them out and list them in a separate sheet for later. The loader rejects rows without traceable
references and does not load any rows if validation fails (unless `--skip-bad` is explicitly supplied).

The current sheets are drafts: no row-level supporting references or access dates have been supplied. They are
not ready to load. Do not replace missing references with guessed URLs or a generic source label.