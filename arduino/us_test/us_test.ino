/*
 * HC-SR04 diagnostic — prints RAW echo pulse duration so we can tell
 * wiring/power/dead-sensor apart from the main firmware.
 *
 * Tests BOTH orientations every cycle:
 *   A) TRIG=D12, ECHO=D11   (current intended wiring)
 *   B) TRIG=D11, ECHO=D12   (in case TRIG/ECHO are swapped)
 *
 * Reads: dur = microseconds of echo HIGH pulse (0 = no echo).
 *        cm  = computed distance (999 = no echo).
 */

#define P12 12
#define P11 11

long pingRaw(int trig, int echo) {
  pinMode(trig, OUTPUT);
  pinMode(echo, INPUT);
  digitalWrite(trig, LOW);
  delayMicroseconds(4);
  digitalWrite(trig, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig, LOW);
  return pulseIn(echo, HIGH, 30000);   // microseconds, 0 if timeout
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println(F("HC-SR04 diagnostic starting"));
}

void loop() {
  long a = pingRaw(P12, P11);   // TRIG=12 ECHO=11
  delay(60);
  long b = pingRaw(P11, P12);   // TRIG=11 ECHO=12
  Serial.print(F("A(T12,E11) dur="));
  Serial.print(a);
  Serial.print(F("us cm="));
  Serial.print(a == 0 ? 999 : a * 0.034 / 2);
  Serial.print(F("   |   B(T11,E12) dur="));
  Serial.print(b);
  Serial.print(F("us cm="));
  Serial.println(b == 0 ? 999 : b * 0.034 / 2);
  delay(500);
}
