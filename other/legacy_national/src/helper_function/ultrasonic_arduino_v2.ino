#include <ESP32Servo.h>

// ══════════════════════════════════════════════════════════════════════════════
//  ULTRASONIC PINS
//  Hardware: LEFT ultrasonic + RIGHT ultrasonic
//  Serial output:
//      USL <cm>
//      USR <cm>
// ══════════════════════════════════════════════════════════════════════════════

// LEFT ultrasonic
#define LEFT_TRIG_PIN  13
#define LEFT_ECHO_PIN  39

// RIGHT ultrasonic
#define RIGHT_TRIG_PIN 4
#define RIGHT_ECHO_PIN 16

// Send ultrasonic data every 100 ms
unsigned long lastUltrasonicTime = 0;
const unsigned long ULTRASONIC_INTERVAL = 100;

// ══════════════════════════════════════════════════════════════════════════════
//  MOTOR / SERVO PINS
// ══════════════════════════════════════════════════════════════════════════════
#define SERVO_PIN     17
#define MOTOR_IN1     26
#define MOTOR_IN2     25
#define MOTOR_PWM_PIN 33
#define MOTOR_PWM_CH  2
#define MOTOR_FREQ    20000
#define MOTOR_RES     8

// ══════════════════════════════════════════════════════════════════════════════
//  SERVO SETTINGS
//  right = +, left = -
// ══════════════════════════════════════════════════════════════════════════════
const int SERVO_MIN = 35;
const int SERVO_MAX = 145;
const int SERVO_MID = 90;

const int TURN_AMT    = 35;
const int CORRECT_AMT = 25;
const int NUDGE_AMT   = 4;

// ══════════════════════════════════════════════════════════════════════════════
//  MOTOR SETTINGS
// ══════════════════════════════════════════════════════════════════════════════
const int MOTOR_SPEED = 120;

// ══════════════════════════════════════════════════════════════════════════════
Servo myServo;
int servoAngle = SERVO_MID;

// Serial command buffer
char buf[40];
uint8_t idx = 0;

// ══════════════════════════════════════════════════════════════════════════════
//  MOTOR / SERVO HELPERS
// ══════════════════════════════════════════════════════════════════════════════
void motorForward() {
  digitalWrite(MOTOR_IN1, HIGH);
  digitalWrite(MOTOR_IN2, LOW);
  ledcWrite(MOTOR_PWM_CH, MOTOR_SPEED);
}

void motorBackward() {
  digitalWrite(MOTOR_IN1, LOW);
  digitalWrite(MOTOR_IN2, HIGH);
  ledcWrite(MOTOR_PWM_CH, MOTOR_SPEED);
}

void motorStop() {
  digitalWrite(MOTOR_IN1, LOW);
  digitalWrite(MOTOR_IN2, LOW);
  ledcWrite(MOTOR_PWM_CH, 0);
}

void motorDriveForward(int speed) {
  speed = constrain(speed, 0, 255);

  if (speed == 0) {
    motorStop();
    return;
  }

  digitalWrite(MOTOR_IN1, HIGH);
  digitalWrite(MOTOR_IN2, LOW);
  ledcWrite(MOTOR_PWM_CH, speed);
}

void motorDriveBackward(int speed) {
  speed = constrain(speed, 0, 255);

  if (speed == 0) {
    motorStop();
    return;
  }

  digitalWrite(MOTOR_IN1, LOW);
  digitalWrite(MOTOR_IN2, HIGH);
  ledcWrite(MOTOR_PWM_CH, speed);
}

void setServo(int angle) {
  servoAngle = constrain(angle, SERVO_MIN, SERVO_MAX);
  myServo.write(servoAngle);
}

// ══════════════════════════════════════════════════════════════════════════════
//  ULTRASONIC FUNCTIONS
// ══════════════════════════════════════════════════════════════════════════════
float readUltrasonicCm(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);

  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  long duration = pulseIn(echoPin, HIGH, 25000);  // 25 ms timeout

  if (duration == 0) {
    return -1.0;   // no echo
  }

  float distance = (duration * 0.0343) / 2.0;
  return distance;
}

void sendUltrasonicData() {
  float leftCm = readUltrasonicCm(LEFT_TRIG_PIN, LEFT_ECHO_PIN);
  delay(5);  // small delay to reduce ultrasonic interference

  float rightCm = readUltrasonicCm(RIGHT_TRIG_PIN, RIGHT_ECHO_PIN);

  // LEFT ultrasonic data
  if (leftCm < 0) {
    Serial.println("USL NO_ECHO");
  } else {
    Serial.print("USL ");
    Serial.println(leftCm, 2);
  }

  // RIGHT ultrasonic data
  if (rightCm < 0) {
    Serial.println("USR NO_ECHO");
  } else {
    Serial.print("USR ");
    Serial.println(rightCm, 2);
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  COMMAND HANDLER
// ══════════════════════════════════════════════════════════════════════════════
void handleCommand(char* cmd) {
  // Forward proportional drive:
  // DRIVE <steerDeg> <speed>
  // Example: DRIVE -20 110
  if (strncmp(cmd, "DRIVE ", 6) == 0) {
    int steer = 0;
    int spd = 0;

    if (sscanf(cmd + 6, "%d %d", &steer, &spd) == 2) {
      setServo(SERVO_MID + steer);
      motorDriveForward(spd);

      Serial.print("OK DRIVE s=");
      Serial.print(servoAngle);
      Serial.print(" v=");
      Serial.println(spd);
    } else {
      Serial.println("BAD DRIVE");
    }

    return;
  }

  // Backward proportional drive:
  // BACK <steerDeg> <speed>
  // Example: BACK 15 90
  if (strncmp(cmd, "BACK ", 5) == 0) {
    int steer = 0;
    int spd = 0;

    if (sscanf(cmd + 5, "%d %d", &steer, &spd) == 2) {
      setServo(SERVO_MID + steer);
      motorDriveBackward(spd);

      Serial.print("OK BACK s=");
      Serial.print(servoAngle);
      Serial.print(" v=");
      Serial.println(spd);
    } else {
      Serial.println("BAD BACK");
    }

    return;
  }

  // Discrete commands
  if      (strcmp(cmd, "FORWARD")       == 0) { setServo(SERVO_MID);               motorForward();  }
  else if (strcmp(cmd, "BACKWARD")      == 0) { setServo(SERVO_MID);               motorBackward(); }
  else if (strcmp(cmd, "STOP")          == 0) { setServo(SERVO_MID);               motorStop();     }

  else if (strcmp(cmd, "TURN_RIGHT")    == 0) { setServo(SERVO_MID + TURN_AMT);    motorForward();  }
  else if (strcmp(cmd, "TURN_LEFT")     == 0) { setServo(SERVO_MID - TURN_AMT);    motorForward();  }

  else if (strcmp(cmd, "BACK_RIGHT")    == 0) { setServo(SERVO_MID + TURN_AMT);    motorBackward(); }
  else if (strcmp(cmd, "BACK_LEFT")     == 0) { setServo(SERVO_MID - TURN_AMT);    motorBackward(); }

  else if (strcmp(cmd, "CORRECT_RIGHT") == 0) { setServo(SERVO_MID + CORRECT_AMT); motorForward();  }
  else if (strcmp(cmd, "CORRECT_LEFT")  == 0) { setServo(SERVO_MID - CORRECT_AMT); motorForward();  }

  else if (strcmp(cmd, "NUDGE_RIGHT")   == 0) { setServo(SERVO_MID + NUDGE_AMT);   motorForward();  }
  else if (strcmp(cmd, "NUDGE_LEFT")    == 0) { setServo(SERVO_MID - NUDGE_AMT);   motorForward();  }

  else {
    Serial.print("Unknown cmd: ");
    Serial.println(cmd);
    return;
  }

  Serial.print("OK ");
  Serial.print(cmd);
  Serial.print(" servo=");
  Serial.println(servoAngle);
}

// ══════════════════════════════════════════════════════════════════════════════
//  SETUP
// ══════════════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);

  // Ultrasonic sensors
  pinMode(LEFT_TRIG_PIN, OUTPUT);
  pinMode(LEFT_ECHO_PIN, INPUT);
  digitalWrite(LEFT_TRIG_PIN, LOW);

  pinMode(RIGHT_TRIG_PIN, OUTPUT);
  pinMode(RIGHT_ECHO_PIN, INPUT);
  digitalWrite(RIGHT_TRIG_PIN, LOW);

  // Servo
  ESP32PWM::allocateTimer(0);
  myServo.setPeriodHertz(50);
  myServo.attach(SERVO_PIN);
  myServo.write(SERVO_MID);

  // Motor
  pinMode(MOTOR_IN1, OUTPUT);
  pinMode(MOTOR_IN2, OUTPUT);

  ledcSetup(MOTOR_PWM_CH, MOTOR_FREQ, MOTOR_RES);
  ledcAttachPin(MOTOR_PWM_PIN, MOTOR_PWM_CH);

  motorStop();

  Serial.println("ESP32 ready");
}

// ══════════════════════════════════════════════════════════════════════════════
//  LOOP
// ══════════════════════════════════════════════════════════════════════════════
void loop() {
  // 1. Read Jetson commands
  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\n' || c == '\r') {
      if (idx > 0) {
        buf[idx] = '\0';
        handleCommand(buf);
        idx = 0;
      }
    } else if (idx < sizeof(buf) - 1) {
      buf[idx++] = c;
    }
  }

  // 2. Send ultrasonic data every 100 ms
  unsigned long now = millis();

  if (now - lastUltrasonicTime >= ULTRASONIC_INTERVAL) {
    lastUltrasonicTime = now;
    sendUltrasonicData();
  }
}
