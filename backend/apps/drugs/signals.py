"""Any admin/ORM change to the drug tables makes cached lookups stale: bump the data version."""
from django.db.models.signals import post_delete, post_save

from . import services
from .models import BrandMapping, Drug, Interaction


def _bump(sender, **kwargs):
    services.invalidate_cache()


def connect():
    for model in (Drug, BrandMapping, Interaction):
        post_save.connect(_bump, sender=model, weak=False, dispatch_uid=f"drugs-cache-save-{model.__name__}")
        post_delete.connect(_bump, sender=model, weak=False, dispatch_uid=f"drugs-cache-del-{model.__name__}")
