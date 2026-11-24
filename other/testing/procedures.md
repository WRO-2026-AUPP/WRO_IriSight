# Repeatable test procedures

These procedures cover final vehicle behavior rather than AI-training metrics,
which are documented separately in `src/ai_model/`. Every run is recorded in
its own dated log with the configuration listed in the
[testing README](README.md#configuration-record-required-for-every-run).

## Safety and preparation

Before every powered test:

1. Inspect the batteries for swelling or damage; do not use a damaged battery.
2. Check the wheel retainers, M2.5 steering-pivot screws, drivetrain bushes,
   motor fasteners and sensor mounts.
3. Confirm the robot is running the intended controller, JSON map and firmware.
4. Put the robot on a stand and check motor direction, steering direction,
   camera-pan movement and the STOP command.
5. Place the robot on the field only after the raised-wheel check passes.
6. Record the robot configuration and battery voltage before the run.

Stop immediately if a cable becomes loose, a printed part cracks, steering
binds, a sensor becomes stale or the robot moves outside the safe test area.

## MECH-01 — Dimensions and mass

**Purpose:** demonstrate compliance and preserve the exact measured
configuration.

**Equipment:** rigid ruler or caliper, flat surface and scale.

**Procedure:**

1. Install all competition batteries, sensors, guards, wheels and cables.
2. Center the steering and place all moving mechanisms in their starting state.
3. Measure the maximum length, width and height, including protruding cables or
   connectors.
4. Weigh the same complete configuration.
5. Photograph every measurement and the scale display.

**Known measurement:** 298 × 159 × 223 mm and 1.28 kg.

**Acceptance:** no dimension exceeds 300 × 200 × 300 mm. The current length
has only 2 mm of reported margin, so repeat it after any front or rear change.

## MECH-02 — Steering retention and repeatability

**Purpose:** confirm that Steering Knuckles V2 prevent the previous broken-pin
and vertical-drift failures.

**Procedure:**

1. Mark both knuckle/pivot positions so migration is visible.
2. With the wheels lifted, command ten full left-center-right-center cycles.
3. On the field, complete repeated cornering in both directions.
4. Recheck the M2.5 screws, vertical position, free movement and visible cracks.
5. Record any steering-center change observed by the controller or wheels.

**Acceptance:** no cracking, loosening, vertical migration, binding or visible
change in steering center.

## MECH-03 — Rear drivetrain and axle retention

**Purpose:** confirm that the integrated motor-differential mount and added bush
retain both rear axles at running speed.

**Procedure:**

1. Rotate each wheel by hand and confirm differential action.
2. Run the drivetrain with the wheels lifted at low, medium and intended run
   PWM.
3. Perform repeated starts, stops and turns on the field.
4. Inspect the coupler, gear mesh, bushes, axle positions and printed mount.

**Acceptance:** continuous drive without axle walk-out, gear skipping,
coupler slip, abnormal vibration or contact between rotating and printed parts.

## SENS-01 — LiDAR distance and sector check

**Purpose:** verify the distance source used for manoeuvre timing.

**Procedure:**

1. Place a flat target at several known front and side distances.
2. Record the physical distance and dashboard median for each relevant sector.
3. Repeat each position three times.
4. Move the target near sector boundaries to confirm left/right angle mapping.

**Record:** physical distance, reported distance, absolute error, stale scans
and missing values.

**Acceptance:** consistent sector orientation and an error/tolerance selected
from the controller's real manoeuvre margins. Do not invent a tolerance before
recording the sensor data.

## SENS-02 — IMU heading check

**Purpose:** verify lap counting and heading-controlled manoeuvres.

**Procedure:**

1. Zero the IMU at the marked starting orientation.
2. Rotate the robot physically through 90°, 180°, 270° and back to 0°.
3. Record the reported heading at every mark.
4. Repeat the full sequence three times and record drift at the final 0°.

**Acceptance:** repeatable heading readings within the tolerances used by the
controller and no disconnection during the sequence.

## SENS-03 — Rear ToF parking-distance check

**Purpose:** verify the VL53L0X thresholds used during reverse parking.

**Procedure:**

1. Position a flat parking wall at several known rear distances, including the
   controller's steering-switch and stop regions.
2. Record physical and reported distances three times per position.
3. Repeat with the motor and steering operating to expose electrical noise.

**Acceptance:** stable measurements at the parking thresholds with no stale or
missing reading that could permit unsafe reversing.

## MAP-01 — Stationary three-angle pillar map

**Purpose:** validate the complete map that the Obstacle controller freezes
before driving. This procedure applies when the automatic scanner is integrated.

**Procedure:**

1. Photograph the real eight-pillar layout from above or from four field sides.
2. Start the robot in the legal parking position.
3. Record the three camera views and their camera-servo angles.
4. Save the generated JSON and any HSV/YOLO confidence output.
5. Compare all eight generated section/order/color assignments with the ground
   truth layout.
6. Repeat under the expected venue lighting and with at least three layouts.

**Metrics:** correctly classified pillars / 8, complete-map success rate,
rescans, scan duration and disagreements between HSV and YOLO evidence.

**Acceptance:** all eight assignments correct, schema validation passes and an
incomplete or conflicting map causes a rescan or safe stop rather than a
guessed color.

## NAV-OPEN-01 — Complete Open Challenge run

Run this procedure separately for clockwise and counter-clockwise.

**Procedure:**

1. Record field width/layout, controller file and calibration values.
2. Start from the legal starting position and use only the permitted Start
   action.
3. Record the entire vehicle and field continuously.
4. Record lap count, completion time, contacts, manual interventions, sensor
   faults and final stop position.
5. Repeat until three consecutive valid trials have been recorded.

**Pass:** three laps completed in the required direction, no wall contact or
manual correction, correct lap count and autonomous stop.

## NAV-OBS-01 — Complete Obstacle Challenge and parking

Run this procedure separately for clockwise and counter-clockwise and record
the exact pillar layout.

**Procedure:**

1. Complete MAP-01 or identify the autonomous map evidence used for the run.
2. Start from the legal parking position and record the entire field.
3. For every pillar, record required passing side, actual passing side and any
   contact.
4. Record all completed sections/laps, sensor or cable faults and manual input.
5. Measure the final parked position and note whether any part lies outside the
   required parking area.
6. Repeat with different layouts and obtain three consecutive final trials for
   each direction.

**Pass:** correct side for every pillar, required route and laps completed, no
contact or intervention, successful final parking and autonomous stop.

## PARK-01 — Parking-only refinement

**Purpose:** tune parking without counting a partial test as a full Obstacle
run.

**Procedure:** record the direction, entry pose, front and rear distances,
steering-switch point, reverse-stop point, elapsed time and final position.
Measure the final clearance to the parking boundaries. Keep failed attempts and
record the parameter changed before each retest.

**Pass:** the complete robot finishes inside the required parking area without
contact and stops autonomously. Final numerical clearance targets should be
recorded from the actual rule/field setup rather than guessed here.

## REL-01 — Power, cable and endurance run

**Purpose:** expose faults that a short navigation demonstration may miss.

**Procedure:**

1. Record both battery voltages before the test.
2. Run repeated challenge-length operation with all competition sensors active.
3. Record sensor disconnects, ESP32 communication faults, Jetson resets,
   converter temperature observations and mechanical loosening.
4. Record battery voltage immediately after the test and the total runtime.

**Pass:** no reset, stale sensor, communication loss, cable disconnection,
unsafe temperature, steering migration or drivetrain failure during the chosen
endurance interval.

## Failure and retest rule

When a test fails, preserve the original log and evidence. Create a new log for
the retest and link the two records through:

```text
failure → suspected cause → engineering change → retest → decision
```

This chain is more useful to judges than presenting only the final successful
attempt.
