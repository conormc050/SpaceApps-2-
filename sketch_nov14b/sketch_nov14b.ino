#include <Wire.h>
#include <SPI.h>
#include <MFRC522.h>
#include "MAX30105.h"
#include "heartRate.h"
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <LiquidCrystal_I2C.h>

// Traffic Light Pins
#define LED_RED    3
#define LED_YELLOW 4
#define LED_GREEN  5

// Joystick Pins
#define JOY_X   A0
#define JOY_Y   A1
#define JOY_SW  2

// RFID SPI Pins
#define SS_PIN  53
#define RST_PIN 49
MFRC522 rfid(SS_PIN, RST_PIN);

MAX30105 particleSensor;
Adafruit_MPU6050 mpu;
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Heart Rate Variables
const byte RATE_SIZE = 4;
byte rates[RATE_SIZE];
byte rateSpot = 0;
long lastBeat = 0;
float beatsPerMinute = 0;
int beatAvg = 0;

// Menu & Navigation State
const int NUM_MENUS = 4;
const char* menuItems[NUM_MENUS] = {
  "1.Heart Rate",
  "2.Motion/MPU",
  "3.RFID Badge",
  "4.All-Stream"
};
int menuIndex = 0;
bool inTestMode = false;
unsigned long lastNavMove = 0;
unsigned long lastBtnPress = 0;
unsigned long lastUpdate = 0;

String lastCardUID = "None";
unsigned long rfidFlashUntil = 0;

void setTrafficLight(bool r, bool y, bool g) {
  digitalWrite(LED_RED, r ? HIGH : LOW);
  digitalWrite(LED_YELLOW, y ? HIGH : LOW);
  digitalWrite(LED_GREEN, g ? HIGH : LOW);
}

void setup() {
  Serial.begin(9600);
  Serial1.begin(9600);

  // Configure Traffic Light & run quick startup lamp check
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  setTrafficLight(true, false, false);  delay(200);
  setTrafficLight(false, true, false);  delay(200);
  setTrafficLight(false, false, true);  delay(200);
  setTrafficLight(false, true, false);  // Hold Yellow during boot

  pinMode(JOY_SW, INPUT_PULLUP);

  // Clean hardware reset for MFRC522
  pinMode(RST_PIN, OUTPUT);
  digitalWrite(RST_PIN, LOW);
  delay(50);
  digitalWrite(RST_PIN, HIGH);
  delay(50);

  Wire.begin();
  Wire.setWireTimeout(3000, true);

  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Booting System..");
  delay(500);

  if (!particleSensor.begin(Wire, I2C_SPEED_STANDARD)) {
    lcd.clear();
    lcd.print("ERR: MAX30102");
    setTrafficLight(true, false, false);
    while (1);
  }
  particleSensor.setup(0x1F, 4, 2, 100, 411, 4096);
  particleSensor.setPulseAmplitudeRed(0x1F);
  particleSensor.setPulseAmplitudeGreen(0);

  if (!mpu.begin()) {
    lcd.clear();
    lcd.print("ERR: MPU6050");
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
  Serial.println("ALL 7 MODULES READY (HR + MPU + BT + LCD + RFID + JOY + LIGHTS)");
  Serial1.println("ALL 7 MODULES READY");
}

void loop() {
  // 1. Poll Heart Rate Sensor continuously
  long irValue = particleSensor.getIR();
  if (irValue > 50000) {
    if (checkForBeat(irValue) == true) {
      long delta = millis() - lastBeat;
      lastBeat = millis();
      float instantBpm = 60.0 / (delta / 1000.0);
      if (instantBpm < 200 && instantBpm > 40) {
        beatsPerMinute = instantBpm;
        rates[rateSpot++] = (byte)beatsPerMinute;
        rateSpot %= RATE_SIZE;
        beatAvg = 0;
        for (byte x = 0; x < RATE_SIZE; x++) beatAvg += rates[x];
        beatAvg /= RATE_SIZE;
      }
    }
  } else {
    beatsPerMinute = 0;
    beatAvg = 0;
  }

  // 2. Poll RFID Reader continuously
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    String uidStr = "";
    for (byte i = 0; i < rfid.uid.size; i++) {
      if (rfid.uid.uidByte[i] < 0x10) uidStr += "0";
      uidStr += String(rfid.uid.uidByte[i], HEX);
      if (i < rfid.uid.size - 1) uidStr += ":";
    }
    uidStr.toUpperCase();
    lastCardUID = uidStr;
    rfidFlashUntil = millis() + 1000; // Flash Yellow LED for 1s on badge scan

    Serial.println(">>> RFID SCANNED: " + lastCardUID);
    Serial1.println(">>> RFID SCANNED: " + lastCardUID);
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
  }

  // 3. Read Joystick Navigation & Click
  int yVal = analogRead(JOY_Y);
  int xVal = analogRead(JOY_X);

  if (!inTestMode && (millis() - lastNavMove > 250)) {
    if (yVal < 200 || xVal < 200) {
      menuIndex = (menuIndex - 1 + NUM_MENUS) % NUM_MENUS;
      lastNavMove = millis();
      lcd.clear();
    } else if (yVal > 820 || xVal > 820) {
      menuIndex = (menuIndex + 1) % NUM_MENUS;
      lastNavMove = millis();
      lcd.clear();
    }
  }

  if (digitalRead(JOY_SW) == LOW && (millis() - lastBtnPress > 300)) {
    lastBtnPress = millis();
    inTestMode = !inTestMode;
    lcd.clear();
  }

  // 4. Refresh LCD, Traffic Light Status & Telemetry every 250ms
  if (millis() - lastUpdate >= 250) {
    lastUpdate = millis();

    sensors_event_t a, g, temp;
    mpu.getEvent(&a, &g, &temp);

    // Compute total acceleration magnitude (~9.8 m/s^2 at rest; >18 indicates impact/fall)
    float totalAccel = sqrt(sq(a.acceleration.x) + sq(a.acceleration.y) + sq(a.acceleration.z));

    // Update Traffic Light Indicator
    String lightStatus = "YELLOW";
    if (millis() < rfidFlashUntil) {
      setTrafficLight(false, true, false); // Yellow confirmation on RFID scan
      lightStatus = "YELLOW(RFID)";
    } else if (totalAccel > 18.0 || (irValue > 50000 && beatAvg > 100)) {
      setTrafficLight(true, false, false); // Red alert for impact or high BPM (>100)
      lightStatus = "RED(ALERT)";
    } else if (irValue > 50000 && beatAvg >= 45) {
      setTrafficLight(false, false, true); // Green for normal resting heart rate
      lightStatus = "GREEN(OK)";
    } else {
      setTrafficLight(false, true, false); // Yellow when waiting for finger / stabilizing
      lightStatus = "YELLOW(WAIT)";
    }

    // Update 16x2 LCD
    if (!inTestMode) {
      lcd.setCursor(0, 0);
      lcd.print("> " + String(menuItems[menuIndex]) + "   ");
      lcd.setCursor(0, 1);
      lcd.print("Click stick: Run");
    } else {
      if (menuIndex == 0) {
        lcd.setCursor(0, 0);
        lcd.print("HEART RATE TEST ");
        lcd.setCursor(0, 1);
        lcd.print(irValue > 50000 ? "BPM: " + String(beatAvg) + "        " : "Place Finger... ");
      } else if (menuIndex == 1) {
        lcd.setCursor(0, 0);
        lcd.print("X:" + String(a.acceleration.x, 1) + " Y:" + String(a.acceleration.y, 1) + "   ");
        lcd.setCursor(0, 1);
        lcd.print("Z:" + String(a.acceleration.z, 1) + " m/s2     ");
      } else if (menuIndex == 2) {
        lcd.setCursor(0, 0);
        lcd.print("TAP RFID CARD:  ");
        lcd.setCursor(0, 1);
        lcd.print("ID:" + lastCardUID + "  ");
      } else if (menuIndex == 3) {
        lcd.setCursor(0, 0);
        lcd.print("HR:" + String(beatAvg) + " X:" + String(a.acceleration.x, 1) + "  ");
        lcd.setCursor(0, 1);
        lcd.print("ID:" + lastCardUID + "  ");
      }
    }

    // Stream full telemetry packet to USB & Bluetooth
    String hrStatus = (irValue > 50000) ? String(beatAvg) + " BPM" : "NoFinger";
    String packet = "Status:" + lightStatus +
                    " | HR:" + hrStatus +
                    " | AccX:" + String(a.acceleration.x, 1) +
                    " AccY:" + String(a.acceleration.y, 1) +
                    " | ID:" + lastCardUID;
    Serial.println(packet);
    Serial1.println(packet);
  }
}