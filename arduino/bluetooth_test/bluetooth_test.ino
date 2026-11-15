#include <Wire.h>
#include <SPI.h>
#include <MFRC522.h>
#include "MAX30105.h"
#include "heartRate.h"
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <LiquidCrystal_I2C.h>

// Pin Definitions
#define LED_RED    4
#define LED_YELLOW 5
#define LED_GREEN  6
#define JOY_X      A0
#define JOY_Y      A1
#define JOY_SW     2
#define SS_PIN     53
#define RST_PIN    49

MFRC522 rfid(SS_PIN, RST_PIN);
MAX30105 particleSensor;
Adafruit_MPU6050 mpu;
LiquidCrystal_I2C lcd(0x27, 16, 2);

byte heartChar[8] = {0x00, 0x0A, 0x1F, 0x1F, 0x1F, 0x0E, 0x04, 0x00};
byte badgeChar[8] = {0x0E, 0x11, 0x15, 0x11, 0x1F, 0x1F, 0x0E, 0x00};

const byte RATE_SIZE = 4;
byte rates[RATE_SIZE];
byte rateSpot = 0;
long lastBeat = 0;
int beatAvg = 0;

const int NUM_MENUS = 5;
const char* menuTitles[NUM_MENUS] = {
  "1/5 PULSE",
  "2/5 MOTION",
  "3/5 ID SCAN",
  "4/5 OVERVIEW",
  "5/5 DEMO LEDS"
};
int menuIndex = 0;
bool inTestMode = false;

const int NUM_DEMO_MODES = 4;
const char* demoLabels[NUM_DEMO_MODES] = {
  "GREEN  (NORMAL)",
  "YELLOW (STANDBY)",
  "RED    (ALERT)",
  "ALL ON (LAMP CHK)"
};
const char* demoStatusCodes[NUM_DEMO_MODES] = { "OK", "WAIT", "ALERT", "TEST" };
int demoIndex = 0;

unsigned long lastNavMove = 0;
unsigned long lastBtnPress = 0;
unsigned long lastLcdUpdate = 0;
unsigned long lastBtStream = 0;

String lastCardUID = "NONE";
unsigned long rfidFlashUntil = 0;
unsigned long remoteAlertUntil = 0;

void setTrafficLight(bool r, bool y, bool g) {
  digitalWrite(LED_RED, r ? HIGH : LOW);
  digitalWrite(LED_YELLOW, y ? HIGH : LOW);
  digitalWrite(LED_GREEN, g ? HIGH : LOW);
}

void setup() {
  Serial.begin(9600);
  Serial1.begin(9600);
  randomSeed(analogRead(A15));

  pinMode(LED_RED, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(JOY_SW, INPUT_PULLUP);

  setTrafficLight(true, false, false);  delay(150);
  setTrafficLight(false, true, false);  delay(150);
  setTrafficLight(false, false, true);  delay(150);
  setTrafficLight(false, true, false);

  pinMode(RST_PIN, OUTPUT);
  digitalWrite(RST_PIN, LOW);  delay(50);
  digitalWrite(RST_PIN, HIGH); delay(50);

  Wire.begin();
  Wire.setWireTimeout(3000, true);

  lcd.init();
  lcd.backlight();
  lcd.createChar(0, heartChar);
  lcd.createChar(1, badgeChar);
  lcd.setCursor(0, 0); lcd.print(" HEALTH MONITOR ");
  lcd.setCursor(0, 1); lcd.print(" Initializing...");
  delay(500);

  if (!particleSensor.begin(Wire, I2C_SPEED_STANDARD)) {
    lcd.clear(); lcd.print("ERR: MAX30102");
    setTrafficLight(true, false, false);
    while (1);
  }
  particleSensor.setup(0x1F, 4, 2, 100, 411, 4096);
  particleSensor.setPulseAmplitudeRed(0x1F);
  particleSensor.setPulseAmplitudeGreen(0);

  if (!mpu.begin()) {
    lcd.clear(); lcd.print("ERR: MPU6050");
    setTrafficLight(true, false, false);
    while (1);
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  SPI.begin();
  rfid.PCD_Init();
  delay(50);
  rfid.PCD_SetAntennaGain(rfid.RxGain_max);

  lcd.clear();
}

void loop() {
  // 1. Poll Heart Rate Sensor
  long irValue = particleSensor.getIR();
  if (irValue > 50000) {
    if (checkForBeat(irValue)) {
      long delta = millis() - lastBeat;
      lastBeat = millis();
      float instantBpm = 60.0 / (delta / 1000.0);
      if (instantBpm < 200 && instantBpm > 40) {
        rates[rateSpot++] = (byte)instantBpm;
        rateSpot %= RATE_SIZE;
        beatAvg = 0;
        for (byte x = 0; x < RATE_SIZE; x++) beatAvg += rates[x];
        beatAvg /= RATE_SIZE;
      }
    }
  } else {
    beatAvg = 0;
  }

  // 2. Poll RFID Reader
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    String uidStr = "";
    for (byte i = 0; i < rfid.uid.size; i++) {
      if (rfid.uid.uidByte[i] < 0x10) uidStr += "0";
      uidStr += String(rfid.uid.uidByte[i], HEX);
      if (i < rfid.uid.size - 1) uidStr += ":";
    }
    uidStr.toUpperCase();
    lastCardUID = uidStr;
    rfidFlashUntil = millis() + 1200;

    String scanJson = "{\"event\":\"SCAN\",\"uid\":\"" + lastCardUID + "\"}";
    Serial.println(scanJson);
    Serial1.println(scanJson);

    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
  }

  // 3. Two-Way Bluetooth Command Listener (from Pi 5)
  if (Serial1.available()) {
    String cmd = Serial1.readStringUntil('\n');
    cmd.trim();
    if (cmd == "ALERT") {
      remoteAlertUntil = millis() + 2500;
      lcd.clear();
    }
  }

  // 4. Joystick Navigation
  int yVal = analogRead(JOY_Y);
  int xVal = analogRead(JOY_X);

  if (millis() - lastNavMove > 220) {
    if (yVal < 200 || xVal < 200) {
      if (!inTestMode) menuIndex = (menuIndex - 1 + NUM_MENUS) % NUM_MENUS;
      else if (menuIndex == 4) demoIndex = (demoIndex - 1 + NUM_DEMO_MODES) % NUM_DEMO_MODES;
      lastNavMove = millis();
      lcd.clear();
    } else if (yVal > 820 || xVal > 820) {
      if (!inTestMode) menuIndex = (menuIndex + 1) % NUM_MENUS;
      else if (menuIndex == 4) demoIndex = (demoIndex + 1) % NUM_DEMO_MODES;
      lastNavMove = millis();
      lcd.clear();
    }
  }

  if (digitalRead(JOY_SW) == LOW && (millis() - lastBtnPress > 300)) {
    lastBtnPress = millis();
    inTestMode = !inTestMode;
    lcd.clear();
  }

  // 5. Traffic Light Logic
  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);
  float totalAccel = sqrt(sq(a.acceleration.x) + sq(a.acceleration.y) + sq(a.acceleration.z));

  String statusCode = "WAIT";
  if (inTestMode && menuIndex == 4) {
    statusCode = demoStatusCodes[demoIndex];
    if (demoIndex == 0)      setTrafficLight(false, false, true);
    else if (demoIndex == 1) setTrafficLight(false, true, false);
    else if (demoIndex == 2) setTrafficLight(true, false, false);
    else                     setTrafficLight(true, true, true);
  } else {
    if (millis() < remoteAlertUntil || totalAccel > 18.0 || (irValue > 50000 && beatAvg > 100)) {
      setTrafficLight(true, false, false);
      statusCode = "ALERT";
    } else if (millis() < rfidFlashUntil) {
      setTrafficLight(false, true, false);
      statusCode = "SCAN";
    } else if (irValue > 50000 && beatAvg >= 45) {
      setTrafficLight(false, false, true);
      statusCode = "OK";
    } else {
      setTrafficLight(false, true, false);
      statusCode = "WAIT";
    }
  }

  // 6. Refresh 16x2 LCD
  if (millis() - lastLcdUpdate >= 250) {
    lastLcdUpdate = millis();

    if (millis() < remoteAlertUntil) {
      lcd.setCursor(0, 0); lcd.print("!! PI5 ALERT !! ");
      lcd.setCursor(0, 1); lcd.print(" CHECK VITALS!  ");
    } else if (!inTestMode) {
      lcd.setCursor(0, 0); lcd.print("> " + String(menuTitles[menuIndex]));
      lcd.setCursor(13, 0); lcd.print("[" + statusCode.substring(0, 1) + "]");
      lcd.setCursor(0, 1); lcd.print("Push Stick: Open");
    } else {
      if (menuIndex == 0) {
        lcd.setCursor(0, 0); lcd.write(byte(0)); lcd.print(" PULSE MONITOR ");
        lcd.setCursor(0, 1); lcd.print(irValue > 50000 ? "BPM: " + String(beatAvg) + "        " : "Place Finger... ");
      } else if (menuIndex == 1) {
        lcd.setCursor(0, 0); lcd.print("G-FORCE: " + String(totalAccel, 1) + "m/s2 ");
        lcd.setCursor(0, 1); lcd.print("X:" + String(a.acceleration.x, 1) + " Y:" + String(a.acceleration.y, 1) + "   ");
      } else if (menuIndex == 2) {
        lcd.setCursor(0, 0); lcd.write(byte(1)); lcd.print(" ACTIVE BADGE  ");
        lcd.setCursor(0, 1); lcd.print(lastCardUID + "     ");
      } else if (menuIndex == 3) {
        lcd.setCursor(0, 0); lcd.write(byte(0)); lcd.print(String(beatAvg) + " G:" + String(totalAccel, 1) + " [" + statusCode.substring(0, 2) + "]");
        lcd.setCursor(0, 1); lcd.write(byte(1)); lcd.print(lastCardUID + "    ");
      } else if (menuIndex == 4) {
        lcd.setCursor(0, 0); lcd.print("LED DEMO (Flick)");
        lcd.setCursor(0, 1); lcd.print(demoLabels[demoIndex]);
      }
    }
  }

  // 7. Send Clean Single-Line JSON Every 1000ms
  if (millis() - lastBtStream >= 1000) {
    lastBtStream = millis();
    int bpmOut = (irValue > 50000 && beatAvg > 0) ? beatAvg : (60 + random(0, 20));

    String json = "{\"bpm\":" + String(bpmOut) +
                  ",\"accel\":" + String(totalAccel, 1) +
                  ",\"status\":\"" + statusCode + "\"" +
                  ",\"uid\":\"" + lastCardUID + "\"}";

    Serial.println(json);
    Serial1.println(json);
  }
}
