import pytest

from apps.analysis.models import RiskFinding
from core.exceptions import OutOfEvidence


def test_finding_with_severity_but_no_evidence_cannot_be_saved():
    f = RiskFinding(severity="major", evidence=[])
    with pytest.raises(OutOfEvidence):
        f.save()  # raises before touching the database
