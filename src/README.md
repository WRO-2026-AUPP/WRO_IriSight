# 💻 Source Code

This directory contains the control software for the IriSight vehicle for the **Open Challenge** and the **Obstacle Challenge**. The Jetson runs all sensing and decision-making in Python, and sends simple text commands over USB serial to an **ESP32**, which drives the motor and steering servo.

> **Status:** This directory is under active development for the International Round. The previous National Round software is archived in [`other/legacy_national/`](../other/legacy_national/).
>
> **Not implemented yet:** the automatic **pillar scan from the parking lot** (see [Planned: Scan → JSON → Run](#-planned-scan--json--run-pipeline)). Today the run script reads a pillar JSON that is written by hand.

---

## 📁 Directory Structure

```
src/
├── ai_model/                      # YOLOv8n pillar detector
│   ├── best1.pt                   #   trained weights (greenbox / redbox / xparking)
│   └── README.md                  #   training details and usage
├── open_challenge/                # Open Challenge: LiDAR wall following
│   ├── open_clockwise.py          #   clockwise (follows inner RIGHT wall)
│   └── open_counter_clockwise.py  #   counter-clockwise (follows inner LEFT wall)
├── obstacle_avoidance/            # Obstacle Challenge
│   ├── obstacle_counter_clockwise.py   # full counter-clockwise run
│   ├── obstacle_clockwise.py           # full clockwise run
│   └── wro_pillar_0_270_180_90.json    # example pillar map (hand-written today; the scan will produce this file)
├── main_controller/               # reserved, currently empty
└── microcontroller/               # reserved, currently empty (ESP32 firmware not yet added)
```

---

## 🧠 System Overview

```
 Hokuyo LiDAR (Ethernet) ──┐
 BNO055 IMU (I²C bus 7) ───┤
 USB camera + YOLOv8n ─────┼──►  Jetson (Python)  ──  serial 115200  ──►  ESP32  ──►  motor + steering servo
 VL53L0X rear ToF (I²C 1) ─┘          │
                                      └── Flask web dashboard (port 5000)
```

| Sensor / Device | Role | Used in |
|---|---|---|
| **Hokuyo LiDAR** (`192.168.0.10:10940`, via `hokuyolx`) | Front, side and front-corner distances, wall and corner detection | Both challenges |
| **BNO055 IMU** (I²C bus 7, addr `0x28`) | Yaw heading, turn completion, lap counting | Both challenges |
| **USB camera + YOLOv8n** (`best1.pt`) | Classifies red/green pillars | Obstacle Challenge |
| **VL53L0X** (I²C bus 1, addr `0x29`, facing backward) | Rear distance during final parking | Obstacle Challenge |
| **ESP32** (`/dev/ttyUSB0`, 115200 baud) | Executes drive commands | Both challenges |

### Software design (shared by every script)

- **Three threads:** a LiDAR thread, a control thread, and a Flask web server, all sharing state under a lock.
- **Fail-safe behaviour:** the robot sends `STOP` if LiDAR data is stale (`SCAN_TIMEOUT = 0.5 s`), if a front or front-side reading is missing, or when the program exits. A watchdog on the ESP32 is also required (see Safety).
- **Median sampling** over angular sectors rather than single rays, to reject noise. Angles use the convention **+90° = left, 0° = front, −90° = right**.
- **Live dashboard:** open `http://<jetson-ip>:5000` to see the LiDAR scan, distances, the command being sent, steering, PWM, yaw and lap count. The obstacle script also streams the annotated camera view at `/camera`. A JSON feed is at `/scan`.

### ESP32 serial protocol

Commands are ASCII lines terminated by `\n`:

| Command | Meaning |
|---|---|
| `DRIVE <steering> <pwm>` | Steering angle in degrees (**positive = right, negative = left**) and motor PWM `0–255` |
| `STOP` | Stop the motor and centre the steering |

The ESP32 firmware is not in this repository yet.

---

## 🟢 Open Challenge (`open_challenge/`)

A reactive **inner-wall follower**. The robot holds a fixed distance from the inner wall using a proportional controller on the LiDAR side reading, and detects corners from the opening that appears in the front-corner sector.

| Script | Direction | Wall followed | Corner sensor sector |
|---|---|---|---|
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

## 🧭 Planned: Scan → JSON → Run pipeline

> ⚠️ **Not implemented yet.** This is the intended design for the Obstacle Challenge. The run script already consumes the JSON described below, but nothing in the repository produces that JSON automatically.

The robot does not know where the pillars are until the round starts, so the obstacle run is split into two phases that communicate through a single JSON file.

```
 ┌───────────────────────────┐     pillar map     ┌───────────────────────────┐
 │ Phase 1: SCAN             │  ──  (JSON file) ──►│ Phase 2: RUN              │
 │ robot sits in the parking │                     │ load JSON, decode it into │
 │ lot and looks at the field│                     │ a per-section plan, drive │
 └───────────────────────────┘                     └───────────────────────────┘
```

**Phase 1: Scan (planned)**

1. The robot starts in the parking lot and, **without driving the field**, looks at the pillars with the camera and the YOLOv8n model (`greenbox` / `redbox`).
2. Each detected pillar is assigned to a track **section** (`top`, `left`, `bottom`, `right`), a **colour** (`red` / `green`), and a **position** that defines its order within the section. The LiDAR and IMU can help turn a camera detection into a position (bearing and distance).
3. The result is **stored in a JSON file** (same schema as the example in the next section), so the run phase can start from a saved, inspectable map instead of detecting everything on the fly.

**Phase 2: Run (decode the JSON)**

1. The run script loads the JSON and validates it (`load_test_plan`).
2. It **decodes** the raw pillar list into a plan: pillars are grouped by section and sorted into driving order, leaving just the colour sequence for each section, e.g. `{"top": ["red", "red"], "left": ["red", "green"], ...}`.
3. `FourSectionController` and the parking-exit routine then use this plan to pick the manoeuvre for every pillar (the first pillar of the next section decides how the current section ends) and the parking-exit route.

**What is still to do**

- [ ] Scan script that captures the pillars from the parking lot and writes the JSON.
- [ ] Convert detections into the section / colour / order format, and decide how to handle a pillar that is missed or seen twice.
- [ ] Check the JSON before the run starts (the loader already rejects a section that does not have exactly two pillars).
- [ ] Call the scan phase from the run script, or keep it as a separate script run first (not decided).

---

## 🔴🟢 Obstacle Challenge (`obstacle_avoidance/`)

`obstacle_counter_clockwise.py` is a staged, **map-driven** controller rather than a free-form wall follower. The pillar layout is read once from a JSON file, so the robot knows the colour and order of every pillar in advance. In the final design this JSON comes from the [parking-lot scan](#-planned-scan--json--run-pipeline); for now it is written by hand. LiDAR and IMU decide *when* to act; the camera is used to confirm that something seen in front is a pillar and not a wall.

### Running it

```bash
cd src/obstacle_avoidance
python3 obstacle_counter_clockwise.py wro_pillar_0_270_180_90.json
```

The script expects `best1.pt` in the working directory (copy it from `../ai_model/` or change `CAMERA_MODEL_PATH`).

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

The loader checks the schema and rejects invalid colours, out-of-bounds positions, or a section without exactly two pillars. Pillars are then **decoded** into a plan by sorting them in the direction of travel: top right→left, left top→bottom, bottom left→right, right bottom→top. Only the colour sequence per section is kept for the run.

### Run sequence

0. **Pillar map:** load and decode the JSON (hand-written today; produced by the parking-lot scan once implemented).
1. **IMU zero:** yaw is zeroed while the robot sits still at its parking start, and that reference is never changed afterwards.
2. **Parking exit:** a timed, open-loop manoeuvre chosen by the colour of the second right-hand pillar (`PARKING_EXIT_ENABLED`).
3. **TOP entry:** a custom first turn onto the top section.
4. **`FourSectionController`:** drives **TOP → LEFT → BOTTOM → RIGHT** for `TARGET_LAPS = 3`. It reuses the TOP and LEFT manoeuvres for the BOTTOM and RIGHT sections by rotating the virtual heading by 0°, 90°, 180° and 270°.
5. **Per-section logic (`TwoCornerController`):** a timed first turn, heading hold using IMU yaw, then a red-pillar or green-pillar manoeuvre triggered by the front LiDAR distance. Many phases use timeouts and heading-error limits that **fail-stop** the robot.
6. **Final parking:** after the last lap, the robot approaches, then uses the rear **VL53L0X** to back into the parking space.

### Camera (YOLO) fusion

The camera thread runs YOLOv8n and converts each detection's pixel position into a bearing relative to the LiDAR using `CAMERA_FOV_DEG` and `CAMERA_YAW_OFFSET_DEG`. It **never sends motion commands**. It only stops the controller from treating a pillar as a wall when interpreting the LiDAR, and all emergency distance checks still use raw LiDAR values. Detections older than `CAMERA_MAX_AGE_S` are ignored.

### Dry run

Set `DRY_RUN = True` near the top of the file to run the full decision logic while only sending `STOP` to the ESP32. The dashboard shows the command that *would* have been sent.

### Known limitations

- **The parking-lot scan is not implemented.** The pillar JSON must currently be created manually before every run.
- `obstacle_clockwise.py` is an **empty file**. Only the counter-clockwise run is implemented.
- The BOTTOM and RIGHT sections reuse TOP and LEFT behaviour with rotated headings. Their values are **starting points that still need to be tuned**, not a validated trajectory.
- Camera `CAMERA_FOV_DEG` (70°) and `CAMERA_YAW_OFFSET_DEG` (0°) are **uncalibrated defaults**. Calibrate them with a target at a known position.
- Parking exit is timed and open-loop with no obstacle detection, so it must be run in a clear, supervised area.

---

## 🤖 AI Model (`ai_model/`)

A custom **YOLOv8n** detector with three classes: `greenbox`, `redbox`, `xparking`. Weights are in `best1.pt` (640×640 input, validation mAP@50 ≈ 0.995). See [`ai_model/README.md`](./ai_model/README.md) for training and usage details.

---

## ⚙️ Setup

**Hardware:** NVIDIA Jetson, Hokuyo LiDAR on Ethernet (set the Jetson to the same `192.168.0.x` subnet), ESP32 on USB, BNO055 on I²C bus 7, USB camera, rear VL53L0X on I²C bus 1.

**Python dependencies** (no `requirements.txt` in the repo yet; these are collected from the imports):

```bash
pip install numpy pyserial flask smbus2 hokuyolx
# Obstacle Challenge only:
pip install opencv-python ultralytics adafruit-extended-bus adafruit-circuitpython-vl53l0x
```

On Jetson, install NVIDIA's JetPack build of PyTorch **before** `ultralytics` (see `ai_model/README.md`).

**Run the Open Challenge:**

```bash
python3 open_challenge/open_clockwise.py            # or open_counter_clockwise.py
```

Then open `http://<jetson-ip>:5000` to monitor. Press `Ctrl+C` to stop.

**Adjust hardware settings** at the top of each script if your setup differs: `LIDAR_IP`, `ESP32_PORT`, `IMU_BUS`, `CAMERA_INDEX`, `WEB_PORT`.

---

## ⚠️ Safety

- **Test with the wheels lifted** before enabling the motors, and verify steering direction and sensor angles first.
- The scripts assume an **ESP32 command watchdog** (the motor stops if commands stop arriving) and an **independent emergency stop**, to cover a crashed process or a lost USB connection.
- Corner timings and wall offsets in the code are approximate and field-dependent, so re-tune them on the actual track.

---

## 🗄️ Legacy Code

The National Round software (RealSense depth-camera navigation, ultrasonic sensors, Jetson + ESP32 with a custom PCB) is preserved in [`other/legacy_national/src/`](../other/legacy_national/src/).
