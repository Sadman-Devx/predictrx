from django.contrib import admin

from .models import ClinicalNote, LabResult, Medication, PrescriptionScan

admin.site.register([PrescriptionScan, Medication, LabResult, ClinicalNote])
