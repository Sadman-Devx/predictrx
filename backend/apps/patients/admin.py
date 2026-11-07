from django.contrib import admin

from .models import Consent, FamilyLink, Patient

admin.site.register([Patient, Consent, FamilyLink])
