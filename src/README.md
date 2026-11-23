# 💻 Robot Software

This directory contains the software for the International robot:

- the Python programs on the NVIDIA Jetson Orin Nano (the main controller);
- the firmware on the custom ESP32 board (the microcontroller);
- the trained traffic-sign model.

The Jetson does all of the sensing and decision-making in Python. It sends short text commands over USB serial to the **ESP32**, which drives the motor and steering servo.

> **Status:** The Open Challenge and Obstacle Challenge programs below are the current International versions. Some competition features are still missing; see [Not implemented yet](#-not-implemented-yet). The National Round software is archived in [`../other/legacy_national/`](../other/legacy_national/) and must not be used on the rebuilt robot.

---

## 📁 Directory Map

```text
src/
├── main_controller/                      # Jetson programs (Python)
│   ├── open_challenge/
│   │   ├── open_clockwise.py             #   follows the inner RIGHT wall
│   │   └── open_counter_clockwise.py     #   follows the inner LEFT wall
│   ├── obstacle_challenge/
│   │   ├── obstacle_clockwise.py         #   full clockwise run
│   │   └── obstacle_counter_clockwise.py #   full counter-clockwise run
│   ├── config/                           #   pillar map files read by the obstacle programs
│   ├── sensors/                          #   where the sensor code is in each program
│   └── requirements.txt                  #   Python packages
├── microcontroller/
│   └── firmware/firmware.ino             # ESP32 motor and servo firmware
└── ai_model/
    └── traffic_sign_detector.pt          # YOLOv8n traffic-sign (pillar) detector
```

| Path | Purpose |
| --- | --- |
| [`main_controller/`](main_controller/) | Jetson programs, setup, run commands and safety notes |
| [`microcontroller/`](microcontroller/) | ESP32 firmware, pin map and flashing |
| [`ai_model/`](ai_model/) | Trained pillar detector and how it was trained |

---

## 🧠 System Overview

```text
 Hokuyo UST-30LX LiDAR (Ethernet) ──┐
 BNO055 IMU (I²C bus 7) ────────────┤
 USB camera + YOLOv8n model ────────┼──► Jetson (Python) ── USB serial 115200 ──► ESP32 ──► motor + steering servo
 VL53L0X rear distance (I²C bus 1) ─┘          │
                                               └── web dashboard (port 5000), for testing only
```

| Sensor or device | Role | Used in |
| --- | --- | --- |
| **Hokuyo UST-30LX LiDAR** (`192.168.0.10:10940`, via `hokuyolx`) | Front, side and front-corner distances; wall and corner detection | Both challenges |
| **BNO055 IMU** (I²C bus 7, address `0x28`) | Heading (yaw), turn completion and lap counting | Both challenges |
| **USB camera + YOLOv8n** (`traffic_sign_detector.pt`) | Tells red pillars from green pillars | Obstacle Challenge |
| **VL53L0X** (I²C bus 1, address `0x29`, facing backward) | Rear distance during final parking | Obstacle Challenge |
| **ESP32 board** (`/dev/ttyUSB0`, 115200 baud) | Carries out the drive commands | Both challenges |

### Software design (shared by every program)

- **Three threads:** a LiDAR thread, a control thread, and a Flask web server, all sharing state under a lock.
- **Fail-safe behaviour:** the robot sends `STOP` if LiDAR data is stale (`SCAN_TIMEOUT = 0.5 s`), if a front or front-side reading is missing, or when the program exits. A watchdog on the ESP32 is also required (see [Safety](#️-safety)).
- **Median sampling** over angular sectors rather than single rays, to reject noise. Angles use the convention **+90° = left, 0° = front, −90° = right**.
- **Live dashboard (testing only):** open `http://<jetson-ip>:5000` to see the LiDAR scan, distances, the command being sent, steering, PWM, yaw and lap count. The obstacle programs also stream the annotated camera view at `/camera`. A JSON feed is at `/scan`.

### Jetson → ESP32 commands

Commands are ASCII text lines ending in a newline (`\n`):

| Command | Meaning | Used by |
| --- | --- | --- |
| `DRIVE <steering> <pwm>` | Drive forward. Steering is in degrees from centre (**positive = right, negative = left**); PWM is motor speed, `0–255` | All programs |
| `BACK <steering> <pwm>` | Drive backward with the same steering and speed values | Obstacle programs (parking exit and final parking) |
| `STOP` | Stop the motor and centre the steering | All programs |

The firmware adds the steering value to the servo centre (95°) and limits the servo to 35°–150°. Details are in [`microcontroller/`](microcontroller/).

---

## 🚧 Not Implemented Yet

These items are needed for competition runs and are not yet in the code:

- **Start button.** The programs start driving as soon as they run and the LiDAR gives valid scans. They do not yet wait for the start button (General Rules 9.10–9.11). The start button on the ESP32 board is not read by the firmware yet.
- **Starting without a laptop.** During testing, the programs are started over SSH and stopped with `Ctrl+C`. For competition, the robot must start without any wireless connection (rule 11.10).
- **Automatic pillar scan.** The obstacle programs read the pillar colours and order from a JSON file that is currently written by hand. A scan that creates this file from the camera has not been written yet (see [Planned: Scan → JSON → Run](#-planned-scan--json--run-pipeline)).
- **ESP32 command timeout.** The programs assume the ESP32 stops the motor when commands stop arriving, but the current firmware does not do this yet.

---

## 🟢 Open Challenge (`main_controller/open_challenge/`)

A reactive **inner-wall follower**. The robot holds a fixed distance from the inner wall using a proportional controller on the LiDAR side reading, and detects corners from the opening that appears in the front-corner sector.

| Program | Direction | Wall followed | Corner sensor sector |
| --- | --- | --- | --- |
| `open_clockwise.py` | Clockwise | Inner **right** wall | Front-right, −50° to −40° |
| `open_counter_clockwise.py` | Counter-clockwise | Inner **left** wall | Front-left, 40° to 50° |

**How it works**

1. **Wall following:** `steering = KP × (side_distance − 0.35 m)`, clamped to ±29°. Too far from the wall steers toward it, too close steers away.
2. **Corner detection:** once the robot has recently seen the inner wall, a front-corner reading above 0.80 m for 2 consecutive scans confirms an opening and starts a corner turn.
3. **Corner turn:** gentle entry steering, then full steering until the old wall is left behind and the next inner wall is re-acquired for 2 scans.
4. **Safety limits:** the controller stops if the front reading is under 0.20 m, if no valid front reading is available, or if a corner turn lasts more than 2 s (it latches a fault and needs a restart).
5. **Lap counting:** the IMU yaw is zeroed at start. The counter arms once the robot has turned more than 45° away from the start heading, and counts a lap when it returns within 18° of it. After `TARGET_LAPS = 3` laps the robot stops.

Main tuning constants (at the top of each file): `TARGET_RIGHT` / `TARGET_LEFT`, `FRONT_*_OPEN_DISTANCE`, `KP`, `MAX_STEERING_DEG`, `FORWARD_PWM`, `TURN_PWM`, `TARGET_LAPS`.

---

## 🔴🟢 Obstacle Challenge (`main_controller/obstacle_challenge/`)

Both obstacle programs (`obstacle_clockwise.py` and `obstacle_counter_clockwise.py`) are staged, **map-driven** controllers rather than free-form wall followers. The pillar layout is read once from a JSON file in `config/`, so the robot knows the colour and order of every pillar in advance. LiDAR and IMU decide *when* to act; the camera is used to confirm that something seen in front is a pillar and not a wall.

Under rule 9.19, the robot passes a **red** pillar on its **right** and a **green** pillar on its **left**.

### Running it

```bash
cd main_controller/obstacle_challenge
python3 obstacle_counter_clockwise.py ../config/wro_pillar_0_270_180_90.json
```

The programs load the model from the folder they are run in. Copy `traffic_sign_detector.pt` from `../../ai_model/` or change `CAMERA_MODEL_PATH`. See the README in that folder for the exact run commands.

### Pillar map JSON

> Today this file is **written by hand** to match the field layout. Once the scan phase exists, the robot will generate it.

The map lists exactly **two pillars per section** (`top`, `left`, `bottom`, `right`). Positions are image pixels with the origin at the top-left. They are used only to determine **colour and order**, not physical distances.

```json
{
  "image_width": 804,
  "image_height": 815,
  "coordinate_system": "image pixels, origin top-left",
  "pillars": [
    {"x": 526, "y": 130, "color": "red",   "section": "top"},
    {"x": 275, "y": 130, "color": "red",   "section": "top"}
  ]
}
```

The loader checks the schema and rejects invalid colours, out-of-bounds positions, or a section without exactly two pillars. Pillars are then **decoded** into a plan by sorting them in the direction of travel: top right→left, left top→bottom, bottom left→right, right bottom→top. Only the colour sequence per section is kept, e.g. `{"top": ["red", "red"], "left": ["red", "green"], ...}`.

### Run sequence

0. **Pillar map:** load and decode the JSON (hand-written today).
1. **IMU zero:** yaw is zeroed while the robot sits still at its parking start, and that reference is never changed afterwards.
2. **Parking exit:** a timed, open-loop manoeuvre chosen by the colour of the second right-hand pillar (`PARKING_EXIT_ENABLED`).
3. **TOP entry:** a custom first turn onto the top section.
4. **`FourSectionController`:** drives **TOP → LEFT → BOTTOM → RIGHT** for `TARGET_LAPS = 3`. It reuses the TOP and LEFT manoeuvres for the BOTTOM and RIGHT sections by rotating the virtual heading by 0°, 90°, 180° and 270°. The first pillar of the next section decides how the current section ends.
5. **Per-section logic (`TwoCornerController`):** a timed first turn, heading hold using IMU yaw, then a red-pillar or green-pillar manoeuvre triggered by the front LiDAR distance. Many phases use timeouts and heading-error limits that **fail-stop** the robot.
6. **Final parking:** after the last lap, the robot approaches, then uses the rear **VL53L0X** to back into the parking space (`BACK` command).

### Camera (YOLO) fusion

The camera thread runs YOLOv8n and converts each detection's pixel position into a bearing relative to the LiDAR using `CAMERA_FOV_DEG` (70°) and `CAMERA_YAW_OFFSET_DEG` (0°). Only `redbox` and `greenbox` detections with confidence of at least 0.65 (`CAMERA_CONFIDENCE`) are used. The camera **never sends motion commands**. It only stops the controller from treating a pillar as a wall when interpreting the LiDAR. Detections older than `CAMERA_MAX_AGE_S` (0.3 s) are ignored, and all emergency distance checks still use raw LiDAR values.

### Dry run

Set `DRY_RUN = True` near the top of the file to run the full decision logic while only sending `STOP` to the ESP32. The dashboard shows the command that *would* have been sent.

### Known limitations

> Carried over from the first version of this README. Please re-check them against the current code.

- The BOTTOM and RIGHT sections reuse TOP and LEFT behaviour with rotated headings. Their values are **starting points that still need to be tuned**, not a validated trajectory.
- `CAMERA_FOV_DEG` and `CAMERA_YAW_OFFSET_DEG` are **uncalibrated defaults**. Calibrate them with a target at a known position.
- Parking exit is timed and open-loop with no obstacle detection, so it must be run in a clear, supervised area.

---

## 🧭 Planned: Scan → JSON → Run pipeline

> ⚠️ **Not implemented yet.** This is the intended design. The run programs already consume the JSON described above, but nothing in the repository produces that JSON automatically.

The robot does not know where the pillars are until the round starts, so the obstacle run is split into two phases that communicate through a single JSON file.

```text
 ┌───────────────────────────┐     pillar map     ┌───────────────────────────┐
 │ Phase 1: SCAN             │ ── (JSON file) ──► │ Phase 2: RUN              │
 │ robot sits in the parking │                    │ load JSON, decode it into │
 │ lot and looks at the field│                    │ a per-section plan, drive │
 └───────────────────────────┘                    └───────────────────────────┘
```

**Phase 1: Scan (planned)**

1. The robot starts in the parking lot and, **without driving the field**, looks at the pillars with the camera and the YOLOv8n model (`greenbox` / `redbox`).
2. Each detected pillar is assigned to a track **section** (`top`, `left`, `bottom`, `right`), a **colour** (`red` / `green`), and a **position** that defines its order within the section. The LiDAR and IMU can help turn a camera detection into a position (bearing and distance).
3. The result is **stored in a JSON file** (same schema as above), so the run phase starts from a saved, inspectable map.

**Phase 2: Run (decode the JSON)**

1. The run program loads the JSON and validates it (`load_test_plan`).
2. It decodes the raw pillar list into a per-section colour plan.
3. `FourSectionController` and the parking-exit routine use this plan to pick the manoeuvre for every pillar and the parking-exit route.

**To do**

- [ ] Scan program that captures the pillars from the parking lot and writes the JSON.
- [ ] Convert detections into the section / colour / order format, and decide how to handle a pillar that is missed or seen twice.
- [ ] Check the JSON before the run starts (the loader already rejects a section that does not have exactly two pillars).
- [ ] Call the scan phase from the run program, or keep it as a separate program run first (not decided).

---

## 🤖 AI Model (`ai_model/`)

A custom **YOLOv8n** detector with three classes: `greenbox`, `redbox`, `xparking` (the current programs use only the first two). Weights are in `traffic_sign_detector.pt` (640 × 640 input, validation mAP@50 ≈ 0.995). See [`ai_model/README.md`](./ai_model/README.md) for training and usage details.

---

## ⚙️ Setup

**Hardware:** NVIDIA Jetson Orin Nano, Hokuyo UST-30LX LiDAR on Ethernet (set the Jetson to the same `192.168.0.x` subnet), custom ESP32 board on USB, BNO055 on I²C bus 7, USB camera, rear VL53L0X on I²C bus 1.

**Python dependencies:**

```bash
pip install -r main_controller/requirements.txt
```

On the Jetson, install NVIDIA's JetPack build of PyTorch **before** `ultralytics` (see [`ai_model/README.md`](./ai_model/README.md)).

**Run the Open Challenge:**

```bash
python3 main_controller/open_challenge/open_clockwise.py   # or open_counter_clockwise.py
```

Then open `http://<jetson-ip>:5000` to monitor. Press `Ctrl+C` to stop.

**Adjust hardware settings** at the top of each program if your setup differs: `LIDAR_IP`, `ESP32_PORT`, `IMU_BUS`, `CAMERA_INDEX`, `WEB_PORT`.

**Flash the ESP32:** see [`microcontroller/`](microcontroller/) for the pin map and flashing steps.

More setup, run commands and safety notes are in [`main_controller/README.md`](main_controller/README.md).

---

## ⚠️ Safety

- **Test with the wheels lifted** before enabling the motors, and verify steering direction and sensor angles first.
- The programs assume an **ESP32 command watchdog** (the motor stops if commands stop arriving), but the current firmware does not have one yet. Until it does, use an **independent emergency stop** to cover a crashed process or a lost USB connection.
- Corner timings and wall offsets in the code are approximate and field-dependent, so re-tune them on the actual track.

---

## 🗄️ Legacy Code

The National Round software (RealSense depth-camera navigation, ultrasonic sensors, Jetson + ESP32 with a custom PCB) is preserved in [`../other/legacy_national/`](../other/legacy_national/). It must not be used on the rebuilt robot.
