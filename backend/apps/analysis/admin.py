from django.contrib import admin

from .models import AgentTrace, AnalysisRun, RiskFinding, RiskSummary

admin.site.register([AnalysisRun, AgentTrace, RiskFinding, RiskSummary])
