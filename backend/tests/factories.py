"""factory_boy helpers. All data is synthetic: drug names are `testdrugN`, never real clinical claims."""
import factory

from apps.drugs.models import Drug, Interaction


class DrugFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Drug

    generic_name = factory.Sequence(lambda n: f"testdrug{n}")
    aliases = factory.LazyFunction(list)


def make_interaction(drug_x, drug_y, *, severity="moderate", source="testsource", **extra):
    """Create an Interaction in canonical order whichever way the drugs are passed."""
    lo, hi = Interaction.canonical(drug_x.id, drug_y.id)
    fields = {"source_ref": "synthetic", "license_note": "synthetic test data", **extra}
    return Interaction.objects.create(drug_a_id=lo, drug_b_id=hi, severity=severity, source=source, **fields)