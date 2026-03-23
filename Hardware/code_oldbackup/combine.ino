#include "Audio.h"
#include "SD.h"
#include "FS.h"
#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h> 
#include <ESP32Servo.h>
// === COMPATIBILITY ===
bool end_mp3 = false; 

// === PIN DEFINITIONS ===
#define SPI_SCK      19
#define SPI_MISO     16
#define SPI_MOSI     4
#define RFID_SS_PIN  14
#define RFID_RST_PIN 17
#define SD_CS_PIN    18
#define I2S_DOUT     25
#define I2S_LRC      26
#define I2S_BCLK     27 
#define SERVO_PIN    5
#define BUTTON_PIN   13 
#define I2C_SDA      21
#define I2C_SCL      22
#define LED_PIN      2 

// ======================= WIFI & MQTT CONFIG =======================
const char *ssid = "HH-Freshmen";
const char *password = "sao3159hh";
const char *mqtt_server = "dd28cecf47f84578948ef8d895d0d2cb.s1.eu.hivemq.cloud";
const char *mqtt_username = "hyuvuhjb";
const char *mqtt_password = "Qweasd12";
const int mqtt_port = 8883;
const char *mqtt_publish_topic = "Hospital/Room/1/01/Toilet/RFID";

// === TIME SETTINGS ===
const unsigned long TIME_LIMIT_INITIAL = 10000; 
const unsigned long TIME_LIMIT_EXTENDED = 25000; 
const unsigned long TIME_WAIT_FOR_ACCIDENT = 15000; 
const unsigned long DOOR_OPEN_DURATION = 10000;

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
    audioTaskCode,   // Function to call
    "AudioTask",     // Name of task
    10000,           // Stack size (bytes)
    NULL,            // Parameter
    1,               // Priority (High=1)
    &AudioTask,      // Task handle
    0                // Run on Core 0
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
  espClient.setInsecure();
  client.setServer(mqtt_server, mqtt_port);

  currentWarningThreshold = TIME_LIMIT_INITIAL;
  lcd.clear(); lcd.print("System Ready");
}

// ======================= MAIN LOOP (CORE 1) =======================
void loop() {
  // NO audio.loop() HERE! It's running on Core 0 now.

  // 1. MQTT
  if (!client.connected()) {
    if (millis() - mqttReconnectTimer > 5000) {
      // Non-blocking reconnect attempt
      String clientId = "ESP32-" + String(random(0xffff), HEX);
      if (client.connect(clientId.c_str(), mqtt_username, mqtt_password)) {
        Serial.println("MQTT Connected");
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
      if (elapsedTime > currentWarningThreshold) changeState(STATE_WARNING);
      break;
    case STATE_WARNING:
      if (elapsedTime > TIME_WAIT_FOR_ACCIDENT) changeState(STATE_ACCIDENT);
      break;
    case STATE_ACCIDENT: break;
  }

  // 4. Door Logic
  if (isDoorOpen && !keepDoorOpen) {
    if (millis() - doorOpenTimer > DOOR_OPEN_DURATION) closeDoor();
  }
}

// ======================= HELPER FUNCTIONS =======================
// ... (The rest of your functions: changeState, checkRFID, etc. remain the same)
// ... (Please copy them from the previous code)

void changeState(State newState) {
    // Copy the implementation from previous response
    // Ensure audio.connecttoFS() is called here
    // Since audio object is global, Core 0 will pick up the new file automatically.
    
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
            audio.connecttoFS(SD, "/reminder.mp3");
            break;

        case STATE_ACCIDENT:
            Serial.println("State -> ACCIDENT");
            lcd.print("EMERGENCY!");
            lcd.setCursor(0,1); lcd.print("Help Needed");
            audio.connecttoFS(SD, "/info.mp3");
            
            openDoor(); 
            keepDoorOpen = true; 
            publishMQTT(currentUserUID, "ACCIDENT");
            break;
    }
}

// ... (Copy checkRFID, checkButton, openDoor, closeDoor, publishMQTT, setup_wifi, audio_info from previous code) ...

// --- Copy helper functions below to complete the code ---
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
  if (currentState == STATE_WARNING) {
    if (digitalRead(BUTTON_PIN) == LOW) {
      Serial.println("Button: Safety Confirmed");
      currentWarningThreshold = TIME_LIMIT_EXTENDED; 
      changeState(STATE_USER_INSIDE); 
      buttonCooldown = millis(); 
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

void publishMQTT(String uid, String status) {
  StaticJsonDocument<200> doc;
  doc["uid"] = uid;
  doc["status"] = status;
  if (status == "ACCIDENT") doc["accident"] = true;
  char jsonBuffer[200];
  serializeJson(doc, jsonBuffer);
  client.publish(mqtt_publish_topic, jsonBuffer);
}

void setup_wifi() {
  delay(10);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("WiFi OK");
}

void audio_info(const char *info) {
  Serial.print("Audio: "); Serial.println(info);
}


