# PredictRx IoT (Future Roadmap module)

ESP32 + MAX30102 -> HTTPS POST -> Django `vitals` app -> Celery triage -> doctor dashboard.
Not part of the main demo flow. Code and endpoint are ready for the roadmap slide.

## Backend setup
The module is already wired into the monorepo as `backend/apps/vitals/` (INSTALLED_APPS + `/api/vitals/...` routes).
1. `python manage.py migrate`
2. `python manage.py create_device esp32-001`  -> copy the token
3. Celery worker (optional, inline fallback exists): `celery -A <project> worker -l info`

## Firmware setup
1. Arduino IDE: install ESP32 board package + "SparkFun MAX3010x" library.
2. Edit CONFIG block in `predictrx_vitals.ino` (WiFi, API_URL, DEVICE_TOKEN, PATIENT_ID).
3. Wiring: VIN->3V3, GND->GND, SDA->GPIO21, SCL->GPIO22.
4. No hardware? set `SIMULATE true` (readings are tagged `simulated`).

## Test without ESP32
curl -X POST https://YOUR_HOST/api/vitals/ingest/ \
  -H "Content-Type: application/json" -H "X-Device-Token: TOKEN" \
  -d '{"device_id":"esp32-001","patient_id":"1","spo2":96,"pulse":78,"source":"simulated"}'

## Notes
- Triage thresholds are demo rules, not clinical guidance. State this in the pitch.
- Simulated data must be labeled simulated (Congress rules: no fabricated demos).
- For production: pin TLS cert on the device instead of setInsecure().
