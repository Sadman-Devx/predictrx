/*
 * PredictRx - ESP32 Vitals Node (SpO2 + Pulse)
 * Sensor : MAX30102 / MAX30105 (I2C: SDA=21, SCL=22)
 * Libs   : "SparkFun MAX3010x Pulse and Proximity Sensor Library"
 * Board  : ESP32 Dev Module
 *
 * Status : FUTURE ROADMAP - not part of the main demo flow.
 * Set SIMULATE true to test the endpoint without hardware.
 */
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Wire.h>
#include "MAX30105.h"
#include "spo2_algorithm.h"

// ---------- CONFIG ----------
const char* WIFI_SSID    = "YOUR_WIFI_SSID";
const char* WIFI_PASS    = "YOUR_WIFI_PASSWORD";
const char* API_URL      = "https://YOUR-TUNNEL.trycloudflare.com/api/vitals/ingest/";
const char* DEVICE_ID    = "esp32-001";
const char* DEVICE_TOKEN = "PASTE_TOKEN_FROM_create_device";
const char* PATIENT_ID   = "1";
#define SIMULATE            false
#define POST_INTERVAL_MS    5000
#define FINGER_IR_THRESHOLD 50000
// ----------------------------

MAX30105 sensor;
const int32_t BUFFER_LEN = 100;
uint32_t irBuffer[BUFFER_LEN];
uint32_t redBuffer[BUFFER_LEN];
int32_t spo2 = 0, heartRate = 0;
int8_t validSpo2 = 0, validHr = 0;
unsigned long lastPost = 0;

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi connecting");
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries++ < 40) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? " connected" : " FAILED");
}

bool postReading(int spo2Val, int hrVal) {
  if (WiFi.status() != WL_CONNECTED) connectWifi();
  if (WiFi.status() != WL_CONNECTED) return false;

  WiFiClientSecure client;
  client.setInsecure();  // tunnel/dev only. Pin a CA cert for production.
  HTTPClient http;
  http.begin(client, API_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Token", DEVICE_TOKEN);

  String body = String("{\"device_id\":\"") + DEVICE_ID +
                "\",\"patient_id\":\"" + PATIENT_ID +
                "\",\"spo2\":" + spo2Val +
                ",\"pulse\":" + hrVal +
                ",\"source\":\"" + (SIMULATE ? "simulated" : "esp32") + "\"}";

  int code = http.POST(body);
  Serial.printf("POST %s -> %d\n", body.c_str(), code);
  http.end();
  return code >= 200 && code < 300;
}

void setup() {
  Serial.begin(115200);
  connectWifi();
  if (SIMULATE) return;

  Wire.begin(21, 22);
  if (!sensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("MAX30102 not found. Check wiring.");
    while (true) delay(1000);
  }
  // ledBrightness, sampleAverage, ledMode, sampleRate, pulseWidth, adcRange
  sensor.setup(60, 4, 2, 100, 411, 4096);

  for (int i = 0; i < BUFFER_LEN; i++) {
    while (!sensor.available()) sensor.check();
    redBuffer[i] = sensor.getRed();
    irBuffer[i]  = sensor.getIR();
    sensor.nextSample();
  }
  maxim_heart_rate_and_oxygen_saturation(irBuffer, BUFFER_LEN, redBuffer,
                                         &spo2, &validSpo2, &heartRate, &validHr);
}

void loop() {
  if (SIMULATE) {
    int s = random(94, 100);
    int h = random(60, 100);
    postReading(s, h);
    delay(POST_INTERVAL_MS);
    return;
  }

  // slide window: drop oldest 25, add newest 25
  for (int i = 25; i < BUFFER_LEN; i++) {
    redBuffer[i - 25] = redBuffer[i];
    irBuffer[i - 25]  = irBuffer[i];
  }
  for (int i = BUFFER_LEN - 25; i < BUFFER_LEN; i++) {
    while (!sensor.available()) sensor.check();
    redBuffer[i] = sensor.getRed();
    irBuffer[i]  = sensor.getIR();
    sensor.nextSample();
  }

  if (irBuffer[BUFFER_LEN - 1] < FINGER_IR_THRESHOLD) {
    Serial.println("No finger detected");
    return;
  }

  maxim_heart_rate_and_oxygen_saturation(irBuffer, BUFFER_LEN, redBuffer,
                                         &spo2, &validSpo2, &heartRate, &validHr);

  if (validSpo2 && validHr && millis() - lastPost >= POST_INTERVAL_MS) {
    if (postReading(spo2, heartRate)) lastPost = millis();
  }
}
