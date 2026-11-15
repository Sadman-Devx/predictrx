"""Data step before the integrity constraints of 0003.

Kept in its own migration on purpose: on PostgreSQL, changing rows of a table with foreign keys and then altering
that same table inside one transaction fails ("pending trigger events"). The schema changes are in 0003.

What it does:
  * refuses to continue (with a readable list) if an existing case has the same drug twice, a label outside
    none/minor/moderate/major, or a duplicate pair. Fix those in the admin first, then migrate again;
  * puts every pair into canonical order (drug_a.id < drug_b.id).
An empty EvalCase table (the normal case before Day 9) passes through untouched.
"""
from django.db import migrations

VALID = ["none", "minor", "moderate", "major"]


def prepare_cases(apps, schema_editor):
    EvalCase = apps.get_model("evaluation", "EvalCase")
    problems, seen = [], {}
    for case in EvalCase.objects.order_by("id"):
        low, high = sorted((case.drug_a_id, case.drug_b_id))
        if low == high:
            problems.append(f"case {case.id}: the same drug twice")
        if case.expected_severity not in VALID:
            problems.append(f"case {case.id}: expected_severity {case.expected_severity!r} is not one of {VALID}")
        if (low, high) in seen:
            problems.append(f"case {case.id}: duplicate pair (same pair as case {seen[(low, high)]})")
        seen.setdefault((low, high), case.id)
    if problems:
        raise RuntimeError(
            "EvalCase rows must be fixed before this migration can run (use the Django admin):\n  - "
            + "\n  - ".join(problems[:30])
        )

    for case in EvalCase.objects.all():
        if case.drug_a_id > case.drug_b_id:
            case.drug_a_id, case.drug_b_id = case.drug_b_id, case.drug_a_id
            case.save(update_fields=["drug_a", "drug_b"])


class Migration(migrations.Migration):

    dependencies = [
        ("evaluation", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(prepare_cases, migrations.RunPython.noop),
    ]