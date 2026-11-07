from celery import shared_task

from .models import VitalReading


def evaluate(spo2: int, pulse: int):
    """Rule-based triage. Replace/extend with the Advisory agent later."""
    reasons, level = [], "normal"
    if spo2 < 90:
        level = "critical"; reasons.append(f"SpO2 {spo2}% < 90")
    elif spo2 < 94:
        level = "warning"; reasons.append(f"SpO2 {spo2}% < 94")
    if pulse < 40 or pulse > 130:
        level = "critical"; reasons.append(f"Pulse {pulse} out of safe range")
    elif pulse < 50 or pulse > 110:
        if level != "critical":
            level = "warning"
        reasons.append(f"Pulse {pulse} abnormal")
    return level, "; ".join(reasons)


@shared_task
def analyze_reading(reading_id: int):
    reading = VitalReading.objects.get(id=reading_id)
    reading.severity, reading.alert_reason = evaluate(reading.spo2, reading.pulse)
    reading.save(update_fields=["severity", "alert_reason"])
    return reading.severity
