#include <ESP32Servo.h>

#define SERVO_PIN     18
#define MOTOR_IN1     25
#define MOTOR_IN2     26
#define MOTOR_PWM_PIN 33

#define MOTOR_PWM_CH  4
#define MOTOR_FREQ    20000
#define MOTOR_RES     8

// Original steering settings preserved
const int SERVO_MIN = 35;
const int SERVO_MAX = 150;
const int SERVO_MID = 95;

const int TURN_AMT    = 45;
const int CORRECT_AMT = 35;
const int NUDGE_AMT   = 10;

// ================= MOTOR SETTINGS =================
const int MOTOR_SPEED = 150;

// ================= VARIABLES =================
Servo myServo;
int servoAngle = SERVO_MID;

// Serial command buffer
char buf[40];
uint8_t idx = 0;

// ================= MOTOR FUNCTIONS =================
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

// ================= SERVO FUNCTION =================
void setServo(int angle) {
  servoAngle = constrain(angle, SERVO_MIN, SERVO_MAX);
  myServo.write(servoAngle);
}

// ================= COMMAND HANDLER =================
void handleCommand(char* cmd) {
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
  if (strcmp(cmd, "FORWARD") == 0) {
    setServo(SERVO_MID);
    motorForward();
  }
  else if (strcmp(cmd, "BACKWARD") == 0) {
    setServo(SERVO_MID);
    motorBackward();
  }
  else if (strcmp(cmd, "STOP") == 0) {
    setServo(SERVO_MID);
    motorStop();
  }
  else if (strcmp(cmd, "TURN_RIGHT") == 0) {
    setServo(SERVO_MID + TURN_AMT);
    motorForward();
  }
  else if (strcmp(cmd, "TURN_LEFT") == 0) {
    setServo(SERVO_MID - TURN_AMT);
    motorForward();
  }
  else if (strcmp(cmd, "BACK_RIGHT") == 0) {
    setServo(SERVO_MID + TURN_AMT);
    motorBackward();
  }
  else if (strcmp(cmd, "BACK_LEFT") == 0) {
    setServo(SERVO_MID - TURN_AMT);
    motorBackward();
  }
  else if (strcmp(cmd, "CORRECT_RIGHT") == 0) {
    setServo(SERVO_MID + CORRECT_AMT);
    motorForward();
  }
  else if (strcmp(cmd, "CORRECT_LEFT") == 0) {
    setServo(SERVO_MID - CORRECT_AMT);
    motorForward();
  }
  else if (strcmp(cmd, "NUDGE_RIGHT") == 0) {
    setServo(SERVO_MID + NUDGE_AMT);
    motorForward();
  }
  else if (strcmp(cmd, "NUDGE_LEFT") == 0) {
    setServo(SERVO_MID - NUDGE_AMT);
    motorForward();
  }
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

// ================= SETUP =================
void setup() {
  Serial.begin(115200);

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

// ================= LOOP =================
void loop() {
  // Read serial commands from Jetson / computer
  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\n' || c == '\r') {
      if (idx > 0) {
        buf[idx] = '\0';
        handleCommand(buf);
        idx = 0;
      }
    }
    else if (idx < sizeof(buf) - 1) {
      buf[idx++] = c;
    }
  }
}
