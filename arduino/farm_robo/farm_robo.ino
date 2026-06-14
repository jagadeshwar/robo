/*
 * FarmRobo - Arduino Low-Level Controller
 *
 * Hardware:
 *   - L298N Motor Driver  (4-wheel drive)
 *   - Soil Moisture Sensors (A0, A1, A2 - up to 3 zones)
 *   - NPK Sensor via RS485 (Serial1 on Mega / SoftwareSerial on Uno)
 *   - DHT22 Temperature & Humidity sensor (D2)
 *   - Ultrasonic sensors HC-SR04 (front, left, right obstacle detection)
 *   - Spray pump relay (D22)
 *   - Weed blade relay / servo (D23)
 *   - Gate servo signal (D24)
 *   - Buck converter powers Arduino + sensors from battery pack
 *
 * Communication: Serial (USB) to Raspberry Pi 5 at 115200 baud
 * Protocol: JSON lines  {"cmd":"...","val":...}  /  {"type":"...","data":{...}}
 */

#include <Arduino.h>
#include <Servo.h>
#include <DHT.h>

// Detect hardware Serial1 availability (Mega/2560 have Serial1)
#if defined(__AVR_ATmega2560__) || defined(__AVR_ATmega1280__)
#define HAS_SERIAL1 1
#else
#define HAS_SERIAL1 0
#endif

// ─── PIN DEFINITIONS ────────────────────────────────────────────────────────

// L298N Motor Driver - Left side
// Wiring from photos: ENA=D9, IN1=D8, IN2=D7
#define L_ENA   9   // PWM speed left
#define L_IN1   8
#define L_IN2   7

// L298N Motor Driver - Right side
// Wiring from photos: ENB=D3, IN3=D6, IN4=D5
#define R_ENB   3   // PWM speed right
#define R_IN3   6
#define R_IN4   5

// Ultrasonic sensors (HC-SR04)
// Wiring from photos: FRONT TRIG=D12, FRONT ECHO=D13
#define FRONT_TRIG  12
#define FRONT_ECHO  13
// LEFT/RIGHT sensors not present in provided photo; keep defaults for boards that support them
#define LEFT_TRIG   32
#define LEFT_ECHO   33
#define RIGHT_TRIG  34
#define RIGHT_ECHO  35

// Soil moisture sensors (analog)
#define MOISTURE_1  A0
#define MOISTURE_2  A1
#define MOISTURE_3  A2

// DHT22 temperature & humidity
#define DHT_PIN     2
#define DHT_TYPE    DHT22

// Actuators
#define SPRAY_RELAY   22   // HIGH = pump ON
#define WEED_RELAY    23   // HIGH = weed cutter ON
#define GATE_SERVO_PIN 24  // Servo signal

// NPK RS485 sensor (uses Serial1 on Arduino Mega)
// Connect: DE+RE tied to D25 (HIGH=transmit, LOW=receive)
#define RS485_DE_RE  25

// ─── CONSTANTS ───────────────────────────────────────────────────────────────

#define OBSTACLE_THRESHOLD_CM  30   // stop if obstacle < 30 cm
#define MOISTURE_DRY_THRESHOLD 400  // ADC < 400 = dry soil (needs water)
#define MOISTURE_WET_THRESHOLD 700  // ADC > 700 = wet soil
#define MAX_MOTOR_SPEED        200  // 0-255 PWM

// NPK RS485 query command (standard Modbus RTU for most NPK sensors)
const byte NPK_QUERY[] = {0x01, 0x03, 0x00, 0x00, 0x00, 0x03, 0x05, 0xCB};

// ─── GLOBALS ─────────────────────────────────────────────────────────────────

DHT dht(DHT_PIN, DHT_TYPE);
Servo gateServo;

bool   sprayActive    = false;
bool   weedActive     = false;
bool   gateOpen       = false;
int    motorSpeed     = 0; // safe default: require explicit SPEED command or non-zero val
unsigned long lastSensorReport = 0;
unsigned long lastNPKQuery     = 0;

// Parsed NPK values (mg/kg)
uint16_t npkN = 0, npkP = 0, npkK = 0;

// ─── HELPERS ─────────────────────────────────────────────────────────────────

long ultrasonicDistance(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  long dur = pulseIn(echoPin, HIGH, 30000);
  return dur == 0 ? 999 : dur * 0.034 / 2;
}

int readMoisturePercent(int pin) {
  // Map ADC: 1023 = completely dry air, ~200 = submerged in water
  int raw = analogRead(pin);
  return map(constrain(raw, 200, 1023), 1023, 200, 0, 100);
}

// ─── MOTORS ──────────────────────────────────────────────────────────────────

void stopMotors() {
  analogWrite(L_ENA, 0); analogWrite(R_ENB, 0);
  digitalWrite(L_IN1, LOW); digitalWrite(L_IN2, LOW);
  digitalWrite(R_IN3, LOW); digitalWrite(R_IN4, LOW);
}

void moveForward(int speed) {
  analogWrite(L_ENA, speed); analogWrite(R_ENB, speed);
  digitalWrite(L_IN1, HIGH); digitalWrite(L_IN2, LOW);
  digitalWrite(R_IN3, HIGH); digitalWrite(R_IN4, LOW);
}

void moveBackward(int speed) {
  analogWrite(L_ENA, speed); analogWrite(R_ENB, speed);
  digitalWrite(L_IN1, LOW); digitalWrite(L_IN2, HIGH);
  digitalWrite(R_IN3, LOW); digitalWrite(R_IN4, HIGH);
}

void turnLeft(int speed) {
  analogWrite(L_ENA, speed); analogWrite(R_ENB, speed);
  digitalWrite(L_IN1, LOW); digitalWrite(L_IN2, HIGH);
  digitalWrite(R_IN3, HIGH); digitalWrite(R_IN4, LOW);
}

void turnRight(int speed) {
  analogWrite(L_ENA, speed); analogWrite(R_ENB, speed);
  digitalWrite(L_IN1, HIGH); digitalWrite(L_IN2, LOW);
  digitalWrite(R_IN3, LOW); digitalWrite(R_IN4, HIGH);
}

// ─── NPK SENSOR (RS485) ───────────────────────────────────────────────────────

// NPK/RS485 not used on Uno build here — provide empty stub
void queryNPK() {
  // NOP: RS485 NPK sensor disabled in this build
}

// ─── JSON COMMAND PARSER ──────────────────────────────────────────────────────
// Simple key-value parser — avoids heavy JSON library on Uno/Mega.
// Commands from Pi look like:  {"cmd":"FORWARD","val":150}

String extractJsonString(const String& json, const String& key) {
  int ki = json.indexOf("\"" + key + "\"");
  if (ki == -1) return "";
  int ci = json.indexOf(":", ki);
  if (ci == -1) return "";
  int q1 = json.indexOf("\"", ci);
  int q2 = json.indexOf("\"", q1 + 1);
  if (q1 != -1 && q2 != -1) return json.substring(q1 + 1, q2);
  // numeric value
  int vs = ci + 1;
  while (vs < (int)json.length() && (json[vs] == ' ')) vs++;
  int ve = vs;
  while (ve < (int)json.length() && (json[ve] != ',' && json[ve] != '}')) ve++;
  return json.substring(vs, ve);
}

void handleCommand(const String& json) {
  String cmd = extractJsonString(json, "cmd");
  int    val  = extractJsonString(json, "val").toInt();
  int    clampVal = constrain(val, 0, 255);
  int    useSpeed = (clampVal > 0) ? clampVal : motorSpeed; // motorSpeed defaults to 0 for safety

  if      (cmd == "FORWARD")   moveForward(useSpeed);
  else if (cmd == "BACKWARD")  moveBackward(useSpeed);
  else if (cmd == "LEFT")      turnLeft(useSpeed);
  else if (cmd == "RIGHT")     turnRight(useSpeed);
  else if (cmd == "STOP")      stopMotors();
  else if (cmd == "SPEED")     motorSpeed = constrain(val, 0, 255);
  else if (cmd == "SPRAY_ON")  { digitalWrite(SPRAY_RELAY, HIGH); sprayActive = true; }
  else if (cmd == "SPRAY_OFF") { digitalWrite(SPRAY_RELAY, LOW);  sprayActive = false; }
  else if (cmd == "WEED_ON")   { digitalWrite(WEED_RELAY,  HIGH); weedActive  = true; }
  else if (cmd == "WEED_OFF")  { digitalWrite(WEED_RELAY,  LOW);  weedActive  = false; }
  else if (cmd == "GATE_OPEN") {
    gateServo.write(90);  // 90° = open
    gateOpen = true;
  }
  else if (cmd == "GATE_CLOSE") {
    gateServo.write(0);   // 0° = closed
    gateOpen = false;
  }
  else if (cmd == "PING") {
    Serial.println(F("{\"type\":\"PONG\"}"));
  }
}

// ─── SENSOR REPORT ────────────────────────────────────────────────────────────

void sendSensorReport() {
  long  frontDist = ultrasonicDistance(FRONT_TRIG, FRONT_ECHO);
  long  leftDist  = ultrasonicDistance(LEFT_TRIG,  LEFT_ECHO);
  long  rightDist = ultrasonicDistance(RIGHT_TRIG, RIGHT_ECHO);
  int   m1 = readMoisturePercent(MOISTURE_1);
  int   m2 = readMoisturePercent(MOISTURE_2);
  int   m3 = readMoisturePercent(MOISTURE_3);
  float temp = dht.readTemperature();
  float hum  = dht.readHumidity();

  // Obstacle check — send alert if something is close
  bool obstacle = (frontDist < OBSTACLE_THRESHOLD_CM);
  if (obstacle) stopMotors();

  Serial.print(F("{\"type\":\"SENSORS\",\"data\":{"
    "\"moisture\":["));
  Serial.print(m1); Serial.print(",");
  Serial.print(m2); Serial.print(",");
  Serial.print(m3);
  Serial.print(F("],\"npk\":{\"N\":"));
  Serial.print(npkN);
  Serial.print(F(",\"P\":"));
  Serial.print(npkP);
  Serial.print(F(",\"K\":"));
  Serial.print(npkK);
  Serial.print(F("},\"temp\":"));
  Serial.print(isnan(temp) ? 0.0 : temp, 1);
  Serial.print(F(",\"humidity\":"));
  Serial.print(isnan(hum)  ? 0.0 : hum,  1);
  Serial.print(F(",\"dist\":{\"front\":"));
  Serial.print(frontDist);
  Serial.print(F(",\"left\":"));
  Serial.print(leftDist);
  Serial.print(F(",\"right\":"));
  Serial.print(rightDist);
  Serial.print(F("},\"obstacle\":"));
  Serial.print(obstacle ? "true" : "false");
  Serial.print(F(",\"spray\":"));
  Serial.print(sprayActive ? "true" : "false");
  Serial.print(F(",\"weed\":"));
  Serial.print(weedActive ? "true" : "false");
  Serial.print(F(",\"gate\":\""));
  Serial.print(gateOpen ? "open" : "closed");
  Serial.println(F("\"}}"));
}

// ─── SETUP / LOOP ─────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(115200);   // Pi communication
  // NPK RS485 sensor not initialized on Uno build

  // Motor driver pins
  pinMode(L_ENA, OUTPUT); pinMode(L_IN1, OUTPUT); pinMode(L_IN2, OUTPUT);
  pinMode(R_ENB, OUTPUT); pinMode(R_IN3, OUTPUT); pinMode(R_IN4, OUTPUT);

  // Ultrasonic
  pinMode(FRONT_TRIG, OUTPUT); pinMode(FRONT_ECHO, INPUT);
  pinMode(LEFT_TRIG,  OUTPUT); pinMode(LEFT_ECHO,  INPUT);
  pinMode(RIGHT_TRIG, OUTPUT); pinMode(RIGHT_ECHO, INPUT);

  // Actuators
  pinMode(SPRAY_RELAY, OUTPUT);   digitalWrite(SPRAY_RELAY, LOW);
  pinMode(WEED_RELAY,  OUTPUT);   digitalWrite(WEED_RELAY,  LOW);
  pinMode(RS485_DE_RE, OUTPUT);   digitalWrite(RS485_DE_RE, LOW);

  gateServo.attach(GATE_SERVO_PIN);
  gateServo.write(0);   // start closed

  dht.begin();
  stopMotors();

  Serial.println(F("{\"type\":\"READY\",\"msg\":\"FarmRobo Arduino online\"}"));
}

void loop() {
  // Read incoming commands from Raspberry Pi
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.startsWith("{")) handleCommand(line);
  }

  // Send sensor report every 2000 ms
  if (millis() - lastSensorReport >= 2000) {
    lastSensorReport = millis();
    sendSensorReport();
  }

  // Query NPK sensor every 5 seconds
  if (millis() - lastNPKQuery >= 5000) {
    lastNPKQuery = millis();
    queryNPK();
  }
}
