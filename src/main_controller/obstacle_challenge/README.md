# Obstacle Challenge programs

The Obstacle Challenge programs are a staged, **map-driven** controller, not a
free wall follower. The pillar colours and their order are read once from a
JSON pillar map. The LiDAR and the IMU then decide *when* each manoeuvre starts
and ends. The camera confirms that something in front is a pillar and not a
wall.

| Program | Direction | Validation status on rebuilt robot |
| --- | --- | --- |
| [`obstacle_counter_clockwise.py`](obstacle_counter_clockwise.py) | Counter-clockwise (TOP → LEFT → BOTTOM → RIGHT) | Active calibration baseline; final repeatability records remain pending |
| [`obstacle_clockwise.py`](obstacle_clockwise.py) | Clockwise (TOP → RIGHT → BOTTOM → LEFT) | Direction-aware mirrored implementation; final direction-specific regression records remain pending |

**How the clockwise version works:** it sets `CLOCKWISE = True` and mirrors the
world at the sensor and motor boundaries, so the navigation logic itself is
unchanged. It flips:

- the LiDAR angles;
- the sign of the IMU yaw;
- the camera angles;
- the steering in every `DRIVE` and `BACK` command.

The dashboard still shows the true physical left and right.

The clockwise version also has a few separately tuned changes:

- the red and green parking-exit routes are swapped;
- one top-entry trigger distance is lower (0.40 m → 0.35 m);
- after the parking exit it allows a larger heading error (45° instead of 25°)
  and steers back to the start heading more strongly.

## Pillar map (JSON)

The program is given a pillar map file when it starts. The map lists exactly
**two pillars per section** (`top`, `left`, `bottom`, `right`). Positions are
image pixels with the origin at the top-left, and are used only to work out the
**colour and order** of the pillars, not distances. The file format and the
two example maps are described in [`../config/`](../config/).

The loader (`load_test_plan`) rejects:

- an unknown coordinate system;
- invalid colours;
- positions outside the image;
- any section that does not have exactly two pillars.

It then sorts the pillars in the driving direction, leaving only the colour
sequence for each section, for example
`{"top": ["red", "red"], "left": ["red", "green"], ...}`.

> **Current implementation boundary:** the map is currently **written by
> hand** for development. The driving controller can validate, sort and consume
> the JSON, but the automatic camera-pan map generator is not yet present.

## Engineering decision: scan once, then drive from a frozen map

The planned competition workflow separates perception from motion:

```text
Robot stationary in parking lot
        ↓
Camera servo moves to three calibrated pan positions
        ↓
YOLO detects red and green pillars in all three views
        ↓
Repeated observations are merged and assigned to track sections/order
        ↓
JSON map is validated and saved once
        ↓
Driving controller loads the frozen map and executes the planned route
```

This architecture was selected after real testing showed that continuous
camera detection was sensitive to chassis vibration, changing robot position
and occasional camera-cable disconnections. A stationary scan provides a more
stable view, while the driving loop can use the faster and more reliable LiDAR
and IMU for manoeuvre timing. The trade-off is that the pre-scan must observe
and classify the complete layout correctly; therefore the generated JSON must
pass the same strict checks already implemented in `load_test_plan`.

The future generator will write the existing schema rather than changing the
navigation interface. This lets the team test the perception stage and the
driving stage independently. The three physical servo angles and detection
merging rules will be documented after calibration instead of being invented.

## Run sequence

0. **Pillar map:** load and check the JSON file.
1. **IMU zero:** the yaw is set to zero while the robot is still at its parking
   start, and this reference is kept for the whole run.
2. **Parking exit:** a timed, open-loop sequence of `DRIVE` and `BACK` commands.
   The route depends on the colour of the second pillar in the right-hand
   section (`PARKING_EXIT_ENABLED`).
3. **Top entry:** a custom first turn onto the top section.
4. **Four-section controller (`FourSectionController`):** drives the four
   sections for `TARGET_LAPS = 3` laps. The bottom section reuses the top
   section's manoeuvres, and the fourth section reuses the second section's
   manoeuvres, using virtual heading rotations of 0°, 90°, 180° and 270°.
5. **Per-section logic (`TwoCornerController`):**
   - a timed first turn;
   - holding the heading with the IMU yaw;
   - a red-pillar or green-pillar manoeuvre, started when the front LiDAR
     distance falls below a trigger value.

   Many phases have time limits and heading-error limits that stop the robot if
   they are exceeded.
6. **Final parking:** after the last lap, the robot approaches the parking lot,
   then uses the rear **VL53L0X** to back into the parking space. It switches
   steering at 360 mm and stops reversing at 60 mm (`FINAL_REVERSE_*`).

## Camera (YOLO) fusion

The camera thread runs the YOLOv8n model ([`traffic_sign_detector.pt`](../../ai_model/)). It
converts each detection's position in the image into a bearing relative to the
LiDAR, using `CAMERA_FOV_DEG` and `CAMERA_YAW_OFFSET_DEG`.

The camera **never sends motion commands**. It only stops the controller from
treating a pillar as a wall when it reads the LiDAR. All emergency distance
checks still use the raw LiDAR values. Detections older than `CAMERA_MAX_AGE_S`
(0.3 s) are ignored.

This live camera worker is separate from the planned stationary three-angle
mapping stage. It does not move the camera servo and does not write the JSON
map. The current code also filters detections to red and green pillars;
`xparking` is not used by these programs.

## Dry run

Set `DRY_RUN = True` near the top of the file to run the full decision logic
while sending only `STOP` to the ESP32. The parking exit is skipped, and the
dashboard shows the command that *would* have been sent.

## Running

```bash
cd src/main_controller/obstacle_challenge
ln -s ../../ai_model/traffic_sign_detector.pt traffic_sign_detector.pt     # the model is loaded from the working folder
python3 obstacle_counter_clockwise.py ../config/wro_pillar_0_270_180_90.json
python3 obstacle_clockwise.py ../config/pillar_clockwise.json
```

Setup and safety notes are in [`../README.md`](../README.md).

## Known limitations

- **Automatic map generation is unfinished:** the driving side of the JSON
  interface exists, but camera-servo control, three-view fusion and JSON
  generation have not been added.
- **No start-button wait:** the program starts the parking exit a few seconds
  after it starts (after opening the serial port and zeroing the IMU). It does
  not yet wait for the start button.
- **Copied manoeuvres:** the bottom and fourth sections reuse the first two
  sections' manoeuvres with rotated headings. Their values are starting points
  that still need tuning, not a checked path.
- **Camera not calibrated:** `CAMERA_FOV_DEG` (70°) and `CAMERA_YAW_OFFSET_DEG`
  (0°) are default values, not calibrated ones. Calibrate them with a target at a
  known position.
- **Parking exit is unsupervised:** it is timed and open-loop, with no obstacle
  detection, so it must be run in a clear, supervised area.
- **Final parking:** implemented for both directions. Counter-clockwise parking
  entry has one minor refinement in progress, and final repeatability records
  remain pending.
- **Clockwise validation:** the clockwise controller mirrors the same
  direction-aware architecture as the counter-clockwise baseline. Final
  direction-specific regression records remain pending; mirroring reduces
  implementation time but does not replace physical validation.
- **Surprise Rule:** behaviour has not been implemented yet.

## Previous version

The National programs, which used the RealSense camera and ultrasonic sensors,
are archived in
[`other/legacy_national/src/obs_challenge/`](../../../other/legacy_national/src/obs_challenge/).
