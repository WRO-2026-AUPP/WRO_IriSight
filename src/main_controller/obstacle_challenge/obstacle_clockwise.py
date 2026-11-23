#!/usr/bin/env python3

"""Map-driven Obstacle Challenge controller for clockwise driving.

Current controller
------------------
This file loads a validated JSON pillar map, mirrors the counter-clockwise
sensor/control frame for clockwise travel, exits the parking area, completes
three laps and attempts final reverse parking with the rear VL53L0X. LiDAR
decides when manoeuvres begin, the BNO055 controls heading, and the camera's
red/green detections help distinguish pillars from walls.

Planned perception-to-map stage -- NOT implemented in this file
---------------------------------------------------------------
Before the driving controller starts, the stationary robot is intended to pan
its camera through three calibrated servo positions in the parking lot. YOLO
detections from those views will be merged into the same JSON schema consumed
by ``load_test_plan``. The map is then frozen for the run, decoupling perception
from navigation. This decision responds to observed camera vibration, changing
robot pose and intermittent camera-cable disconnections during real-time use.

Validation status (team report, 2026-11-23)
-------------------------------------------
This clockwise mirror is implemented as a development draft but has not yet
been tested on the physical robot. Mirroring the tested counter-clockwise
concept reduces development time, but it does not prove equivalent behaviour;
mechanical asymmetry and sensor placement still require clockwise testing.

Safety and current limitations
------------------------------
The program presently accepts a JSON file supplied on the command line and
starts without waiting for the competition Start button. The camera-pan map
generator, autonomous launch and ESP32 command watchdog are not implemented.
Final parking is still under development. Test with the wheels lifted before
allowing movement, and use DRY_RUN during command-only validation.
"""


import math
import cv2
import json
import sys
from pathlib import Path

import threading

import time


import numpy as np

import serial

from flask import Flask, Response, jsonify, render_template_string

from hokuyolx import HokuyoLX
from smbus2 import SMBus
from adafruit_extended_bus import ExtendedI2C
import adafruit_vl53l0x


# =========================================================

# CONFIGURATION

# =========================================================


LIDAR_IP = "192.168.0.10"

LIDAR_PORT = 10940


ESP32_PORT = "/dev/ttyUSB0"

ESP32_BAUD = 115200


WEB_PORT = 5000

# True  = drive CLOCKWISE (mirror-image world: TOP -> RIGHT -> BOTTOM -> LEFT)
# False = original COUNTERCLOCKWISE (TOP -> LEFT -> BOTTOM -> RIGHT)
# Implemented by mirroring LiDAR, IMU yaw, camera angles and steering at the
# boundaries; the navigation logic itself is unchanged.
CLOCKWISE = True

# OPTIONAL YOLO camera fusion. Existing navigation parameters are unchanged.
# Set camera index to the device that works on this robot.
CAMERA_INDEX = 0
CAMERA_MODEL_PATH = "traffic_sign_detector.pt"
CAMERA_CONFIDENCE = 0.65
CAMERA_FRAME_WIDTH = 640
CAMERA_FOV_DEG = 70.0        # CALIBRATE using a known target; not a measured specification
CAMERA_YAW_OFFSET_DEG = 0.0 # CALIBRATE camera optical axis relative to LiDAR 0deg
CAMERA_MAX_AGE_S = 0.30
CAMERA_PILLAR_EXTRA_MARGIN_DEG = 2.0
# Pillar classification only vetoes wall STEERING/OPENING interpretation at matching angles.
# Raw distances, all emergency checks and forward turn triggers remain unchanged.


# BNO055 IMU
IMU_BUS = 7
IMU_ADDRESS = 0x28
OPR_MODE = 0x3D
CONFIG_MODE = 0x00
NDOF_MODE = 0x0C
EUL_HEADING_LSB = 0x1A
EUL_HEADING_MSB = 0x1B


# Preserve the angle mapping from your working LiDAR code:

# +90 = left, 0 = front, -90 = right

RAW_ANGLE_MIN = -135.0

RAW_ANGLE_MAX = 135.0


VIEW_ANGLE_MIN = -90.0

VIEW_ANGLE_MAX = 90.0


MIN_DISTANCE_M = 0.05

MAX_DISTANCE_M = 3.0


# Clearance and heading settings (no wall following)
FRONT_STOP_DISTANCE = 0.03
# If the left 80-90 degree sector is missing, the 40-50 degree front-left
# reading may be used ONLY as a provisional first-turn check.
# This is NOT proof of full left-side clearance.
TURN1_FRONT_LEFT_FALLBACK_MIN = 0.05
LEFT_MIN_CLEARANCE = 0.05
RIGHT_MIN_CLEARANCE = 0.05
CONTROL_MAX_DISTANCE_M = 30.0

# Side-wall avoidance while moving STRAIGHT (not continuous wall following).
# LiDAR readings are distances from the SENSOR, not robot body clearance.
SIDE_AVOID_ENTER = 0.16       # begin steering before approaching the 0.12m target
SIDE_AVOID_RELEASE = 0.10    # hysteresis so correction does not chatter
SIDE_AVOID_STEER = 10       # left too close => +10 right; right => -10 left
SIDE_AVOID_PWM = 90         # slower during corrections, adjust after raised-wheel test
# If both sides are simultaneously near, no known safe side to steer toward.


# Desired LiDAR-to-object side distance, not body-to-wall clearance.
SIDE_TARGET_M = 0.12
# Steering away from a wall takes space; do not attempt forward recovery
# once a sector is already inside the emergency threshold.
SIDE_RECOVERY_MAX_SECONDS = 0.8
SIDE_OPPOSITE_MIN_M = 0.25

MAX_STEERING_DEG = 35  # Default limit for all other maneuvers
LEFT_GREEN_FIRST_TURN_STEER_DEG = 38  # Special LEFT section first GREEN turn (degrees)
# Keep dry-run enabled until the steering direction, JSON and clearance are verified.
DRY_RUN = False  # Command-only validation of changed post-corner transitions
TEST_PWM = 160  # Default driving PWM for normal movement
TURN_PWM = 120  # Default TURN_1 corner PWM when no route-specific turn PWM is set
# Only TOP RED-RED -> LEFT RED-RED, physical yaw 270 -> 180.
RRRR_LEFT_CORNER_PWM = 140       # Independent motor PWM for this corner; tune separately
RRRR_LEFT_CORNER_STEER_DEG = 38  # Requested servo steering magnitude (LEFT is negative)
RRRR_LEFT_CORNER_TIMEOUT_S = 3.0 # Fail-stop maximum, IMU still ends the turn
HEADING_TOLERANCE = 12.0
FIRST_RED_TURN_SECONDS = 1.1
FIRST_GREEN_TURN_SECONDS = 1.2
FIRST_HEADING_MAX_ERROR = 35.0  # hard bound after initial turn, not completion tolerance
FIRST_TURN_TARGET = 270.0
FIRST_TURN_REACHED_TOLERANCE = 15.0
FIRST_TURN_MAX_SECONDS = 3.5  # fail-stop, not an instruction to keep turning
TURN_SETTLE_SECONDS = 0.25  # stop and let momentum settle
TURN_FINE_TIMEOUT = 1.6
TURN_FINE_STEER = 12
TURN_FINE_PWM = 170
TURN_FINE_MIN_FRONT = 0.55
TURN_FINE_SIDE_MIN = 0.20
HEADING_KP = 0.8  # steering deg per yaw-error deg; heading hold, NOT wall following
HEADING_STEERING_LIMIT = 12
# A short straight segment AFTER the green corner and BEFORE red avoidance.
# This is time-based, not proof that the green pillar has been cleared.
GREEN_CLEAR_STRAIGHT_SECONDS = 0.65
GREEN_CLEAR_FRONT_GUARD = 0.65
GREEN_CLEAR_PWM = 120
RED_RIGHT_FRONT_TRIGGER = 0.5  # metres; front LiDAR triggers transition to left
RED_RIGHT_STEER = 36
RED_LEFT_STEER = -35
GREEN_LEFT_FRONT_TRIGGER = 0.5   # metres; switch from left swerve to recovery
GREEN_LEFT_STEER = -20
GREEN_RIGHT_STEER = 25
RED_MANEUVER_TIMEOUT = 2.5  # per phase; fail-stop
RED_EXIT_MAX_SECONDS = 2.0   # bounded post-turn test, not proof of passing pillar
RED_EXIT_FRONT_GUARD = 0.60  # conservative: do not continue toward unknown obstacle
SECOND_GREEN_TEST_FRONT_LIMIT = 0.40
# TOP GREEN-GREEN -> LEFT RED: begin second GREEN maneuver earlier.
TOP_GG_TO_LEFT_RED_GREEN_TRIGGER_M = 1.30  # earlier approach window; verify target on real field
TOP_GG_TO_LEFT_RED_LEFT_SWITCH_M = 0.95  # recover before the near-wall reading
TOP_GG_TO_LEFT_RED_MIN_YAW_CHANGE_DEG = 6.0
TOP_GG_TO_LEFT_RED_LEFT_PWM = 95
TOP_GG_TO_LEFT_RED_RECOVER_PWM = 95
TOP_GG_TO_LEFT_RED_LEFT_STEER_DEG = 18
TOP_GG_TO_LEFT_RED_RECOVER_STEER_DEG = 25
TOP_GG_TO_LEFT_RED_FRONT_BRAKE_M = 0.45  # do not drive toward obstacle below this
TOP_GG_TO_LEFT_RED_LATE_START_M = 1.05  # fail-stop if first detection is already too close
TOP_GG_TO_LEFT_RED_MAX_YAW_CHANGE_DEG = 40.0
TOP_GG_TO_LEFT_RED_HANDOFF_FRONT_M = 0.75
TOP_GG_TO_LEFT_RED_HANDOFF_MIN_FRONT_M = 0.65
TOP_GG_TO_LEFT_RED_LEFT_OPEN_M = 1.00
# GREEN-GREEN -> LEFT first RED only: small IMU-controlled pre-corner RIGHT offset.
TOP_GG_TO_LEFT_RED_RIGHT_OFFSET_DEG = 10.0
TOP_GG_TO_LEFT_RED_RIGHT_STEER_DEG = 10
TOP_GG_TO_LEFT_RED_RIGHT_PWM = 90
TOP_GG_TO_LEFT_RED_RIGHT_TIMEOUT_S = 1.2
TOP_GG_TO_LEFT_RED_RIGHT_TOL_DEG = 2.0
TOP_GG_TO_LEFT_RED_RIGHT_MIN_CLEARANCE_M = 0.05
TOP_GG_TO_LEFT_RED_RIGHT_MIN_FRONT_M = 0.80
# TOP GREEN-GREEN -> LEFT first GREEN: hand over BEFORE 1.10m turn.
TOP_GG_TO_LEFT_GREEN_SECOND_TRIGGER_M = 1.50  # start TOP pillar-2 avoidance earlier for LEFT GREEN
TOP_GG_TO_LEFT_GREEN_APPROACH_PWM = 90
TOP_GG_TO_LEFT_GREEN_HANDOFF_FRONT_M = 1.30
TOP_GG_TO_LEFT_GREEN_MIN_HANDOFF_FRONT_M = 1.10
SECOND_GREEN_MIN_FRONT = 0.30  # guard: do not start maneuver too close
SECOND_GREEN_MIN_LEFT = 0.05   # require valid left side > 0.30 m
# NEW: TOP GREEN-GREEN follows the LEFT wall after the first 270-degree turn.
# The next section's first color selects the subsequent corner strategy.
TOP_GG_WALL_TARGET_M = 0.29
TOP_GG_WALL_DEADBAND_M = 0.03
TOP_GG_WALL_KP = 55.0
TOP_GG_WALL_MAX_STEER_DEG = 17
TOP_GG_WALL_PWM = 130
TOP_GG_WALL_MAX_HEADING_ERR_DEG = 15.0
TOP_GG_WALL_MIN_FRONT_M = 0.45
TOP_GG_WALL_RIGHT_MIN_M = 0.04
TOP_GG_LEFT_OPEN_TRIGGER_M = 0.35
TOP_GG_LEFT_OPEN_SCANS = 3
# A gap cannot count as a corner until the robot has tracked an actual inner wall.
TOP_GG_WALL_ACQUIRE_MAX_M = 0.30
TOP_GG_WALL_ACQUIRE_SCANS = 3
# Maximum straight, low-speed search after first TOP GG corner (not guaranteed travel).
TOP_GG_ACQUIRE_STRAIGHT_SECONDS = 5.0
TOP_GG_ACQUIRE_STRAIGHT_PWM = 85
TOP_GG_ACQUIRE_MIN_FRONT_M = 0.80
TOP_GG_ACQUIRE_MIN_FRONT_LEFT_M = 0.05
TOP_GG_ACQUIRE_MIN_RIGHT_M = 0.05
TOP_GG_GREEN_TURN_FRONT_M = 1.00
TOP_GG_RED_TURN_FRONT_M = 0.75
TOP_GG_RED_RIGHT_OFFSET_YAW_DEG = 18.0   # physical yaw 270 -> 280
TOP_GG_RED_RIGHT_STEER_DEG = 16.0        # servo steering angle, not yaw
TOP_GG_RED_RIGHT_PWM = 110
TOP_GG_RED_RIGHT_MIN_START_FRONT_M = 0.5
TOP_GG_RED_RIGHT_TIMEOUT_S = 2.5
TOP_GG_RED_RIGHT_TOL_DEG = 2.0
TOP_GG_CORNER_FRONT_LEFT_MIN_M = 0.05
# GREEN corner: the side sector can still see the inner wall when the
# front-left sector sees an opening. This is a *provisional* LiDAR check,
# not proof of rear wheel / swept-body clearance.
TOP_GG_GREEN_CORNER_LEFT_MIN_M = 0.05
TOP_GG_GREEN_CORNER_FRONT_LEFT_MIN_M = 0.05
TOP_GG_GREEN_CORNER_RIGHT_MIN_M = 0.05
TOP_GG_GREEN_CORNER_MIN_FRONT_M = 0.75
TOP_GG_GREEN_TURN_PWM = 130
TOP_GG_LEFT_RED_TURN_PWM = 120  # Only TOP GG -> LEFT first RED corner turn
TOP_GG_LEFT_RED_TURN_STEER_DEG = 35  # Dedicated LEFT steering, overrides default 30-degree limit
TOP_GG_GR_LEFT_RED_TURN_MAX_SECONDS = 3.0  # GG/GR TOP -> LEFT first RED only; fail-stop
# Bounded LiDAR dropout handling for TOP GG -> LEFT GREEN during TURN_1.
# A previously verified LEFT reading may bridge a brief missing sector only
# while front-left and RIGHT are concurrently clear. NOT proof of body clearance.
TOP_GG_TURN_LEFT_DROPOUT_MAX_S = 0.20
TOP_GG_TURN_LAST_LEFT_MIN_M = 0.35
TOP_GG_TURN_FRONT_LEFT_DROPOUT_MIN_M = 0.70
TOP_GG_TURN_RIGHT_DROPOUT_MIN_M = 0.22
TOP_GG_TURN_FRONT_DROPOUT_MIN_M = 0.60
# Experimental late-phase guard for TOP GG -> LEFT GREEN only.
# Do not infer full robot swept clearance from these sectors: verify chassis
# dimensions, sensor mounting, and the field geometry before enabling motors.
TOP_GG_GREEN_LATE_START_PHYSICAL_YAW_DEG = 205.0
TOP_GG_GREEN_LATE_FRONT_LEFT_MIN_M = 0.10
TOP_GG_GREEN_LATE_LEFT_MIN_M = 0.05
TOP_GG_GREEN_LATE_RIGHT_MIN_M = 0.05
TOP_GG_GREEN_TURN_RIGHT_HARD_MIN_M = 0.05  # STOP on observed near-right intrusion during turning

# RED-first sequences only; GREEN-first paths retain their existing code.
RED_RED_STOP_FRONT_M = 0.50
# TOP Red-Red -> LEFT Green: hand of35ver at the GREEN corner turn distance.
# Hand off before LEFT_GREEN_TURN_DISTANCE to allow a straight approach.
TOP_RR_LEFT_GREEN_HANDOFF_FRONT_M = 1.35
# Independent distances for each first-pillar turn (LiDFAR metres).
# The TOP handoff occurs slightly earlier, allowing LEFT to trigger at 0.55 m.
# Handoff is not a turning command. These are LiDAR-to-obstacle distances.
TOP_GREEN_TURN_DISTANCE = 1.1
LEFT_GREEN_TURN_DISTANCE = 1.08
TOP_RED_TURN_DISTANCE = 0.6
LEFT_RED_TURN_DISTANCE = 0.6
TOP_RR_LEFT_RED_HANDOFF_FRONT_M = 0.7
# RED -> RED ONLY: follow RIGHT wall where a consistent right-side return exists.
# Ranges are measured from the LiDAR, NOT the robot outer body.
RR_RIGHT_TARGET_M = 0.20
# RIGHT section RED-RED only: track the outer RIGHT wall at 0.40 m.
RIGHT_RR_RIGHT_TARGET_M = 0.33
RIGHT_RR_RIGHT_MAX_TRACK_M = 0.65  # must exceed target to allow correction above 0.40 m
RR_RIGHT_DEADBAND_M = 0.025   # tolerate 0.125 .. 0.175 m
RR_RIGHT_KP = 62.0           # steering degrees per metre of range error
RR_RIGHT_MAX_STEER = 17    # limit correction to keep the route broadly straight
RR_RIGHT_MAX_TRACK_M = 0.40  # beyond this, do NOT chase an opening / distant pillar
RR_HEADING_KP = 0.40        # smaller yaw correction while wall-following
RR_MAX_HEADING_ERROR = 25.0
RR_FOLLOW_PWM = 150
RR_MIN_OPPOSITE_M = 0.22    # no steering LEFT if the left side is too close

# RED -> GREEN ONLY: short straight period after the first RED corner turn.
# Timed clearance is NOT confirmation that the red pillar is behind the car.
RED_GREEN_CLEAR_STRAIGHT_SECONDS = 1.5
RED_GREEN_CLEAR_PWM = 130
RED_GREEN_CLEAR_FRONT_GUARD_M = 0.5
RED_GREEN_START_FRONT_M = 1.8  # TOP RED->GREEN left swerve trigger
TOP_RG_LATE_TRIGGER_MIN_FRONT_M = 1.0  # fail-stop rather than launch a late timed turn
# LEFT Red->Green: wait until closer to the GREEN/wall before beginning
# the left swerve; prevents the observed 35-degree overturn at front 1.55m.
LEFT_RG_START_FRONT_M = 1.00  # tune cautiously in 0.10m steps on actual field
RED_GREEN_LEFT_TO_FRONT_M = 0.30  # TOP RG: switch right before the observed 0.65m timeout point
# LEFT-section Red->Green only: start right recovery earlier at second corner.
LEFT_RG_SWITCH_FRONT_M = 0.50
LEFT_RG_MAX_LEFT_YAW_DEVIATION_DEG = 35.0
TOP_RG_MAX_LEFT_YAW_DEVIATION_DEG = 90.0  # fail-stop; no timed RG_LEFT cutoff
RED_GREEN_LEFT_STEER = -40       # limited to -MAX_STEERING_DEG (-37 currently)
RED_GREEN_RIGHT_STEER = 37
RED_GREEN_FOLLOW_FRONT_M = 0.42
RED_GREEN_FOLLOW_LEFT_OPEN_M = 0.30
RED_GREEN_FOLLOW_LEFT_TARGET_M = 0.15  # LiDAR range, not body clearance
RED_GREEN_FOLLOW_STEER = 8
RED_GREEN_FOLLOW_PWM = 130
RED_GREEN_MANEUVER_TIMEOUT_S = 2.5
RED_GREEN_RIGHT_MIN_SECONDS = 0.20
RED_GREEN_RIGHT_YAW_DEVIATION = 8.0  # requires measurable prior left change
RED_GREEN_HEADING_TOLERANCE = 10.0
RED_GREEN_FRONT_GUARD_M = 0.50
RED_GREEN_MAX_FOLLOW_SECONDS = 8.0

# TOP RED -> GREEN: LiDAR-ended LEFT swerve and LEFT-wall tracking.
# Steering commands are requested servo angles; physical response must be verified.
TOP_RG_LEFT_STEER_DEG = 40
TOP_RG_LEFT_SWITCH_FRONT_M = 0.45 # switch LEFT -> RIGHT when front <= 25 cm
TOP_RG_LEFT_MIN_FRONT_M = 0.05  # below this, refuse the recovery turn
TOP_RG_LEFT_MAX_SECONDS = 2.0  # fail-stop only; NOT a switching trigger
TOP_RG_RIGHT_STEER_DEG = 37
TOP_RG_RIGHT_MIN_SECONDS = 0.05
TOP_RG_LEFT_WALL_TARGET_M = 0.15  # measured from LiDAR, NOT outer-body clearance
TOP_RG_LEFT_WALL_DEADBAND_M = 0.025
TOP_RG_LEFT_WALL_KP = 50.0
TOP_RG_LEFT_WALL_MAX_STEER = 9
TOP_RG_LEFT_WALL_MAX_TRACK_M = 0.40  # don't chase gaps
TOP_RG_LEFT_WALL_HEADING_KP = 0.40
TOP_RG_LEFT_WALL_MAX_HEADING_ERR = 20.0
TOP_RG_LEFT_WALL_MIN_OPPOSITE_M = 0.22
TOP_RG_FOLLOW_PWM = 100
# Only TOP RED->GREEN followed by LEFT RED: gently bias RIGHT before corner.
# These are PHYSICAL yaw degrees (270 -> 277), NOT servo steering degrees.
TOP_RG_TO_LEFT_RED_RIGHT_OFFSET_DEG = 13.0
TOP_RG_TO_LEFT_RED_RIGHT_STEER_DEG = 13
TOP_RG_TO_LEFT_RED_OFFSET_PWM = 90
TOP_RG_TO_LEFT_RED_OFFSET_TIMEOUT_S = 1.2
TOP_RG_TO_LEFT_RED_RIGHT_CLEARANCE_M = 0.05
TOP_RG_TO_LEFT_RED_LEFT_CLEARANCE_M = 0.05
TOP_RG_TO_LEFT_RED_MIN_FRONT_M = 0.6
TOP_RG_TO_LEFT_RED_TARGET_TOL_DEG = 2.0
TOP_RG_FOLLOW_TIMEOUT_S = 9.0
TOP_RG_LEFT_GREEN_HANDOFF_FRONT_M = 0.96  # hand over before LEFT GREEN 1.05m
TOP_RG_LEFT_RED_HANDOFF_FRONT_M = 0.7  # hand over before LEFT RED 0.65m
TOP_RG_MIN_TRACK_READINGS = 3
# TOP RED-GREEN: the LEFT sector can already be open after passing the inner wall.
TOP_RG_CORNER_LEFT_OPEN_M = 1.10
TOP_RG_CORNER_OPEN_SCANS = 3
TOP_RG_CORNER_FRONT_LEFT_MIN_M = 0.35
TOP_RG_CORNER_RIGHT_MIN_M = 0.1
TOP_RG_CORNER_HEADING_TOL_DEG = 15.0
TOP_RG_MAX_LEFT_DEVIATION_DEG = 90.0  # stop if the timed swerve turns unexpectedly far
# TOP GREEN -> RED only: RIGHT swerve, LEFT recovery, OUTER (RIGHT) wall follow.
# These are trial parameters, independent of all TOP RG / GG routes.
TOP_GR_RIGHT_START_FRONT_M = 1.70
TOP_GR_RIGHT_SWITCH_FRONT_M = 0.45
TOP_GR_RIGHT_STEER_DEG = 40
TOP_GR_LEFT_RECOVER_STEER_DEG = -37
TOP_GR_MANEUVER_PWM = 110
TOP_GR_RIGHT_MAX_SECONDS = 2.5
TOP_GR_LEFT_MAX_SECONDS = 2.5
TOP_GR_MAX_YAW_DEVIATION_DEG = 90.0
TOP_GR_MIN_YAW_DEVIATION_DEG = 8.0
TOP_GR_MIN_SIDE_M = 0.12
TOP_GR_MIN_FRONT_M = 0.10
TOP_GR_RECOVERY_HEADING_TOL_DEG = 10.0
TOP_GR_RIGHT_WALL_TARGET_M = 0.17
TOP_GR_RIGHT_WALL_TRACK_MAX_M = 0.40
TOP_GR_RIGHT_WALL_KP = 50.0
TOP_GR_RIGHT_WALL_HEADING_KP = 0.4
TOP_GR_RIGHT_WALL_STEER_MAX = 9
TOP_GR_FOLLOW_PWM = 100
TOP_GR_FOLLOW_MAX_SECONDS = 9.0
TOP_GR_LEFT_OPEN_M = 0.35
TOP_GR_OPEN_SCANS = 3
TOP_GR_CORNER_FRONT_LEFT_MIN_M = 0.1
TOP_GR_CORNER_RIGHT_MIN_M = 0.15
TOP_GR_LEFT_GREEN_HANDOFF_FRONT_M = 1.30
TOP_GR_LEFT_RED_HANDOFF_FRONT_M = 0.70

# LEFT route parameters - independent copies of TOP behavior (TOP unchanged).
LEFT_GG_WALL_TARGET_M = TOP_GG_WALL_TARGET_M
LEFT_GG_WALL_DEADBAND_M = TOP_GG_WALL_DEADBAND_M
LEFT_GG_WALL_KP = TOP_GG_WALL_KP
LEFT_GG_WALL_MAX_STEER_DEG = TOP_GG_WALL_MAX_STEER_DEG
LEFT_GG_WALL_PWM = TOP_GG_WALL_PWM
LEFT_GG_END_FRONT_M = 0.50
# LEFT GG -> BOTTOM RED and RIGHT GG -> TOP RED (on nonfinal laps):
# wait for a verified inner-wall opening, then make a bounded RIGHT yaw bias.
# These are LiDAR-to-object ranges, not robot-body clearances.
GG_LR_RED_RIGHT_OFFSET_DEG = 18.0
GG_LR_RED_RIGHT_STEER_DEG = 18.0
GG_LR_RED_RIGHT_PWM = 100
GG_LR_RED_RIGHT_TIMEOUT_S = 8
GG_LR_RED_RIGHT_TOL_DEG = 5.0
GG_LR_RED_OPEN_M = 1.30
GG_LR_RED_OPEN_SCANS = 2
GG_LR_RED_OPEN_MIN_FRONT_M = 0.05
GG_LR_RED_BIAS_START_FRONT_M = 1.40
GG_LR_RED_MIN_RIGHT_M = 0.22
GG_LR_RED_MIN_FRONT_LEFT_M = 0.05
GG_LR_RED_MIN_LEFT_M = 0.05
GG_LR_RED_APPROACH_MAX_YAW_ERR_DEG = 20.0
LEFT_RR_RIGHT_TARGET_M = RR_RIGHT_TARGET_M
LEFT_RR_FOLLOW_PWM = RR_FOLLOW_PWM
LEFT_RR_END_FRONT_M = RED_RED_STOP_FRONT_M

LEFT_RG_LEFT_START_FRONT_M = 1.80
LEFT_RG_LEFT_SWITCH_FRONT_M = TOP_RG_LEFT_SWITCH_FRONT_M
LEFT_RG_LEFT_STEER_DEG = TOP_RG_LEFT_STEER_DEG
LEFT_RG_RIGHT_STEER_DEG = TOP_RG_RIGHT_STEER_DEG
LEFT_RG_MANEUVER_PWM = RED_GREEN_FOLLOW_PWM
LEFT_RG_LEFT_MAX_SECONDS = TOP_RG_LEFT_MAX_SECONDS
LEFT_RG_RIGHT_MAX_SECONDS = RED_GREEN_MANEUVER_TIMEOUT_S
LEFT_RG_RIGHT_MIN_SECONDS = TOP_RG_RIGHT_MIN_SECONDS
LEFT_RG_RECOVERY_TOLERANCE_DEG = RED_GREEN_HEADING_TOLERANCE
LEFT_RG_LEFT_WALL_TARGET_M = TOP_RG_LEFT_WALL_TARGET_M
LEFT_RG_LEFT_WALL_DEADBAND_M = TOP_RG_LEFT_WALL_DEADBAND_M
LEFT_RG_LEFT_WALL_KP = TOP_RG_LEFT_WALL_KP
LEFT_RG_LEFT_WALL_MAX_STEER = TOP_RG_LEFT_WALL_MAX_STEER
LEFT_RG_LEFT_WALL_MAX_TRACK_M = TOP_RG_LEFT_WALL_MAX_TRACK_M
LEFT_RG_LEFT_WALL_HEADING_KP = TOP_RG_LEFT_WALL_HEADING_KP
LEFT_RG_FOLLOW_PWM = TOP_RG_FOLLOW_PWM
LEFT_RG_FOLLOW_MAX_SECONDS = TOP_RG_FOLLOW_TIMEOUT_S
LEFT_RG_END_FRONT_M = 0.50
LEFT_RG_END_LEFT_OPEN_M = 0.30

LEFT_GR_RIGHT_START_FRONT_M = TOP_GR_RIGHT_START_FRONT_M
LEFT_GR_RIGHT_SWITCH_FRONT_M = TOP_GR_RIGHT_SWITCH_FRONT_M
LEFT_GR_RIGHT_STEER_DEG = TOP_GR_RIGHT_STEER_DEG
LEFT_GR_LEFT_RECOVER_STEER_DEG = TOP_GR_LEFT_RECOVER_STEER_DEG
LEFT_GR_MANEUVER_PWM = TOP_GR_MANEUVER_PWM
LEFT_GR_RIGHT_MAX_SECONDS = TOP_GR_RIGHT_MAX_SECONDS
LEFT_GR_LEFT_MAX_SECONDS = TOP_GR_LEFT_MAX_SECONDS
LEFT_GR_MIN_YAW_DEVIATION_DEG = TOP_GR_MIN_YAW_DEVIATION_DEG
LEFT_GR_MAX_YAW_DEVIATION_DEG = TOP_GR_MAX_YAW_DEVIATION_DEG
LEFT_GR_MIN_SIDE_M = TOP_GR_MIN_SIDE_M
LEFT_GR_RECOVERY_HEADING_TOL_DEG = TOP_GR_RECOVERY_HEADING_TOL_DEG
LEFT_GR_RIGHT_WALL_TARGET_M = TOP_GR_RIGHT_WALL_TARGET_M
LEFT_GR_RIGHT_WALL_TRACK_MAX_M = TOP_GR_RIGHT_WALL_TRACK_MAX_M
LEFT_GR_RIGHT_WALL_KP = TOP_GR_RIGHT_WALL_KP
LEFT_GR_RIGHT_WALL_HEADING_KP = TOP_GR_RIGHT_WALL_HEADING_KP
LEFT_GR_RIGHT_WALL_STEER_MAX = TOP_GR_RIGHT_WALL_STEER_MAX
LEFT_GR_FOLLOW_PWM = TOP_GR_FOLLOW_PWM
LEFT_GR_FOLLOW_MAX_SECONDS = TOP_GR_FOLLOW_MAX_SECONDS
LEFT_GR_END_FRONT_M = 0.50

# BOTTOM and RIGHT (new routes). Values are copies/starting points, not validated.
# BOTTOM reuses TOP behavior with a +180-degree virtual heading rotation.
# RIGHT reuses LEFT behavior with a +270-degree virtual heading rotation.
BOTTOM_GREEN_TURN_DISTANCE = TOP_GREEN_TURN_DISTANCE
BOTTOM_RED_TURN_DISTANCE = TOP_RED_TURN_DISTANCE
RIGHT_GREEN_TURN_DISTANCE = LEFT_GREEN_TURN_DISTANCE
RIGHT_RED_TURN_DISTANCE = 0.75  # RIGHT only: first RED pillar LEFT turn trigger

# LEFT -> BOTTOM and BOTTOM -> RIGHT must hand off BEFORE next first turn.
# Use next pillar's color, not a fixed late endpoint. All distances in metres.
LEFT_TO_BOTTOM_GREEN_HANDOFF_FRONT_M = 1.35
LEFT_TO_BOTTOM_RED_HANDOFF_FRONT_M = 0.75
BOTTOM_TO_RIGHT_GREEN_HANDOFF_FRONT_M = TOP_GG_TO_LEFT_GREEN_HANDOFF_FRONT_M
BOTTOM_TO_RIGHT_RED_HANDOFF_FRONT_M = 1.05  # Handoff before RIGHT first RED turn at 0.80 m

# First corner tuning for new sections. TOP/LEFT existing values unchanged.
BOTTOM_TURN_PWM = TURN_PWM
RIGHT_TURN_PWM = TURN_PWM
BOTTOM_FIRST_TURN_MAX_SECONDS = FIRST_TURN_MAX_SECONDS
RIGHT_FIRST_TURN_MAX_SECONDS = FIRST_TURN_MAX_SECONDS

# After each first corner in RG / GR, approach the second pillar STRAIGHT.
# Do not turn from a stale/already-near front measurement immediately after corner.
POST_CORNER_RG_GR_TRIGGER_M = 1.80
POST_CORNER_RG_GR_MIN_STRAIGHT_S = 0.30  # drive straight after settling before second-pillar steering
POST_CORNER_RG_GR_LATE_MIN_FRONT_M = 1.00  # fail-stop if trigger was missed too closely
POST_CORNER_RG_GR_PWM = 110
POST_CORNER_RG_GR_HEADING_TOL_DEG = 25.0
# RIGHT GR: only start on a verified approach from beyond 1.70m.
RIGHT_GR_ARM_FRONT_M = 1.80
RIGHT_GR_START_FRONT_M = 1.80
RIGHT_GR_MIN_STRAIGHT_S = 0.0  # allow first downward crossing after initial post-corner scan
# Narrow central forward beam only for RIGHT GR's 1.50m trigger.
# Keep the original +/-2deg front for emergency and all other routes.
RIGHT_GR_TRIGGER_ANGLE_HALF_WIDTH_DEG = 0.75
RIGHT_GR_RIGHT_MIN_SIDE_M = 0.10  # LiDAR distance, not body clearance

TARGET_LAPS = 3  # Complete TOP -> LEFT -> BOTTOM -> RIGHT three times.
# On laps 2 and 3 there is NO parking exit. RIGHT hands over early to TOP,
# then TOP uses its normal first-pillar LiDAR threshold (GREEN 1.10m / RED 0.53m).
RIGHT_TO_TOP_GREEN_HANDOFF_FRONT_M = 1.35
RIGHT_TO_TOP_RED_HANDOFF_FRONT_M = 0.75

# Final lap: complete RIGHT corner near yaw 0, then approach straight to 0.70 m.
FINAL_RIGHT_HANDOFF_FRONT_M = 1.0  # finish RIGHT route before starting dedicated straight
FINAL_PARKING_FRONT_START_M = 0.9
FINAL_APPROACH_PWM = 85
FINAL_APPROACH_MAX_STEER = 8
FINAL_APPROACH_MAX_YAW_ERROR_DEG = 20.0
FINAL_APPROACH_TIMEOUT_S = 8.0

# Return-to-parking sequence: VL53L0X faces backward, on /dev/i2c-1.
FINAL_REVERSE_PWM = 80
FINAL_FORWARD_PWM = 80
FINAL_REVERSE_RIGHT_STEER = 50
FINAL_REVERSE_LEFT_STEER = -50
FINAL_FORWARD_RIGHT_STEER = 10
FINAL_REVERSE_SWITCH_MM = 360
FINAL_REVERSE_STOP_MM = 60
FINAL_FORWARD_STOP_M = 0.10  # Hokuyo UST-30LX: 0.03 m is below its specified minimum
FINAL_REVERSE_PHASE_MAX_S = 8.0
FINAL_FORWARD_MAX_S = 2.0
FINAL_PARKING_COMMAND_PERIOD_S = 0.05
FINAL_PARKING_SETTLE_SECONDS = 0.75  # Remain stopped before reverse parking


CONTROL_INTERVAL = 0.05

SCAN_TIMEOUT = 0.50


# =========================================================

# FLASK AND SHARED DATA

# =========================================================


def mirror_command(command):
    """Clockwise = mirror image: negate steering on DRIVE/BACK commands."""
    if not CLOCKWISE:
        return command
    parts = command.split()
    if len(parts) == 3 and parts[0] in ("DRIVE", "BACK"):
        return f"{parts[0]} {-int(parts[1])} {parts[2]}"
    return command


app = Flask(__name__)


data_lock = threading.Lock()

stop_event = threading.Event()

camera_data = {"connected": False, "received_at": 0.0, "detections": [], "error": "Camera starting"}
camera_preview_jpeg = None


def camera_worker():
    """Run live red/green pillar detection during driving.

    This worker is NOT the planned three-angle parking-lot scan. It neither
    moves the camera servo nor writes the JSON route map. Its limited current
    role is to help the LiDAR controller distinguish a coloured pillar from a
    wall; it never sends motion commands or overrides emergency distance data.
    """
    global camera_data, camera_preview_jpeg
    try:
        from ultralytics import YOLO
        model = YOLO(CAMERA_MODEL_PATH)
    except Exception as exc:
        with data_lock:
            camera_data = {"connected": False, "received_at": 0.0, "detections": [], "error": str(exc)}
        print("[CAMERA] Model unavailable:", exc)
        return
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
    if not cap.isOpened():
        with data_lock:
            camera_data = {"connected": False, "received_at": 0.0, "detections": [], "error": f"Cannot open camera {CAMERA_INDEX}"}
        print("[CAMERA] Cannot open camera", CAMERA_INDEX)
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_FRAME_WIDTH)
    try:
        while not stop_event.is_set():
            ok, frame = cap.read()
            if not ok:
                with data_lock:
                    camera_data = {"connected": False, "received_at": 0.0, "detections": [], "error": "Camera frame failed"}
                stop_event.wait(0.1)
                continue
            try:
                preds = model.predict(frame, conf=CAMERA_CONFIDENCE, verbose=False)
                detections = []
                width = frame.shape[1]
                names = model.names
                for result in preds:
                    for box in result.boxes:
                        cls = int(box.cls[0].item())
                        label = str(names[cls]).lower() if isinstance(names, (list, dict)) else str(cls)
                        if not ("red" in label or "green" in label):
                            continue
                        x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                        # LiDAR convention: image LEFT = positive LiDAR angle.
                        lo = (0.5 - x2 / width) * CAMERA_FOV_DEG + CAMERA_YAW_OFFSET_DEG
                        hi = (0.5 - x1 / width) * CAMERA_FOV_DEG + CAMERA_YAW_OFFSET_DEG
                        if CLOCKWISE:
                            lo, hi = -hi, -lo  # same mirrored frame as the LiDAR sectors
                        detections.append({"color": "red" if "red" in label else "green",
                                           "confidence": round(float(box.conf[0].item()), 3),
                                           "angle_min": lo, "angle_max": hi,
                                           "bbox": [round(x1), round(y1), round(x2), round(y2)]})
                # Preview only: show what the exact same YOLO pass detected.
                # Does not change any robot movement, safety, or LiDAR parameters.
                preview = frame.copy()
                h, w = preview.shape[:2]
                cv2.line(preview, (w // 2, 0), (w // 2, h), (255, 255, 0), 1)
                for det in detections:
                    x1, y1, x2, y2 = det["bbox"]
                    color = (0, 0, 255) if det["color"] == "red" else (0, 255, 0)
                    cv2.rectangle(preview, (x1, y1), (x2, y2), color, 2)
                    label_text = (f'{det["color"].upper()} {det["confidence"]:.2f} '
                                  f'{det["angle_min"]:+.0f}..{det["angle_max"]:+.0f} deg')
                    cv2.putText(preview, label_text, (max(0, x1), max(20, y1 - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.50, color, 2)
                if not detections:
                    cv2.putText(preview, "NO RED/GREEN PILLAR DETECTED", (12, 28),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 165, 255), 2)
                cv2.putText(preview, "CAMERA VIEW - NOT COLLISION CLEARANCE", (10, h - 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 2)
                encode_ok, encoded = cv2.imencode('.jpg', preview, [cv2.IMWRITE_JPEG_QUALITY, 75])
                with data_lock:
                    camera_data = {"connected": True, "received_at": time.monotonic(),
                                   "detections": detections, "error": ""}
                    if encode_ok:
                        camera_preview_jpeg = encoded.tobytes()
            except Exception as exc:
                with data_lock:
                    camera_data = {"connected": False, "received_at": 0.0, "detections": [], "error": str(exc)}
                stop_event.wait(0.1)
    finally:
        cap.release()


def camera_pillar_in_sector(camera, sector_min, sector_max):
    """Returns True only for a fresh, angle-overlapping red/green detection.

    NOTE camera FOV and optical-axis offset MUST be calibrated. An angle overlap
    alone does not prove which LiDAR return is a pillar; it only vetoes an
    ambiguous wall steering correction, never the raw collision guard.
    """
    if not camera or not camera.get("connected") or time.monotonic() - camera.get("received_at", 0) > CAMERA_MAX_AGE_S:
        return False
    return any(det["angle_min"] - CAMERA_PILLAR_EXTRA_MARGIN_DEG <= sector_max
               and det["angle_max"] + CAMERA_PILLAR_EXTRA_MARGIN_DEG >= sector_min
               for det in camera.get("detections", []))


latest_data = {

    "connected": False,

    "error": "Waiting for LiDAR...",

    "received_at": 0.0,

    "timestamp": 0,

    "angles": [],

    "distances": [],

    "front": None,
    "front_right_gr": None,

    "front_left": None,

    "left": None,

    "right": None

}


control_data = {

    "serial_connected": False,

    "command": "STOP",

    "state": "Waiting for ESP32",

    "steering": 0,

    "speed": 0,

    "yaw": None,

    "lap": 0

}


def camera_front_pillar_status(camera, front_angle_min=-1.0, front_angle_max=1.0):
    """Return fresh YOLO pillar(s) overlapping the actual front LiDAR beam.

    Detection does NOT remove LiDAR returns or prove free space. A confirmed
    front pillar means the front measurement cannot be called a WALL by itself.
    """
    if not camera or not camera.get("connected"):
        return None
    if time.monotonic() - camera.get("received_at", 0) > CAMERA_MAX_AGE_S:
        return None
    matched = [d for d in camera.get("detections", [])
               if d.get("color") in ("red", "green")
               and d.get("angle_min", 999) <= front_angle_max
               and d.get("angle_max", -999) >= front_angle_min]
    if not matched:
        return None
    best = max(matched, key=lambda d: d.get("confidence", 0))
    return f'{best["color"]} {best.get("confidence", 0):.2f}'


# =========================================================
# BNO055 IMU + LAP COUNTER
# =========================================================

class IMUHeading:
    def __init__(self):
        self.bus = SMBus(IMU_BUS)
        self.bus.write_byte_data(IMU_ADDRESS, OPR_MODE, CONFIG_MODE)
        time.sleep(0.1)
        self.bus.write_byte_data(IMU_ADDRESS, OPR_MODE, NDOF_MODE)
        time.sleep(0.7)
        time.sleep(1.0)  # Keep robot stationary while zeroing.
        self.zero_yaw = self.read_raw_yaw()
        print(f"IMU initialized at zero (raw {self.zero_yaw:.2f} deg)")

    def read_raw_yaw(self):
        lsb = self.bus.read_byte_data(IMU_ADDRESS, EUL_HEADING_LSB)
        msb = self.bus.read_byte_data(IMU_ADDRESS, EUL_HEADING_MSB)
        return ((msb << 8) | lsb) / 16.0

    def read_yaw(self):
        delta = self.read_raw_yaw() - self.zero_yaw
        # Clockwise: a physical RIGHT turn (raw yaw increasing) must look like
        # the controller's LEFT turn (yaw decreasing), so mirror the sign.
        return ((-delta) if CLOCKWISE else delta) % 360.0

    def close(self):
        self.bus.close()


# =========================================================

# DISTANCE CALCULATION

# =========================================================


def get_median_distance(scan, angles, minimum_angle, maximum_angle):

    selected = scan[

        (angles >= minimum_angle)

        & (angles <= maximum_angle)

        & np.isfinite(scan)

    ]


    if selected.size == 0:

        return None


    return float(np.median(selected))


# =========================================================

# LIDAR THREAD

# =========================================================


def lidar_worker():

    global latest_data


    while not stop_event.is_set():

        laser = None


        try:

            print(f"Connecting to LiDAR: {LIDAR_IP}:{LIDAR_PORT}")


            laser = HokuyoLX(

                addr=(LIDAR_IP, LIDAR_PORT),

                timeout=5.0

            )


            print("LiDAR connected")


            while not stop_event.is_set():

                # Use acquisition start time conservatively.

                # A scan that takes too long will be treated as stale.

                scan_started = time.monotonic()


                timestamp, raw_scan = laser.get_dist()


                # Convert millimetres to metres

                raw_scan = np.asarray(raw_scan, dtype=float) / 1000.0


                if raw_scan.ndim != 1 or raw_scan.size == 0:

                    raise ValueError("Empty or unexpected LiDAR scan")


                # Preserve your working reversed angle mapping

                raw_angles = np.linspace(

                    RAW_ANGLE_MAX,

                    RAW_ANGLE_MIN,

                    raw_scan.size

                )
                # Debug raw LiDAR data
                center_index = raw_scan.size // 2

                # print("\n========== RAW LIDAR CHECK ==========")
                # print(f"Total scan points: {raw_scan.size}")

                # for offset in range(-8, 9):
                #     idx = center_index + offset

                #     if 0 <= idx < raw_scan.size:
                #         print(
                #             f"Index: {idx:4d} | "
                #             f"Mapped angle: {raw_angles[idx]:+6.2f}° | "
                #             f"Distance: {raw_scan[idx]:.3f} m"
                #         )

                # print("=====================================\n")


                valid = (

                    (raw_angles >= VIEW_ANGLE_MIN)

                    & (raw_angles <= VIEW_ANGLE_MAX)

                    & (raw_scan >= MIN_DISTANCE_M)

                    & (raw_scan <= CONTROL_MAX_DISTANCE_M)

                    & np.isfinite(raw_scan)

                )


                angles = raw_angles[valid]

                scan = raw_scan[valid]

                display_angles = angles.copy()  # true physical angles for web view
                if CLOCKWISE:
                    angles = -angles  # controller "left" sectors read the physical RIGHT

                # Debug front LiDAR between -5 and +5 degrees
                front_mask = (angles >= -5) & (angles <= 5)

                front_angles = angles[front_mask]
                front_distances = scan[front_mask]

                # print("\n========== FRONT LIDAR ==========")

                # for angle, distance in zip(front_angles, front_distances):
                #     print(f"Angle: {angle:+6.2f}° | Distance: {distance:.3f} m")

                # print("=================================\n")

                front = get_median_distance(

                    scan, angles, -1, 1

                )


                front_right_gr = get_median_distance(
                    scan, angles,
                    -RIGHT_GR_TRIGGER_ANGLE_HALF_WIDTH_DEG,
                    RIGHT_GR_TRIGGER_ANGLE_HALF_WIDTH_DEG
                )

                front_left = get_median_distance(

                    scan, angles, 40, 50

                )


                left = get_median_distance(

                    scan, angles, 80, 90

                )


                right = get_median_distance(

                    scan, angles, -90, -80

                )


                new_data = {

                    "connected": True,

                    "error": "",

                    "received_at": scan_started,

                    "timestamp": int(timestamp),

                    "angles": np.round(angles[scan <= MAX_DISTANCE_M], 2).tolist(),

                    "display_angles": np.round(display_angles[scan <= MAX_DISTANCE_M], 2).tolist(),

                    "distances": np.round(scan[scan <= MAX_DISTANCE_M], 3).tolist(),

                    "front": front,
                    "front_right_gr": front_right_gr,

                    "front_left": front_left,

                    "left": left,

                    "right": right

                }


                with data_lock:

                    latest_data = new_data


        except Exception as error:

            print(f"LiDAR error: {error}")


            with data_lock:

                latest_data = {

                    "connected": False,

                    "error": str(error),

                    "received_at": 0.0,

                    "timestamp": 0,

                    "angles": [],

                    "distances": [],

                    "front": None,
    "front_right_gr": None,

                    "front_left": None,

                    "left": None,

                    "right": None

                }


        finally:

            if laser is not None:

                try:

                    laser.close()

                except Exception:

                    pass


        if not stop_event.is_set():

            print("Retrying LiDAR connection in 2 seconds...")

            stop_event.wait(2.0)


# =========================================================

# JSON PILLAR PLAN AND STRAIGHT-APPROACH CONTROLLER

# =========================================================


def load_test_plan(filename):
    """Validate and load the perception/navigation interface file.

    The planned camera-pan mapper will write this same schema. Keeping a strict
    loader here allows the mapping stage and driving stage to be developed and
    tested separately without changing the motion controller.

    Load two pillars for each of TOP, LEFT, BOTTOM and RIGHT.

    Counterclockwise: TOP right-to-left; LEFT top-to-bottom; BOTTOM left-to-right; RIGHT bottom-to-top.
    Clockwise (CLOCKWISE=True): TOP left-to-right; RIGHT top-to-bottom; BOTTOM right-to-left; LEFT bottom-to-top.
    Pixel coordinates determine ORDER, not physical clearance.
    """
    obj = json.loads(Path(filename).read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or not isinstance(obj.get("pillars"), list):
        raise ValueError("Expected a 'pillars' list in map JSON")
    if obj.get("coordinate_system") != "image pixels, origin top-left":
        raise ValueError("Unexpected coordinate system")
    width, height = obj.get("image_width"), obj.get("image_height")
    if not all(isinstance(v, (int, float)) and v > 0 for v in (width, height)):
        raise ValueError("Invalid image dimensions")
    sections = {"top": [], "left": [], "bottom": [], "right": []}
    for i, item in enumerate(obj["pillars"]):
        section = item.get("section")
        if section not in sections:
            continue
        color = str(item.get("color", "")).lower()
        x, y = item.get("x"), item.get("y")
        if color not in ("red", "green"):
            raise ValueError(f"Pillar {i} has invalid color")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not 0 <= x < width or not 0 <= y < height:
            raise ValueError(f"Pillar {i} has invalid pixel position")
        sections[section].append((x, y, color))
    for section in sections:
        if len(sections[section]) != 2:
            raise ValueError(f"Expected exactly 2 pillars in '{section}'; found {len(sections[section])}")
    if CLOCKWISE:
        sections["top"].sort(key=lambda item: item[0])      # left -> right
        sections["right"].sort(key=lambda item: item[1])    # top -> bottom
        sections["bottom"].sort(key=lambda item: -item[0])  # right -> left
        sections["left"].sort(key=lambda item: -item[1])    # bottom -> top
        # Controller slots (TOP, LEFT, BOTTOM, RIGHT) = physical (TOP, RIGHT, BOTTOM, LEFT)
        ordered = {"top": sections["top"], "left": sections["right"],
                   "bottom": sections["bottom"], "right": sections["left"]}
    else:
        sections["top"].sort(key=lambda item: -item[0])
        sections["left"].sort(key=lambda item: item[1])
        sections["bottom"].sort(key=lambda item: item[0])
        sections["right"].sort(key=lambda item: -item[1])
        ordered = sections
    plan = {key: [p[2] for p in entries] for key, entries in ordered.items()}
    print("DIRECTION:", "CLOCKWISE" if CLOCKWISE else "COUNTERCLOCKWISE")
    print("1st section, physical TOP   :", plan["top"])
    print("2nd section, physical", "RIGHT:" if CLOCKWISE else "LEFT: ", plan["left"])
    print("3rd section, physical BOTTOM:", plan["bottom"])
    print("4th section, physical", "LEFT: " if CLOCKWISE else "RIGHT:", plan["right"])
    return plan


def angle_error(target, actual):
    return (target - actual + 180) % 360 - 180


class TwoCornerController:
    """Two mapped pillars: timed first left turn, heading hold, LiDAR-triggered red right/left.

    JSON defines COLOR and ORDER only. A front return is not necessarily a wall.
    This is a supervised low-speed experiment, not guaranteed obstacle clearance.
    """
    def __init__(self, plan):
        self.top_rg_wall_seen = False
        self.top_rg_wall_end_seen = False
        self.top_rg_open_count = 0
        self.plan = plan
        self.state = "APPROACH_1"
        self.started = time.monotonic()
        self.last_command = ("STOP", 0, 0, "Initializing")
        self.fault = None
        self.recovery_started = None
        self.recovery_side = None
        self.recovery_last_time = None
        self.section_label = "TOP"
        self.physical_section = "TOP"
        self.first_green_distance_override = None
        self.first_red_distance_override = None
        self.end_front_override = None
        self.turn_pwm_override = None
        self.turn_timeout_override = None
        self.rr_stop_front_override = None  # TOP RR handoff override for next LEFT corner
        self.top_rg_special = False
        self.top_rg_handoff_front = None
        self.top_rg_track_count = 0
        self.top_rg_left_first_red = False
        self.top_rg_right_offset_done = False
        self.left_rg_next_first_red = False  # LEFT RG -> BOTTOM first RED only
        self.left_rg_right_offset_done = False
        self.top_gg_to_left_red = False
        self.top_gg_to_left_green = False
        self.top_gg_right_offset_done = False
        self.green_left_start_yaw = None
        self.green_left_yaw_seen = False
        self.gg_open_scans = 0
        self.gg_wall_acquired = False
        self.gg_wall_acquire_scans = 0
        self.left_green_from_top_gg = False
        self.left_red_from_top_gg = False
        self.left_red_from_top_gr = False
        self.left_red_from_top_rr = False
        self.gg_turn_last_left = None
        self.gg_turn_last_left_at = None
        self.top_gr_special = False
        self.top_gr_handoff_front = None
        self.gr_right_start_yaw = None
        self.gr_right_yaw_seen = False
        self.gr_open_scans = 0
        self.post_corner_armed = False
        self.gg_lr_next_first_red = False
        self.gg_lr_open_scans = 0
        self.gg_lr_open_confirmed = False
        self.gg_lr_offset_done = False
        self.gg_lr_handoff_front = None

    def stop(self, reason):
        self.last_command = ("STOP", 0, 0, reason)
        return self.last_command

    def drive(self, steering, reason, speed=None, steering_limit=None):
        # Only a specifically authorized maneuver may exceed the default 30-degree limit.
        limit = MAX_STEERING_DEG if steering_limit is None else float(steering_limit)
        steering = int(round(max(-limit, min(limit, steering))))
        pwm = TEST_PWM if speed is None else int(speed)
        self.last_command = (f"DRIVE {steering} {pwm}", steering, pwm, reason)
        return self.last_command

    def confirm_rg_gr_front_wall(self, data, front, transition):
        """Require a geometrically broad LiDAR surface before a front-triggered
        RG/GR steering reversal. Never remove objects from collision checks.
        A YOLO detection or ambiguous range is NOT evidence of a wall.
        Returns a stop reason, or None after 3 distinct corroborating scans.
        """
        cam = getattr(self, "current_camera", None)
        fresh = (bool(cam) and cam.get("connected") and
                 time.monotonic() - cam.get("received_at", 0) <= CAMERA_MAX_AGE_S)
        key = (self.section_label, self.state, transition)
        if getattr(self, "wall_check_key", None) != key:
            self.wall_check_key = key
            self.wall_check_scans = 0
            self.wall_check_last_scan = None

        if not fresh:
            self.wall_check_scans = 0
            err = cam.get("error", "camera unavailable") if cam else "camera missing"
            return f"[WALL CHECK] {transition}: camera stale/offline ({err}); no automatic reversal"

        # The front LiDAR beam is only +/-1 degree, but a nearby pillar may
        # appear elsewhere in the forward image. This broad camera veto is
        # deliberately conservative and only applies to RG/GR reversal.
        forward_pillars = [d for d in cam.get("detections", [])
                           if d.get("color") in ("red", "green")
                           and d.get("angle_min", 999) <= 15
                           and d.get("angle_max", -999) >= -15]
        if forward_pillars:
            self.wall_check_scans = 0
            labels = ", ".join(f'{d["color"]}:{d.get("confidence", 0):.2f}'
                               for d in forward_pillars)
            return (f"[WALL CHECK] {transition}: YOLO pillar {labels} in forward view, "
                    f"front={front:.2f}m; do not interpret as wall")

        # Look for a broad, continuous frontal surface extending to BOTH sides
        # of the centre beam. A slender pillar typically lacks this support.
        angles = data.get("angles", [])
        distances = data.get("distances", [])
        if len(angles) != len(distances) or not angles:
            self.wall_check_scans = 0
            return f"[WALL CHECK] {transition}: no usable raw LiDAR geometry"
        side_samples = []
        for low, high in ((-12, -7), (7, 12)):
            values = [float(r) for a, r in zip(angles, distances)
                      if low <= a <= high and isinstance(r, (int, float))
                      and math.isfinite(r) and r > 0]
            if len(values) < 3:
                self.wall_check_scans = 0
                return f"[WALL CHECK] {transition}: insufficient side-angle scan support"
            values.sort()
            side_samples.append(values[len(values) // 2])
        lshoulder, rshoulder = side_samples
        # These are new verification criteria, NOT changes to any existing
        # steering/turn/range configuration parameters.
        if not (0.70 * front <= lshoulder <= 1.40 * front and
                0.70 * front <= rshoulder <= 1.40 * front):
            self.wall_check_scans = 0
            return (f"[WALL CHECK] {transition}: front={front:.2f}, "
                    f"shoulders={lshoulder:.2f}/{rshoulder:.2f}m; "
                    "not a confirmed broad wall (pillar/edge possible)")
        scan_id = data.get("received_at")
        if scan_id != self.wall_check_last_scan:
            self.wall_check_last_scan = scan_id
            self.wall_check_scans += 1
        if self.wall_check_scans < 3:
            return (f"[WALL CHECK] {transition}: broad surface confirmed "
                    f"{self.wall_check_scans}/3 LiDAR scans; STOP pending confirmation")
        return None

    def side_clearance_correction(self, front, left, right, front_left, now):
        """Override navigation briefly to steer AWAY from a near wall.

        Returns None if no correction is needed. Do not confuse a 0.15m
        LiDAR range with clearance of the car's wheels or rear corner.
        """
        valid = lambda x: x is not None and math.isfinite(x)
        # Start only when a measured side is BELOW the target band.
        # If a correction has already started, keep it until >= RELEASE.
        # This avoids treating an acceptable 0.18 m as a failure to reach 0.15 m.
        if self.recovery_side == "LEFT":
            if not valid(left):
                return self.stop("LEFT range lost during recovery")
            if left >= SIDE_AVOID_RELEASE:
                self.started += now - self.recovery_started
                self.recovery_started = None
                self.recovery_side = None
                return None
        elif self.recovery_side == "RIGHT":
            if not valid(right):
                return self.stop("RIGHT range lost during recovery")
            if right >= SIDE_AVOID_RELEASE:
                self.started += now - self.recovery_started
                self.recovery_started = None
                self.recovery_side = None
                return None

        # Camera-confirmed pillar at the matching side angle is NOT a wall.
        # Skip ONLY optional side-steering; keep the raw emergency STOP upstream.
        cam = getattr(self, "current_camera", None)
        if camera_pillar_in_sector(cam, 80, 90) or camera_pillar_in_sector(cam, -90, -80):
            return None
        left_near = valid(left) and left < SIDE_AVOID_ENTER
        right_near = valid(right) and right < SIDE_AVOID_ENTER
        if self.recovery_side is None:
            if not left_near and not right_near:
                return None
            if left_near and right_near:
                return self.stop("Both sides below side-entry distance; corridor not verified")
            self.recovery_side = "LEFT" if left_near else "RIGHT"
            self.recovery_started = now

        if not valid(front) or front < 0.35:
            return self.stop("Forward clearance insufficient for side correction")
        side = self.recovery_side
        measured = left if side == "LEFT" else right
        opposite = right if side == "LEFT" else left
        if not valid(opposite) or opposite < SIDE_OPPOSITE_MIN_M:
            return self.stop(f"{side} too near; opposite clearance unverified")
        if side == "LEFT" and valid(front_left) and front_left <= FRONT_STOP_DISTANCE:
            return self.stop("Front-left emergency clearance")
        if now - self.recovery_started > SIDE_RECOVERY_MAX_SECONDS:
            return self.stop(f"{side} recovery failed to reach {SIDE_AVOID_RELEASE:.2f}m; STOP")
        steer = SIDE_AVOID_STEER if side == "LEFT" else -SIDE_AVOID_STEER
        return self.drive(steer,
                          f"{side} {measured:.2f}m: steer {'RIGHT' if side == 'LEFT' else 'LEFT'} "
                          f"until >= {SIDE_AVOID_RELEASE:.2f}m [LiDAR-only, body clearance unverified]",
                          SIDE_AVOID_PWM)

    def straight_with_side_avoidance(self, front, left, right, nominal_steer, reason):
        # Side correction already checked in update before stage logic.
        return self.drive(nominal_steer, reason)

    def phase(self, name, now):
        self.state = name
        self.started = now
        # Never carry side-correction hysteresis across planned maneuvers.
        self.side_mode = None
        self.recovery_started = None
        self.recovery_side = None

    def first_turn_distance(self):
        """Get independent LiDAR turn threshold by section and first pillar color."""
        if self.plan[0] == "green" and self.first_green_distance_override is not None:
            return self.first_green_distance_override
        if self.plan[0] == "red" and self.first_red_distance_override is not None:
            return self.first_red_distance_override
        if self.plan[0] == "green":
            return (LEFT_GREEN_TURN_DISTANCE if self.section_label == "LEFT"
                    else TOP_GREEN_TURN_DISTANCE)
        return (LEFT_RED_TURN_DISTANCE if self.section_label == "LEFT"
                else TOP_RED_TURN_DISTANCE)

    def hold_heading(self, yaw, target=270.0):
        # Positive steering right, heading increases right on this BNO055 setup.
        error = angle_error(target, yaw)
        steering = HEADING_KP * error
        return int(round(max(-HEADING_STEERING_LIMIT, min(HEADING_STEERING_LIMIT, steering))))

    def finish_first_turn(self, now, yaw):
        # RG/GR in ALL four physical sections: finish corner, then drive STRAIGHT
        # until the second-pillar front range crosses 1.70 m. Avoid immediately
        # launching a swerve simply because the distance is already below threshold.
        if self.plan in (["red", "green"], ["green", "red"]):
            self.post_corner_armed = False
            self.phase("POST_CORNER_RG_GR_STRAIGHT", now)
            return self.stop(f"{self.section_label} {''.join(c[0].upper() for c in self.plan)} corner finished; straight toward 1.70m trigger")
        if self.plan[0] == "green" and self.plan[1] == "red":
            if self.section_label == "LEFT":
                self.phase("LEFT_GR_APPROACH", now)
                return self.stop("LEFT GR first GREEN turn settled; approach RED for RIGHT then LEFT")
            if self.section_label == "TOP" and self.top_gr_special:
                self.phase("GR_APPROACH", now)
                return self.stop("TOP GR first GREEN turn settled; approach RED for RIGHT then LEFT")
            self.phase("CLEAR_GREEN", now)
            return self.stop(f"First turn settled at {yaw:.1f}; next CLEAR_GREEN")
        # Both RED-first plans get their own second-pillar behavior.
        if self.plan[0] == "red" and self.plan[1] == "red":
            self.phase("RR_STRAIGHT", now)
            return self.stop(f"First RED turn complete at {yaw:.1f}; RED-RED straight to 0.50m")
        if self.plan[0] == "red" and self.plan[1] == "green":
            self.phase("RG_CLEAR_RED", now)
            return self.stop(f"First RED turn complete at {yaw:.1f}; short RED clearance before GREEN approach")
        if self.section_label == "LEFT" and self.plan == ["green", "green"]:
            self.phase("LEFT_GG_WALL_FOLLOW", now)
            return self.stop("LEFT GG first turn completed; follow LEFT wall like TOP GG")
        # TOP GREEN-GREEN is a wall-following corner approach, not a second
        # GREEN_LEFT/GREEN_RIGHT swerve. The LEFT pillar map chooses the turn.
        if self.section_label == "TOP" and (self.top_gg_to_left_red or self.top_gg_to_left_green):
            self.gg_open_scans = 0
            self.gg_wall_acquired = False
            self.gg_wall_acquire_scans = 0
            self.phase("GG_WALL_FOLLOW", now)
            return self.stop("TOP GG first turn complete; follow LEFT wall toward next corner")
        self.phase("APPROACH_2", now)
        return self.stop(f"First turn settled at {yaw:.1f}; next APPROACH_2")

    def update(self, data, yaw):
        now = time.monotonic()
        if self.fault:
            return self.stop(self.fault)
        if self.state == "DONE":
            return self.stop("Two-pillar test finished")
        if self.state == "BLOCKED_EXIT":
            return self.stop(self.fault or "RED_EXIT blocked; reposition and restart")
        if not data.get("connected") or now - data.get("received_at", 0) > SCAN_TIMEOUT:
            return self.stop("Stale LiDAR scan")
        front, left, right = (data.get(k) for k in ("front", "left", "right"))
        front_left = data.get("front_left")
        self.current_camera = data.get("camera")
        front_right_gr = data.get("front_right_gr")  # Narrow center sector; None if unavailable.

        def valid(value):
            return value is not None and math.isfinite(value)

        # No front reading means the forward path is unknown: STOP.
        if not valid(front):
            return self.stop("Missing front LiDAR: cannot assess forward clearance")

        # Missing side sectors are UNKNOWN, not an automatic collision and NOT free space.
        # Check the emergency threshold for every sector with a valid return.
        sectors = {"front": front,
                    "front_right_gr": front_right_gr, "left": left, "right": right,
                   "front_left": front_left}
        for sector, value in sectors.items():
            if valid(value) and value <= FRONT_STOP_DISTANCE:
                self.fault = (f"Emergency {sector}: {value:.3f}m <= "
                              f"{FRONT_STOP_DISTANCE:.3f}m")
                return self.stop(self.fault)

        # Prioritize proactive side correction during planned turns and straight
        # travel. Missing side data remains unknown, never assumed clear.
        # Don't override a stage transition or terminal state.
        if self.state in ("APPROACH_1", "CLEAR_GREEN", "APPROACH_2", "RED_EXIT", "RG_APPROACH"):
            # Check the second-GREEN arrival condition before any side-recovery
            # command can delay it. The actual transition is handled below.
            green_arrival = (self.state == "APPROACH_2" and
                             self.plan[1] == "green" and
                             front <= (TOP_GG_TO_LEFT_GREEN_SECOND_TRIGGER_M if self.top_gg_to_left_green
                                       else TOP_GG_TO_LEFT_RED_GREEN_TRIGGER_M if self.top_gg_to_left_red
                                       else SECOND_GREEN_TEST_FRONT_LIMIT))
            red_first_arrival = ((self.state == "RR_STRAIGHT" and front <= RED_RED_STOP_FRONT_M)
                                 or (self.state == "RG_APPROACH" and front <= RED_GREEN_START_FRONT_M))
            # Do not allow side correction to postpone a first-corner turn
            # that has already reached its LiDAR threshold.
            first_turn_arrival = (self.state == "APPROACH_1" and
                                  front <= self.first_turn_distance())
            if not (green_arrival or red_first_arrival or first_turn_arrival):
                correction = self.side_clearance_correction(front, left, right,
                                                            front_left, now)
                if correction is not None:
                    return correction

        # During a left/right steering maneuver require visibility on that side.
        # The +45-degree front-left sector is NOT a replacement for the +90 side sector.
        if self.state == "TURN_1" and not valid(left):
            if not valid(front_left) or front_left < TURN1_FRONT_LEFT_FALLBACK_MIN:
                return self.stop("TURN_1: left unknown and front-left fallback missing/too close")
            # First-turn fallback; cannot verify clearance beside the rear/side body.
            # Keep the original timed turn, front emergency stop, and heading checks.
        elif self.state == "RED_LEFT" and not valid(left):
            return self.stop("RED_LEFT: left side unknown; cannot verify recovery clearance")
        if self.state == "RED_RIGHT" and not valid(right):
            return self.stop("Right sector unknown while steering RIGHT")
        if self.state == "GREEN_LEFT" and not valid(left):
            return self.stop("Left sector unknown while steering LEFT")
        elif self.state == "GREEN_RIGHT" and not valid(right):
            return self.stop("GREEN_RIGHT: right side unknown; cannot verify recovery clearance")
        # Fail-stop also if heading sensor fails.
        if yaw is None or not math.isfinite(yaw):
            self.fault = "Invalid IMU heading"
            return self.stop(self.fault)

        # Shared RG/GR post-corner gate. TOP/BOTTOM and LEFT/RIGHT reuse
        # original second-pillar maneuvers, but never start them during TURN_SETTLE.
        if self.state == "POST_CORNER_RG_GR_STRAIGHT":
            err = angle_error(270.0, yaw)
            if abs(err) > POST_CORNER_RG_GR_HEADING_TOL_DEG:
                return self.stop(f"{self.section_label} post-corner heading off: virtual yaw={yaw:.1f}, err={err:+.1f}")
            if not valid(left) or not valid(right):
                return self.stop(f"{self.section_label} post-corner: side LiDAR unknown")
            threshold = (RIGHT_GR_START_FRONT_M if self.physical_section == "RIGHT"
                         and self.plan == ["green", "red"] else POST_CORNER_RG_GR_TRIGGER_M)
            # RIGHT GR requires a measured crossing of 1.50m on its narrow
            # central sector; broad front remains an independent safety input.
            right_gr = self.physical_section == "RIGHT" and self.plan == ["green", "red"]
            elapsed = now - self.started
            trigger_front = data.get("front_right_gr") if right_gr else front
            if right_gr and not valid(trigger_front):
                return self.stop("RIGHT GR central front sector missing; cannot verify 1.50m trigger")
            if right_gr and not self.post_corner_armed:
                if trigger_front >= RIGHT_GR_ARM_FRONT_M:
                    self.post_corner_armed = True
                    return self.drive(max(-6, min(6, self.hold_heading(yaw))),
                        f"RIGHT GR armed: central={trigger_front:.2f}m broad={front:.2f}m; straight to 1.50m",
                        POST_CORNER_RG_GR_PWM)
                self.fault = (f"RIGHT GR trigger was already missed after corner: "
                              f"central={trigger_front:.2f}m < {RIGHT_GR_ARM_FRONT_M:.2f}m; broad={front:.2f}m")
                return self.stop(self.fault)
            straight_min = (RIGHT_GR_MIN_STRAIGHT_S if right_gr
                            else POST_CORNER_RG_GR_MIN_STRAIGHT_S)
            if elapsed < straight_min:
                if front <= POST_CORNER_RG_GR_LATE_MIN_FRONT_M:
                    self.fault = (f"{self.section_label} post-corner too close to continue "
                                  f"straight: front={front:.2f}m")
                    return self.stop(self.fault)
                steer = max(-6, min(6, self.hold_heading(yaw)))
                return self.drive(steer,
                    f"{self.section_label} post-corner STRAIGHT "
                    f"{elapsed:.2f}/{straight_min:.2f}s; front={front:.2f}m",
                    POST_CORNER_RG_GR_PWM)
            if front < POST_CORNER_RG_GR_LATE_MIN_FRONT_M:
                self.fault = (f"{self.section_label} RG/GR second-pillar trigger missed: "
                              f"front={front:.2f}m < late minimum "
                              f"{POST_CORNER_RG_GR_LATE_MIN_FRONT_M:.2f}m")
                return self.stop(self.fault)
            if trigger_front <= threshold:
                if self.plan == ["red", "green"]:
                    if not valid(front_left) or front_left < TURN1_FRONT_LEFT_FALLBACK_MIN:
                        return self.stop(f"{self.section_label} RG front-left clearance unverified")
                    self.rg_start_yaw = yaw
                    self.rg_left_deviation_seen = False
                    next_state = "LEFT_RG_LEFT" if self.section_label == "LEFT" else "RG_LEFT"
                    self.phase(next_state, now)
                    return self.stop(f"{self.section_label} RG reached {front:.2f}m: begin LEFT swerve next cycle")
                min_right = (RIGHT_GR_RIGHT_MIN_SIDE_M if right_gr else
                             LEFT_GR_MIN_SIDE_M if self.section_label == "LEFT" else TOP_GR_MIN_SIDE_M)
                if right < min_right:
                    return self.stop(f"{self.section_label} GR RIGHT clearance unverified")
                self.gr_right_start_yaw = yaw
                self.gr_right_yaw_seen = False
                next_state = "LEFT_GR_RIGHT" if self.section_label == "LEFT" else "GR_RIGHT"
                self.phase(next_state, now)
                return self.stop(f"{self.section_label} GR trigger: central={trigger_front:.2f}m, broad={front:.2f}m; begin RIGHT next cycle")
            if front <= RED_GREEN_CLEAR_FRONT_GUARD_M:
                return self.stop(f"{self.section_label} post-corner forward obstacle")
            # Small heading corrections only; do not command a major avoidance turn.
            steer = max(-6, min(6, self.hold_heading(yaw)))
            return self.drive(steer,
                              f"{self.section_label} {''.join(c[0].upper() for c in self.plan)} "
                              f"post-corner STRAIGHT trigger_front={trigger_front:.2f}m, broad={front:.2f}m > {threshold:.2f}m",
                              POST_CORNER_RG_GR_PWM)

        # LEFT routes use the TOP steering concept with a virtual yaw target 270.
        # The physical target is 180; TOP sections never enter these named states.
        if self.section_label == "LEFT" and self.state == "LEFT_GG_WALL_FOLLOW":
            # Only LEFT GG -> BOTTOM RED and nonfinal RIGHT GG -> TOP RED.
            # A normal end-of-section distance cannot complete this path until
            # the opening and RIGHT pre-corner yaw offset are both verified.
            if self.gg_lr_next_first_red:
                if not valid(left) or not valid(right) or not valid(front_left):
                    return self.stop(f"{self.physical_section} GG RED: side/front-left unknown")
                if left >= GG_LR_RED_OPEN_M:
                    self.gg_lr_open_scans += 1
                else:
                    self.gg_lr_open_scans = 0
                if self.gg_lr_open_scans >= GG_LR_RED_OPEN_SCANS:
                    self.gg_lr_open_confirmed = True
                if front <= self.gg_lr_handoff_front:
                    return self.stop(f"{self.physical_section} GG -> RED reached handoff before RIGHT offset; "
                                     f"front={front:.2f}, opening={self.gg_lr_open_scans}/{GG_LR_RED_OPEN_SCANS}")
                # Initiate offset only after the wall gap is verified, and early
                # enough to leave room for the following RED first turn.
                if self.gg_lr_open_confirmed and front <= GG_LR_RED_BIAS_START_FRONT_M:
                    if front < GG_LR_RED_OPEN_MIN_FRONT_M:
                        return self.stop(f"{self.physical_section} GG RED offset too late at {front:.2f}m")
                    if right < GG_LR_RED_MIN_RIGHT_M or front_left < GG_LR_RED_MIN_FRONT_LEFT_M:
                        return self.stop(f"{self.physical_section} GG RED offset blocked: "
                                         f"right={right:.2f} front-left={front_left:.2f}")
                    self.phase("GG_LR_RED_RIGHT_BIAS", now)
                    return self.stop(f"{self.physical_section} GG -> next RED: opening verified; start RIGHT offset")
            elif front <= (self.end_front_override if self.end_front_override is not None else LEFT_GG_END_FRONT_M):
                self.phase("DONE", now)
                return self.stop("LEFT GG reached final section endpoint")
            if not valid(left) or not valid(right):
                return self.stop("LEFT GG wall-follow missing side sector")
            err = angle_error(270, yaw)
            if abs(err) > TOP_GG_WALL_MAX_HEADING_ERR_DEG:
                return self.stop("LEFT GG heading drift too large")
            steer = HEADING_KP * err
            if left <= TOP_GG_LEFT_OPEN_TRIGGER_M:
                diff = left - LEFT_GG_WALL_TARGET_M
                if abs(diff) > LEFT_GG_WALL_DEADBAND_M:
                    steer -= LEFT_GG_WALL_KP * diff
            steer = int(round(max(-LEFT_GG_WALL_MAX_STEER_DEG,
                                  min(LEFT_GG_WALL_MAX_STEER_DEG, steer))))
            if steer > 0 and right < TOP_GG_WALL_RIGHT_MIN_M:
                return self.stop("LEFT GG opposite RIGHT side too close")
            return self.drive(steer, "LEFT GG follow LEFT wall", LEFT_GG_WALL_PWM)

        if self.section_label == "LEFT" and self.state == "GG_LR_RED_RIGHT_BIAS":
            # Virtual heading is 270 in LEFT and RIGHT wall-following controllers.
            # The physical IMU is not reset when sections change.
            target = (270.0 + GG_LR_RED_RIGHT_OFFSET_DEG) % 360.0
            err = angle_error(target, yaw)
            if abs(err) <= GG_LR_RED_RIGHT_TOL_DEG:
                self.gg_lr_offset_done = True
                self.phase("GG_LR_RED_APPROACH", now)
                return self.stop(f"{self.physical_section} GG RIGHT offset completed: virtual yaw {yaw:.1f}")
            if now - self.started > GG_LR_RED_RIGHT_TIMEOUT_S or err < 0:
                self.fault = f"{self.physical_section} GG RIGHT bias timeout/overshoot: yaw {yaw:.1f}"
                return self.stop(self.fault)
            if (front < GG_LR_RED_OPEN_MIN_FRONT_M or not valid(left) or not valid(right)
                or not valid(front_left) or left < GG_LR_RED_MIN_LEFT_M
                or right < GG_LR_RED_MIN_RIGHT_M or front_left < GG_LR_RED_MIN_FRONT_LEFT_M):
                return self.stop(f"{self.physical_section} GG RIGHT bias unsafe: "
                                 f"front={front:.2f}, left={left}, right={right}, front-left={front_left}")
            return self.drive(GG_LR_RED_RIGHT_STEER_DEG,
                f"{self.physical_section} GG -> RED pre-corner RIGHT target={target:.1f}, yaw={yaw:.1f}",
                GG_LR_RED_RIGHT_PWM)

        if self.section_label == "LEFT" and self.state == "GG_LR_RED_APPROACH":
            if not self.gg_lr_offset_done or not self.gg_lr_open_confirmed:
                self.fault = f"{self.physical_section} GG RED: pre-corner offset/opening unconfirmed"
                return self.stop(self.fault)
            target = (270.0 + GG_LR_RED_RIGHT_OFFSET_DEG) % 360.0
            if abs(angle_error(target, yaw)) > GG_LR_RED_APPROACH_MAX_YAW_ERR_DEG:
                return self.stop(f"{self.physical_section} GG RED: offset heading lost")
            if (not valid(left) or not valid(right) or not valid(front_left)
                or left < GG_LR_RED_MIN_LEFT_M or right < GG_LR_RED_MIN_RIGHT_M
                or front_left < GG_LR_RED_MIN_FRONT_LEFT_M):
                return self.stop(f"{self.physical_section} GG RED approach clearance unverified: "
                                 f"left={left}, right={right}, front-left={front_left}")
            if front <= self.gg_lr_handoff_front:
                self.phase("DONE", now)
                return self.stop(f"{self.physical_section} GG -> next RED handoff at {front:.2f}m "
                                 f"after verified RIGHT yaw offset")
            return self.drive(self.hold_heading(yaw, target),
                f"{self.physical_section} GG RED heading-offset approach "
                f"front={front:.2f}, handoff={self.gg_lr_handoff_front:.2f}",
                GG_LR_RED_RIGHT_PWM)

        if self.section_label == "LEFT" and self.state == "LEFT_GR_APPROACH":
            if abs(angle_error(270, yaw)) > 25:
                return self.stop("LEFT GR approach heading drift")
            if front <= LEFT_GR_RIGHT_START_FRONT_M:
                if not valid(right) or right < LEFT_GR_MIN_SIDE_M or not valid(left):
                    return self.stop("LEFT GR RIGHT trigger: side range unverified")
                self.gr_right_start_yaw = yaw
                self.gr_right_yaw_seen = False
                self.phase("LEFT_GR_RIGHT", now)
                return self.stop("LEFT GR front trigger: begin RIGHT steering")
            return self.drive(self.hold_heading(yaw), "LEFT GR approach RED", LEFT_GR_MANEUVER_PWM)

        if self.section_label == "LEFT" and self.state == "LEFT_GR_RIGHT":
            if self.physical_section == "RIGHT" and (not valid(right) or right < RIGHT_GR_RIGHT_MIN_SIDE_M):
                self.fault = (f"RIGHT GR abort RIGHT swerve: right LiDAR {right}m "
                              f"below {RIGHT_GR_RIGHT_MIN_SIDE_M:.2f}m minimum")
                return self.stop(self.fault)
            deviation = angle_error(yaw, self.gr_right_start_yaw)
            if deviation >= LEFT_GR_MIN_YAW_DEVIATION_DEG:
                self.gr_right_yaw_seen = True
            if deviation > LEFT_GR_MAX_YAW_DEVIATION_DEG:
                self.fault = "LEFT GR excessive RIGHT yaw deviation"
                return self.stop(self.fault)
            if front <= LEFT_GR_RIGHT_SWITCH_FRONT_M:
                wall_issue = self.confirm_rg_gr_front_wall(
                    data, front, f"{self.section_label}/{self.state} reversal")
                if wall_issue is not None:
                    return self.stop(wall_issue)
                if not self.gr_right_yaw_seen or not valid(left) or left < LEFT_GR_MIN_SIDE_M:
                    return self.stop("LEFT GR LEFT-recovery clearance/yaw unverified")
                self.phase("LEFT_GR_LEFT_RECOVER", now)
                return self.stop("LEFT GR front wall reached: switch RIGHT -> LEFT")
            if now - self.started > LEFT_GR_RIGHT_MAX_SECONDS:
                self.fault = "LEFT GR RIGHT steering timeout"
                return self.stop(self.fault)
            if not valid(right) or right < LEFT_GR_MIN_SIDE_M:
                return self.stop("LEFT GR RIGHT side unverified")
            return self.drive(LEFT_GR_RIGHT_STEER_DEG, "LEFT GR RIGHT toward front wall",
                              LEFT_GR_MANEUVER_PWM, steering_limit=LEFT_GR_RIGHT_STEER_DEG)

        if self.section_label == "LEFT" and self.state == "LEFT_GR_LEFT_RECOVER":
            if abs(angle_error(270, yaw)) <= LEFT_GR_RECOVERY_HEADING_TOL_DEG:
                self.phase("LEFT_GR_FOLLOW_RIGHT", now)
                return self.stop("LEFT GR recovered toward physical yaw 180; follow RIGHT wall")
            if now - self.started > LEFT_GR_LEFT_MAX_SECONDS:
                self.fault = "LEFT GR LEFT recovery timeout"
                return self.stop(self.fault)
            if not valid(left) or left < LEFT_GR_MIN_SIDE_M:
                return self.stop("LEFT GR LEFT side unverified")
            return self.drive(LEFT_GR_LEFT_RECOVER_STEER_DEG, "LEFT GR LEFT heading recovery",
                              LEFT_GR_MANEUVER_PWM, steering_limit=abs(LEFT_GR_LEFT_RECOVER_STEER_DEG))

        if self.section_label == "LEFT" and self.state == "LEFT_GR_FOLLOW_RIGHT":
            if front <= (self.end_front_override if self.end_front_override is not None else LEFT_GR_END_FRONT_M):
                self.phase("DONE", now)
                return self.stop("LEFT GR endpoint reached")
            if now - self.started > LEFT_GR_FOLLOW_MAX_SECONDS:
                self.fault = "LEFT GR RIGHT-wall-follow timeout"
                return self.stop(self.fault)
            if not valid(left) or not valid(right):
                return self.stop("LEFT GR wall-follow sectors missing")
            err = angle_error(270, yaw)
            steer = LEFT_GR_RIGHT_WALL_HEADING_KP * err
            if right <= LEFT_GR_RIGHT_WALL_TRACK_MAX_M:
                steer += LEFT_GR_RIGHT_WALL_KP * (right - LEFT_GR_RIGHT_WALL_TARGET_M)
            steer = int(round(max(-LEFT_GR_RIGHT_WALL_STEER_MAX,
                                  min(LEFT_GR_RIGHT_WALL_STEER_MAX, steer))))
            if steer < 0 and left < RR_MIN_OPPOSITE_M:
                return self.stop("LEFT GR follow: opposite side too close")
            return self.drive(steer, "LEFT GR follow RIGHT wall", LEFT_GR_FOLLOW_PWM)

        if self.section_label == "LEFT" and self.state == "LEFT_RG_LEFT":
            if front <= LEFT_RG_LEFT_SWITCH_FRONT_M:
                wall_issue = self.confirm_rg_gr_front_wall(
                    data, front, f"{self.section_label}/{self.state} reversal")
                if wall_issue is not None:
                    return self.stop(wall_issue)
                if not valid(right) or right <= FRONT_STOP_DISTANCE:
                    return self.stop("LEFT RG switch RIGHT clearance unverified")
                self.phase("LEFT_RG_RIGHT", now)
                return self.stop("LEFT RG front wall reached: switch LEFT -> RIGHT")
            if now - self.started > LEFT_RG_LEFT_MAX_SECONDS:
                self.fault = "LEFT RG LEFT front-switch timeout"
                return self.stop(self.fault)
            if not valid(left) or left <= FRONT_STOP_DISTANCE:
                return self.stop("LEFT RG LEFT side unverified")
            return self.drive(-LEFT_RG_LEFT_STEER_DEG, "LEFT RG LEFT until front wall",
                              LEFT_RG_MANEUVER_PWM, steering_limit=LEFT_RG_LEFT_STEER_DEG)

        if self.section_label == "LEFT" and self.state == "LEFT_RG_RIGHT":
            elapsed = now - self.started
            if (elapsed >= LEFT_RG_RIGHT_MIN_SECONDS and
                    abs(angle_error(270, yaw)) <= LEFT_RG_RECOVERY_TOLERANCE_DEG):
                if self.left_rg_next_first_red:
                    self.phase("LEFT_RG_PRECORNER_RIGHT", now)
                    return self.stop(
                        "LEFT RG recovered to physical yaw 180; next BOTTOM first RED: "
                        "prepare small RIGHT offset before LEFT corner")
                self.phase("LEFT_RG_FOLLOW_LEFT", now)
                return self.stop("LEFT RG RIGHT recovered to physical yaw 180")
            if elapsed > LEFT_RG_RIGHT_MAX_SECONDS:
                self.fault = "LEFT RG RIGHT recovery timeout"
                return self.stop(self.fault)
            if not valid(right) or right <= FRONT_STOP_DISTANCE:
                return self.stop("LEFT RG RIGHT side unverified")
            return self.drive(LEFT_RG_RIGHT_STEER_DEG, "LEFT RG RIGHT heading recovery",
                              LEFT_RG_MANEUVER_PWM, steering_limit=LEFT_RG_RIGHT_STEER_DEG)

        if self.section_label == "LEFT" and self.state == "LEFT_RG_PRECORNER_RIGHT":
            # LEFT RG -> BOTTOM first RED only. Reuse the already-working TOP RG
            # pre-corner offset settings; all numerical parameters stay unchanged.
            # Virtual 270 -> 277 corresponds to physical 180 -> 187 on LEFT.
            target = 270.0 + TOP_RG_TO_LEFT_RED_RIGHT_OFFSET_DEG
            err = angle_error(target, yaw)
            if abs(err) <= TOP_RG_TO_LEFT_RED_TARGET_TOL_DEG:
                self.left_rg_right_offset_done = True
                self.phase("LEFT_RG_FOLLOW_LEFT", now)
                return self.stop(
                    f"LEFT RG -> BOTTOM RED right offset complete, virtual yaw={yaw:.1f}; "
                    "approach next corner before existing LEFT turn")
            if now - self.started > TOP_RG_TO_LEFT_RED_OFFSET_TIMEOUT_S:
                self.fault = f"LEFT RG pre-corner RIGHT offset timeout at yaw={yaw:.1f}"
                return self.stop(self.fault)
            if err < 0:
                self.fault = f"LEFT RG pre-corner RIGHT offset overshot yaw={yaw:.1f}"
                return self.stop(self.fault)
            if (not valid(right) or right < TOP_RG_TO_LEFT_RED_RIGHT_CLEARANCE_M
                    or not valid(left) or left < TOP_RG_TO_LEFT_RED_LEFT_CLEARANCE_M
                    or front < TOP_RG_TO_LEFT_RED_MIN_FRONT_M):
                return self.stop(
                    f"LEFT RG pre-corner RIGHT blocked: front={front:.2f}, "
                    f"left={left}, right={right}; inspect full-body clearance")
            return self.drive(
                TOP_RG_TO_LEFT_RED_RIGHT_STEER_DEG,
                f"LEFT RG -> BOTTOM RED: small RIGHT bias toward yaw {target:.1f}, now {yaw:.1f}",
                TOP_RG_TO_LEFT_RED_OFFSET_PWM)

        if self.section_label == "LEFT" and self.state == "LEFT_RG_FOLLOW_LEFT":
            if front <= (self.end_front_override if self.end_front_override is not None else LEFT_RG_END_FRONT_M) and valid(left) and left >= LEFT_RG_END_LEFT_OPEN_M:
                self.phase("DONE", now)
                return self.stop("LEFT RG endpoint reached with LEFT opening")
            if now - self.started > LEFT_RG_FOLLOW_MAX_SECONDS:
                self.fault = "LEFT RG LEFT-wall-follow timeout"
                return self.stop(self.fault)
            if not valid(left) or not valid(right):
                return self.stop("LEFT RG follow sectors missing")
            # Keep the small pre-corner RIGHT heading offset when the NEXT
            # section starts with RED; otherwise preserve original wall follow.
            heading_target = (270.0 + TOP_RG_TO_LEFT_RED_RIGHT_OFFSET_DEG
                              if self.left_rg_next_first_red and self.left_rg_right_offset_done
                              else 270.0)
            err = angle_error(heading_target, yaw)
            steer = LEFT_RG_LEFT_WALL_HEADING_KP * err
            if not (self.left_rg_next_first_red and self.left_rg_right_offset_done):
                if left <= LEFT_RG_LEFT_WALL_MAX_TRACK_M:
                    diff = left - LEFT_RG_LEFT_WALL_TARGET_M
                    if abs(diff) > LEFT_RG_LEFT_WALL_DEADBAND_M:
                        steer -= LEFT_RG_LEFT_WALL_KP * diff
            steer = int(round(max(-LEFT_RG_LEFT_WALL_MAX_STEER,
                                  min(LEFT_RG_LEFT_WALL_MAX_STEER, steer))))
            if steer > 0 and right < RR_MIN_OPPOSITE_M:
                return self.stop("LEFT RG follow: opposite RIGHT side too close")
            return self.drive(steer, "LEFT RG follow LEFT wall", LEFT_RG_FOLLOW_PWM)

        if self.state == "APPROACH_1":
            if abs(angle_error(0, yaw)) > 25:
                self.fault = "Unexpected heading before first turn"
                return self.stop(self.fault)
            color = self.plan[0]
            distance = self.first_turn_distance()
            if front <= distance:
                print(f"[TURN TRIGGER] section={self.section_label} "
                      f"color={color} front={front:.3f}m "
                      f"threshold={distance:.3f}m virtual_yaw={yaw:.1f}")
                self.phase("TURN_1", now)
                return self.stop(
                    f"[TURN TRIGGER] {self.section_label} {color} "
                    f"front={front:.3f}m <= {distance:.3f}m; turn next cycle")
            return self.straight_with_side_avoidance(
                front, left, right, 0,
                f"Approach pillar 1 {color}; front trigger {distance:.2f}m")

        if self.state == "TURN_1":
            # Complete the first turn from IMU yaw, not from a fixed timer.
            # This assumes verified LEFT steering decreases relative heading.
            elapsed = now - self.started
            err = abs(angle_error(FIRST_TURN_TARGET, yaw))
            if err <= FIRST_TURN_REACHED_TOLERANCE:
                self.phase("TURN_SETTLE", now)
                return self.stop(f"IMU reached first turn target: yaw={yaw:.1f}; settling")
            turn_timeout = (RRRR_LEFT_CORNER_TIMEOUT_S if self.left_red_from_top_rr
                            else TOP_GG_GR_LEFT_RED_TURN_MAX_SECONDS
                            if (self.left_red_from_top_gg or self.left_red_from_top_gr)
                            else self.turn_timeout_override if self.turn_timeout_override is not None
                            else FIRST_TURN_MAX_SECONDS)
            if elapsed >= turn_timeout:
                physical_yaw = ((yaw - 90.0) % 360.0 if self.section_label == "LEFT"
                                else yaw)
                physical_target = (180.0 if self.section_label == "LEFT" else 270.0)
                self.fault = (f"{self.section_label} first LEFT turn timed out after "
                              f"{elapsed:.2f}s: physical yaw={physical_yaw:.1f} "
                              f"(target {physical_target:.0f}), virtual yaw={yaw:.1f} "
                              f"(target 270). Check turn actuation and range stops")
                return self.stop(self.fault)
            # Do not continue rotating left after overshooting below 270 degrees.
            signed = angle_error(FIRST_TURN_TARGET, yaw)
            if signed > 0 and yaw < FIRST_TURN_TARGET - FIRST_TURN_REACHED_TOLERANCE:
                self.phase("TURN_SETTLE", now)
                return self.stop(f"First turn overshot yaw={yaw:.1f}; settling before adjustment")
            if not valid(left) and (not valid(front_left) or
                                    front_left < TURN1_FRONT_LEFT_FALLBACK_MIN):
                return self.stop("TURN_1: no verified left/front-left space")
            # Stronger steering only for the LEFT section's first GREEN pillar.
            special_green = (self.section_label == "LEFT" and self.plan[0] == "green")
            turn_steer = (RRRR_LEFT_CORNER_STEER_DEG if self.left_red_from_top_rr
                          else TOP_GG_LEFT_RED_TURN_STEER_DEG if (self.left_red_from_top_gg or self.left_red_from_top_gr)
                          else LEFT_GREEN_FIRST_TURN_STEER_DEG if special_green
                          else MAX_STEERING_DEG)
            # GG-specific corner constraints must not alter the previously tested
            # TOP RED->GREEN -> LEFT GREEN path. All generic emergency checks above
            # remain active for every plan.
            if special_green and self.left_green_from_top_gg:
                # During the LEFT turn the +90 LiDAR sector can become open or
                # return no valid sample. A very short dropout is tolerated only
                # after a genuinely valid LEFT reading, with simultaneous valid
                # front/front-left/right measurements. Never replace None with
                # an arbitrary large distance.
                if valid(left):
                    self.gg_turn_last_left = left
                    self.gg_turn_last_left_at = now
                left_recently_verified = (
                    self.gg_turn_last_left_at is not None
                    and now - self.gg_turn_last_left_at <= TOP_GG_TURN_LEFT_DROPOUT_MAX_S
                    and self.gg_turn_last_left is not None
                    and self.gg_turn_last_left >= TOP_GG_TURN_LAST_LEFT_MIN_M
                )
                dropout_ok = (
                    not valid(left) and left_recently_verified
                    and front >= TOP_GG_TURN_FRONT_DROPOUT_MIN_M
                    and valid(front_left)
                    and front_left >= TOP_GG_TURN_FRONT_LEFT_DROPOUT_MIN_M
                    and valid(right) and right >= TOP_GG_TURN_RIGHT_DROPOUT_MIN_M
                )
                # Around physical yaw 205..180 the front-left sector sweeps
                # toward the side wall. Use a different guarded test only
                # after substantial verified left-turn progress, never earlier.
                physical_yaw = (yaw - 90.0) % 360.0
                late_turn = (self.section_label == "LEFT"
                             and 180.0 <= physical_yaw <= TOP_GG_GREEN_LATE_START_PHYSICAL_YAW_DEG)
                late_clear = (late_turn
                              and valid(left) and left >= TOP_GG_GREEN_LATE_LEFT_MIN_M
                              and valid(front_left)
                              and front_left >= TOP_GG_GREEN_LATE_FRONT_LEFT_MIN_M
                              and valid(right) and right >= TOP_GG_GREEN_LATE_RIGHT_MIN_M)
                # Earlier logs showed RIGHT 0.13-0.14 m while turning.
                # A sector return this close must not be treated as clear.
                if not valid(right) or right < TOP_GG_GREEN_TURN_RIGHT_HARD_MIN_M:
                    self.fault = (f"TOP GG LEFT GREEN: RIGHT sector too close or missing "
                                  f"({right}); cannot validate turn envelope")
                    return self.stop(self.fault)
                normal_clear = (valid(right) and right >= TOP_GG_GREEN_CORNER_RIGHT_MIN_M
                                and valid(front_left)
                                and front_left >= TOP_GG_GREEN_CORNER_FRONT_LEFT_MIN_M
                                and ((valid(left) and left >= TOP_GG_GREEN_CORNER_LEFT_MIN_M)
                                     or dropout_ok))
                if not (late_clear or normal_clear):
                    physical_yaw = (yaw - 90.0) % 360.0
                    age = (now - self.gg_turn_last_left_at
                           if self.gg_turn_last_left_at is not None else None)
                    self.fault = (
                        f"TOP GG -> LEFT GREEN corner clearance blocked: "
                        f"left={left}, last_left={self.gg_turn_last_left}, "
                        f"last_left_age={age}, front-left={front_left}, "
                        f"right={right}; physical yaw={physical_yaw:.1f}, "
                        f"virtual yaw={yaw:.1f}, late_turn={late_turn}. "
                        "Inspect turning envelope")
                    return self.stop(self.fault)
                if dropout_ok:
                    return self.drive(-turn_steer,
                        f"TOP GG LEFT GREEN: brief missing LEFT sector "
                        f"({now - self.gg_turn_last_left_at:.2f}s), "
                        f"last verified {self.gg_turn_last_left:.2f}m; "
                        f"physical yaw={(yaw - 90.0) % 360.0:.1f}",
                        speed=TOP_GG_GREEN_TURN_PWM, steering_limit=turn_steer)
            return self.drive(-turn_steer,
                              f"First LEFT turn using IMU: virtual yaw={yaw:.1f}, target=270 "
                              f"(physical target=180), steer=-{turn_steer:.0f}, "
                              f"elapsed={elapsed:.2f}s",
                              speed=(RRRR_LEFT_CORNER_PWM if self.left_red_from_top_rr
                                     else TOP_GG_GREEN_TURN_PWM if self.left_green_from_top_gg
                                     else TOP_GG_LEFT_RED_TURN_PWM if (self.left_red_from_top_gg or self.left_red_from_top_gr)
                                     else self.turn_pwm_override if self.turn_pwm_override is not None
                                     else TURN_PWM),
                              steering_limit=turn_steer)

        if self.state == "TURN_SETTLE":
            if now - self.started < TURN_SETTLE_SECONDS:
                return self.stop(f"Settling first turn; yaw={yaw:.1f}")
            error = angle_error(270.0, yaw)
            if abs(error) > FIRST_HEADING_MAX_ERROR:
                self.fault = (f"First turn heading outside recovery range: yaw={yaw:.1f}, "
                              f"error={error:.1f}; reposition required")
                return self.stop(self.fault)
            if abs(error) <= FIRST_TURN_REACHED_TOLERANCE:
                return self.finish_first_turn(now, yaw)
            self.phase("TURN_FINE", now)
            return self.stop(f"Fine adjustment needed: yaw={yaw:.1f}, error={error:.1f}")

        if self.state == "TURN_FINE":
            error = angle_error(270.0, yaw)
            if abs(error) <= FIRST_TURN_REACHED_TOLERANCE:
                return self.finish_first_turn(now, yaw)
            if now - self.started > TURN_FINE_TIMEOUT:
                self.fault = f"Fine turn timeout: yaw={yaw:.1f}, error={error:.1f}"
                return self.stop(self.fault)
            if front < TURN_FINE_MIN_FRONT:
                return self.stop(f"Fine turn paused: front only {front:.2f}m")
            # Positive heading error => right steering; negative => left steering.
            # Require visible clearance in the direction of the planned correction.
            if error < 0:
                if not valid(left) or left < TURN_FINE_SIDE_MIN:
                    return self.stop("Fine LEFT turn paused: left side not verified clear")
                steering = -TURN_FINE_STEER
            else:
                if not valid(right) or right < TURN_FINE_SIDE_MIN:
                    return self.stop("Fine RIGHT turn paused: right side not verified clear")
                steering = TURN_FINE_STEER
            return self.drive(steering,
                              f"Fine heading correction to 270: yaw={yaw:.1f}, error={error:.1f}",
                              TURN_FINE_PWM)

        # Dedicated TOP GREEN->RED path. Do not change TOP RED->GREEN or GG modes.
        if self.top_gr_special and self.state == "GR_APPROACH":
            if abs(angle_error(270.0, yaw)) > 25:
                self.fault = f"TOP GR approach heading drift: yaw={yaw:.1f}"
                return self.stop(self.fault)
            if front <= TOP_GR_RIGHT_START_FRONT_M:
                if front < 0.85:
                    self.fault = f"TOP GR RIGHT trigger too late: front={front:.2f}m"
                    return self.stop(self.fault)
                if not valid(right) or right < TOP_GR_MIN_SIDE_M or not valid(left):
                    return self.stop("TOP GR RIGHT trigger: side range not verified")
                self.gr_right_start_yaw = yaw
                self.gr_right_yaw_seen = False
                self.phase("GR_RIGHT", now)
                return self.stop(f"TOP GR RED detected front={front:.2f}; begin RIGHT swerve")
            if not valid(left) or not valid(right):
                return self.stop("TOP GR approach: missing side sector")
            return self.drive(self.hold_heading(yaw),
                f"TOP GR approach RED trigger {TOP_GR_RIGHT_START_FRONT_M:.2f}m front={front:.2f}",
                TOP_GR_MANEUVER_PWM)

        if self.top_gr_special and self.state == "GR_RIGHT":
            deviation = angle_error(yaw, self.gr_right_start_yaw)
            if deviation >= TOP_GR_MIN_YAW_DEVIATION_DEG:
                self.gr_right_yaw_seen = True
            if deviation > TOP_GR_MAX_YAW_DEVIATION_DEG:
                self.fault = f"TOP GR RIGHT excessive yaw change {deviation:.1f}deg"
                return self.stop(self.fault)
            if front <= TOP_GR_RIGHT_SWITCH_FRONT_M:
                wall_issue = self.confirm_rg_gr_front_wall(
                    data, front, f"{self.section_label}/{self.state} reversal")
                if wall_issue is not None:
                    return self.stop(wall_issue)
                if not self.gr_right_yaw_seen:
                    self.fault = "TOP GR front switch reached before confirmed RIGHT yaw"
                    return self.stop(self.fault)
                if not valid(left) or left < TOP_GR_MIN_SIDE_M:
                    return self.stop("TOP GR LEFT recovery: left clearance unavailable")
                self.phase("GR_LEFT_RECOVER", now)
                return self.stop(f"TOP GR RIGHT->LEFT at front={front:.2f}m yaw={yaw:.1f}")
            if now-self.started > TOP_GR_RIGHT_MAX_SECONDS:
                self.fault = f"TOP GR RIGHT timeout front={front:.2f}m yaw={yaw:.1f}"
                return self.stop(self.fault)
            if front < TOP_GR_MIN_FRONT_M or not valid(right) or right < TOP_GR_MIN_SIDE_M:
                return self.stop(f"TOP GR RIGHT clearance blocked: front={front}, right={right}")
            return self.drive(TOP_GR_RIGHT_STEER_DEG,
                f"TOP GR RIGHT until front <= {TOP_GR_RIGHT_SWITCH_FRONT_M:.2f}m; now {front:.2f}m",
                TOP_GR_MANEUVER_PWM, steering_limit=TOP_GR_RIGHT_STEER_DEG)

        if self.top_gr_special and self.state == "GR_LEFT_RECOVER":
            if abs(angle_error(270.0, yaw)) <= TOP_GR_RECOVERY_HEADING_TOL_DEG:
                self.gr_open_scans = 0
                self.phase("GR_FOLLOW_RIGHT", now)
                return self.stop(f"TOP GR LEFT recovered to yaw={yaw:.1f}; follow outer RIGHT wall")
            if now-self.started > TOP_GR_LEFT_MAX_SECONDS:
                self.fault = f"TOP GR LEFT recovery timeout yaw={yaw:.1f}"
                return self.stop(self.fault)
            # Refuse recovery if the yaw has gone past the desired heading.
            if angle_error(270.0, yaw) > 0:
                return self.stop(f"TOP GR recovery yaw overshot 270: {yaw:.1f}; needs reposition")
            if not valid(left) or left < TOP_GR_MIN_SIDE_M or front < TOP_GR_MIN_FRONT_M:
                return self.stop(f"TOP GR LEFT recovery clearance unverified left={left}, front={front}")
            return self.drive(TOP_GR_LEFT_RECOVER_STEER_DEG,
                f"TOP GR LEFT recover heading to 270; yaw={yaw:.1f}",
                TOP_GR_MANEUVER_PWM, steering_limit=abs(TOP_GR_LEFT_RECOVER_STEER_DEG))

        if self.top_gr_special and self.state == "GR_FOLLOW_RIGHT":
            if now-self.started > TOP_GR_FOLLOW_MAX_SECONDS:
                self.fault = "TOP GR follow RIGHT wall timeout before LEFT corner"
                return self.stop(self.fault)
            heading_err = angle_error(270.0, yaw)
            if abs(heading_err) > 22:
                self.fault = f"TOP GR follow heading deviation {heading_err:.1f}deg"
                return self.stop(self.fault)
            if not valid(left) or not valid(right) or not valid(front_left):
                return self.stop("TOP GR wall follow: LiDAR sectors missing")
            if left > TOP_GR_LEFT_OPEN_M:
                self.gr_open_scans += 1
            else:
                self.gr_open_scans = 0
            if front <= self.top_gr_handoff_front:
                if (self.gr_open_scans >= TOP_GR_OPEN_SCANS
                    and front_left >= TOP_GR_CORNER_FRONT_LEFT_MIN_M
                    and right >= TOP_GR_CORNER_RIGHT_MIN_M):
                    self.phase("DONE", now)
                    return self.stop(f"TOP GR corner confirmed front={front:.2f}, LEFT open {left:.2f}; handoff")
                return self.stop(f"TOP GR corner pending LEFT opening: front={front:.2f}m, "
                    f"left={left:.2f}m, scans={self.gr_open_scans}/{TOP_GR_OPEN_SCANS}")
            if front < TOP_GR_MIN_FRONT_M or left < TOP_GR_MIN_SIDE_M:
                return self.stop("TOP GR follow: forward/left clearance insufficient")
            if right > TOP_GR_RIGHT_WALL_TRACK_MAX_M:
                steer = TOP_GR_RIGHT_WALL_HEADING_KP * heading_err
            else:
                steer = (TOP_GR_RIGHT_WALL_HEADING_KP*heading_err
                    + TOP_GR_RIGHT_WALL_KP*(right-TOP_GR_RIGHT_WALL_TARGET_M))
            steer = int(round(max(-TOP_GR_RIGHT_WALL_STEER_MAX,
                                  min(TOP_GR_RIGHT_WALL_STEER_MAX, steer))))
            if steer < 0 and left < 0.22:
                return self.stop("TOP GR follow: LEFT opposite side too close for steering")
            return self.drive(steer, f"TOP GR outer RIGHT wall follow right={right:.2f}, "
                f"left={left:.2f}, front={front:.2f}, yaw={yaw:.1f}", TOP_GR_FOLLOW_PWM)

        if self.state == "CLEAR_GREEN":
            elapsed = now - self.started
            if abs(angle_error(270, yaw)) > 35:
                self.fault = "Excess heading drift while clearing green pillar"
                return self.stop(self.fault)
            if front <= GREEN_CLEAR_FRONT_GUARD:
                self.fault = (f"Green clearance forward blocked: front {front:.2f}m "
                              f"<= {GREEN_CLEAR_FRONT_GUARD:.2f}m")
                return self.stop(self.fault)
            if elapsed >= GREEN_CLEAR_STRAIGHT_SECONDS:
                self.phase("APPROACH_2", now)
                return self.stop("Green forward segment complete; now check second red pillar")
            # Keep the wheels close to straight to avoid cutting back toward GREEN.
            # The emergency LiDAR checks at the top of update still apply.
            steer = self.hold_heading(yaw)
            steer = max(-6, min(6, steer))
            if valid(left) and left < SIDE_AVOID_ENTER:
                steer = max(0, steer)
            if valid(right) and right < SIDE_AVOID_ENTER:
                steer = min(0, steer)
            return self.drive(steer,
                              f"CLEAR_GREEN straight {elapsed:.2f}/{GREEN_CLEAR_STRAIGHT_SECONDS:.2f}s "
                              f"before red right turn; yaw={yaw:.1f}", GREEN_CLEAR_PWM)

        # RED -> RED ONLY: follow the RIGHT wall (RIGHT section has its own 0.40 m target).
        # This replaces the previous yaw-only straight drive in RR_STRAIGHT.
        if self.state == "RR_STRAIGHT":
            # TOP RR hands off early according to LEFT first pillar color.
            # All other RR configurations preserve their original stop distance.
            rr_stop_front = (self.end_front_override if self.end_front_override is not None
                             else self.rr_stop_front_override
                             if self.rr_stop_front_override is not None
                             else RED_RED_STOP_FRONT_M)
            if front <= rr_stop_front:
                self.phase("DONE", now)
                return self.stop(f"RED-RED: front {front:.2f}m <= {rr_stop_front:.2f}m; "
                                 "section handoff / endpoint reached")
            heading_err = angle_error(270.0, yaw)
            if abs(heading_err) > RR_MAX_HEADING_ERROR:
                self.fault = (f"RED-RED: heading drift {heading_err:+.1f}deg exceeds "
                              f"{RR_MAX_HEADING_ERROR:.0f}deg; right wall tracking unreliable")
                return self.stop(self.fault)
            if not valid(right):
                return self.stop("RED-RED: missing right LiDAR; cannot follow right wall")
            if not valid(left):
                return self.stop("RED-RED: missing left LiDAR; opposite clearance unknown")

            rr_target = (RIGHT_RR_RIGHT_TARGET_M if self.physical_section == "RIGHT"
                         else RR_RIGHT_TARGET_M)
            rr_max_track = (RIGHT_RR_RIGHT_MAX_TRACK_M if self.physical_section == "RIGHT"
                            else RR_RIGHT_MAX_TRACK_M)

            if camera_pillar_in_sector(self.current_camera, -90, -80):
                steer = int(round(max(-RR_RIGHT_MAX_STEER, min(RR_RIGHT_MAX_STEER,
                                     RR_HEADING_KP * heading_err))))
                return self.drive(steer, "RR: camera pillar at RIGHT side; hold heading, not wall", RR_FOLLOW_PWM)
            # A distant reading is likely a gap, corner, or pillar. Do not turn
            # sharply into it. In this case maintain yaw 270 and log the fallback.
            if right > rr_max_track:
                steer = max(-RR_RIGHT_MAX_STEER, min(RR_RIGHT_MAX_STEER,
                            int(round(RR_HEADING_KP * heading_err))))
                # Keep from steering into the close left side.
                if left < RR_MIN_OPPOSITE_M:
                    steer = max(0, steer)
                return self.drive(steer,
                    f"RED-RED: right {right:.2f}m > {rr_max_track:.2f}m; "
                    f"right wall not tracked, hold yaw 270 (err {heading_err:+.1f}deg)",
                    RR_FOLLOW_PWM)

            # Right wall close -> steer LEFT (negative).
            # Right wall far -> steer RIGHT (positive).
            range_err = right - rr_target
            correction = 0.0 if abs(range_err) <= RR_RIGHT_DEADBAND_M else RR_RIGHT_KP * range_err
            steer = RR_HEADING_KP * heading_err + correction
            steer = int(round(max(-RR_RIGHT_MAX_STEER, min(RR_RIGHT_MAX_STEER, steer))))
            if steer < 0 and left < RR_MIN_OPPOSITE_M:
                # Cannot safely steer toward a near left wall.
                return self.stop(f"RED-RED: right {right:.2f}m near, but left {left:.2f}m "
                                 "too close to verify LEFT correction")
            return self.drive(steer,
                f"RED-RED right-wall follow target {rr_target:.2f}m; "
                f"right {right:.2f}m, left {left:.2f}m, yaw {yaw:.1f}, "
                f"correction {steer:+d}deg; front {front:.2f}m",
                RR_FOLLOW_PWM)

        # Red -> Green ONLY: allow the car to travel straight briefly after
        # completing the first 270-degree turn, before any 1.70m trigger.
        if self.state == "RG_CLEAR_RED":
            elapsed = now - self.started
            # TOP RED->GREEN: do not wait 1.5 seconds while the GREEN trigger passes.
            # This is only for the dedicated TOP route; other RG routes are unchanged.
            if ((self.top_rg_special and front <= RED_GREEN_START_FRONT_M)
                    or (self.section_label == "LEFT" and front <= LEFT_RG_LEFT_START_FRONT_M)):
                if self.top_rg_special and front < TOP_RG_LATE_TRIGGER_MIN_FRONT_M:
                    self.fault = (f"TOP RG missed {RED_GREEN_START_FRONT_M:.2f}m turn window: "
                                  f"front already {front:.2f}m; STOP and reduce approach speed / "
                                  "recheck LiDAR target and first RED clearance")
                    return self.stop(self.fault)
                if abs(angle_error(270.0, yaw)) > RED_GREEN_HEADING_TOLERANCE:
                    return self.stop(f"TOP RG turn ready but heading {yaw:.1f} not aligned to 270")
                if not valid(left) or not valid(right) or not valid(front_left):
                    return self.stop("TOP RG turn: side/front-left range unknown")
                if front_left < TURN1_FRONT_LEFT_FALLBACK_MIN:
                    return self.stop("TOP RG turn: front-left insufficient clearance")
                self.phase("LEFT_RG_LEFT" if self.section_label == "LEFT" else "RG_LEFT", now)
                self.rg_start_yaw = yaw
                self.rg_left_deviation_seen = False
                print(f"[TOP RG TURN TRIGGER] front={front:.3f}m <= "
                      f"{RED_GREEN_START_FRONT_M:.3f}m, clear-red elapsed={elapsed:.2f}s")
                return self.stop(f"TOP RG start timed LEFT on {front:.2f}m threshold")
            if abs(angle_error(270, yaw)) > 35:
                self.fault = "RED-GREEN clear-red: excessive heading deviation"
                return self.stop(self.fault)
            if front <= RED_GREEN_CLEAR_FRONT_GUARD_M:
                self.fault = (f"RED-GREEN clear-red blocked: front {front:.2f}m <= "
                              f"{RED_GREEN_CLEAR_FRONT_GUARD_M:.2f}m")
                return self.stop(self.fault)
            if elapsed >= RED_GREEN_CLEAR_STRAIGHT_SECONDS:
                self.phase("RG_APPROACH", now)
                return self.stop("RED-GREEN: brief straight completed; now approach GREEN trigger")
            # Maintain near-270 heading; never steer toward a detected close side.
            if not valid(left) or not valid(right):
                return self.stop("RED-GREEN clear-red: side clearance unavailable")
            if left < SIDE_AVOID_ENTER and right < SIDE_AVOID_ENTER:
                return self.stop("RED-GREEN clear-red: both sides near")
            steer = max(-6, min(6, self.hold_heading(yaw)))
            if left < SIDE_AVOID_ENTER:
                steer = max(0, steer)
            if right < SIDE_AVOID_ENTER:
                steer = min(0, steer)
            return self.drive(steer,
                              f"RED-GREEN clear first RED: straight {elapsed:.2f}/"
                              f"{RED_GREEN_CLEAR_STRAIGHT_SECONDS:.2f}s before GREEN left; yaw {yaw:.1f}",
                              RED_GREEN_CLEAR_PWM)

        # Red -> Green: TOP remains at its proven 1.67m trigger.
        # LEFT needs a closer approach before starting its swerve: at 1.55m
        # the front reading barely changed while the yaw dropped by 35 degrees.
        if self.state == "RG_APPROACH":
            approach_trigger = (LEFT_RG_LEFT_START_FRONT_M if self.section_label == "LEFT"
                                else RED_GREEN_START_FRONT_M)
            if front <= approach_trigger:
                self.phase("LEFT_RG_LEFT" if self.section_label == "LEFT" else "RG_LEFT", now)
                self.rg_start_yaw = yaw
                self.rg_left_deviation_seen = False
                return self.stop(f"{self.section_label} RED-GREEN: front {front:.2f}m "
                                 f"<= {approach_trigger:.2f}m; start LEFT steering")
            if abs(angle_error(270, yaw)) > 35:
                self.fault = "RED-GREEN approach: excessive heading deviation"
                return self.stop(self.fault)
            return self.straight_with_side_avoidance(front, left, right,
                                                     self.hold_heading(yaw),
                                                     f"{self.section_label} RED-GREEN approach: front {front:.2f}m "
                                                     f"> trigger {approach_trigger:.2f}m; hold lane heading")

        if self.state == "RG_LEFT":
            if self.top_rg_special:
                elapsed = now - self.started
                deviation = abs(angle_error(270.0, yaw))
                # Stop on excessive heading change; never use time to trigger RIGHT.
                if deviation > TOP_RG_MAX_LEFT_DEVIATION_DEG:
                    self.fault = f"TOP RG LEFT yaw deviation {deviation:.1f} deg; STOP"
                    return self.stop(self.fault)
                # The front reading can change abruptly when the LiDAR sweeps past
                # a pillar. Do not initiate a right recovery when already too close.
                if front < TOP_RG_LEFT_MIN_FRONT_M:
                    self.fault = (f"TOP RG LEFT front={front:.2f}m below "
                                  f"{TOP_RG_LEFT_MIN_FRONT_M:.2f}m recovery guard; STOP")
                    return self.stop(self.fault)
                if front <= TOP_RG_LEFT_SWITCH_FRONT_M:
                    wall_issue = self.confirm_rg_gr_front_wall(
                        data, front, f"{self.section_label}/{self.state} reversal")
                    if wall_issue is not None:
                        return self.stop(wall_issue)
                    if deviation < RED_GREEN_RIGHT_YAW_DEVIATION:
                        self.fault = "TOP RG LEFT: front trigger reached without sufficient LEFT yaw"
                        return self.stop(self.fault)
                    if not valid(right) or right <= FRONT_STOP_DISTANCE:
                        return self.stop("TOP RG LEFT: RIGHT clearance unknown/too close for recovery")
                    self.phase("RG_RIGHT", now)
                    return self.stop(
                        f"TOP RG LEFT->RIGHT: front={front:.2f}m <= "
                        f"{TOP_RG_LEFT_SWITCH_FRONT_M:.2f}m, yaw={yaw:.1f}; "
                        f"next command RIGHT +{TOP_RG_RIGHT_STEER_DEG}")
                if elapsed >= TOP_RG_LEFT_MAX_SECONDS:
                    self.fault = (f"TOP RG LEFT timeout: front={front:.2f}m has not reached "
                                  f"{TOP_RG_LEFT_SWITCH_FRONT_M:.2f}m; STOP")
                    return self.stop(self.fault)
                if not valid(left) or left <= FRONT_STOP_DISTANCE:
                    return self.stop("TOP RG LEFT: left LiDAR unknown or too close")
                if valid(front_left) and front_left < TURN1_FRONT_LEFT_FALLBACK_MIN:
                    return self.stop("TOP RG LEFT: front-left insufficient for swerve")
                return self.drive(-TOP_RG_LEFT_STEER_DEG,
                                  f"TOP RG LEFT until front <= {TOP_RG_LEFT_SWITCH_FRONT_M:.2f}m "
                                  f"(now {front:.2f}m), elapsed={elapsed:.2f}s, "
                                  f"yaw={yaw:.1f}, steer=-{TOP_RG_LEFT_STEER_DEG}",
                                  RED_GREEN_FOLLOW_PWM, steering_limit=TOP_RG_LEFT_STEER_DEG)
            # LEFT section approaches physical yaw 180; do not let the
            # left swerve continue far beyond its initial heading.
            left_deviation = abs(angle_error(270.0, yaw))
            switch_front = (LEFT_RG_SWITCH_FRONT_M if self.section_label == "LEFT"
                            else RED_GREEN_LEFT_TO_FRONT_M)
            # Front-distance-only transition; no RG_LEFT timeout.
            # Priority: switch before heading guard, provided safety checks above passed.
            if front <= switch_front:
                wall_issue = self.confirm_rg_gr_front_wall(
                    data, front, f"{self.section_label}/{self.state} reversal")
                if wall_issue is not None:
                    return self.stop(wall_issue)
                self.rg_left_deviation_seen = (abs(angle_error(270, yaw)) >= RED_GREEN_RIGHT_YAW_DEVIATION)
                self.phase("RG_RIGHT", now)
                return self.stop(f"{self.section_label} RED-GREEN: front {front:.2f}m; switch LEFT -> RIGHT")
            max_deviation = (LEFT_RG_MAX_LEFT_YAW_DEVIATION_DEG if self.section_label == "LEFT"
                             else TOP_RG_MAX_LEFT_YAW_DEVIATION_DEG)
            if left_deviation > max_deviation:
                self.fault = (f"{self.section_label} RED-GREEN: yaw deviation {left_deviation:.1f}deg "
                              f"> {max_deviation:.1f}deg before front <= {switch_front:.2f}m "
                              f"(front={front:.2f}m); unsafe to continue LEFT")
                return self.stop(self.fault)
            # Negative steering is left on this ESP32; LiDAR must see the left side.
            if not valid(left) or left <= 0.07:
                return self.stop("RED-GREEN LEFT: left clearance too small/unknown for swerve")
            return self.drive(RED_GREEN_LEFT_STEER,
                              f"{self.section_label} RED-GREEN LEFT steer {RED_GREEN_LEFT_STEER} "
                              f"(clamped to {MAX_STEERING_DEG}): front {front:.2f}m "
                              f"until {switch_front:.2f}m",
                              RED_GREEN_FOLLOW_PWM)

        if self.state == "RG_RIGHT":
            if self.top_rg_special:
                elapsed = now - self.started
                heading_error = angle_error(270.0, yaw)
                if (elapsed >= TOP_RG_RIGHT_MIN_SECONDS and
                        abs(heading_error) <= RED_GREEN_HEADING_TOLERANCE):
                    self.top_rg_track_count = 0
                    if self.top_rg_left_first_red:
                        self.phase("RG_PRECORNER_RIGHT", now)
                        return self.stop(
                            f"TOP RG GREEN cleared at yaw={yaw:.1f}; "
                            "prepare small RIGHT offset for LEFT first RED")
                    self.phase("RG_FOLLOW_LEFT", now)
                    return self.stop(f"TOP RG RIGHT recovered yaw={yaw:.1f}; start LEFT wall follow")
                if elapsed > RED_GREEN_MANEUVER_TIMEOUT_S:
                    self.fault = f"TOP RG RIGHT timeout yaw={yaw:.1f}"
                    return self.stop(self.fault)
                if not valid(right) or right <= FRONT_STOP_DISTANCE:
                    return self.stop("TOP RG RIGHT: right-side range unknown or too close")
                return self.drive(TOP_RG_RIGHT_STEER_DEG,
                                  f"TOP RG RIGHT toward 270 yaw={yaw:.1f} err={heading_error:+.1f}",
                                  RED_GREEN_FOLLOW_PWM, steering_limit=TOP_RG_RIGHT_STEER_DEG)
            # Both sections use the same virtual heading target of 270 degrees:
            # TOP -> physical 270 deg, LEFT -> physical 180 deg.
            # The LEFT LiDAR may read >1m (an opening). This is normal here.
            # Do NOT demand a nearby left wall during RIGHT recovery.
            elapsed = now - self.started
            heading_error = angle_error(270.0, yaw)
            left_display = f"{left:.2f}m" if valid(left) else "UNKNOWN"

            # Completion depends on the IMU, not LEFT wall distance.
            # Prior RG_LEFT must have made a measurable leftward heading change.
            if abs(heading_error) >= RED_GREEN_RIGHT_YAW_DEVIATION:
                self.rg_left_deviation_seen = True
            if (elapsed >= RED_GREEN_RIGHT_MIN_SECONDS
                    and self.rg_left_deviation_seen
                    and abs(heading_error) <= RED_GREEN_HEADING_TOLERANCE):
                self.phase("RG_FOLLOW_LEFT", now)
                return self.stop(
                    f"{self.section_label} RED-GREEN RIGHT complete at yaw {yaw:.1f}; "
                    f"left={left_display} is NOT a recovery requirement; begin follow-left")

            # Keep fault protection: a large left measurement doesn't establish
            # right-side clearance or safety for the robot's full turning body.
            if not valid(right) or right <= 0.07:
                return self.stop(
                    f"{self.section_label} RED-GREEN RIGHT: right-side clearance "
                    "missing or <= 0.15m")
            if elapsed > RED_GREEN_MANEUVER_TIMEOUT_S:
                self.fault = (f"{self.section_label} RED-GREEN RIGHT timed out "
                              f"at yaw {yaw:.1f}, error {heading_error:+.1f}deg")
                return self.stop(self.fault)
            if elapsed >= 0.8 and not self.rg_left_deviation_seen:
                self.fault = "RED-GREEN: no measurable left yaw deviation; recovery unverified"
                return self.stop(self.fault)

            return self.drive(
                RED_GREEN_RIGHT_STEER,
                f"{self.section_label} RED-GREEN RIGHT: recover heading 270 "
                f"(virtual yaw={yaw:.1f}, err={heading_error:+.1f}); "
                f"left={left_display} allowed OPEN, right={right:.2f}m",
                RED_GREEN_FOLLOW_PWM)

        if self.state == "RG_PRECORNER_RIGHT":
            # Only entered for TOP RED-GREEN -> LEFT first RED.
            # Build a modest RIGHT heading offset before approaching the corner;
            # unlike a timed steer this ends from IMU feedback.
            target = 270.0 + TOP_RG_TO_LEFT_RED_RIGHT_OFFSET_DEG
            err = angle_error(target, yaw)
            if abs(err) <= TOP_RG_TO_LEFT_RED_TARGET_TOL_DEG:
                self.top_rg_right_offset_done = True
                self.phase("RG_FOLLOW_LEFT", now)
                return self.stop(f"TOP RG pre-corner RIGHT offset done, yaw={yaw:.1f}; approach LEFT RED corner")
            if now - self.started > TOP_RG_TO_LEFT_RED_OFFSET_TIMEOUT_S:
                self.fault = f"TOP RG pre-corner RIGHT offset timeout at yaw={yaw:.1f}"
                return self.stop(self.fault)
            if err < 0:
                self.fault = f"TOP RG pre-corner RIGHT offset overshot at yaw={yaw:.1f}"
                return self.stop(self.fault)
            if (not valid(right) or right < TOP_RG_TO_LEFT_RED_RIGHT_CLEARANCE_M
                    or not valid(left) or left < TOP_RG_TO_LEFT_RED_LEFT_CLEARANCE_M
                    or front < TOP_RG_TO_LEFT_RED_MIN_FRONT_M):
                return self.stop(
                    f"TOP RG pre-corner RIGHT blocked: front={front:.2f}, "
                    f"left={left}, right={right}; inspect full-body clearance")
            return self.drive(TOP_RG_TO_LEFT_RED_RIGHT_STEER_DEG,
                              f"TOP RG pre-corner steer RIGHT toward yaw {target:.1f}, now {yaw:.1f}",
                              TOP_RG_TO_LEFT_RED_OFFSET_PWM)

        if self.state == "RG_FOLLOW_LEFT":
            if self.top_rg_special:
                if now - self.started > TOP_RG_FOLLOW_TIMEOUT_S:
                    self.fault = "TOP RG LEFT-wall following timed out before corner"
                    return self.stop(self.fault)
                heading_err = angle_error(270.0, yaw)
                if abs(heading_err) > TOP_RG_LEFT_WALL_MAX_HEADING_ERR:
                    self.fault = f"TOP RG heading drift {heading_err:+.1f} deg"
                    return self.stop(self.fault)
                if not valid(left) or not valid(right):
                    return self.stop("TOP RG follow: LEFT/RIGHT range missing; cannot verify clearance")
                if left <= FRONT_STOP_DISTANCE or right <= FRONT_STOP_DISTANCE:
                    return self.stop("TOP RG follow: side clearance at emergency threshold")
                if camera_pillar_in_sector(self.current_camera, 80, 90):
                    self.top_rg_open_count = 0
                    steer = int(round(max(-TOP_RG_LEFT_WALL_MAX_STEER,
                              min(TOP_RG_LEFT_WALL_MAX_STEER,
                                  TOP_RG_LEFT_WALL_HEADING_KP * heading_err))))
                    return self.drive(steer, "TOP RG: camera LEFT pillar; no wall/opening correction", TOP_RG_FOLLOW_PWM)
                # Confirm repeated side measurements before declaring a stable wall track.
                # Remember that we successfully detected the inner wall.
                if 0.10 <= left <= TOP_RG_LEFT_WALL_MAX_TRACK_M:
                    self.top_rg_track_count += 1
                    self.top_rg_open_count = 0

                    if self.top_rg_track_count >= TOP_RG_MIN_TRACK_READINGS:
                        self.top_rg_wall_seen = True

                elif left >= TOP_RG_CORNER_LEFT_OPEN_M:
                    self.top_rg_open_count += 1

                    # The wall must have been detected before accepting its end.
                    if self.top_rg_wall_seen and self.top_rg_open_count >= 3:
                        self.top_rg_wall_end_seen = True

                else:
                    self.top_rg_open_count = 0

                # At the corner the LiDAR may already be BEYOND the inner wall.
                # Accept a sustained left opening after the completed TOP RG S-turn
                # even if this state never sampled the short inner-wall segment.
                # Three consecutive scans reduce one-frame false handoffs.
                # This is a geometry-specific condition, NOT proof of rear clearance.
                if front <= self.top_rg_handoff_front:
                    left_open_at_corner = (
                        left >= TOP_RG_CORNER_LEFT_OPEN_M
                        and self.top_rg_open_count >= TOP_RG_CORNER_OPEN_SCANS
                        and valid(front_left)
                        and front_left >= TOP_RG_CORNER_FRONT_LEFT_MIN_M
                        and right >= TOP_RG_CORNER_RIGHT_MIN_M
                        and abs(heading_err) <= TOP_RG_CORNER_HEADING_TOL_DEG
                    )
                    if self.top_rg_wall_end_seen or left_open_at_corner:
                        self.phase("DONE", now)
                        return self.stop(
                            f"TOP RG open corner confirmed; front={front:.2f}m, "
                            f"left={left:.2f}m, open_scans={self.top_rg_open_count}; "
                            "handoff to LEFT section"
                        )
                    # At the configured handoff distance, permit a guarded
                    # section transition without requiring the 1.10 m LEFT-opening
                    # reading for 3 scans. Keep current sector clearance and IMU
                    # checks. The NEXT section still controls its own first turn.
                    # This is not proof of full vehicle swept-path clearance.
                    if (valid(front_left)
                            and left >= 0.50
                            and front_left >= TOP_RG_CORNER_FRONT_LEFT_MIN_M
                            and right >= max(TOP_RG_CORNER_RIGHT_MIN_M, 0.20)
                            and abs(heading_err) <= TOP_RG_CORNER_HEADING_TOL_DEG):
                        self.phase("DONE", now)
                        return self.stop(
                            f"TOP RG distance handoff at front={front:.2f}m "
                            f"(left={left:.2f}m, front-left={front_left:.2f}m, "
                            f"right={right:.2f}m); next section controls LEFT turn"
                        )
                    return self.stop(
                        f"TOP RG handoff blocked by clearance/heading: front={front:.2f}m "
                        f"left={left:.2f}m right={right:.2f}m "
                        f"front-left={front_left}, heading_err={heading_err:+.1f}"
                    )
                if self.top_rg_left_first_red and self.top_rg_right_offset_done:
                    # Maintain the modest RIGHT bias until LEFT first RED corner.
                    # Don't chase a wall opening or steer further RIGHT near a boundary.
                    offset_target = 270.0 + TOP_RG_TO_LEFT_RED_RIGHT_OFFSET_DEG
                    offset_error = angle_error(offset_target, yaw)
                    steer = int(round(TOP_RG_LEFT_WALL_HEADING_KP * offset_error))
                    steer = max(-TOP_RG_LEFT_WALL_MAX_STEER,
                                min(TOP_RG_LEFT_WALL_MAX_STEER, steer))
                elif left > TOP_RG_LEFT_WALL_MAX_TRACK_M:
                    steer = int(round(TOP_RG_LEFT_WALL_HEADING_KP * heading_err))
                else:
                    range_err = left - TOP_RG_LEFT_WALL_TARGET_M
                    range_term = (0.0 if abs(range_err) <= TOP_RG_LEFT_WALL_DEADBAND_M
                                  else -TOP_RG_LEFT_WALL_KP * range_err)
                    steer = int(round(TOP_RG_LEFT_WALL_HEADING_KP * heading_err + range_term))
                steer = max(-TOP_RG_LEFT_WALL_MAX_STEER,
                            min(TOP_RG_LEFT_WALL_MAX_STEER, steer))
                if steer > 0 and right < TOP_RG_LEFT_WALL_MIN_OPPOSITE_M:
                    return self.stop("TOP RG: too near RIGHT side to correct away from LEFT wall")
                return self.drive(steer,
                                  f"TOP RG follow LEFT target={TOP_RG_LEFT_WALL_TARGET_M:.2f}m "
                                  f"left={left:.2f}m right={right:.2f}m front={front:.2f}m "
                                  f"yaw={yaw:.1f} steer={steer:+d}", TOP_RG_FOLLOW_PWM)
            if now - self.started > RED_GREEN_MAX_FOLLOW_SECONDS:
                self.fault = "RED-GREEN left follow timed out; opening/stop conditions not confirmed"
                return self.stop(self.fault)
            # Stop only when BOTH requested conditions are met.
            if front <= RED_GREEN_FOLLOW_FRONT_M:
                if valid(left) and left > RED_GREEN_FOLLOW_LEFT_OPEN_M:
                    self.phase("DONE", now)
                    return self.stop(f"RED-GREEN DONE: front {front:.2f}m <= 0.50m; left opening {left:.2f}m > 0.30m")
                return self.stop(f"RED-GREEN: front {front:.2f}m at stop boundary but left opening NOT >0.30m; cannot advance")
            if not valid(left) or not valid(right):
                return self.stop("RED-GREEN left following: missing side range")
            if abs(angle_error(270, yaw)) > 35:
                self.fault = "RED-GREEN left following: heading diverged >35 degrees"
                return self.stop(self.fault)
            # Left is inner wall: steer right if close; mild left if far, but never
            # move toward a detected opening/pillar without verified forward space.
            if left < 0.14:
                if right < SIDE_OPPOSITE_MIN_M:
                    return self.stop("RED-GREEN left wall near; right correction space insufficient")
                steer = +RED_GREEN_FOLLOW_STEER
            elif left <= 0.22:
                steer = max(-4, min(4, self.hold_heading(yaw)))
            else:
                # A large left measurement can be a gap, not a wall: avoid diving left.
                steer = max(0, min(4, self.hold_heading(yaw)))
            return self.drive(steer,
                              f"RED-GREEN left-wall follow; left {left:.2f}m; front {front:.2f}m",
                              RED_GREEN_FOLLOW_PWM)

        if self.state == "GG_WALL_FOLLOW":
            # Exclusive to TOP GG; no second-pillar LEFT swerve in this route.
            if not (self.top_gg_to_left_green or self.top_gg_to_left_red):
                self.fault = "GG wall follow called for wrong mapped route"
                return self.stop(self.fault)
            if not valid(left) or not valid(right) or not valid(front_left):
                return self.stop("TOP GG wall follow: missing side/front-left LiDAR")
            if right < TOP_GG_WALL_RIGHT_MIN_M:
                return self.stop("TOP GG wall follow: right clearance insufficient")
            if left <= FRONT_STOP_DISTANCE:
                return self.stop("TOP GG wall follow: left emergency clearance")
            yaw_err = angle_error(270.0, yaw)
            if abs(yaw_err) > TOP_GG_WALL_MAX_HEADING_ERR_DEG:
                self.fault = f"TOP GG wall follow yaw drift {yaw_err:+.1f} degrees"
                return self.stop(self.fault)
            # If the camera actually sees a pillar in the LiDAR LEFT side sector,
            # do not treat its range as a wall or an opening. Hold existing yaw;
            # never bypass the raw LiDAR safety checks above.
            if camera_pillar_in_sector(self.current_camera, 80, 90):
                self.gg_open_scans = 0
                self.gg_wall_acquire_scans = 0
                if front < TOP_GG_WALL_MIN_FRONT_M:
                    return self.stop("TOP GG: pillar overlaps LEFT side; front guard")
                return self.drive(self.hold_heading(yaw),
                    "TOP GG: camera sees pillar at LEFT side angle; hold heading, no wall correction",
                    TOP_GG_WALL_PWM)
            # A large LEFT range just after the first turn may mean that the
            # wall has not yet been acquired; it is NOT evidence of the corner.
            # Require 3 consecutive scans of a nearby inner wall first.
            if not self.gg_wall_acquired:
                if FRONT_STOP_DISTANCE < left <= TOP_GG_WALL_ACQUIRE_MAX_M:
                    self.gg_wall_acquire_scans += 1
                    if self.gg_wall_acquire_scans >= TOP_GG_WALL_ACQUIRE_SCANS:
                        self.gg_wall_acquired = True
                        self.gg_open_scans = 0
                else:
                    self.gg_wall_acquire_scans = 0
                if not self.gg_wall_acquired:
                    elapsed = now - self.started
                    if elapsed >= TOP_GG_ACQUIRE_STRAIGHT_SECONDS:
                        self.fault = (
                            f"TOP GG wall not acquired after {elapsed:.2f}s straight search: "
                            f"left={left:.2f}m, front={front:.2f}m; STOP"
                        )
                        return self.stop(self.fault)
                    # Bounded straight search, not a blind 2-second drive.
                    # Keep steering centered to avoid swinging the front-left
                    # corner toward the very close +45-degree return.
                    if (front < TOP_GG_ACQUIRE_MIN_FRONT_M
                        or front_left < TOP_GG_ACQUIRE_MIN_FRONT_LEFT_M
                        or right < TOP_GG_ACQUIRE_MIN_RIGHT_M):
                        return self.stop(
                            f"TOP GG wall search unsafe: front={front:.2f}m, "
                            f"front-left={front_left:.2f}m, right={right:.2f}m; "
                            f"need >= {TOP_GG_ACQUIRE_MIN_FRONT_M:.2f}/"
                            f"{TOP_GG_ACQUIRE_MIN_FRONT_LEFT_M:.2f}/"
                            f"{TOP_GG_ACQUIRE_MIN_RIGHT_M:.2f}m")
                    return self.drive(
                        0,
                        f"TOP GG bounded STRAIGHT acquisition {elapsed:.2f}/"
                        f"{TOP_GG_ACQUIRE_STRAIGHT_SECONDS:.2f}s: "
                        f"left={left:.2f}m, front-left={front_left:.2f}m, "
                        f"wall scans={self.gg_wall_acquire_scans}/{TOP_GG_WALL_ACQUIRE_SCANS}",
                        TOP_GG_ACQUIRE_STRAIGHT_PWM)

            if left > TOP_GG_LEFT_OPEN_TRIGGER_M:
                self.gg_open_scans += 1
            else:
                self.gg_open_scans = 0
            open_confirmed = self.gg_open_scans >= TOP_GG_LEFT_OPEN_SCANS
            if self.top_gg_to_left_green and front <= TOP_GG_GREEN_TURN_FRONT_M:
                # Unlike the RED branch, GREEN must not wait for left >0.35m:
                # at the corner the 90-degree sector can still see the inner
                # wall, even when the +45-degree sector looks into the opening.
                # Use separate conservative provisional range checks. Geometry
                # must be validated against the actual robot footprint.
                if (front < TOP_GG_GREEN_CORNER_MIN_FRONT_M
                    or left < TOP_GG_GREEN_CORNER_LEFT_MIN_M
                    or front_left < TOP_GG_GREEN_CORNER_FRONT_LEFT_MIN_M
                    or right < TOP_GG_GREEN_CORNER_RIGHT_MIN_M):
                    return self.stop(
                        f"TOP GG GREEN corner range guard: front={front:.2f}, "
                        f"left={left:.2f}, front-left={front_left:.2f}, "
                        f"right={right:.2f}; body clearance unverified")
                self.phase("DONE", now)
                return self.stop(
                    f"TOP GG -> LEFT GREEN handoff at front {front:.2f}m "
                    f"(target 1.10m; diagonal opening provisional)")
            if self.top_gg_to_left_red:
                if front <= TOP_GG_RED_TURN_FRONT_M:
                    return self.stop("TOP GG RED corner reached 0.60m before RIGHT bias; STOP")
                if open_confirmed:
                    if front < TOP_GG_RED_RIGHT_MIN_START_FRONT_M:
                        return self.stop("TOP GG RED left opening detected too late for RIGHT bias")
                    self.phase("GG_RED_RIGHT_BIAS", now)
                    return self.stop(
                        f"TOP GG LEFT range {left:.2f}m > 0.35m; start slow RIGHT 10deg yaw offset")
            if front <= TOP_GG_WALL_MIN_FRONT_M:
                return self.stop("TOP GG wall follow: insufficient front clearance")
            # Tracking near wall, avoiding large steering into an opening.
            if left > TOP_GG_LEFT_OPEN_TRIGGER_M:
                steer = max(-TOP_GG_WALL_MAX_STEER_DEG,
                            min(TOP_GG_WALL_MAX_STEER_DEG, round(HEADING_KP * yaw_err)))
            else:
                range_err = left - TOP_GG_WALL_TARGET_M
                correction = 0.0 if abs(range_err) <= TOP_GG_WALL_DEADBAND_M else -TOP_GG_WALL_KP * range_err
                steer = max(-TOP_GG_WALL_MAX_STEER_DEG,
                            min(TOP_GG_WALL_MAX_STEER_DEG, round(HEADING_KP * yaw_err + correction)))
            if steer > 0 and right < 0.05:
                return self.stop("TOP GG wall follow: cannot correct RIGHT into close obstacle")
            return self.drive(steer,
                f"TOP GG follow LEFT wall: left={left:.2f}m front={front:.2f}m "
                f"inner wall acquired; target={TOP_GG_WALL_TARGET_M:.2f}m "
                f"steer={steer:+d}; opening scans={self.gg_open_scans}/{TOP_GG_LEFT_OPEN_SCANS}; "
                f"next LEFT first {'GREEN' if self.top_gg_to_left_green else 'RED'}",
                TOP_GG_WALL_PWM)

        if self.state == "GG_RED_RIGHT_BIAS":
            # +10 degrees of physical yaw using servo +10 steering at PWM 90.
            target = 270.0 + TOP_GG_RED_RIGHT_OFFSET_YAW_DEG
            err = angle_error(target, yaw)
            if abs(err) <= TOP_GG_RED_RIGHT_TOL_DEG:
                self.phase("GG_RED_TO_CORNER", now)
                return self.stop(f"TOP GG RIGHT offset complete yaw={yaw:.1f}; approach 0.60m")
            if now - self.started > TOP_GG_RED_RIGHT_TIMEOUT_S:
                self.fault = f"TOP GG RIGHT bias timeout at yaw {yaw:.1f}"
                return self.stop(self.fault)
            if err < 0:
                self.fault = f"TOP GG RIGHT bias overshot yaw {yaw:.1f}"
                return self.stop(self.fault)
            if (front <= TOP_GG_RED_RIGHT_MIN_START_FRONT_M or not valid(right)
                or right < TOP_GG_TO_LEFT_RED_RIGHT_MIN_CLEARANCE_M
                or not valid(left) or left <= TOP_GG_LEFT_OPEN_TRIGGER_M
                or not valid(front_left) or front_left < TOP_GG_CORNER_FRONT_LEFT_MIN_M):
                return self.stop("TOP GG RIGHT bias: clearance not verified; STOP")
            return self.drive(TOP_GG_RED_RIGHT_STEER_DEG,
                f"TOP GG slow RIGHT: yaw {yaw:.1f} -> {target:.1f}, front {front:.2f}m",
                TOP_GG_RED_RIGHT_PWM)

        if self.state == "GG_RED_TO_CORNER":
            target = 270.0 + TOP_GG_RED_RIGHT_OFFSET_YAW_DEG
            if abs(angle_error(target, yaw)) > 12.0:
                return self.stop("TOP GG RED corner approach: heading offset lost")
            if (not valid(left) or not valid(right) or not valid(front_left)
                or right < TOP_GG_WALL_RIGHT_MIN_M or front_left < TOP_GG_CORNER_FRONT_LEFT_MIN_M):
                return self.stop(
                    f"TOP GG RED approach clearance blocked: left={left}, "
                    f"right={right} (min {TOP_GG_WALL_RIGHT_MIN_M:.2f}), "
                    f"front-left={front_left} (min {TOP_GG_CORNER_FRONT_LEFT_MIN_M:.2f})")
            if front <= TOP_GG_RED_TURN_FRONT_M:
                # The LEFT opening was already confirmed in GG_WALL_FOLLOW.
                # Do not require it to remain visible: the +90-degree LiDAR
                # sector may see the next inner wall as we approach the corner.
                # Keep the right/front-left clearance guard above, plus the
                # global emergency-stop checks, and let the LEFT section's
                # existing first-RED TURN_1 controller execute the LEFT turn.
                self.phase("DONE", now)
                return self.stop(
                    f"TOP GG -> LEFT RED: front LiDAR {front:.2f}m <= "
                    f"{TOP_GG_RED_TURN_FRONT_M:.2f}m; handoff for LEFT RED turn "
                    f"(left={left:.2f}m, right={right:.2f}m, "
                    f"front-left={front_left:.2f}m)")
            if front < TOP_GG_WALL_MIN_FRONT_M:
                return self.stop("TOP GG RED corner approach: front too close")
            return self.drive(self.hold_heading(yaw, target),
                f"TOP GG slow RED approach at yaw={yaw:.1f}, front={front:.2f}m until 0.60m",
                TOP_GG_RED_RIGHT_PWM)

        if self.state == "APPROACH_2":
            err = abs(angle_error(270, yaw))
            if err > 35:
                self.fault = "Heading drift >35 degrees approaching pillar 2"
                return self.stop(self.fault)
            color = self.plan[1]
            if color == "red" and front <= 1.70:
                self.phase("RED_RIGHT", now)
                return self.stop("Pillar 2 RED: 1.70m trigger; begin right then left")
            green_trigger = (TOP_GG_TO_LEFT_GREEN_SECOND_TRIGGER_M if self.top_gg_to_left_green
                             else TOP_GG_TO_LEFT_RED_GREEN_TRIGGER_M if self.top_gg_to_left_red
                             else SECOND_GREEN_TEST_FRONT_LIMIT)
            if color == "green" and front <= green_trigger:
                # Both conditions are required. If the left opening never
                # appears, stop instead of driving into the front obstacle.
                if front < (TOP_GG_TO_LEFT_RED_LATE_START_M if (self.top_gg_to_left_red or self.top_gg_to_left_green) else SECOND_GREEN_MIN_FRONT):
                    return self.stop(
                        f"Second GREEN: front {front:.2f}m is below safe "
                        f"minimum starting front distance "
                        f"{(TOP_GG_TO_LEFT_RED_LATE_START_M if (self.top_gg_to_left_red or self.top_gg_to_left_green) else SECOND_GREEN_MIN_FRONT):.2f}m")
                if not valid(left) or left <= SECOND_GREEN_MIN_LEFT:
                    return self.stop(
                        f"Second GREEN: front {front:.2f}m reached; "
                        f"waiting for verified left > {SECOND_GREEN_MIN_LEFT:.2f}m "
                        "(STOP, not moving closer)")
                self.phase("GREEN_LEFT", now)
                if self.top_gg_to_left_red or self.top_gg_to_left_green:
                    self.green_left_start_yaw = yaw
                    self.green_left_yaw_seen = False
                return self.stop(
                    f"Second GREEN: front {front:.2f}m and left {left:.2f}m; "
                    "begin LEFT maneuver")
            steer = self.hold_heading(yaw)
            if color == "green" and self.top_gg_to_left_green:
                # Slow BEFORE reaching the trigger; speed changes cannot prevent
                # a sudden range jump, so the late-start fail-stop remains active.
                return self.drive(steer,
                    f"TOP GG -> LEFT GREEN: slow approach to TOP pillar-2 trigger "
                    f"{green_trigger:.2f}m, front={front:.2f}m",
                    TOP_GG_TO_LEFT_GREEN_APPROACH_PWM)
            return self.straight_with_side_avoidance(
                front, left, right, steer,
                f"Pillar 2 {color}: hold yaw 270; front {front:.2f}m; "
                f"left {left if valid(left) else 'UNKNOWN'}")

        if self.state == "GREEN_LEFT":
            if now - self.started > RED_MANEUVER_TIMEOUT:
                self.fault = "Green left maneuver timeout"
                return self.stop(self.fault)
            # If close to the LEFT boundary, end the left swerve early and
            # recover by steering RIGHT. Do not wait for the front threshold.
            left_close = valid(left) and left < SIDE_AVOID_ENTER
            right_open = valid(right) and right >= SIDE_OPPOSITE_MIN_M
            if self.top_gg_to_left_red or self.top_gg_to_left_green:
                if front <= TOP_GG_TO_LEFT_RED_FRONT_BRAKE_M:
                    self.fault = (f"TOP GG GREEN_LEFT front={front:.2f}m: too close to safely continue; STOP")
                    return self.stop(self.fault)
                deviation = (self.green_left_start_yaw - yaw + 180.0) % 360.0 - 180.0
                if deviation >= TOP_GG_TO_LEFT_RED_MIN_YAW_CHANGE_DEG:
                    self.green_left_yaw_seen = True
                if abs(deviation) > TOP_GG_TO_LEFT_RED_MAX_YAW_CHANGE_DEG:
                    self.fault = f"TOP GG LEFT excessive yaw deviation {deviation:.1f}deg"
                    return self.stop(self.fault)
                if front <= TOP_GG_TO_LEFT_RED_LEFT_SWITCH_M and not self.green_left_yaw_seen:
                    self.fault = (f"TOP GG GREEN not cleared: front={front:.2f}m "
                                  f"before measurable LEFT yaw; STOP")
                    return self.stop(self.fault)
                if front <= TOP_GG_TO_LEFT_RED_LEFT_SWITCH_M or (left_close and right_open):
                    if not self.green_left_yaw_seen:
                        return self.stop("TOP GG GREEN: side near before confirmed LEFT motion")
                    self.phase("GREEN_RIGHT", now)
                    return self.stop(f"TOP GG: LEFT yaw change {deviation:.1f}deg; recover RIGHT")
                if not valid(left) or left < 0.20 or not valid(front_left) or front_left < 0.35:
                    return self.stop("TOP GG LEFT: left/front-left clearance not verified")
                return self.drive(-TOP_GG_TO_LEFT_RED_LEFT_STEER_DEG,
                    f"TOP GG slower GREEN LEFT: front {front:.2f}m, yaw change {deviation:.1f}deg",
                    TOP_GG_TO_LEFT_RED_LEFT_PWM)
            if front <= GREEN_LEFT_FRONT_TRIGGER or (left_close and right_open):
                self.phase("GREEN_RIGHT", now)
                return self.stop(
                    "Green pillar 2: switch LEFT -> RIGHT (front trigger or left near)"
                )
            return self.drive(GREEN_LEFT_STEER,
                              f"Green pillar 2: LEFT until front <= {GREEN_LEFT_FRONT_TRIGGER:.2f}m (now {front:.2f}m)")

        if self.state == "GREEN_RIGHT":
            if (self.top_gg_to_left_red or self.top_gg_to_left_green) and front <= TOP_GG_TO_LEFT_RED_FRONT_BRAKE_M:
                self.fault = (f"TOP GG GREEN_RIGHT front={front:.2f}m: too close for forward recovery; STOP")
                return self.stop(self.fault)
            if now - self.started > RED_MANEUVER_TIMEOUT:
                self.fault = "Green right return timeout"
                return self.stop(self.fault)
            if abs(angle_error(270, yaw)) <= HEADING_TOLERANCE:
                if self.top_gg_to_left_red or self.top_gg_to_left_green:
                    if not self.green_left_yaw_seen:
                        self.fault = "TOP GG: GREEN_RIGHT recovered without confirmed LEFT maneuver"
                        return self.stop(self.fault)
                    if (front < TOP_GG_TO_LEFT_RED_HANDOFF_MIN_FRONT_M or
                            not valid(left) or left < TOP_GG_TO_LEFT_RED_LEFT_OPEN_M or
                            not valid(right) or right < 0.22 or
                            not valid(front_left) or front_left < 0.35):
                        self.fault = (f"TOP GG: no verified room for LEFT RED corner: "
                                      f"front={front:.2f}, left={left}, right={right}, "
                                      f"front_left={front_left}; STOP")
                        return self.stop(self.fault)
                    # LEFT first GREEN does NOT need pre-corner right offset.
                    # Hand off while still safely ahead of the 1.10m LEFT turn threshold.
                    if self.top_gg_to_left_green:
                        if front <= LEFT_GREEN_TURN_DISTANCE:
                            self.fault = (f"TOP GG -> LEFT GREEN too late: front={front:.2f}m "
                                          f"<= {LEFT_GREEN_TURN_DISTANCE:.2f}m; STOP")
                            return self.stop(self.fault)
                        self.phase("GG_TO_LEFT_GREEN_APPROACH", now)
                        return self.stop("TOP GG GREEN recovered; LEFT first GREEN, no RIGHT offset")
                    # LEFT first RED gets a 10-degree RIGHT yaw offset first.
                    if front < TOP_GG_TO_LEFT_RED_RIGHT_MIN_FRONT_M:
                        self.fault = (f"TOP GG: too late for pre-corner RIGHT adjustment: "
                                      f"front={front:.2f}m; STOP")
                        return self.stop(self.fault)
                    self.phase("GG_PRECORNER_RIGHT", now)
                    return self.stop(f"TOP GG GREEN cleared at yaw={yaw:.1f}; begin pre-corner RIGHT offset")
                self.phase("RED_EXIT", now)   # reuse the bounded exit segment
                return self.stop(f"Yaw recovered at {yaw:.1f}; bounded exit (pillar clearance unverified)")
            if self.top_gg_to_left_red or self.top_gg_to_left_green:
                if not valid(right) or right < TOP_GG_TO_LEFT_RED_RIGHT_MIN_CLEARANCE_M:
                    return self.stop("TOP GG GREEN_RIGHT: right-side clearance not verified")
                return self.drive(TOP_GG_TO_LEFT_RED_RECOVER_STEER_DEG,
                                  f"TOP GG slower GREEN_RIGHT to 270deg (yaw {yaw:.1f})",
                                  TOP_GG_TO_LEFT_RED_RECOVER_PWM)
            return self.drive(GREEN_RIGHT_STEER, f"Green pillar 2: RIGHT toward 270deg (yaw {yaw:.1f})")

        if self.state == "GG_TO_LEFT_GREEN_APPROACH":
            # TOP GG completed, LEFT first pillar GREEN: turn at 1.10m via LEFT controller.
            # This state only hands control over; it does not issue a left turn itself.
            if abs(angle_error(270.0, yaw)) > 12.0:
                self.fault = "TOP GG -> LEFT GREEN heading drift"
                return self.stop(self.fault)
            if not valid(left) or left < TOP_GG_TO_LEFT_RED_LEFT_OPEN_M:
                return self.stop("TOP GG -> LEFT GREEN: left opening not verified")
            if not valid(right) or right < 0.22 or not valid(front_left) or front_left < 0.35:
                return self.stop("TOP GG -> LEFT GREEN: side/front-left space not verified")
            if front <= TOP_GG_TO_LEFT_GREEN_HANDOFF_FRONT_M:
                if front <= TOP_GG_TO_LEFT_GREEN_MIN_HANDOFF_FRONT_M:
                    self.fault = f"TOP GG -> LEFT GREEN late handoff at {front:.2f}m"
                    return self.stop(self.fault)
                self.phase("DONE", now)
                return self.stop(f"TOP GG -> LEFT GREEN handoff at front {front:.2f}m")
            return self.drive(self.hold_heading(yaw),
                              f"TOP GG -> LEFT GREEN slow approach; handoff at "
                              f"{TOP_GG_TO_LEFT_GREEN_HANDOFF_FRONT_M:.2f}m", 90)

        if self.state == "GG_PRECORNER_RIGHT":
            # Only TOP GREEN-GREEN followed by LEFT first RED reaches this stage.
            # Steering +10 is NOT 10 degrees yaw: use IMU to stop at 270 + offset.
            target = 270.0 + TOP_GG_TO_LEFT_RED_RIGHT_OFFSET_DEG
            err = angle_error(target, yaw)
            if abs(err) <= TOP_GG_TO_LEFT_RED_RIGHT_TOL_DEG:
                self.top_gg_right_offset_done = True
                self.phase("GG_TO_LEFT_RED_APPROACH", now)
                return self.stop(f"TOP GG RIGHT offset reached yaw={yaw:.1f}; approach LEFT RED corner")
            if now - self.started > TOP_GG_TO_LEFT_RED_RIGHT_TIMEOUT_S:
                self.fault = f"TOP GG RIGHT offset timeout at yaw={yaw:.1f}"
                return self.stop(self.fault)
            if err < 0:
                self.fault = f"TOP GG RIGHT offset overshot yaw={yaw:.1f}"
                return self.stop(self.fault)
            if (front < TOP_GG_TO_LEFT_RED_RIGHT_MIN_FRONT_M or
                    not valid(right) or right < TOP_GG_TO_LEFT_RED_RIGHT_MIN_CLEARANCE_M or
                    not valid(left) or left < 0.20 or
                    not valid(front_left) or front_left < 0.35):
                return self.stop(f"TOP GG RIGHT offset: clearance insufficient "
                                 f"front={front:.2f}, left={left}, right={right}; STOP")
            return self.drive(TOP_GG_TO_LEFT_RED_RIGHT_STEER_DEG,
                              f"TOP GG pre-corner RIGHT yaw={yaw:.1f}, target={target:.1f}",
                              TOP_GG_TO_LEFT_RED_RIGHT_PWM)

        if self.state == "GG_TO_LEFT_RED_APPROACH":
            if not self.top_gg_right_offset_done:
                self.fault = "TOP GG pre-corner RIGHT offset not completed"
                return self.stop(self.fault)
            target = 270.0 + TOP_GG_TO_LEFT_RED_RIGHT_OFFSET_DEG
            if abs(angle_error(target, yaw)) > 12.0:
                self.fault = "TOP GG handoff approach: offset heading drift"
                return self.stop(self.fault)
            if not valid(left) or left < TOP_GG_TO_LEFT_RED_LEFT_OPEN_M or not valid(right) or right < 0.22:
                return self.stop("TOP GG handoff approach: side clearance not verified")
            if not valid(front_left) or front_left < 0.35:
                return self.stop("TOP GG handoff approach: front-left clearance not verified")
            gg_red_handoff = (BOTTOM_TO_RIGHT_RED_HANDOFF_FRONT_M
                              if self.physical_section == "BOTTOM"
                              else TOP_GG_TO_LEFT_RED_HANDOFF_FRONT_M)
            if front <= gg_red_handoff:
                if front < TOP_GG_TO_LEFT_RED_HANDOFF_MIN_FRONT_M:
                    self.fault = f"TOP GG missed LEFT RED handoff window: front={front:.2f}m"
                    return self.stop(self.fault)
                self.phase("DONE", now)
                return self.stop(f"TOP GG -> LEFT RED handoff at front={front:.2f}m")
            steer = int(round(HEADING_KP * angle_error(target, yaw)))
            steer = max(-HEADING_STEERING_LIMIT, min(HEADING_STEERING_LIMIT, steer))
            if steer > 0 and right < TOP_GG_TO_LEFT_RED_RIGHT_MIN_CLEARANCE_M:
                return self.stop("TOP GG offset hold: RIGHT side clearance insufficient")
            return self.drive(steer,
                f"TOP GG: maintain {target:.1f} yaw, approach LEFT RED handoff "
                f"at {gg_red_handoff:.2f}m", 90)

        if self.state == "RED_RIGHT":
            if now - self.started > RED_MANEUVER_TIMEOUT:
                self.fault = "Red right maneuver timeout"
                return self.stop(self.fault)
            if front <= RED_RIGHT_FRONT_TRIGGER:
                self.phase("RED_LEFT", now)
                return self.stop(
                    f"Red pillar 2: front {front:.2f}m <= {RED_RIGHT_FRONT_TRIGGER:.2f}m; "
                    "switch RIGHT -> LEFT toward yaw 270"
                )
            # Side scan does not prove full-body clearance; remain fail-safe at minimum distances.
            return self.drive(RED_RIGHT_STEER,
                              f"Red pillar 2: RIGHT until front <= {RED_RIGHT_FRONT_TRIGGER:.2f}m "
                              f"(now {front:.2f}m)")

        if self.state == "RED_LEFT":
            if now - self.started > RED_MANEUVER_TIMEOUT:
                self.fault = "Red left return timeout"
                return self.stop(self.fault)
            if abs(angle_error(270, yaw)) <= HEADING_TOLERANCE:
                # Yaw recovery does NOT imply that the rear axle has cleared RED.
                self.phase("RED_EXIT", now)
                return self.stop(f"Yaw recovered at {yaw:.1f}; preparing bounded exit test (pillar clearance unverified)")
            return self.drive(RED_LEFT_STEER, f"Red pillar 2: LEFT toward 270deg (yaw {yaw:.1f})")

        if self.state == "RED_EXIT":
            # Continue on the 270-degree heading instead of treating both
            # 0.24m side-avoidance readings as a blocked corridor.
            # Global valid-sector <=0.10m emergency checks still run above.
            # This does NOT verify that the rear of the car cleared the pillar.
            if front <= RED_EXIT_FRONT_GUARD:
                self.fault = (f"RED_EXIT blocked: front {front:.2f}m <= "
                              f"{RED_EXIT_FRONT_GUARD:.2f}m; pass unverified")
                return self.stop(self.fault)
            if now - self.started >= RED_EXIT_MAX_SECONDS:
                self.phase("DONE", now)
                return self.stop("RED_EXIT bounded test ended; pillar pass NOT verified")
            # Never command automatic correction TOWARD a measured near wall.
            # If the opposite side is also close, steer straight rather than
            # forcing a side-avoidance maneuver into an unknown corridor.
            steer = self.hold_heading(yaw)
            side_warning = []
            if valid(left) and left < SIDE_AVOID_ENTER:
                side_warning.append(f"left={left:.2f}m near")
                steer = max(0, steer)  # no left steering toward a close left side
            if valid(right) and right < SIDE_AVOID_ENTER:
                side_warning.append(f"right={right:.2f}m near")
                steer = min(0, steer)  # no right steering toward a close right side
            reason = (f"RED_EXIT forward heading 270, {now-self.started:.2f}s "
                      f"[pass not verified] " + ", ".join(side_warning))
            return self.drive(steer, reason, SIDE_AVOID_PWM)

        self.fault = f"Unknown state: {self.state}"
        return self.stop(self.fault)


# =========================================================
# TWO SECTION WRAPPER (TOP: 0 -> 270; LEFT: 270 -> 180)
# =========================================================

class FourSectionController:
    """Repeated laps: TOP -> LEFT -> BOTTOM -> RIGHT, then wrap to TOP.

    Original controller logic is reused with virtual heading rotations:
        TOP: +0, LEFT: +90, BOTTOM: +180, RIGHT: +270.
    BOTTOM executes the TOP-style maneuvers; RIGHT executes LEFT-style ones.
    This is a copied movement strategy, not a validated four-sided trajectory.
    """
    ORDER = ("TOP", "LEFT", "BOTTOM", "RIGHT")
    YAW_OFFSET = {"TOP": 0., "LEFT": 90., "BOTTOM": 180., "RIGHT": 270.}
    ENTRY_HEADING = {"TOP": 0., "LEFT": 270., "BOTTOM": 180., "RIGHT": 90.}

    def __init__(self, plan):
        self.plans = plan
        self.section_index = 0
        self.section = "TOP"
        self.controller = None
        self.state = "TOP/APPROACH_1"
        self.fault = None
        self.lap_count = 0
        self.final_approach_started = None
        for section in self.ORDER:
            if section.lower() not in plan or len(plan[section.lower()]) != 2:
                raise ValueError(f"Four-section map needs exactly 2 {section} pillars")
        for section, next_section in zip(self.ORDER[:-1], self.ORDER[1:]):
            color = plan[next_section.lower()][0]
            needed = (LEFT_GREEN_TURN_DISTANCE if next_section == "LEFT" and color == "green"
                      else LEFT_RED_TURN_DISTANCE if next_section == "LEFT" else
                      (BOTTOM_GREEN_TURN_DISTANCE if color == "green" else BOTTOM_RED_TURN_DISTANCE)
                      if next_section == "BOTTOM" else
                      RIGHT_GREEN_TURN_DISTANCE if color == "green" else RIGHT_RED_TURN_DISTANCE)
            if section == "LEFT":
                handoff = (LEFT_TO_BOTTOM_GREEN_HANDOFF_FRONT_M if color == "green"
                           else LEFT_TO_BOTTOM_RED_HANDOFF_FRONT_M)
                if handoff <= needed:
                    raise ValueError("LEFT->BOTTOM handoff must precede next section turn trigger")
        self._new_section()

    def _new_section(self):
        section = self.section
        colors = self.plans[section.lower()]
        self.controller = TwoCornerController(colors)
        # Reuse original TOP and LEFT route implementations without editing their settings.
        self.controller.section_label = "TOP" if section in ("TOP", "BOTTOM") else "LEFT"
        self.controller.physical_section = section
        if section in ("BOTTOM", "RIGHT"):
            self.controller.first_green_distance_override = (
                BOTTOM_GREEN_TURN_DISTANCE if section == "BOTTOM" else RIGHT_GREEN_TURN_DISTANCE)
            self.controller.first_red_distance_override = (
                BOTTOM_RED_TURN_DISTANCE if section == "BOTTOM" else RIGHT_RED_TURN_DISTANCE)
            self.controller.turn_pwm_override = BOTTOM_TURN_PWM if section == "BOTTOM" else RIGHT_TURN_PWM
            self.controller.turn_timeout_override = (BOTTOM_FIRST_TURN_MAX_SECONDS if section == "BOTTOM"
                                                     else RIGHT_FIRST_TURN_MAX_SECONDS)
        # RIGHT also has a next section on laps 1/2: TOP of the next lap.
        # On the last lap, RIGHT is terminal and uses its original stop distance.
        if self.section_index < len(self.ORDER) - 1:
            next_section = self.ORDER[self.section_index + 1]
        elif self.lap_count + 1 < TARGET_LAPS:
            next_section = "TOP"
        else:
            next_section = None
        next_first = self.plans[next_section.lower()][0] if next_section else None
        if section in ("TOP", "BOTTOM"):
            self.controller.top_gr_special = colors == ["green", "red"]
            if self.controller.top_gr_special:
                self.controller.top_gr_handoff_front = (
                    TOP_GR_LEFT_GREEN_HANDOFF_FRONT_M if next_first == "green"
                    else TOP_GR_LEFT_RED_HANDOFF_FRONT_M)
            self.controller.top_gg_to_left_red = colors == ["green", "green"] and next_first == "red"
            self.controller.top_gg_to_left_green = colors == ["green", "green"] and next_first == "green"
            if colors == ["red", "green"]:
                self.controller.top_rg_special = True
                self.controller.top_rg_left_first_red = next_first == "red"
                self.controller.top_rg_handoff_front = (
                    TOP_RG_LEFT_GREEN_HANDOFF_FRONT_M if next_first == "green"
                    else TOP_RG_LEFT_RED_HANDOFF_FRONT_M)
            if colors == ["red", "red"]:
                self.controller.rr_stop_front_override = (
                    TOP_RR_LEFT_GREEN_HANDOFF_FRONT_M if next_first == "green"
                    else TOP_RR_LEFT_RED_HANDOFF_FRONT_M)
            if section == "BOTTOM":
                # Separate BOTTOM -> RIGHT handoff tuning. TOP remains unmodified.
                handoff = (BOTTOM_TO_RIGHT_GREEN_HANDOFF_FRONT_M if next_first == "green"
                           else BOTTOM_TO_RIGHT_RED_HANDOFF_FRONT_M)
                if colors == ["red", "red"]:
                    self.controller.rr_stop_front_override = handoff
                elif colors == ["red", "green"]:
                    self.controller.top_rg_handoff_front = handoff
                elif colors == ["green", "red"]:
                    self.controller.top_gr_handoff_front = handoff
                # GG uses its own fixed TOP_GG_* handoff logic. It already uses
                # matching reference thresholds; use those defaults.
        elif section == "LEFT":
            top_colors = self.plans["top"]
            self.controller.left_green_from_top_gg = top_colors == ["green", "green"] and colors[0] == "green"
            self.controller.left_red_from_top_gg = top_colors == ["green", "green"] and colors[0] == "red"
            self.controller.left_red_from_top_gr = top_colors == ["green", "red"] and colors[0] == "red"
            self.controller.left_red_from_top_rr = top_colors == ["red", "red"] and colors == ["red", "red"]
            self.controller.left_rg_next_first_red = (colors == ["red", "green"]
                                                      and next_first == "red")
        if section in ("LEFT", "RIGHT") and colors == ["green", "green"] and next_first == "red":
            self.controller.gg_lr_next_first_red = True
            self.controller.gg_lr_handoff_front = (LEFT_TO_BOTTOM_RED_HANDOFF_FRONT_M
                if section == "LEFT" else RIGHT_TO_TOP_RED_HANDOFF_FRONT_M)
        if section == "LEFT":
            self.controller.end_front_override = (
                LEFT_TO_BOTTOM_GREEN_HANDOFF_FRONT_M if next_first == "green"
                else LEFT_TO_BOTTOM_RED_HANDOFF_FRONT_M)
        elif section == "RIGHT" and next_section == "TOP":
            # Finish RIGHT early so TOP can see its first pillar at a safe
            # approach distance. Preserve the four RIGHT color maneuvers.
            # This applies to RIGHT GG, GR, RG, and RR endpoint logic.
            self.controller.end_front_override = (
                RIGHT_TO_TOP_GREEN_HANDOFF_FRONT_M if next_first == "green"
                else RIGHT_TO_TOP_RED_HANDOFF_FRONT_M)
        elif section == "RIGHT" and next_section is None:
            # Last-lap handoff BEFORE 0.70 m, so a straight final approach
            # follows completion of the existing RIGHT corner maneuver.
            self.controller.end_front_override = FINAL_RIGHT_HANDOFF_FRONT_M
        self.state = f"{section}/APPROACH_1"

    def update(self, data, yaw):
        if self.fault:
            return ("STOP", 0, 0, self.fault)
        if yaw is None or not math.isfinite(yaw):
            self.fault = "Missing/invalid physical heading"
            return ("STOP", 0, 0, self.fault)
        if self.state == "FINAL/APPROACH":
            now = time.monotonic()
            front = data.get("front")
            if not data.get("connected") or now - data.get("received_at", 0) > SCAN_TIMEOUT:
                self.fault = "Final straight: stale/missing Hokuyo scan"
                return ("STOP", 0, 0, self.fault)
            if front is None or not math.isfinite(front):
                self.fault = "Final straight: no front distance"
                return ("STOP", 0, 0, self.fault)
            for sector in ("front", "front_left", "left", "right"):
                value = data.get(sector)
                if value is not None and math.isfinite(value) and value <= FRONT_STOP_DISTANCE:
                    self.fault = f"Final straight: emergency {sector} {value:.3f}m"
                    return ("STOP", 0, 0, self.fault)
            err = angle_error(0.0, yaw)
            if abs(err) > FINAL_APPROACH_MAX_YAW_ERROR_DEG:
                self.fault = f"Final straight heading deviated from 0: yaw={yaw:.1f}"
                return ("STOP", 0, 0, self.fault)
            if front <= FINAL_PARKING_FRONT_START_M:
                self.lap_count += 1
                self.state = "FINAL/PARKING_READY"
                print(f"[LAP] Finished {self.lap_count}/{TARGET_LAPS}; front={front:.2f}m; parking ready")
                return ("STOP", 0, 0, f"Front {front:.2f}m <= 0.70m; stop for parking")
            if now - self.final_approach_started > FINAL_APPROACH_TIMEOUT_S:
                self.fault = "Final straight approach timeout"
                return ("STOP", 0, 0, self.fault)
            # Keep heading at initial IMU zero; no section/pillar logic after lap 3.
            steer = int(round(max(-FINAL_APPROACH_MAX_STEER,
                                  min(FINAL_APPROACH_MAX_STEER, HEADING_KP * err))))
            return (f"DRIVE {steer} {FINAL_APPROACH_PWM}", steer, FINAL_APPROACH_PWM,
                    f"FINAL straight to 0.70m, front={front:.2f}m yaw={yaw:.1f}")
        if self.state == "FINAL/PARKING_READY":
            return ("STOP", 0, 0, "Ready for final parking")
        if self.state == "FINAL/DONE":
            return ("STOP", 0, 0, "Parking completed")
        virtual_yaw = (yaw + self.YAW_OFFSET[self.section]) % 360.0
        result = self.controller.update(data, virtual_yaw)
        self.state = f"{self.section}/{self.controller.state}"
        # DEBUG: GG inner-wall and RR outer-wall following on laps 2 and 3
        if self.lap_count >= 1:
            current_state = self.controller.state
            plan = self.plans[self.section.lower()]

            gg_follow = current_state in (
                "GG_WALL_FOLLOW",
                "LEFT_GG_WALL_FOLLOW"
            )
            rr_follow = current_state == "RR_STRAIGHT"

            if (plan == ["green", "green"] and gg_follow) or (
                plan == ["red", "red"] and rr_follow
            ):
                wall_side = "LEFT INNER" if gg_follow else "RIGHT OUTER"
                wall_distance = data.get("left" if gg_follow else "right")
                wall_target = (
                    TOP_GG_WALL_TARGET_M
                    if gg_follow else
                    RIGHT_RR_RIGHT_TARGET_M
                    if self.section == "RIGHT" else RR_RIGHT_TARGET_M
                )

                print(
                    f"[WALL DEBUG] "
                    f"Lap={self.lap_count + 1} "
                    f"Section={self.section} "
                    f"Mode={'GG' if gg_follow else 'RR'} "
                    f"Wall={wall_side} "
                    f"Distance={wall_distance} "
                    f"Target={wall_target:.2f}m "
                    f"PhysicalYaw={yaw:.2f} "
                    f"VirtualYaw={virtual_yaw:.2f} "
                    f"Steer={result[1]:+d} "
                    f"PWM={result[2]} "
                    f"Command={result[0]} "
                    f"Reason={result[3]}"
                )
        if self.controller.fault or self.controller.state == "BLOCKED_EXIT":
            self.fault = self.controller.fault or f"{self.section} navigation blocked"
            return result
        if self.controller.state != "DONE":
            return result
        # A full lap is counted only after RIGHT has really finished.
        # The physical IMU zero is retained for all laps: never re-zero.
        at_right_end = self.section_index == len(self.ORDER) - 1
        if at_right_end:
            if self.lap_count + 1 >= TARGET_LAPS:
                if abs(angle_error(0.0, yaw)) > FINAL_APPROACH_MAX_YAW_ERROR_DEG:
                    self.fault = f"Last RIGHT corner not aligned at 0 deg (yaw={yaw:.1f})"
                    return ("STOP", 0, 0, self.fault)
                # The user wants parking to begin when the final RIGHT route
                # finishes, even if the front LiDAR is above 0.74 m.
                # Require a fresh, valid LiDAR reading and preserve the
                # near-obstacle emergency checks before enabling parking.
                front = data.get("front")
                if (not data.get("connected") or
                        time.monotonic() - data.get("received_at", 0) > SCAN_TIMEOUT or
                        front is None or not math.isfinite(front)):
                    self.fault = "Final parking entry: missing/stale front LiDAR"
                    return ("STOP", 0, 0, self.fault)
                for sector in ("front", "front_left", "left", "right"):
                    value = data.get(sector)
                    if value is not None and math.isfinite(value) and value <= FRONT_STOP_DISTANCE:
                        self.fault = f"Final parking entry: emergency {sector} {value:.3f}m"
                        return ("STOP", 0, 0, self.fault)
                self.lap_count += 1
                self.state = "FINAL/PARKING_READY"
                print(f"[LAP] Finished {self.lap_count}/{TARGET_LAPS}; "
                      f"front={front:.2f}m; parking ready (no 0.74m approach)")
                return ("STOP", 0, 0,
                        f"Last RIGHT completed; parking ready at front={front:.2f}m")
            self.lap_count += 1
            print(f"[LAP] Completed {self.lap_count}/{TARGET_LAPS} at yaw={yaw:.1f}")
        destination = "TOP" if at_right_end else self.ORDER[self.section_index+1]
        expected = self.ENTRY_HEADING[destination]
        if abs(angle_error(expected, yaw)) > 25.0:
            self.fault = (f"{self.section} handoff heading error: physical yaw={yaw:.1f}, "
                          f"expected {expected:.0f}; manual inspection required")
            self.state = f"{self.section}/HANDOFF_BLOCKED"
            return ("STOP", 0, 0, self.fault)
        prior = self.section
        self.section_index = 0 if at_right_end else self.section_index + 1
        self.section = self.ORDER[self.section_index]
        self._new_section()
        if at_right_end:
            print(f"[LAP] Starting lap {self.lap_count + 1}/{TARGET_LAPS}: "
                  "RIGHT -> TOP; parking exit SKIPPED; TOP first turn uses front LiDAR")
        virtual_yaw = (yaw + self.YAW_OFFSET[self.section]) % 360.0
        # Heading at entry maps to virtual 0 degrees as in original first approach.
        result = self.controller.update(data, virtual_yaw)
        self.state = f"{self.section}/{self.controller.state}"
        print(f"[SECTION] {prior} -> {self.section} at yaw={yaw:.1f}; "
              f"plan={self.plans[self.section.lower()]}, command={result[0]}")
        if self.controller.fault:
            self.fault = self.controller.fault
        return result


# =========================================================
# PARKING EXIT (TIMED, NO IMU HEADING FEEDBACK)
# =========================================================

PARKING_EXIT_ENABLED = True
PARKING_COMMAND_PERIOD_S = 0.05

# (ESP32 command, duration seconds, description)
PARKING_RED = [
    ("DRIVE -50 120", 1.0, "RED: forward LEFT -50"),
    ("DRIVE 30 0",   0.3, "RED: steer RIGHT +30, motor stopped"),
    ("BACK 30 120",  0.5, "RED: reverse RIGHT +30"),
    ("STOP",         0.2, "RED: stop and center"),
    ("DRIVE -30 120", 1.10, "RED: forward LEFT -30"),
    ("DRIVE 50 120",  1.15, "RED: forward RIGHT +50"),
]
PARKING_GREEN = [
    ("DRIVE -50 150", 0.65, "GREEN: forward LEFT -50"),
    ("DRIVE 45 150",  0.4, "GREEN: forward RIGHT +45"),
]


def send_esp_command(esp, command):
    message = (mirror_command(command) + "\n").encode("ascii")
    if esp.write(message) != len(message):
        raise RuntimeError("Incomplete serial write: " + command)
    # ESP32 command-only interface: do not read unsolicited serial bytes.


def parking_exit(esp, plan):
    """Run the previously tested timed parking route without LiDAR or IMU gating.

    This mode has NO automatic obstacle detection during parking exit.
    Only use in a verified clear, supervised setup with independent E-stop.
    """
    color = plan["right"][1].lower()
    if color not in ("red", "green"):
        raise ValueError("Unexpected second RIGHT pillar color: " + color)

    top_first = plan["top"][0].lower()
    steps = list(PARKING_GREEN if color == "green" else PARKING_RED)
    if color == "green" and top_first == "green":
        command, _, description = steps[-1]
        steps[-1] = (command, 1.10, description + " [TOP GREEN adjustment]")
    print(f"[PARKING] TOP first pillar = {top_first.upper()}")
    print(f"[PARKING] RIGHT second pillar = {color.upper()}")
    print("[PARKING] Timed open-loop exit: no IMU or LiDAR checks")

    for step_index, (command, duration, description) in enumerate(steps):
        print(f"[PARKING] {description}: {duration:.2f}s")
        start = time.monotonic()
        while not stop_event.is_set():
            elapsed = time.monotonic() - start
            if elapsed >= duration:
                break
            send_esp_command(esp, command)
            with data_lock:
                control_data.update({
                    "serial_connected": True,
                    "command": command,
                    "state": description,
                    "stage": "PARKING_EXIT",
                    "yaw": None,
                    "steering": 0,
                    "speed": 0,
                    "lap": 0,
                })
            stop_event.wait(min(PARKING_COMMAND_PERIOD_S, duration - elapsed))

    send_esp_command(esp, "STOP")
    print("[PARKING] Exit sequence complete. Motor stopped; original IMU zero preserved.")
    with data_lock:
        control_data.update({"command": "STOP", "state": "Parking exit finished; original IMU zero preserved"})
    return not stop_event.is_set()


# =========================================================
# CUSTOM PARKING -> TOP FIRST-PILLAR HANDOFF
# =========================================================
# These are motor STEERING commands. 45 degrees is servo steering,
# NOT a requested 45-degree change in physical yaw.
TOP_ENTRY_LEFT_STEER = -45
TOP_ENTRY_TURN_PWM = 120
TOP_ENTRY_STRAIGHT_PWM = 120
TOP_ENTRY_TURN_TIMEOUT_S = 3.2
TOP_ENTRY_APPROACH_TIMEOUT_S = 6.0
TOP_ENTRY_FRONT_RED_AFTER_RIGHT_GREEN_M = 0.35
TOP_ENTRY_FRONT_RED_AFTER_RIGHT_RED_M = 0.35
TOP_ENTRY_MIN_TURN_FRONT_M = 0.10
TOP_ENTRY_MIN_TURN_SIDE_M = 0.10
TOP_ENTRY_TARGET_YAW = 270.0
TOP_ENTRY_TARGET_TOLERANCE = FIRST_TURN_REACHED_TOLERANCE
# Max heading error tolerated after the timed parking exit (was a hard 25 deg abort).
TOP_ENTRY_MAX_YAW_ERR_DEG = 45.0
TOP_ENTRY_ALIGN_STEER = 20   # steering limit while re-aligning to yaw 0


def entry_scan():
    """Read only fresh LiDAR data; absence of a scan is not free space."""
    with data_lock:
        data = dict(latest_data)
    now = time.monotonic()
    if not data.get("connected") or now - data.get("received_at", 0) > SCAN_TIMEOUT:
        raise RuntimeError("TOP entry: LiDAR is missing or stale")
    front = data.get("front")
    if front is None or not math.isfinite(front):
        raise RuntimeError("TOP entry: no valid front range")
    for sector in ("front", "front_left", "left", "right"):
        value = data.get(sector)
        if value is not None and math.isfinite(value) and value <= FRONT_STOP_DISTANCE:
            raise RuntimeError(f"TOP entry emergency {sector}={value:.3f}m")
    return data


def entry_command(esp, command, stage, imu):
    send_esp_command(esp, command)
    with data_lock:
        control_data.update({
            "serial_connected": True,
            "command": command,
            "state": stage,
            "stage": "PARKING_TO_TOP",
            "yaw": imu.read_yaw(),
            "lap": 0,
        })


def perform_top_entry(esp, imu, plan):
    """Complete the FIRST TOP corner; caller then resumes at TURN_SETTLE.

    The IMU was zeroed while stationary at the ORIGINAL PARKING START.
    Keep this SAME zero through parking exit, TOP entry and the full route.
    """
    top_color = plan["top"][0].lower()
    right_second = plan["right"][1].lower()
    if top_color not in ("green", "red") or right_second not in ("green", "red"):
        raise RuntimeError("TOP entry: invalid JSON pillar colors")

    # Only RED first pillar needs a LiDAR-controlled straight approach.
    if top_color == "red":
        trigger = (TOP_ENTRY_FRONT_RED_AFTER_RIGHT_GREEN_M
                   if right_second == "green"
                   else TOP_ENTRY_FRONT_RED_AFTER_RIGHT_RED_M)
        print(f"[TOP ENTRY] RIGHT-2={right_second}, TOP-1=RED: straight to {trigger:.2f}m")
        began = time.monotonic()
        while not stop_event.is_set():
            data = entry_scan()
            front = data["front"]
            if front <= trigger:
                entry_command(esp, "STOP", f"TOP RED straight trigger {front:.3f}m", imu)
                break
            yaw = imu.read_yaw()
            if time.monotonic() - began > TOP_ENTRY_APPROACH_TIMEOUT_S:
                raise RuntimeError(f"TOP RED: straight approach timeout: front={front:.3f}m "
                                   f"(trigger {trigger:.2f}m), yaw={yaw:.1f}, "
                                   f"left={data.get('left')}, right={data.get('right')}")
            print(f"[TOP ENTRY] t={time.monotonic() - began:4.1f}s front={front:.3f}m "
                  f"trigger={trigger:.2f}m yaw={yaw:.1f} "
                  f"left={data.get('left')} right={data.get('right')}")
            yaw_err = angle_error(0.0, yaw)
            if abs(yaw_err) > TOP_ENTRY_MAX_YAW_ERR_DEG:
                raise RuntimeError(f"TOP RED: approach heading drift yaw={yaw:.1f}")
            # The open-loop parking exit can leave the car off yaw 0. Use stronger
            # IMU re-alignment steering while the error is large, then the gentle limit.
            steer_limit = TOP_ENTRY_ALIGN_STEER if abs(yaw_err) > 12.0 else 10
            steering = int(max(-steer_limit, min(steer_limit, HEADING_KP * yaw_err)))
            entry_command(esp, f"DRIVE {steering} {TOP_ENTRY_STRAIGHT_PWM}",
                          f"TOP RED straight front={front:.3f}m trigger={trigger:.2f}m", imu)
            stop_event.wait(PARKING_COMMAND_PERIOD_S)
    else:
        print(f"[TOP ENTRY] RIGHT-2={right_second}, TOP-1=GREEN: start IMU turn after exit")

    if stop_event.is_set():
        send_esp_command(esp, "STOP")
        return False

    # LEFT turn until IMU yaw 270, using the same zero as the subsequent controller.
    began = time.monotonic()
    while not stop_event.is_set():
        data = entry_scan()
        front = data["front"]
        left = data.get("left")
        front_left = data.get("front_left")
        yaw = imu.read_yaw()
        if not math.isfinite(yaw):
            raise RuntimeError("TOP entry invalid IMU reading")
        if abs(angle_error(TOP_ENTRY_TARGET_YAW, yaw)) <= TOP_ENTRY_TARGET_TOLERANCE:
            entry_command(esp, "STOP", f"TOP first LEFT turn complete, yaw={yaw:.1f}", imu)
            print(f"[TOP ENTRY] IMU reached yaw={yaw:.2f}; handing over to original controller")
            return True
        if time.monotonic() - began > TOP_ENTRY_TURN_TIMEOUT_S:
            raise RuntimeError(f"TOP entry LEFT turn timed out at yaw={yaw:.1f}")
        if front <= TOP_ENTRY_MIN_TURN_FRONT_M:
            raise RuntimeError(f"TOP entry LEFT turn front too close: {front:.3f}m")
        if ((left is None or not math.isfinite(left) or left < TOP_ENTRY_MIN_TURN_SIDE_M)
            and (front_left is None or not math.isfinite(front_left)
                 or front_left < TOP_ENTRY_MIN_TURN_SIDE_M)):
            raise RuntimeError("TOP entry LEFT clearance missing or too close")
        # Avoid continuing past 270 if the sensor skips the tolerance window.
        if 180.0 <= yaw < TOP_ENTRY_TARGET_YAW - TOP_ENTRY_TARGET_TOLERANCE:
            raise RuntimeError(f"TOP entry LEFT turn overshot target: yaw={yaw:.1f}")
        entry_command(esp, f"DRIVE {TOP_ENTRY_LEFT_STEER} {TOP_ENTRY_TURN_PWM}",
                      f"TOP entry LEFT to yaw 270 (current {yaw:.1f})", imu)
        stop_event.wait(PARKING_COMMAND_PERIOD_S)
    send_esp_command(esp, "STOP")
    return False


# =========================================================

# ESP32 CONTROL THREAD

# =========================================================


def final_parking(esp, imu):
    """Reuse the running Hokuyo thread and ESP32 serial; read rear VL53L0X on I2C 1.

    All motions are supervised/time-bounded. Sensor data do not prove the
    robot's swept rear/side clearance or guarantee a 40 mm physical gap.
    """
    def park_cmd(command, phase, rear_mm=None, front_m=None):
        if stop_event.is_set():
            raise RuntimeError("Final parking interrupted")
        send_esp_command(esp, "STOP" if DRY_RUN else command)
        with data_lock:
            control_data.update({
                "serial_connected": True, "command": "STOP [dry-run]" if DRY_RUN else command,
                "state": phase, "stage": "FINAL/PARKING", "lap": TARGET_LAPS,
                "yaw": imu.read_yaw(),
                "rear_mm": rear_mm, "front": front_m,
            })

    def read_rear(sensor):
        distance = sensor.range
        if distance is None or not isinstance(distance, (int, float)) or not math.isfinite(distance) or distance <= 0:
            raise RuntimeError(f"VL53L0X invalid reading: {distance}")
        return float(distance)

    def fresh_front():
        with data_lock:
            snapshot = dict(latest_data)
        if (not snapshot.get("connected") or
            time.monotonic() - snapshot.get("received_at", 0) > SCAN_TIMEOUT):
            raise RuntimeError("Final parking: Hokuyo scan unavailable/stale")
        front = snapshot.get("front")
        if front is None or not math.isfinite(front):
            raise RuntimeError("Final parking: missing front Hokuyo range")
        # Independent near-obstacle emergency guard remains enabled.
        for sector in ("front", "front_left", "left", "right"):
            val = snapshot.get(sector)
            if val is not None and math.isfinite(val) and val <= FRONT_STOP_DISTANCE:
                raise RuntimeError(f"Final parking emergency {sector}={val:.3f}m")
        return float(front)

    if DRY_RUN:
        park_cmd("STOP", "Final parking skipped (DRY_RUN)")
        return True

    print("[FINAL PARKING] Initializing VL53L0X at /dev/i2c-1, address 0x29")
    rear_i2c = ExtendedI2C(1)
    rear_sensor = adafruit_vl53l0x.VL53L0X(rear_i2c, address=0x29)
    try:
        park_cmd("STOP", "Initialize rear VL53L0X")
        # Confirm a real reading before issuing any reverse command.
        first_rear = read_rear(rear_sensor)
        if first_rear <= FINAL_REVERSE_SWITCH_MM:
            raise RuntimeError(
                f"Parking reverse RIGHT skipped/unsafe: initial rear {first_rear:.0f}mm "
                f"<= switch {FINAL_REVERSE_SWITCH_MM}mm")

        # Phase 1: Reverse RIGHT +50 until rear 280 mm.
        # Phase 2: Continue reversing LEFT -50 until rear 40 mm.
        for phase, steer, threshold in (
            ("BACK RIGHT +50", FINAL_REVERSE_RIGHT_STEER, FINAL_REVERSE_SWITCH_MM),
            ("BACK LEFT -50", FINAL_REVERSE_LEFT_STEER, FINAL_REVERSE_STOP_MM),
        ):
            start = time.monotonic()
            command = f"BACK {steer} {FINAL_REVERSE_PWM}"
            while not stop_event.is_set():
                if time.monotonic() - start > FINAL_REVERSE_PHASE_MAX_S:
                    raise TimeoutError(f"{phase}: reverse timeout")
                mm = read_rear(rear_sensor)
                print(f"[FINAL PARKING] {phase}: rear={mm:.0f} mm, target={threshold} mm")
                if mm <= threshold:
                    park_cmd("STOP", f"{phase} distance reached {mm:.0f}mm", rear_mm=mm)
                    break
                park_cmd(command, phase, rear_mm=mm)
                stop_event.wait(FINAL_PARKING_COMMAND_PERIOD_S)
            else:
                raise RuntimeError("Parking cancelled")

        # Final forward RIGHT +15. Reuse existing shared Hokuyo data instead
        # of opening a second connection to the same LiDAR.
        park_cmd("STOP", "Reverse complete; forward phase preparing")
        stop_event.wait(0.2)
        start = time.monotonic()
        command = f"DRIVE {FINAL_FORWARD_RIGHT_STEER} {FINAL_FORWARD_PWM}"
        while not stop_event.is_set():
            if time.monotonic() - start > FINAL_FORWARD_MAX_S:
                raise TimeoutError("Final forward parking timeout")
            front = fresh_front()
            print(f"[FINAL PARKING] Forward RIGHT +15: front={front:.3f} m")
            if front <= FINAL_FORWARD_STOP_M:
                park_cmd("STOP", f"FINAL parked front={front:.3f}m", front_m=front)
                print("[FINAL PARKING] Complete; motor STOP and servo center via ESP32 STOP")
                return True
            park_cmd(command, "FORWARD RIGHT +15", front_m=front)
            stop_event.wait(FINAL_PARKING_COMMAND_PERIOD_S)
        raise RuntimeError("Parking cancelled")
    finally:
        # STOP is expected to center the steering in the user's ESP32 firmware.
        try:
            send_esp_command(esp, "STOP")
        except Exception:
            pass
        if hasattr(rear_i2c, "deinit"):
            rear_i2c.deinit()


def robot_control_worker():

    esp = None
    imu = None
    follower = None

    try:
        print(f"Opening ESP32 serial port: {ESP32_PORT}")

        esp = serial.Serial(
            ESP32_PORT,
            ESP32_BAUD,
            timeout=0,
            write_timeout=0.2
        )

        # Opening USB serial may reset the ESP32
        if stop_event.wait(2.0):
            return

        esp.reset_input_buffer()
        esp.write(b"STOP\n")

        # CRITICAL: zero the BNO055 while the robot is still stationary at
        # its ORIGINAL PARKING START, before sending any movement command.
        # The reference is not changed after the timed exit. This keeps
        # physical yaw 0 at the starting pose and TOP turn target at 270.
        send_esp_command(esp, "STOP")
        imu = IMUHeading()
        print(f"[IMU] Parking START zero established: yaw={imu.read_yaw():.2f} deg")

        # Parking exit uses second RIGHT pillar color from the JSON plan.
        # It is timed/open-loop, but does NOT reset the IMU heading.
        if PARKING_EXIT_ENABLED and not DRY_RUN:
            if not parking_exit(esp, TEST_PLAN):
                return
        elif PARKING_EXIT_ENABLED and DRY_RUN:
            print("[PARKING] Skipped because DRY_RUN=True")

        send_esp_command(esp, "STOP")
        if stop_event.wait(0.4):
            return
        print(f"[IMU] After parking exit (SAME starting zero): yaw={imu.read_yaw():.2f} deg")
        follower = FourSectionController(TEST_PLAN)
        if PARKING_EXIT_ENABLED and not DRY_RUN:
            if not perform_top_entry(esp, imu, TEST_PLAN):
                return
            # The custom entry has already performed TOP TURN_1.
            # Resume at its original settling / next-pillar logic,
            # rather than repeating TOP APPROACH_1 and TURN_1.
            follower.controller.phase("TURN_SETTLE", time.monotonic())
            follower.state = "TOP/TURN_SETTLE"
            print("[TOP ENTRY] Custom first TOP turn complete; original controller resumed at TOP/TURN_SETTLE")

        with data_lock:
            control_data.update({
                "serial_connected": True,
                "state": "Waiting for valid LiDAR data",
                "yaw": 0.0,
                "lap": 0
            })

        print("ESP32 connected")
        print(f"{TARGET_LAPS} LAPS: TOP -> LEFT -> BOTTOM -> RIGHT; DRY_RUN:", DRY_RUN)
        print("Two-pillar trial: first timed turn, then RED right-left or GREEN heading hold")

        while not stop_event.is_set():
            with data_lock:
                data = dict(latest_data)
                data["camera"] = dict(camera_data)

            # IMU controls yaw; LiDAR monitors clearance.
            yaw = imu.read_yaw()
            lap_count = follower.lap_count

            command, steering, speed, state = follower.update(data, yaw)
            lap_count = follower.lap_count

            message = (("STOP" if DRY_RUN else mirror_command(command)) + "\n").encode("ascii")

            if esp.write(message) != len(message):
                raise RuntimeError("Incomplete serial command write")

            # Do not read ESP32 serial: command-only connection.

            with data_lock:
                control_data.update({
                    "serial_connected": True,
                    "command": "STOP [dry-run: " + command + "]" if DRY_RUN else command,
                    "state": state,
                    "steering": steering,
                    "speed": speed,
                    "yaw": yaw,
                    "lap": lap_count,
                    "stage": follower.state
                })

            front = data.get("front")
            left = data.get("left")
            front_left = data.get("front_left")
            right = data.get("right")

            right_text = "--" if right is None else f"{right:.2f}"
            front_text = "--" if front is None else f"{front:.2f}"
            left_text = "--" if left is None else f"{left:.2f}"
            fl_text = "--" if front_left is None else f"{front_left:.2f}"

            cam = data.get("camera", {})
            cam_desc = ",".join(d["color"] for d in cam.get("detections", [])) if cam.get("connected") else "offline"
            print(
                f"Yaw: {yaw:6.2f} deg | Stage: {follower.state} | "
                f"Front: {front_text} m | "
                f"Left: {left_text} m | Right: {right_text} m | Front-left: {fl_text} m | "
                f"Camera: {cam_desc or 'none'} | {command} | {state}"
            )

            if follower.fault:
                print(f">>> NAVIGATION STOPPED ON FAULT. {follower.fault} <<<")
                break
            if follower.state == "FINAL/PARKING_READY":
                # Stop and let the chassis settle before any reverse steering.
                send_esp_command(esp, "STOP")
                print(f"[FINAL PARKING] Stationary pause for {FINAL_PARKING_SETTLE_SECONDS:.2f}s before reverse")
                if stop_event.wait(FINAL_PARKING_SETTLE_SECONDS):
                    print("[FINAL PARKING] Cancelled during stationary pause")
                    break
                print(f">>> {TARGET_LAPS} LAPS COMPLETE, STARTING FINAL PARKING <<<")
                if final_parking(esp, imu):
                    follower.state = "FINAL/DONE"
                    with data_lock:
                        control_data.update({"command": "STOP", "state": "Final parking complete",
                                             "stage": "FINAL/DONE", "lap": TARGET_LAPS})
                    print(">>> FINAL PARKING COMPLETE <<<")
                break

            stop_event.wait(CONTROL_INTERVAL)

    except Exception as error:
        print(f"Control error: {error}")

        with data_lock:
            control_data.update({
                "serial_connected": False,
                "state": f"Control error: {error}"
            })

    finally:
        stop_sent = False

        if esp is not None:
            try:
                stop_sent = esp.write(b"STOP\n") == 5
            except Exception:
                pass

            esp.close()

        if imu is not None:
            imu.close()

        with data_lock:
            control_data.update({
                "serial_connected": False,
                "command": "STOP" if stop_sent else "STOP unconfirmed",
                "steering": 0,
                "speed": 0
            })

            if stop_event.is_set():
                control_data["state"] = "Controller stopped"

        print("Control thread exited")


# =========================================================

# WEBPAGE

# =========================================================


HTML_PAGE = """

<!DOCTYPE html>

<html lang="en">

<head>

    <meta charset="UTF-8">

    <meta name="viewport" content="width=device-width, initial-scale=1">

    <title>LiDAR Two-Pillar Straight Test</title>


    <style>

        * { box-sizing: border-box; }


        body {

            margin: 0;

            background: #07111f;

            color: #e5e7eb;

            font-family: Arial, sans-serif;

        }


        header {

            padding: 18px 24px;

            background: #111827;

        }


        h1 { margin: 0 0 8px; font-size: 23px; }

        header p { margin: 0; color: #94a3b8; }


        .container {

            display: grid;

            grid-template-columns: minmax(0, 1fr) 280px;

            gap: 16px;

            padding: 16px;

        }


        .viewer {

            height: 75vh;

            min-height: 350px;

            background: #020617;

            border: 1px solid #334155;

            border-radius: 12px;

        }


        canvas { width: 100%; height: 100%; display: block; }


        .sidebar {

            display: flex;

            flex-direction: column;

            gap: 12px;

        }


        .card {

            padding: 16px;

            background: #111827;

            border: 1px solid #334155;

            border-radius: 12px;

        }


        .label { color: #94a3b8; font-size: 13px; margin-bottom: 8px; }

        .value { font-size: 25px; font-weight: bold; }

        .small { line-height: 1.6; overflow-wrap: anywhere; }


        #front { color: #facc15; }

        #left { color: #38bdf8; }

        #right { color: #f472b6; }


        @media (max-width: 800px) {

            .container { grid-template-columns: 1fr; }

            .viewer { height: 55vh; }

        }

    </style>

</head>


<body>

<header>

    <h1>LiDAR Two-Pillar Straight Test</h1>

    <p>Front 180° view | Range 3 m | Straight driving with gentle side-wall avoidance</p>

</header>


<div class="container">

    <div class="viewer">

        <canvas id="canvas"></canvas>

    </div>


    <div class="sidebar">

        <div class="card small">

            <div>LiDAR: <span id="lidarStatus">Waiting...</span></div>

            <div>ESP32: <span id="espStatus">Waiting...</span></div>

            <div id="error"></div>

        </div>


        <div class="card">

            <div class="label">FRONT</div>

            <div id="front" class="value">--</div>

        </div>


        <div class="card">

            <div class="label">LEFT</div>

            <div id="left" class="value">--</div>

        </div>


        <div class="card">

            <div class="label">RIGHT</div>

            <div id="right" class="value">--</div>

        </div>


        <div class="card">

            <div class="label">FRONT-LEFT</div>

            <div id="frontLeft" class="value">--</div>

        </div>


        <div class="card small">

            <div class="label">CONTROL</div>

            <div id="state">Waiting...</div>

            <div>Command: <strong id="command">STOP</strong></div>

            <div>Steering: <span id="steering">0</span>°</div>

            <div>PWM: <span id="speed">0</span></div>

            <div>Yaw: <span id="yaw">--</span>°</div>

            <div>Stage: <span id="stage">--</span></div>

        </div>

    </div>

</div>


<script>

const canvas = document.getElementById("canvas");

const ctx = canvas.getContext("2d");

const MAX_DISTANCE = 3.0;


let scanData = {angles: [], distances: []};


function show(id, value) {

    document.getElementById(id).textContent = value;

}


function distanceText(value) {

    return Number.isFinite(value) ? value.toFixed(2) + " m" : "No valid reading";

}


function resizeCanvas() {

    const ratio = window.devicePixelRatio || 1;

    const rect = canvas.getBoundingClientRect();


    canvas.width = Math.round(rect.width * ratio);

    canvas.height = Math.round(rect.height * ratio);


    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

}


function draw() {

    const w = canvas.clientWidth;

    const h = canvas.clientHeight;

    const ox = w / 2;

    const oy = h * 0.91;

    const scale = Math.min(w * 0.46, h * 0.80) / MAX_DISTANCE;


    ctx.clearRect(0, 0, w, h);

    ctx.lineWidth = 1;

    ctx.strokeStyle = "#263244";

    ctx.fillStyle = "#94a3b8";

    ctx.font = "12px Arial";


    for (let d = 0.5; d <= MAX_DISTANCE; d += 0.5) {

        ctx.beginPath();

        ctx.arc(ox, oy, d * scale, Math.PI, 2 * Math.PI);

        ctx.stroke();

        ctx.fillText(d.toFixed(1) + " m", ox + 6, oy - d * scale + 14);

    }


    for (const angle of [-90, -60, -30, 0, 30, 60, 90]) {

        const rad = angle * Math.PI / 180;

        const x = ox - Math.sin(rad) * MAX_DISTANCE * scale;

        const y = oy - Math.cos(rad) * MAX_DISTANCE * scale;


        ctx.beginPath();

        ctx.moveTo(ox, oy);

        ctx.lineTo(x, y);

        ctx.stroke();

        ctx.fillText(angle + "°", x - 10, y - 8);

    }


    ctx.fillStyle = "#22c55e";


    for (let i = 0; i < scanData.distances.length; i++) {

        const d = scanData.distances[i];

        const angle = scanData.angles[i];


        if (!Number.isFinite(d) || !Number.isFinite(angle)) continue;


        const rad = angle * Math.PI / 180;

        const x = ox - Math.sin(rad) * d * scale;

        const y = oy - Math.cos(rad) * d * scale;


        ctx.beginPath();

        ctx.arc(x, y, 2, 0, 2 * Math.PI);

        ctx.fill();

    }


    ctx.fillStyle = "#ffffff";

    ctx.beginPath();

    ctx.arc(ox, oy, 6, 0, 2 * Math.PI);

    ctx.fill();

    ctx.fillText("LiDAR", ox - 16, oy + 23);


    requestAnimationFrame(draw);

}


async function update() {

    try {

        const response = await fetch("/scan", {cache: "no-store"});

        if (!response.ok) throw new Error("HTTP " + response.status);


        const data = await response.json();


        scanData = data.fresh ? data : {angles: [], distances: []};


        show("lidarStatus", data.fresh ? "Receiving scans" : "Offline / stale");

        show("espStatus",

             data.control.serial_connected ? "Serial open" : "Serial closed");

        show("error", data.error || "");


        show("front", distanceText(data.fresh ? data.front : null));

        show("left", distanceText(data.fresh ? data.left : null));

        show("right", distanceText(data.fresh ? data.right : null));

        show("frontLeft", distanceText(data.fresh ? data.front_left : null));


        show("state", data.control.state);

        show("command", data.control.command);

        show("steering", data.control.steering);

        show("speed", data.control.speed);
        show("yaw", Number.isFinite(data.control.yaw) ? data.control.yaw.toFixed(1) : "--");
        show("stage", data.control.stage || "--");


    } catch (error) {

        show("lidarStatus", "Web connection error");

        show("espStatus", "Unknown");

        show("state", "Web connection lost; robot state unknown");

        scanData = {angles: [], distances: []};


    } finally {

        setTimeout(update, 100);

    }

}


window.addEventListener("resize", resizeCanvas);

resizeCanvas();

draw();

update();

</script>

<section style="margin:20px auto;max-width:960px;padding:16px;background:#18222c;color:white;border-radius:12px">
  <h2 style="margin-top:0">YOLO Camera Debug — traffic_sign_detector.pt</h2>
  <img src="/camera" alt="Annotated camera with live YOLO pillar detections"
       style="display:block;width:100%;max-width:800px;aspect-ratio:4/3;object-fit:contain;background:#050505" />
  <div id="camDebug" style="margin-top:12px;white-space:pre-wrap;font-family:monospace">Waiting for camera…</div>
  <p style="font-size:12px;color:#c2ccd8">Angles are estimated from camera calibration. Front camera usually cannot see side LiDAR sectors at ±85°. Detection does not override collision safety.</p>
</section>
<script>
async function updateCameraDebug() {
  try {
    const response = await fetch('/scan', {cache:'no-store'});
    const data = await response.json();
    const c = data.camera || {};
    const fresh = c.connected && (c.received_at || 0) > 0;
    const items = (c.detections || []).map(d =>
      `${d.color.toUpperCase()}  confidence=${d.confidence}  camera angle=${d.angle_min.toFixed(1)}..${d.angle_max.toFixed(1)} deg`);
    document.getElementById('camDebug').textContent =
      `Camera: ${fresh ? 'connected' : 'offline'} | Detections: ${items.length} | Error: ${c.error || 'none'}\n` +
      (items.join('\n') || 'No red/green boxes above confidence threshold');
  } catch (e) { document.getElementById('camDebug').textContent = 'Camera status unavailable: ' + e; }
}
setInterval(updateCameraDebug, 350);
updateCameraDebug();
</script>
</body>

</html>

"""


# =========================================================

# FLASK ROUTES

# =========================================================


@app.route("/")

def index():

    return render_template_string(HTML_PAGE)


@app.route("/camera")
def camera_stream():
    """Live annotated YOLO preview, separate from robot control."""
    def frames():
        while not stop_event.is_set():
            with data_lock:
                jpg = camera_preview_jpeg
            if jpg is not None:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
            stop_event.wait(0.10)
    return Response(frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/scan")

def scan_endpoint():

    with data_lock:

        data = dict(latest_data)

        data["control"] = dict(control_data)
        data["camera"] = dict(camera_data)


    if CLOCKWISE:
        # Show true physical left/right on the dashboard.
        data["left"], data["right"] = data["right"], data["left"]
        data["angles"] = data.get("display_angles", data["angles"])

    data["fresh"] = bool(

        data["connected"]

        and time.monotonic() - data["received_at"] <= SCAN_TIMEOUT

    )


    return jsonify(data)


# =========================================================

# MAIN

# =========================================================


def main():
    global TEST_PLAN
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 wro_four_sections.py wro_pillars.json")
    # Current development interface: the map is supplied on the command line.
    # Competition workflow: replace this manual input with the JSON produced by
    # the stationary three-angle camera scan, then keep the map immutable while
    # the robot drives.
    TEST_PLAN = load_test_plan(sys.argv[1])
    print("TEST PLAN:", TEST_PLAN, "DRY_RUN:", DRY_RUN)

    lidar_thread = threading.Thread(

        target=lidar_worker,

        daemon=True

    )


    control_thread = threading.Thread(

        target=robot_control_worker,

        daemon=True

    )


    camera_thread = threading.Thread(target=camera_worker, daemon=True)
    camera_thread.start()
    lidar_thread.start()

    control_thread.start()


    print(f"Viewer: http://<computer-IP>:{WEB_PORT}")

    print("Press Ctrl+C to stop")


    try:

        app.run(

            host="0.0.0.0",

            port=WEB_PORT,

            debug=False,

            threaded=True,

            use_reloader=False

        )


    finally:

        stop_event.set()

        control_thread.join(timeout=3.0)

        lidar_thread.join(timeout=6.0)
        camera_thread.join(timeout=2.0)

        print("Application stopped")


if __name__ == "__main__":

    main()
