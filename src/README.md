💻 Control software
====
This directory contains the control software used by our vehicle to participate in the WRO 2026 Future Engineer competition, developed entirely by our team. It includes all code, trained models, and dependency information required to build and run the robot's autonomous behavior for both the Open Challenge and Obstacle Avoidance rounds.

## 🧠 Our Approach

Our robot navigates using the Intel RealSense D455 depth camera as its primary spatial sensor, supplemented by the BNO055 IMU for heading and, in the obstacle round, ultrasonic sensors for redundant close-range sensing.

We chose wall following as our core navigation strategy for a simple reason: with a camera as the primary spatial sensor, walls are the most consistent and reliable reference we can measure. They give a stable, low-noise signal that doesn't depend on track markings or lighting conditions the way pure visual line-following would. This choice also produces smooth, repeatable paths and keeps the robot at a safe, predictable standoff from the track boundary, even with small variations in how the track is physically built.

Because our entire navigation strategy rests on a single depth signal, most of our engineering effort went into making that signal as clean and responsive as possible — filtering noisy depth readings, using median sampling instead of raw pixel reads, and tuning a PD controller so the robot reacts quickly to error without oscillating. The Jetson handles all sensing, vision, and decision-making; it then sends simple, low-level drive commands to an ESP32 over serial, which is responsible only for actually driving the motors and steering servo.

## 🤖 AI Model

While the Open Challenge relies purely on depth-based wall following, the Obstacle Avoidance round additionally requires the robot to recognize and react to colored pillars and the parking signal. For this, we use a custom-trained **YOLOv8** object detection model, which is the primary way our robot perceives obstacles.

#### 🎯 What it detects

| Class | Detect Object | Robot Action |
|-------|---------------|--------------|
| 0 | **Green Obstacle Pillar** (`greenbox`) | Robot turns/passes to the **right** |
| 1 | **Red Obstacle Pillar** (`redbox`) | Robot turns/passes to the **left** |
| 2 | **Parking Marker** (`xparking`) | Robot detects and aligns with the **parking space** |

#### 🏋️ Training details

- **Base architecture:** YOLOv8n (nano) — chosen for its speed/accuracy tradeoff, so it can run in real time on the Jetson alongside the depth-processing pipeline.
- **Input size:** 640×640
- **Epochs:** 100 (batch size 8, auto optimizer, lr0 = 0.01)
- **Dataset:** Custom-labeled images of the competition field's red/green pillars and the parking marker, captured under varied lighting and distances.
- **Validation performance:** precision ≈ 0.997, recall ≈ 0.985, mAP@50 ≈ 0.995, mAP@50-95 ≈ 0.928.
- **Weights file:** `best1.pt` — the best checkpoint by validation fitness, used directly for inference on the robot.

#### ⚙️ How it fits into the pipeline

1. **Color frame → YOLO inference.** Each color frame from the RealSense D455 is passed through the YOLOv8 model to detect and classify `greenbox`, `redbox`, and `xparking` instances, returning bounding boxes and confidence scores.
2. **Depth fusion.** The pixel location of each detected box is cross-referenced with the aligned depth frame to estimate the obstacle's real-world distance and lateral offset, not just its position in the 2D image.
3. **Decision logic.** Based on the detected class, the robot computes a steering offset to pass green pillars on the right and red pillars on the left, while the underlying wall-following PD controller continues to handle smooth trajectory correction.
4. **Parking maneuver.** Once `xparking` is detected and the robot has completed the required laps, detections of this class are used to align the robot with the parking space and trigger the final parking sequence.
5. **Ultrasonic backup.** Ultrasonic sensors provide redundant close-range confirmation so a missed or late detection doesn't result in a collision.

Because object detection only needs to run during the Obstacle Avoidance round, YOLO inference is disabled entirely during the Open Challenge to save compute and keep the depth-based control loop running at full speed.

### 🏁 Open Challenge
#### 📋 Challenge Requirements

The Open Challenge requires the robot to autonomously complete 3 laps around the track, staying within track boundaries and avoiding contact with the walls. There are no pillars or fixed obstacles in this round — the only challenge is smooth, accurate navigation and reliable lap counting.

Since the direction of travel (clockwise or counter-clockwise) is only revealed just before the run starts, our robot needs to be able to run in either direction. We solved this by building two interchangeable driving programs:

| Mode | Wall Followed | Turn at Corners |
|------|---------------|-----------------|
| `clockWise.py` | Left wall | Turns **right** |
| `counterClockWise.py` | Right wall | Turns **left** |

#### 🧭 Navigation Per File

**Left Wall Following (clockWise.py)**
- Follows the left wall and uses the LEFT ROI to keep a consistent distance.
- If the robot is too far from the left wall, it steers right toward the wall.
- If it is too close, it steers left away from the wall.
- At a corner, it makes a fixed right turn (TURN_STEER = +30°) until the path ahead is clear.
- If the left wall cannot be detected, it gently steers left to search for it again.
- Lap checkpoints are detected in the order 90° → 180° → 270° → 0°.

**Right Wall Following (counterClockWise.py)**
- Follows the right wall and uses the RIGHT ROI to keep a consistent distance.
- If the robot is too far from the right wall, it steers right toward the wall.
- If it is too close, it steers left away from the wall.
- At a corner, it makes a fixed left turn (TURN_STEER = −32°) until the path ahead is clear.
- If the right wall cannot be detected, it gently steers right to search for it again.
- Lap checkpoints are detected in the order 270° → 180° → 90° → 0°.

#### 🎯 Our Strategy

1. **Depth camera for navigation, IMU for lap counting** <br>
   In the Open Challenge, steering relies entirely on the RealSense D455 depth stream. YOLO and ultrasonic sensors are not used because there are no pillars to detect. The BNO055 IMU runs
   alongside the camera and is used only to track heading and count laps, not for steering.
3. **Two regions of interest (ROIs) are read from each depth frame** <br>
- FRONT ROI: Centered in the frame and used to detect an approaching wall or corner.
- SIDE ROI: Located on the left or right depending on the mode, and used to measure the robot’s distance from the wall it is following.
3. **PD controller for wall following** <br>
  The PD controller converts the side-wall distance error into a steering angle. The further the robot is from the target distance, the stronger it steers back toward the wall. The  derivative term helps reduce overshooting and oscillation.
4. **Fixed steering at corners.** <br>
  When a corner is detected because the front distance drops below a threshold, the robot temporarily stops using the side-wall PD controller and steers at a fixed angle until the path
  opens up again. This is more reliable for sharp corners than trying to follow the wall using PD control.
5. **Heading-based lap counting.** <br>
  Lap counting is handled independently from vision using the IMU’s heading. This makes lap counting more reliable even if the camera temporarily loses track of the wall.

#### 📉 System Workflow

```mermaid
flowchart TD
    A([START OPEN CHALLENGE]) --> B[Initialize System<br/>• RealSense D455<br/>• BNO055 IMU<br/>• Serial to ESP32<br/>• Flask HUD Server]

    B --> C[Zero IMU Heading<br/>Current direction = 0°<br/>lap_count = 0]

    C --> D[MAIN LOOP]

    D --> E[Capture and align depth and color frames<br/>640×480 @ 30 FPS]

    E --> F[Sample FRONT and SIDE ROIs from depth frame<br/>Median of valid pixels]

    F --> G[Read relative yaw from IMU<br/>Check checkpoint zone<br/>Update lap_count]

    G --> H{In a turn?}

    H -- YES --> I[TURN MODE<br/><br/>steer = fixed TURN_STEER<br/>speed = TURN_SPEED<br/><br/>Exit when front ≥ FRONT_CLEAR]

    H -- NO --> J[WALL-FOLLOW MODE<br/><br/>error = target − actual<br/>steer = Kp × error + Kd × derivative<br/>Clamp to STEER_LIMIT<br/>speed = BASE_SPEED<br/><br/>If side wall not seen:<br/>steer = SEARCH_STEER]

    I --> K[Send DRIVE command<br/>over serial to ESP32]
    J --> K

    K --> L{lap_count ≥ 3?}

    L -- NO --> D

    L -- YES --> M[Continue driving for<br/>STOP_DELAY_AFTER_LAPS]

    M --> N[Send DRIVE 0 0]
    N --> O([STOP])
