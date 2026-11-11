from django.core.management.base import BaseCommand

from apps.drugs.models import BrandMapping, Drug
from apps.drugs.services import clear_brand_index_cache

# DEV ONLY. Unreviewed sample; replace with Docs/QA's curated sheet.
# `verified` stays False until a pharmacist/mentor reviews each row.
SAMPLE = [
    ("Napa", "500 mg", "tablet", "paracetamol"),
    ("Napa Extend", "665 mg", "tablet", "paracetamol"),
    ("Ace", "500 mg", "tablet", "paracetamol"),
    ("Seclo", "20 mg", "capsule", "omeprazole"),
    ("Losectil", "20 mg", "capsule", "omeprazole"),
    ("Maxpro", "20 mg", "tablet", "esomeprazole"),
    ("Sergel", "20 mg", "capsule", "esomeprazole"),
    ("Fexo", "120 mg", "tablet", "fexofenadine"),
    ("Monas", "10 mg", "tablet", "montelukast"),
    ("Ciprocin", "500 mg", "tablet", "ciprofloxacin"),
    ("Azithrocin", "500 mg", "tablet", "azithromycin"),
]


class Command(BaseCommand):
    help = "Load a small unverified dev sample of brand mappings."

    def handle(self, *args, **opts):
        created = 0
        for brand, strength, form, generic in SAMPLE:
            drug, _ = Drug.objects.get_or_create(generic_name=generic)
            _, was_created = BrandMapping.objects.get_or_create(
                brand_name=brand,
                strength=strength,
                defaults={
                    "dosage_form": form,
                    "drug": drug,
                    "source": "dev-seed (unreviewed)",
                    "verified": False,
                    "confidence": 0.90,
                },
            )
            created += int(was_created)
        clear_brand_index_cache()
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} new brand rows."))