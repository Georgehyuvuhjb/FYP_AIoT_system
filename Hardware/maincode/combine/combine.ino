#include "Audio.h"
#include "SD.h"
#include "FS.h"

#include "secrets.h" 

#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h> 
#include <ESP32Servo.h>

#include <time.h>

// === COMPATIBILITY ===
bool end_mp3 = false; 

// === PIN DEFINITIONS ===
#define SPI_SCK 19
#define SPI_MISO 16
#define SPI_MOSI 4
#define RFID_SS_PIN 14
#define RFID_RST_PIN 17
#define SD_CS_PIN 18
#define I2S_DOUT 25
#define I2S_LRC 26
#define I2S_BCLK 27 
#define SERVO_PIN 5
#define BUTTON_PIN 13 
#define I2C_SDA 21
#define I2C_SCL 22
#define LED_PIN 2 

// ======================= WIFI & MQTT CONFIG =======================
const char *ssid = SECRET_WIFI_SSID;
const char *password = SECRET_WIFI_PASS;
const char *mqtt_server = SECRET_MQTT_SERVER;
const char *mqtt_username = SECRET_MQTT_USER;
const char *mqtt_password = SECRET_MQTT_PASS;
const int mqtt_port = 8883;

const char *mqtt_publish_topic = "Hospital/Room/1/01/Toilet/RFID";
const char *mqtt_subscribe_topic = "Hospital/Room/1/01/Toilet/Threshold";

const char* ntpServer = "pool.ntp.org";
const long  gmtOffset_sec = 8 * 3600; 
const int   daylightOffset_sec = 0;   

// === TIME SETTINGS ===
const unsigned long TIME_LIMIT_INITIAL = 1200000; // 20 minutes in ms
const unsigned long TIME_LIMIT_EXTENDED = 1200000; // 20 minutes in ms
const unsigned long TIME_WAIT_FOR_ACCIDENT = 180000; 
const unsigned long DOOR_OPEN_DURATION = 15000;

// === OBJECTS ===
MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);
LiquidCrystal_I2C lcd(0x27, 16, 2);
WiFiClientSecure espClient;
PubSubClient client(espClient);
Servo doorServo;
Audio audio;

// === STATE ===
enum State { STATE_IDLE, STATE_USER_INSIDE, STATE_WARNING, STATE_ACCIDENT };
State currentState = STATE_IDLE;
unsigned long stateEntryTime = 0;
unsigned long currentWarningThreshold;
unsigned long doorOpenTimer = 0;
bool isDoorOpen = false;
bool keepDoorOpen = false; 
String currentUserUID = ""; 

unsigned long rfidCooldown = 0;
unsigned long buttonCooldown = 0;
unsigned long mqttReconnectTimer = 0;

// === MULTITASKING HANDLES ===
TaskHandle_t AudioTask;

// --- Function Prototypes ---
void changeState(State newState, bool playAudio = true);
void checkRFID();
void checkButton();
void openDoor();
void closeDoor();
void publishMQTT(String uid, String status);
String getISO8601TimeStr();
void setup_wifi();
void mqttCallback(char* topic, byte* payload, unsigned int length);
void audio_info(const char *info);

// ======================= AUDIO TASK (CORE 0) =======================
// This function runs on a separate core independently!
void audioTaskCode(void * parameter) {
  while(true) {
    audio.loop(); 
    // Small delay to prevent Watchdog Trigger, but small enough for audio
    delay(1); 
  }
}

// ======================= SETUP =======================
void setup() {
  Serial.begin(115200);

  // GPIO
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // SPI & SD
  SPI.begin(SPI_SCK, SPI_MISO, SPI_MOSI);
  if (!SD.begin(SD_CS_PIN)) Serial.println("SD Fail");

  // Audio Init
  audio.setPinout(I2S_BCLK, I2S_LRC, I2S_DOUT);
  audio.setVolume(15);

  // --- CREATE AUDIO TASK ON CORE 0 ---
  xTaskCreatePinnedToCore(
    audioTaskCode, // Function to call
    "AudioTask",   // Name of task
    10000,         // Stack size (bytes)
    NULL,          // Parameter
    1,             // Priority (High=1)
    &AudioTask,    // Task handle
    0              // Run on Core 0
  );
  Serial.println("Audio Task Started on Core 0");

  // RFID & Servo
  rfid.PCD_Init();
  doorServo.attach(SERVO_PIN);
  closeDoor(); 

  // LCD
  Wire.begin(I2C_SDA, I2C_SCL, 100000);
  lcd.begin();

  // Network
  setup_wifi();
  
  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  Serial.println("Time configured from NTP");

  espClient.setInsecure();
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(mqttCallback);

  currentWarningThreshold = TIME_LIMIT_INITIAL;
  lcd.clear(); lcd.print("System Ready");
}

// ======================= MAIN LOOP (CORE 1) =======================
void loop() {

  // 1. MQTT
  if (!client.connected()) {
    if (millis() - mqttReconnectTimer > 5000) {
      // Non-blocking reconnect attempt
      String clientId = "ESP32-" + String(random(0xffff), HEX);
      if (client.connect(clientId.c_str(), mqtt_username, mqtt_password)) {
        Serial.println("MQTT Connected");
        client.subscribe(mqtt_subscribe_topic);
      }
      mqttReconnectTimer = millis();
    }
  }
  client.loop();

  // 2. Inputs
  checkRFID();
  checkButton();

  // 3. State Logic
  unsigned long elapsedTime = millis() - stateEntryTime;

  switch (currentState) {
    case STATE_IDLE: break;
    case STATE_USER_INSIDE:
      if (elapsedTime > currentWarningThreshold) {
        changeState(STATE_WARNING);
      } else {
        unsigned long remaining = (currentWarningThreshold - elapsedTime) / 1000;
        static unsigned long lastRemaining_inside = 999999;
        if (remaining != lastRemaining_inside) {
          lcd.setCursor(0, 1);
          lcd.print("Time: ");
          lcd.print(remaining / 60);
          lcd.print("m ");
          lcd.print(remaining % 60);
          lcd.print("s      ");
          lastRemaining_inside = remaining;
        }
      }
      break;
    case STATE_WARNING:
      if (elapsedTime > TIME_WAIT_FOR_ACCIDENT) {
        changeState(STATE_ACCIDENT);
      } else {
        unsigned long remaining = (TIME_WAIT_FOR_ACCIDENT - elapsedTime) / 1000;
        static unsigned long lastRemaining_warn = 999999;
        if (remaining != lastRemaining_warn) {
          lcd.setCursor(0, 1);
          lcd.print("Press Btn: ");
          lcd.print(remaining);
          lcd.print("s  ");
          lastRemaining_warn = remaining;
        }
      }
      break;
    case STATE_ACCIDENT: break;
  }

  // 4. Door Logic
  if (isDoorOpen && !keepDoorOpen) {
    if (millis() - doorOpenTimer > DOOR_OPEN_DURATION) closeDoor();
  }
}

// ======================= HELPER FUNCTIONS =======================

void changeState(State newState, bool playAudio) {
  currentState = newState;
  stateEntryTime = millis();
  lcd.clear();

  switch (newState) {
    case STATE_IDLE:
      Serial.println("State -> IDLE");
      lcd.print("Scan Card...");
      audio.stopSong();
      keepDoorOpen = false;
      digitalWrite(LED_PIN, LOW);
      currentWarningThreshold = TIME_LIMIT_INITIAL;
      currentUserUID = "";
      break;

    case STATE_USER_INSIDE:
      Serial.println("State -> USER INSIDE");
      lcd.print("Occupied");
      audio.stopSong();
      digitalWrite(LED_PIN, HIGH);
      break;

    case STATE_WARNING:
      Serial.println("State -> WARNING");
      lcd.print("WARNING!");
      lcd.setCursor(0,1); lcd.print("Press Button");
      if (playAudio) {
        audio.connecttoFS(SD, "/reminder.mp3");
      }
      break;

    case STATE_ACCIDENT:
      Serial.println("State -> ACCIDENT");
      lcd.print("EMERGENCY!");
      lcd.setCursor(0,1); lcd.print("Help Needed");
      if (playAudio) {
        audio.connecttoFS(SD, "/info.mp3");
      }
      
      openDoor(); 
      keepDoorOpen = true; 
      publishMQTT(currentUserUID, "ACCIDENT");
      break;
  }
}

void checkRFID() {
  if (millis() - rfidCooldown < 1000) return;
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial()) return;

  String uidRaw = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    uidRaw += (rfid.uid.uidByte[i] < 0x10 ? "0" : "");
    uidRaw += String(rfid.uid.uidByte[i], HEX);
  }
  uidRaw.toUpperCase();
  Serial.println("Card: " + uidRaw);

  if (currentState == STATE_IDLE) {
    currentUserUID = uidRaw;
    currentWarningThreshold = TIME_LIMIT_INITIAL;
    openDoor();
    changeState(STATE_USER_INSIDE);
    publishMQTT(uidRaw, "IN");
  } else {
    openDoor();
    publishMQTT(uidRaw, "OUT");
    changeState(STATE_IDLE);
  }
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  rfidCooldown = millis();
}

void checkButton() {
  if (millis() - buttonCooldown < 500) return;

  if (digitalRead(BUTTON_PIN) == LOW) {
    if (currentState == STATE_WARNING || currentState == STATE_USER_INSIDE) {
      
      // -- Long press detection for manual emergency --
      unsigned long pressStartTime = millis();
      bool isLongPress = false;
      while (digitalRead(BUTTON_PIN) == LOW) {
        if (millis() - pressStartTime > 3000) {
          isLongPress = true;
          break; // Exit loop if pressed for > 3 seconds
        }
        delay(10); // small delay to prevent watchdog trigger
      }

      if (isLongPress) {
        Serial.println("Button: LONG PRESS -> Manual Emergency!");
        changeState(STATE_ACCIDENT, false); // false = do not play audio
        buttonCooldown = millis();
        // Wait for release so it doesn't immediately reset
        while(digitalRead(BUTTON_PIN) == LOW) delay(10); 
        return; 
      }
      
      // -- Short press logic (+5 mins) --
      Serial.println("Button: Added 5 mins (Short Press)");
      
      if (currentState == STATE_WARNING) {
        changeState(STATE_USER_INSIDE);
        currentWarningThreshold = 300000; 
      } else {
        currentWarningThreshold += 300000; 
      }

      lcd.setCursor(0, 0);
      lcd.print("+5 Minutes!     ");
      delay(1500); 
      
      if (currentState == STATE_USER_INSIDE) {
        lcd.setCursor(0, 0);
        lcd.print("Occupied        ");
      }
      
      buttonCooldown = millis(); 
      
    } else if (currentState == STATE_ACCIDENT) {
      Serial.println("Button: Reset from ACCIDENT");
      publishMQTT(currentUserUID, "OUT");
      changeState(STATE_IDLE);
      buttonCooldown = millis(); 
      while(digitalRead(BUTTON_PIN) == LOW) delay(10); // Wait for release
    }
  }
}

void openDoor() {
  if (!isDoorOpen) {
    doorServo.write(90);
    isDoorOpen = true;
    doorOpenTimer = millis();
  } else {
    doorOpenTimer = millis();
  }
}

void closeDoor() {
  if (isDoorOpen) {
    doorServo.write(0);
    isDoorOpen = false;
  }
}

String getISO8601TimeStr() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    Serial.println("Failed to obtain time");
    return "1970-01-01T00:00:00+08:00"; 
  }
  char timeStringBuff[30];
  strftime(timeStringBuff, sizeof(timeStringBuff), "%Y-%m-%dT%H:%M:%S+08:00", &timeinfo);
  return String(timeStringBuff);
}

void publishMQTT(String uid, String status) {
  StaticJsonDocument<200> doc;
  doc["uid"] = uid;
  doc["status"] = status;
  

  doc["timestamp"] = getISO8601TimeStr();

  if (status == "ACCIDENT") doc["accident"] = true;
  char jsonBuffer[200];
  serializeJson(doc, jsonBuffer);
  client.publish(mqtt_publish_topic, jsonBuffer);
  
  Serial.print("MQTT Sent: ");
  Serial.println(jsonBuffer);
}

void setup_wifi() {
  delay(10);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("WiFi OK");
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message;
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  Serial.println("MQTT Received on " + String(topic) + ": " + message);

  if (String(topic) == mqtt_subscribe_topic) {
    StaticJsonDocument<200> doc;
    DeserializationError error = deserializeJson(doc, message);
    if (!error) {
      if (doc.containsKey("threshold")) {
        int newThreshold = doc["threshold"];
        currentWarningThreshold = newThreshold * 1000; // convert seconds to ms
        Serial.print("Updated WARNING Threshold to: ");
        Serial.print(currentWarningThreshold);
        Serial.println(" ms");
      }
    } else {
      Serial.println("Failed to parse JSON.");
    }
  }
}

void audio_info(const char *info) {
  Serial.print("Audio: "); Serial.println(info);
}
