// ESP32 Dev Module - WiFi UDP pump controller (no web server)
// 1 ESP32 = 1 pump = 1 site (camera) in the dashboard
//
// Commands from the Pi (UDP port 4210):
//   "1 <ms>" -> pump ON for <ms>       reply "OK <ms>"   (or "BUSY <ms left>" if already ON)
//               <ms> is set on the dashboard Settings page (limited to MIN/MAX below)
//   "1"      -> pump ON for DEFAULT_PUMP_TIME
//   "0" -> pump OFF now (emergency)   reply "STOPPED"
//   "?" -> status                      reply "STATUS ON <ms left>" / "STATUS OFF"
// While the pump is ON, any new "1" is IGNORED (timer is not restarted)
//
// Relay module is ACTIVE LOW: LOW = ON, HIGH = OFF
// Wiring: Relay VCC -> 3V3, GND -> GND, IN -> GPIO 26, pump on COM + NO

#include <WiFi.h>
#include <WiFiUdp.h>

// ---------- Change these ----------
const char* WIFI_SSID     = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
// ----------------------------------

const int UDP_PORT = 4210;
const int RELAY_PIN = 26;
// Spray time now comes from the dashboard (Settings page).
// These are only the fallback and the safety limits.
const unsigned long DEFAULT_PUMP_TIME = 2000;    // used if the Pi sends plain "1"
const unsigned long MIN_PUMP_TIME = 500;         // 0.5 s
const unsigned long MAX_PUMP_TIME = 600000;      // 10 min safety limit

WiFiUDP udp;

bool pumpOn = false;
unsigned long startTime = 0;
unsigned long pumpDuration = DEFAULT_PUMP_TIME;   // duration of the current run
unsigned long lastWifiCheck = 0;

void pumpStart(unsigned long duration) {
  pumpDuration = duration;
  digitalWrite(RELAY_PIN, LOW);    // relay ON -> pump ON
  pumpOn = true;
  startTime = millis();
  Serial.printf("Pump ON for %lu ms\n", duration);
}

void pumpStop() {
  digitalWrite(RELAY_PIN, HIGH);   // relay OFF -> pump OFF
  pumpOn = false;
  Serial.println("Pump OFF");
}

unsigned long remainingMs() {
  unsigned long elapsed = millis() - startTime;
  return elapsed >= pumpDuration ? 0 : pumpDuration - elapsed;
}

void connectWiFi() {
  Serial.print("Connecting to WiFi");
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);            // receive packets without delay
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi connected, IP: ");
    Serial.println(WiFi.localIP());   // put this IP in the dashboard (Devices page)
  } else {
    Serial.println("WiFi failed, will keep retrying");
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, HIGH);   // OFF at start

  connectWiFi();
  udp.begin(UDP_PORT);
  Serial.printf("Listening on UDP port %d\n", UDP_PORT);
}

void loop() {
  // 1) Check for a UDP command
  int size = udp.parsePacket();
  if (size > 0) {
    char buf[32];
    int len = udp.read(buf, sizeof(buf) - 1);
    udp.flush();                   // discard anything longer
    if (len < 0) len = 0;
    buf[len] = '\0';
    char c = buf[0];

    udp.beginPacket(udp.remoteIP(), udp.remotePort());
    if (c == '1') {
      if (pumpOn) {
        udp.printf("BUSY %lu", remainingMs());   // already running -> ignore
        Serial.println("Trigger ignored: pump already ON");
      } else {
        unsigned long duration = DEFAULT_PUMP_TIME;
        long requested = atol(buf + 1);              // "1 5000" -> 5000
        if (requested > 0) {
          duration = constrain((unsigned long)requested, MIN_PUMP_TIME, MAX_PUMP_TIME);
        }
        pumpStart(duration);
        udp.printf("OK %lu", duration);
      }
    } else if (c == '0') {
      pumpStop();
      udp.print("STOPPED");
    } else if (c == '?') {
      if (pumpOn) {
        udp.printf("STATUS ON %lu", remainingMs());
      } else {
        udp.print("STATUS OFF");
      }
    } else {
      udp.print("UNKNOWN");
    }
    udp.endPacket();
  }

  // 2) Auto OFF after the requested time (works even if WiFi drops)
  if (pumpOn && millis() - startTime >= pumpDuration) {
    pumpStop();
  }

  // 3) Reconnect WiFi if it drops (check every 10 s)
  if (millis() - lastWifiCheck > 10000) {
    lastWifiCheck = millis();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("WiFi lost, reconnecting...");
      WiFi.reconnect();
    }
  }
}
