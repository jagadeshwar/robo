# FarmRobo — Wiring Guide

## Power Architecture (Buck Converter)

```
Battery Pack (12V LiPo / 3S)
        │
        ├── L298N  VCC (12V motors)
        │
        └── Buck Converter #1  →  7.5V–5V  →  Arduino Mega 5V pin
                                              →  Soil moisture sensors (5V)
                                              →  Ultrasonic sensors (5V)
                                              →  DHT22 sensor (3.3–5V)

        └── Buck Converter #2  →  5.1V 5A  →  Raspberry Pi 5  (USB-C)
```

> Use separate buck converters for Pi and Arduino — motor noise on shared rails
> causes corrupted serial and random reboots.

---

## L298N Motor Driver → Arduino Mega

| L298N Pin | Arduino Pin | Purpose              |
|-----------|-------------|----------------------|
| ENA       | D5 (PWM)    | Left motor speed     |
| IN1       | D6          | Left motor direction |
| IN2       | D7          | Left motor direction |
| ENB       | D9 (PWM)    | Right motor speed    |
| IN3       | D10         | Right motor direction|
| IN4       | D11         | Right motor direction|
| GND       | GND         | Common ground        |
| VCC       | —           | 12V from battery     |
| +5V out   | —           | Do NOT use (noisy)   |

For 4-wheel drive: wire both left motors to OUT1/OUT2, both right to OUT3/OUT4.

---

## HC-SR04 Ultrasonic Sensors

| Sensor     | VCC | GND | TRIG | ECHO |
|------------|-----|-----|------|------|
| Front      | 5V  | GND | D30  | D31  |
| Left       | 5V  | GND | D32  | D33  |
| Right      | 5V  | GND | D34  | D35  |

> ECHO pin outputs 5V — use a voltage divider (1kΩ + 2kΩ) or logic level
> shifter to protect Arduino 3.3V pins if using Arduino Zero/Due.
> Arduino Mega is 5V tolerant — connect directly.

---

## Soil Moisture Sensors (Capacitive recommended)

| Sensor | Signal Pin | VCC | GND |
|--------|------------|-----|-----|
| Zone 1 | A0         | 5V  | GND |
| Zone 2 | A1         | 5V  | GND |
| Zone 3 | A2         | 5V  | GND |

Calibration in firmware: 1023 = dry air, ~200 = fully submerged.

---

## NPK Sensor (RS485 Modbus)

Typical wiring for a 5-pin NPK soil sensor:

| Sensor Wire | Connect To        |
|-------------|-------------------|
| Red (VCC)   | 12V               |
| Black (GND) | GND               |
| Yellow (A+) | RS485 module A+   |
| Green  (B-) | RS485 module B-   |

RS485 Module → Arduino Mega:
| RS485 | Arduino Mega |
|-------|--------------|
| DI    | TX1 (D18)    |
| RO    | RX1 (D19)    |
| DE+RE | D25          |
| VCC   | 5V           |
| GND   | GND          |

---

## DHT22 Temperature & Humidity

| DHT22 Pin | Arduino Pin |
|-----------|-------------|
| VCC       | 5V          |
| Data      | D2          |
| GND       | GND         |

Add 10kΩ pull-up resistor between VCC and Data pin.

---

## Spray Pump (via Relay)

```
Arduino D22 → Relay IN
Relay COM   → Battery 12V +
Relay NO    → Pump +
Pump -      → Battery GND
```

Add a flyback diode across the pump terminals (1N4007).

---

## Weed Cutter Motor (via Relay or L298N second channel)

Same wiring pattern as spray pump, using D23 for the relay signal.
If the cutter is a DC motor, use a separate L298N channel.

---

## Gate Servo

| Servo Wire | Arduino Pin |
|------------|-------------|
| Red (VCC)  | 5V          |
| Brown (GND)| GND         |
| Orange/Yel | D24 (PWM)   |

Gate logic (in firmware):
- `write(0)`  = CLOSED
- `write(90)` = OPEN  (adjust angle for your gate mechanism)

---

## Arduino → Raspberry Pi 5 (Serial)

| Arduino Mega | Raspberry Pi 5        |
|--------------|-----------------------|
| USB port     | USB-A port            |
| GND          | GND (shared)          |

Serial appears as `/dev/ttyUSB0` or `/dev/ttyACM0` on the Pi.

Run to confirm:
```bash
ls /dev/ttyUSB* /dev/ttyACM*
```

---

## Bill of Materials (What to buy if not already owned)

| Item                          | Qty | Notes                           |
|-------------------------------|-----|---------------------------------|
| Arduino Mega 2560             |  1  | Enough pins for all sensors     |
| L298N Motor Driver Module     |  1  | 12V / 2A per channel            |
| Buck Converter (XL4016/LM2596)|  2  | One for Pi, one for Arduino     |
| 12V LiPo (3S 5000mAh)        |  1  | Or equivalent 12V battery       |
| HC-SR04 Ultrasonic            |  3  | Front + Left + Right            |
| Capacitive Soil Moisture v1.2 |  3  | One per zone                    |
| RS485 NPK Soil Sensor         |  1  | 7-in-1 model covers N,P,K,pH,T,H,EC |
| DHT22                         |  1  | Temperature + Humidity          |
| 5V Relay Module (1-ch)        |  2  | Spray pump + Weed cutter        |
| Servo Motor (MG996R)          |  1  | Gate control                    |
| 12V Water Pump                |  1  | Spray mechanism                 |
| 12V DC Weed Cutter Motor      |  1  | Or servo-driven blade           |
| RS485 TTL Module (MAX485)     |  1  | NPK sensor interface            |
| Silicone wire 18AWG           | —   | Motor power runs                |
| Silicone wire 22AWG           | —   | Signal runs                     |
| JST connectors                | —   | Quick-disconnect for sensors    |
