# International testing and results

This directory is the evidence record for the rebuilt International robot.
It separates a demonstrated behavior from a repeatable measured result: a
video can show that an idea worked once, while a regression log records the
robot configuration, field layout, procedure, outcome and any failure.

## Contents

| File | Purpose |
| --- | --- |
| [`procedures.md`](procedures.md) | Repeatable mechanical, perception, navigation, parking and reliability tests |
| [`video_evidence_register.md`](video_evidence_register.md) | What the existing local videos demonstrate and what they do not prove |

Create one dated log for every test that produces a result. Recommended
filename:

```text
YYYY-MM-DD_<test-id>_<direction>_<short-description>.md
```

Example:

```text
2026-11-25_NAV-OPEN-01_cw_full-run.md
```

Store supporting photos, exported dashboard data and short clips in a folder
with the same filename stem. Long presentation videos remain in
[`../../video/`](../../video/).

## Current evidence

| Area | Evidence available now |
| --- | --- |
| Final dimensions | 298 mm long × 159 mm wide × 223 mm high, measured on the complete robot |
| Final mass | 1.28 kg with sensors and batteries installed |
| Mechanical iteration | CAD history and broken steering-pin evidence in [`../../models/`](../../models/) |
| Open Challenge | Team-reported successful operation in both directions; the linked clockwise demonstration shows three laps and an autonomous stop |
| Obstacle Challenge | Counter-clockwise is the calibration baseline; its linked demonstration shows parking exit, full-lap operation and parking entry |
| Clockwise Obstacle implementation | Direction-aware map ordering and mirrored sensor/steering structure |
| Parking | Sensor-guided parking logic for both directions |

The two YouTube demonstrations use footage recorded before the November 21
Steering Knuckles V2 revision. They are valuable historical demonstrations,
but they are not labeled as final-configuration regression trials. See
[`video_evidence_register.md`](video_evidence_register.md).

## Configuration record required for every run

Every result must identify:

- date and local time;
- person conducting the test;
- challenge and direction;
- Git commit or exact uncommitted source-file copy;
- Python controller, JSON map and firmware version;
- mechanical configuration, including steering-knuckle revision;
- installed sensors and battery configuration;
- battery voltage before and after the test, when available;
- track layout, pillar arrangement and starting position;
- important calibrated values changed for that run;
- result, failure point and next engineering decision; and
- links to raw video, photos, logs or dashboard exports.

Without this configuration record, an observation may be kept as a development
note but must not be counted in the final success rate.

## Result vocabulary

Use these terms consistently:

- **Pass:** every acceptance condition in the named procedure was met.
- **Conditional pass:** the primary behavior worked, but a recorded secondary
  condition still needs correction.
- **Fail:** at least one acceptance condition was not met.
- **Aborted:** the test was stopped before a valid result, for example because
  of unsafe behavior, a loose cable or an incorrect setup.
- **Not recorded:** the team has experience with the behavior but no complete
  formal test record is available.

Do not remove failed trials. A failure followed by a documented change and a
successful retest is valuable engineering evidence.

## Final acceptance target

The repository's final target is three consecutive successful trials in each
direction of each challenge on the final mechanical and electrical
configuration:

- Open Challenge clockwise: 3/3;
- Open Challenge counter-clockwise: 3/3;
- Obstacle Challenge clockwise, including parking: 3/3; and
- Obstacle Challenge counter-clockwise, including parking: 3/3.

A full run passes only when it completes the required route, avoids contact,
stops autonomously, uses no operator input after the permitted Start action,
and has no sensor, power or communication failure.
