from django.contrib import admin

from .models import EvalCase, EvalRun

admin.site.register([EvalCase, EvalRun])
