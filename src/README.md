💻 Control software
====
This directory contains the control software used by our vehicle to participate in the WRO 2026 Future Engineer competition, developed entirely by our team. It includes all code, trained models, and dependency information required to build and run the robot's autonomous behavior for both the Open Challenge and Obstacle Avoidance rounds.

## 🧠 Our Approach

Our robot navigates using the Intel RealSense D455 depth camera as its primary spatial sensor, supplemented by the BNO055 IMU for heading and, in the obstacle round, ultrasonic sensors for redundant close-range sensing.

We chose wall following as our core navigation strategy for a simple reason: with a camera as the primary spatial sensor, walls are the most consistent and reliable reference we can measure. They give a stable, low-noise signal that doesn't depend on track markings or lighting conditions the way pure visual line-following would. This choice also produces smooth, repeatable paths and keeps the robot at a safe, predictable standoff from the track boundary, even with small variations in how the track is physically built.

Because our entire navigation strategy rests on a single depth signal, most of our engineering effort went into making that signal as clean and responsive as possible — filtering noisy depth readings, using median sampling instead of raw pixel reads, and tuning a PD controller so the robot reacts quickly to error without oscillating. The Jetson handles all sensing, vision, and decision-making; it then sends simple, low-level drive commands to an ESP32 over serial, which is responsible only for actually driving the motors and steering servo.

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


