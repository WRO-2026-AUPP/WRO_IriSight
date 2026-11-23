# ESP32 firmware

The custom ESP32 board receives commands from the Jetson over USB serial and
controls the JGB37-520 drive motor and MG996R steering servo.

## Current firmware

Flash [`firmware/firmware.ino`](firmware/firmware.ino) using the Arduino IDE or
`arduino-cli` with the `ESP32Servo` library installed.

Confirmed current connections:

| Function | ESP32 pin |
| --- | ---: |
| MG996R servo signal | GPIO 18 |
| TB6612FNG motor input 1 | GPIO 25 |
| TB6612FNG motor input 2 | GPIO 26 |
| TB6612FNG motor PWM | GPIO 33 |

Serial settings: **115200 baud**, newline-terminated commands.

Primary commands:

```text
DRIVE <steering-offset-degrees> <speed-0-to-255>
BACK <steering-offset-degrees> <speed-0-to-255>
STOP
```

The firmware has been confirmed working on the rebuilt robot. Start-button and
CW/CCW state-button handling are planned but not yet implemented. A serial
command timeout is also under consideration and must be tested before it is
introduced.

## Legacy reference

The former [National Arduino firmware](../../other/legacy_national/src/helper_function/ultrasonic_arduino_v2.ino)
is preserved inside the complete National repository archive. It uses the
removed ultrasonic sensors and the old servo pin, so it must not be flashed
onto the rebuilt robot.
