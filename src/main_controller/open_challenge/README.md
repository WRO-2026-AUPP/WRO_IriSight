# Open Challenge programs

The Open Challenge programs follow the **inner wall** using the LiDAR. They
detect each corner from the gap that opens up in the front-corner sector, and
count laps with the BNO055 heading.

| Program | Direction | Wall followed | Corner-detection sector |
| --- | --- | --- | --- |
| [`open_clockwise.py`](open_clockwise.py) | Clockwise | Inner **right** wall | Front-right, −50° to −40° |
| [`open_counter_clockwise.py`](open_counter_clockwise.py) | Counter-clockwise | Inner **left** wall | Front-left, 40° to 50° |

Both programs use the same control architecture with direction-specific code
and tuning. The team reports that both directions have been tested on the
rebuilt robot. Formal trial counts, field layouts and timing logs have not yet
been recorded.

## How it works

1. **Wall following.** A proportional controller holds the robot 0.35 m from the
   inner wall (`TARGET_RIGHT` / `TARGET_LEFT`, measured from the LiDAR, not from
   the side of the robot). The steering is `degrees(KP × distance error)`, with
   `KP = 1.0` rad/m (about 57° of steering per metre of error). It is limited to
   ±29° (`MAX_STEERING_DEG`). Too far from the wall steers toward it; too close
   steers away.
2. **Corner detection.** The inner wall must have been seen in the last 1.5 s.
   A corner is then confirmed when the front-corner reading is above 0.80 m for
   2 scans in a row (`FRONT_*_OPEN_DISTANCE`, `GAP_CONFIRM_SCANS`).
3. **Corner turn.** The robot first steers gently (`CORNER_ENTRY_STEERING`, 10°),
   then turns at full steering. The turn ends once the old wall is behind and
   the next inner wall has been seen for 2 scans (`REACQUIRE_SCANS`).
4. **Safety stops.** The robot stops if:
   - the front reading is below 0.20 m (`FRONT_STOP_DISTANCE`);
   - there is no valid front reading;
   - the LiDAR data is older than 0.5 s.

   A corner turn longer than 2 s (`MAX_TURN_TIME`) is also a fault: the robot
   stays stopped until the program is restarted.
5. **Lap counting.** The IMU heading is set to zero at the start. The counter
   arms once the robot has turned more than 45° away from the start heading
   (`REARM_ANGLE_DEG`). It counts a lap when the heading comes back within 18° of
   the start (`START_ZONE_DEG`). After `TARGET_LAPS = 3` laps the robot sends
   `STOP`.

Speeds: `FORWARD_PWM = 255` on straights and `TURN_PWM = 240` in corners.

## Running

```bash
python3 open_clockwise.py          # or open_counter_clockwise.py
```

Watch the run at `http://<jetson-ip>:5000` during testing. `Ctrl+C` sends
`STOP`. Setup and safety notes are in [`../README.md`](../README.md).

## Known limitations

- The program starts driving as soon as the LiDAR gives valid scans. It does not
  yet wait for the start button.
- Corner timings and the wall distance are tuned by hand on the team's field, and
  are not guaranteed for every wall layout.
- Successful test experience has been reported for both directions, but the
  repository still needs repeatable trial counts and raw results.

## Previous version

The National programs, which used the RealSense camera, are archived in
[`other/legacy_national/src/open_challenge/`](../../../other/legacy_national/src/open_challenge/).
