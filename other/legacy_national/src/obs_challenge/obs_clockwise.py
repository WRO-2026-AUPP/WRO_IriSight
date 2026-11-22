#!/usr/bin/env python3
"""
Depth-only left-wall-following test for RealSense D455.
Clockwise

Behaviour:
- Keep approximately 0.60 m from the left wall using the depth camera.
- When the front distance is below 0.60 m, turn right.
- Continue turning right until the front opens beyond 0.80 m.
- AI (YOLO, best1.pt) + depth-based obstacle avoidance:
    - GREEN box detected close ahead -> steer LEFT to pass it (toward the
      outer/followed wall — guarded by limit_steer_for_outer_wall()).
    - RED box detected close ahead  -> steer RIGHT to pass it (toward the
      inner wall — guarded by limit_steer_for_inner_wall()).
    - Column-based proportional steering (KP_PILLAR + a per-ROI-zone target
      column table, TX_RED/TX_GREEN, looked up via target_column() based on
      whether the box currently sits in the LEFT_ROI, FRONT_ROI, or
      RIGHT_ROI zone of the frame), same-colour handover for two close
      pillars, a corner lock so a pillar seen mid front-wall-turn takes
      priority over the turn, and a stop-then-back recovery if the front
      wall or pillar gets too close mid-avoidance. Ported from the WRO v6
      right-wall-follower reference.
- Left/right ultrasonic sensors (from the ESP32, "USL <cm>" / "USR <cm>")
  back up the RealSense depth ROIs on both wall guards:
    - USR (right ultrasonic) backs up the inner-wall guard.
    - USL (left ultrasonic)  backs up the outer-wall guard.
  Ultrasonic and depth are independent checks; whichever is more
  restrictive at any instant wins.
- Use BNO055 relative yaw to stop after 3 counter-clockwise laps.

Jetson -> ESP32 protocol:
    DRIVE <steerDeg> <speed>\n   (normal driving)
    BACK  <steerDeg> <speed>\n   (fail-recovery reverse — ESP32 firmware
                                  must support this in addition to DRIVE)
    USL <cm>\n / USR <cm>\n      (ESP32 -> Jetson, read continuously by a
                                  background thread)
Steering convention used by the existing robot code:
    positive = RIGHT
    negative = LEFT
"""

import signal
import threading
import time
from collections import deque

import cv2
import numpy as np
import pyrealsense2 as rs
import serial
from flask import Flask, Response
from ultralytics import YOLO

from bno055_yaw import BNO055Yaw


# ---------------------------------------------------------------------------
# TUNABLES
# ---------------------------------------------------------------------------
SERIAL_PORT = "/dev/esp32"
SERIAL_BAUD = 115200

class ResilientSerial:
    def __init__(self, port=SERIAL_PORT, baud=SERIAL_BAUD):
        self.port = port
        self.baud = baud
        self.ser = None
        self.lock = threading.Lock()
        self._connect()

    def _connect(self):
        while True:
            try:
                if self.ser:
                    try:
                        self.ser.close()
                    except Exception:
                        pass
                self.ser = serial.Serial(self.port, self.baud, timeout=1)
                print(f"[SERIAL] connected to {self.port}")
                return
            except (serial.SerialException, FileNotFoundError) as e:
                print(f"[SERIAL] connect failed: {e}, retrying in 1s")
                time.sleep(1)

    def write(self, data):
        with self.lock:
            try:
                self.ser.write(data)
                return True
            except (serial.SerialException, OSError) as e:
                print(f"[SERIAL] write failed: {e}, reconnecting")
                self._connect()
                return False

    def read(self, size=1):
        with self.lock:
            try:
                return self.ser.read(size)
            except (serial.SerialException, OSError) as e:
                print(f"[SERIAL] read failed: {e}, reconnecting")
                self._connect()
                return b""

    def readline(self):
        with self.lock:
            try:
                return self.ser.readline()
            except (serial.SerialException, OSError) as e:
                print(f"[SERIAL] readline failed: {e}, reconnecting")
                self._connect()
                return b""

esp32 = ResilientSerial()

SERIAL_TIMEOUT = 0.05

# BNO055 IMU. Change IMU_ADDRESS to 0x29 if that is your detected address.
IMU_ADDRESS = 0x28
IMU_BUS = 1
IMU_CALIBRATION_FILE = "bno055_calibration.json"

# Counter-clockwise lap sequence for left-wall following:
# Initial direction is always set to relative 0 degrees.
# A checkpoint is accepted when the yaw enters its broad 90-degree zone:
#    90 zone: target 90 degrees
#   180 zone: target 180 degrees
#   270 zone: target 270 degrees
#     0 zone: target 0 degrees 
LAP_YAW_CHECKPOINTS = (90.0, 180.0, 270.0, 0.0)
LAP_ZONE_HALF_WIDTH = 10.0
LAPS_TO_COMPLETE = 3
STOP_DELAY_AFTER_LAPS = 0.5  # seconds to continue driving after lap 3

LEFT_TARGET = 0.81        # m: biased target for an actual 0.60 m wall gap
FRONT_STOP = 0.75         # m: start turning left below this distance 0.60
FRONT_CLEAR = 0.80        # m: finish the left turn above this distance 0.70

KP_STEER = 35.0           # steering degrees per metre of wall-distance error 38
KD_STEER = 4.0            # damping; reduce if steering becomes noisy
STEER_LIMIT = 35.0

BASE_SPEED = 150          # reduce for the first test 150
TURN_SPEED = 130      # 140
TURN_STEER = 30.0         # positive means RIGHT

# If the left wall is temporarily not visible, search gently to the left.
SEARCH_LEFT_STEER = -10.0

# ---- Left-wall reading sanity / smoothing -----------------------------
# roi_distance() can jump a lot in a single frame -- a genuine opening in
# the wall, a glancing-angle depth dropout, or a momentary bad median can
# all send left_distance from "close wall" to "far background" between
# consecutive frames. Feeding that raw jump straight into the PD term below
# saturates steering at -STEER_LIMIT for as long as the reading persists,
# even if it was just one noisy frame. Two independent guards handle this:
#   1. LEFT_WALL_MAX_STEP rate-limits the value used for wall-follow so a
#      one-frame jump can't move the effective reading further than this
#      many metres per frame -- smooths real noise while still tracking a
#      genuinely receding wall over a few frames instead of instantly.
#   2. LEFT_WALL_LOST_MULT: if the (rate-limited) reading is still further
#      than LEFT_TARGET * this multiplier, the "wall" is almost certainly
#      not the actual left wall anymore (an opening/corner, or background
#      leaking through a lost lock) -- treat it as "wall not usable" and
#      fall back to SEARCH_LEFT_STEER instead of demanding a maxed-out PD
#      correction toward open space.
# NOTE: these only affect the wall-FOLLOW term. The raw, un-smoothed
# left_distance still feeds limit_steer_for_outer_wall() immediately, so a
# real close-in hazard is never delayed by this smoothing.
LEFT_WALL_MAX_STEP = 0.15   # m: max per-frame change allowed in the 0.15
                            #    smoothed left-wall reading
LEFT_WALL_LOST_MULT = 1.8   # smoothed reading beyond LEFT_TARGET * this -> 1.8
                            #    treat the wall as lost, not just "far"
LEFT_ERROR_CLAMP = 0.5      # m: hard clamp on (LEFT_TARGET - left_distance)
                            #    before it's multiplied by KP_STEER, so even
                            #    a legitimate large error can't singlehandedly
                            #    demand more than a bounded correction

# ---- Inner-wall (right side) safety guard ----------------------------------
# This track has an inner wall on the robot's right for the whole lap
# (RIGHT_ROI). Any rightward steer command — normal wall-follow correction,
# the front-wall turn, or red-obstacle avoidance — can drive the robot into
# it if we don't check. This guard limits/overrides rightward steering,
# regardless of which mode produced it, based on live right-side clearance.
INNER_WALL_SOFT_CLEAR = 0.50   # m: below this, taper max rightward steer down 0.45
INNER_WALL_HARD_CLEAR = 0.15  # m: below this, block right steer and push left 0.12
INNER_WALL_PUSH_LEFT = -10.0   # deg: forced left steer inside the hard zone

# Wider margins used only while obstacle_corner_lock_until is active. During
# corner lock, pillar avoidance overrides the front-wall turn logic near a
# corner that may already be tight on the inner side — give this specific
# window a bigger buffer so the guard engages sooner instead of relying on
# the normal (tighter) clearances above.
INNER_WALL_SOFT_CLEAR_LOCKED = 0.40
INNER_WALL_HARD_CLEAR_LOCKED = 0.20

# ---- Outer-wall (left side / followed wall) safety guard -------------------
# GREEN-obstacle avoidance steers LEFT — toward the same outer wall we
# normally follow. The PD wall-follower keeps a safe gap during normal
# driving, but the avoidance steer overrides the PD term, so this is an
# independent backup clamp, mirroring the inner-wall guard above but for
# leftward steer and LEFT_ROI/left_distance.
OUTER_WALL_SOFT_CLEAR = 0.45   # m: below this, taper max leftward steer down 0.45
OUTER_WALL_HARD_CLEAR = 0.20   # m: below this, block left steer and push right 0.20
OUTER_WALL_PUSH_RIGHT = 10.0   # deg: forced right steer inside the hard zone

# ---- Ultrasonic backup for both wall guards ---------------------------------
# Read from the ESP32 ("USL <cm>" / "USR <cm>") by a background thread.
# USR (right ultrasonic) backs up the inner-wall guard (RED avoidance side).
# USL (left ultrasonic)  backs up the outer-wall guard (GREEN avoidance side).
# Ultrasonic and RealSense depth are independent checks — whichever is more
# restrictive at any instant wins.
#
# LEFT and RIGHT are tuned independently below -- e.g. the track's inner
# (right) wall and outer (left) wall don't have to be kept at the same
# distance.

# Left ultrasonic (USL) -- how far to stay from the LEFT wall.
US_MIN_CM_LEFT = 15.0      # cm: HARD limit — push away from the left wall 15
US_SOFT_CM_LEFT = 25.0     # cm: SOFT limit — stop steering further toward it
US_PUSH_STEER_LEFT = 15.0  # deg: forced push-away steer inside the hard zone

# Right ultrasonic (USR) -- how far to stay from the RIGHT wall.
US_MIN_CM_RIGHT = 15.0      # cm: HARD limit — push away from the right wall 15
US_SOFT_CM_RIGHT = 25.0     # cm: SOFT limit — stop steering further toward it
US_PUSH_STEER_RIGHT = 15.0  # deg: forced push-away steer inside the hard zone

US_STALE_S = 0.5       # s: ignore a reading if no fresh update this long
US_MEDIAN_N = 3        # median over the last N readings (glitch rejection)

# Ignore unsafe/noisy depth readings outside this interval.
MIN_VALID_DEPTH = 0.15
MAX_VALID_DEPTH = 4.00
MIN_VALID_PIXELS = 50

DEPTH_W, DEPTH_H, FPS = 640, 480, 30

# Regions of interest (x0, x1, y0, y1) as fractions of the frame.
#
# Contiguous full-width split into three equal vertical thirds -- no gaps
# and no overlap between zones -- starting below the horizon line and
# running to the bottom of the frame. This matches the sketch: one
# horizontal line, two vertical dividers, "Left | Front | Right" sitting
# side by side across the whole image width.
ROI_Y0 = 0.40               # top edge of all three ROIs (fraction of height) 0.6
ROI_Y1 = 0.70
ROI_SPLIT_1 = 1.0 / 3.0      # left/front divider (fraction of width)
ROI_SPLIT_2 = 2.0 / 3.0      # front/right divider (fraction of width)

LEFT_ROI  = (0.0,          ROI_SPLIT_1, ROI_Y0, ROI_Y1)
FRONT_ROI = (ROI_SPLIT_1,  ROI_SPLIT_2, ROI_Y0, ROI_Y1)
RIGHT_ROI = (ROI_SPLIT_2,  1.0,         ROI_Y0, ROI_Y1)

WEB_PORT = 5000

# ---------------------------------------------------------------------------
# OBSTACLE AVOIDANCE (AI colour-box detection + depth)
# ---------------------------------------------------------------------------
# best1.pt was trained with classes: 0=greenbox, 1=redbox, 2=xparking.
# Classes are matched by substring ("red"/"green") rather than exact name,
# see build_color_map() below, so "xparking" is automatically ignored.
AI_MODEL_PATH = "best1.pt"
AI_IMG_SIZE = 416
AI_INFER_EVERY_N_FRAMES = 1  # raise (e.g. 2 or 3) if inference is too slow

RED_LABEL = "red"
GREEN_LABEL = "green"
OBSTACLE_CONF_THRESHOLD = 0.70 #0.45

OBSTACLE_BOX_COLOR = {
    RED_LABEL: (0, 0, 255),
    GREEN_LABEL: (0, 255, 0),
}

# ---- pillar tracking / column-based avoidance (ported from the v6 field
# script) ---------------------------------------------------------------
ENGAGE_DIST = 1.6     # m: start actively avoiding a pillar closer than this
PASS_DIST = 0.25      # m: pillar this close = we are physically passing it
MEMORY_TTL = 0.3      # s: YOLO flicker tolerance before dropping a lost pillar
HOLD_TIME = 0.25      # s: keep steering the last avoid command briefly after
                      #    a close pillar is lost, instead of snapping back
                      #    straight to normal wall-follow mid-pass
HOLD_ARM_DIST = 0.55  # m: only hold if the lost pillar was at least this close

KP_PILLAR = 100.0     # deg per unit of pillar column error (0..1)

# ---- pass-side target columns, split per ROI zone --------------------------
# GREEN steers LEFT (toward the outer/followed wall), RED steers RIGHT
# (toward the inner wall).
#
# Which target column to use is looked up via target_column() based on
# which of the three existing ROI zones (LEFT_ROI / FRONT_ROI / RIGHT_ROI)
# the box's cx currently falls into. The three zones are NOT identical:
#   - FRONT zone (dead ahead): full, normal avoidance correction.
#   - The zone on the box's "far" side from its pass-wall (RIGHT_ROI for
#     GREEN, LEFT_ROI for RED): box is still far from being passed, so
#     keep the full aggressive target -- same as FRONT.
#   - The zone on the box's own pass-wall side (LEFT_ROI for GREEN,
#     RIGHT_ROI for RED): if the box is already sitting out here, it's
#     likely already close to that wall, so the target is eased back
#     toward centre -- we let limit_steer_for_outer_wall() /
#     limit_steer_for_inner_wall() do the hard work of keeping clearance
#     instead of the avoidance term demanding an even harder steer into
#     the wall the box is already sitting next to.
# Tune these numbers freely -- they're independent per zone.
TX_GREEN = {
    "left":  0.90,   # was 0.70
    "front": 0.80,   # was 0.75  -> stop constant-saturating at STEER_LIMIT
    "right": 0.85,   # was 0.83 (too high = maxed-out left constantly; too low = weak/late correction or wrong-direction steer)
}
TX_RED = {
    "left":  0.17,   # was 0.20
    "front": 0.42,   # was 0.45  -> now gives real proportional authority
    "right": 0.50,   # was 0.53  # Red avoidance steers RIGHT (positive).lower than typical cx, so (cx − tx) is positive → right steer.
}
AVOID_SPEED = 120     # PWM while a pillar is actively being avoided/held 130

# ---- red-red tight-turn corner ---------------------------------------------
# At an inner-block corner where the course also demands a tight RIGHT turn,
# two RED pillars can sit close together right at that corner (see the WRO
# field sketch — two obstacles stacked right where the path bends around the
# inner block). TURN_STEER (the front-wall turn) and RED-pillar avoidance
# (KP_PILLAR steering right) both push the SAME direction here — unlike the
# green-vs-turn or mixed-colour cases, which conflict — so this is not a
# "cancel the turn" situation like obstacle_corner_lock_until; it's a
# "combine the two rightward demands and slow down" situation.
RED_RED_CORNER_GAP_M = 0.30     # m: max distance between the two REDs to count as one tight-corner pair 0.60
RED_RED_CORNER_STEER = 17.0     # deg: steering floor used while locked into a red-red tight corner
RED_RED_CORNER_SPEED = 110      # PWM: slow down through the tight double-pillar corner

# ---- same-colour handover -----------------------------------------------
# Two same-colour pillars close together (e.g. at a corner): once the
# closest one has visibly slid to its "passed" side of the frame — or is
# basically alongside us — and another same-colour pillar is still ahead,
# switch to it immediately instead of waiting for YOLO to lose the first box.
SAME_COLOR_PASSED_CX = 0.30    # how far toward the frame edge counts as "passed"
SAME_COLOR_MIN_GAP_M = 0.12    # reject a duplicate box at nearly the same depth
SAME_COLOR_HOLD_S = 0.30       # keep the new target through brief YOLO flicker

# ---- corner lock -----------------------------------------------------------
# If a pillar is detected while the robot is mid front-wall turn, cancel the
# turn and commit to avoiding the pillar for a short time, instead of
# alternating between "turn" and "avoid" every frame.
CORNER_LOCK_S = 0 #0.5

# ---- fail recovery: stop, then back up -------------------------------------
# Triggers if the front wall or the actively-avoided pillar gets dangerously
# close mid-avoidance — usually means the gap won't be made in time.
# NOTE: requires the ESP32 firmware to additionally support
# "BACK <steerDeg> <speed>" alongside the existing "DRIVE <steerDeg> <speed>".
FAIL_FRONT_M = 0.35
FAIL_PILLAR_M = 0.25
RECOVERY_MEMORY_S = 0.80
RECOVERY_TRIGGER_HOLD = 0.18
RECOVERY_STOP_S = 0.25
RECOVERY_BACK_S = 0.55
RECOVERY_BACK_MIN_S = 0.18
RECOVERY_BACK_SPEED = 110
RECOVERY_BACK_STEER = 4        # small steer prevents a reverse 180-degree spin
RECOVERY_COOLDOWN_S = 2.50
RECOVERY_EXIT_FRONT_M = 0.48


# ---------------------------------------------------------------------------
# GLOBALS
# ---------------------------------------------------------------------------
running = True
frame_jpg = None
frame_lock = threading.Lock()

# Ultrasonic state (written by the serial-reader thread, read by the main loop).
us_lock = threading.Lock()
usl_hist = deque(maxlen=US_MEDIAN_N)
usr_hist = deque(maxlen=US_MEDIAN_N)
usl_cm = float("nan")
usr_cm = float("nan")
usl_time = 0.0
usr_time = 0.0

app = Flask(__name__)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def limit_steer_for_inner_wall(
    steer: float,
    right_distance: float,
    usr_valid: bool = False,
    usr_value_cm: float = float("nan"),
    locked: bool = False,
) -> float:
    """
    Clamp/override rightward steering so the robot never closes the gap to
    the inner wall (right side, RIGHT_ROI) below a safe minimum.

    This is deliberately applied AFTER every mode decides its steer — normal
    wall-follow, the front-wall turn, and red-obstacle avoidance all issue
    rightward steer commands, and any of them can drive the robot into the
    inner wall if this isn't checked centrally.

    Combines two independent checks — RealSense right-side depth
    (right_distance) and the right ultrasonic sensor (usr) — and applies
    whichever is more restrictive. Only ever pulls the steer toward LEFT
    (reduces or reverses a rightward command); it never pushes further
    right, and never touches a leftward command, so it can't interfere with
    green-obstacle avoidance or normal left-wall correction.

    If locked is True (the robot is inside obstacle_corner_lock_until),
    the wider INNER_WALL_*_LOCKED thresholds are used instead of the normal
    ones: pillar avoidance overriding the front-wall turn near a tight
    inner corner is exactly the scenario this guard needs the most margin
    for, so it engages sooner during that window.
    """
    limited = steer
    soft_clear = INNER_WALL_SOFT_CLEAR_LOCKED if locked else INNER_WALL_SOFT_CLEAR
    hard_clear = INNER_WALL_HARD_CLEAR_LOCKED if locked else INNER_WALL_HARD_CLEAR

    if np.isfinite(right_distance):
        if right_distance <= hard_clear:
            limited = min(limited, INNER_WALL_PUSH_LEFT)
        elif right_distance < soft_clear:
            frac = (right_distance - hard_clear) / (soft_clear - hard_clear)
            limited = min(limited, frac * STEER_LIMIT)
    elif not usr_valid:
        # No RealSense reading AND no ultrasonic backup: we genuinely don't
        # know how close the inner wall is. Don't allow an unrestricted
        # rightward steer into that blind spot -- cap it at straight.
        limited = min(limited, 0.0)

    if usr_valid:
        if usr_value_cm < US_MIN_CM_RIGHT:
            limited = min(limited, -US_PUSH_STEER_RIGHT)
        elif usr_value_cm < US_SOFT_CM_RIGHT:
            limited = min(limited, 0.0)

    return limited


def limit_steer_for_outer_wall(
    steer: float,
    left_distance: float,
    usl_valid: bool = False,
    usl_value_cm: float = float("nan"),
) -> float:
    """
    Clamp/override leftward steering so the robot never closes the gap to
    the outer wall (left side, LEFT_ROI — the wall we normally follow)
    below a safe minimum.

    GREEN-obstacle avoidance steers LEFT, overriding the normal PD
    wall-follow term, so this is an independent backup clamp. Combines
    RealSense left-side depth (left_distance) with the left ultrasonic
    sensor (usl); whichever is more restrictive wins. Mirrors
    limit_steer_for_inner_wall(): only ever pulls steer toward RIGHT
    (reduces or reverses a leftward command); never touches a rightward
    command, so it can't interfere with red-obstacle avoidance.

    NOTE: this is a safety guard, so it deliberately uses the RAW,
    un-smoothed left_distance passed in by the caller (not the rate-limited
    value used for wall-follow steering) -- a real close-in hazard must
    never be delayed by the wall-follow smoothing.
    """
    limited = steer

    if np.isfinite(left_distance):
        if left_distance <= OUTER_WALL_HARD_CLEAR:
            limited = max(limited, OUTER_WALL_PUSH_RIGHT)
        elif left_distance < OUTER_WALL_SOFT_CLEAR:
            frac = (left_distance - OUTER_WALL_HARD_CLEAR) / (
                OUTER_WALL_SOFT_CLEAR - OUTER_WALL_HARD_CLEAR
            )
            limited = max(limited, -frac * STEER_LIMIT)

    if usl_valid:
        if usl_value_cm < US_MIN_CM_LEFT:
            limited = max(limited, US_PUSH_STEER_LEFT)
        elif usl_value_cm < US_SOFT_CM_LEFT:
            limited = max(limited, 0.0)

    return limited


def update_smoothed_left_distance(smoothed: float, raw: float) -> float:
    """
    Rate-limit the left-wall reading used for wall-FOLLOW steering only.

    A single-frame jump in the raw depth ROI (glancing-angle dropout, a
    genuine opening in the wall, or a noisy median) can otherwise send the
    PD error -- and therefore the steer command -- straight to
    -STEER_LIMIT for as long as the jump persists. This caps how far the
    value used for wall-follow can move in a single frame to
    LEFT_WALL_MAX_STEP, so a real change (e.g. approaching a corner) is
    still tracked, just over a few frames instead of instantly, while a
    one-frame glitch is smoothed out.

    This does NOT affect the raw left_distance used by
    limit_steer_for_outer_wall() (the safety guard), which always sees the
    unsmoothed reading so a genuine close-in hazard is never delayed.
    """
    if not np.isfinite(raw):
        return float("nan")
    if not np.isfinite(smoothed):
        return raw
    step = clamp(raw - smoothed, -LEFT_WALL_MAX_STEP, LEFT_WALL_MAX_STEP)
    return smoothed + step


def same_color_pillar_passed(class_name: str, cx: float) -> bool:
    """
    True once a pillar has visibly slid to its "already passed" side of the
    frame: GREEN (passed on the left) slides toward the RIGHT edge of the
    image; RED (passed on the right) slides toward the LEFT edge.
    """
    if not np.isfinite(cx):
        return False
    if class_name == GREEN_LABEL:
        return cx >= (1.0 - SAME_COLOR_PASSED_CX)
    return cx <= SAME_COLOR_PASSED_CX


def classify_zone(cx: float) -> str:
    """
    Classify a detection's horizontal frame position (cx, fraction 0..1)
    into one of the three ROI zones — "left" (LEFT_ROI), "front"
    (FRONT_ROI), or "right" (RIGHT_ROI) — so obstacle avoidance can pick a
    different target column depending on where in the frame the obstacle
    currently sits.

    LEFT_ROI / FRONT_ROI / RIGHT_ROI are contiguous full-width thirds (see
    ROI_SPLIT_1 / ROI_SPLIT_2 above), so every cx in [0, 1] falls cleanly
    into exactly one zone — no gap-filling fallback needed.
    """
    if cx < ROI_SPLIT_1:
        return "left"
    if cx < ROI_SPLIT_2:
        return "front"
    return "right"


def target_column(class_name: str, cx: float) -> float:
    """
    Look up the pass-by target column for a tracked pillar: classify which
    ROI zone its current cx falls into, then pick that zone's entry from
    TX_RED / TX_GREEN for its colour.
    """
    zone = classify_zone(cx)
    table = TX_RED if class_name == RED_LABEL else TX_GREEN
    return table[zone]


def yaw_distance_deg(yaw_a: float, yaw_b: float) -> float:
    """Return the shortest circular distance between two yaw angles."""
    return abs((yaw_a - yaw_b + 180.0) % 360.0 - 180.0)


def yaw_in_checkpoint_zone(yaw: float, checkpoint: float) -> bool:
    """Return True when yaw is inside the checkpoint's broad heading zone."""
    return yaw_distance_deg(yaw, checkpoint) <= LAP_ZONE_HALF_WIDTH


def roi_distance(depth_img_m: np.ndarray, roi) -> float:
    """
    Return the median valid depth inside an ROI, or NaN if unavailable.

    A large fraction of sub-MIN_VALID_DEPTH returns usually means something
    is sitting closer to the sensor than it can reliably measure — not that
    there's "no data." Reporting NaN in that case would silently disable
    any guard relying on this reading right when the object is closest, so
    that case is reported as a very small (dangerously close) distance
    instead of NaN.
    """
    height, width = depth_img_m.shape
    x0 = int(roi[0] * width)
    x1 = int(roi[1] * width)
    y0 = int(roi[2] * height)
    y1 = int(roi[3] * height)

    patch = depth_img_m[y0:y1, x0:x1]
    finite = patch[np.isfinite(patch) & (patch > 0.0)]
    valid = patch[
        (patch > MIN_VALID_DEPTH)
        & (patch < MAX_VALID_DEPTH)
        & np.isfinite(patch)
    ]

    if valid.size < MIN_VALID_PIXELS:
        if finite.size >= MIN_VALID_PIXELS:
            too_close_frac = float(np.mean(finite < MIN_VALID_DEPTH))
            if too_close_frac > 0.3:
                return MIN_VALID_DEPTH * 0.5
        return float("nan")

    return float(np.median(valid))


def bbox_distance(depth_img_m: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> float:
    """Return the median valid depth inside the centre 50% of a pixel bbox."""
    box_w = x1 - x0
    box_h = y1 - y0
    cx0 = int(x0 + 0.25 * box_w)
    cx1 = int(x1 - 0.25 * box_w)
    cy0 = int(y0 + 0.25 * box_h)
    cy1 = int(y1 - 0.25 * box_h)

    patch = depth_img_m[max(cy0, 0):cy1, max(cx0, 0):cx1]
    valid = patch[(patch > MIN_VALID_DEPTH) & (patch < MAX_VALID_DEPTH)]

    if valid.size < 20:
        return float("nan")

    return float(np.median(valid))


def build_color_map(model: YOLO) -> dict:
    """
    Map YOLO class id -> "red" / "green" by matching a substring in the
    model's class names (e.g. "redbox" -> "red", "greenbox" -> "green").
    Any class that matches neither (e.g. "xparking") is left out of the map,
    so detect_obstacles() automatically ignores it.
    """
    color_map = {}
    for class_id, name in model.names.items():
        lname = str(name).lower()
        if RED_LABEL in lname:
            color_map[class_id] = RED_LABEL
        elif GREEN_LABEL in lname:
            color_map[class_id] = GREEN_LABEL

    if not color_map:
        print(
            "[AI][WARN] no class names contain 'red'/'green' — "
            "falling back to id 0=green, 1=red"
        )
        color_map = {0: GREEN_LABEL, 1: RED_LABEL}

    print(f"[AI] colour class map: {color_map}")
    return color_map


def detect_obstacles(
    model: YOLO,
    color_image: np.ndarray,
    depth_img_m: np.ndarray,
    color_map: dict,
):
    """
    Run the AI colour-box detector on the current colour frame and pair each
    red/green detection with its distance from the depth frame.

    Returns (obstacles, wall_depth):
      - obstacles: list of dicts {class_name, cx, distance, bbox, conf},
        sorted by ascending distance (closest first). Detections with no
        usable depth reading, or classes we don't act on (e.g. "xparking"),
        are omitted.
      - wall_depth: a copy of depth_img_m with every detected box (plus a
        small margin) zeroed out, so a red/green pillar sitting inside the
        FRONT/LEFT wall ROI is not mistaken for the wall itself.
    """
    obstacles = []
    height, width = depth_img_m.shape
    wall_depth = depth_img_m.copy()

    results = model.predict(
        color_image,
        imgsz=AI_IMG_SIZE,
        conf=OBSTACLE_CONF_THRESHOLD,
        verbose=False,
    )[0]

    for box in results.boxes:
        class_id = int(box.cls[0])
        if class_id not in color_map:
            continue  # ignore classes we don't avoid, e.g. "xparking"

        conf = float(box.conf[0])
        x0, y0, x1, y1 = [int(v) for v in box.xyxy[0].tolist()]
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, width - 1), min(y1, height - 1)

        # Mask this box out of the wall-ROI depth regardless of whether we
        # can measure a clean distance for it.
        margin = 6
        wall_depth[
            max(y0 - margin, 0):min(y1 + margin, height),
            max(x0 - margin, 0):min(x1 + margin, width),
        ] = 0.0

        distance = bbox_distance(depth_img_m, x0, y0, x1, y1)
        if not np.isfinite(distance):
            continue

        cx_frac = ((x0 + x1) / 2) / width

        obstacles.append(
            {
                "class_name": color_map[class_id],
                "cx": cx_frac,
                "distance": distance,
                "bbox": (x0, y0, x1, y1),
                "conf": conf,
            }
        )

    obstacles.sort(key=lambda item: item["distance"])
    return obstacles, wall_depth


def draw_obstacles(image: np.ndarray, obstacles: list) -> None:
    for obstacle in obstacles:
        x0, y0, x1, y1 = obstacle["bbox"]
        color = OBSTACLE_BOX_COLOR.get(obstacle["class_name"], (255, 255, 0))
        cv2.rectangle(image, (x0, y0), (x1, y1), color, 2)
        label = (
            f"{obstacle['class_name']} {obstacle['distance']:.2f} m "
            f"({obstacle['conf']:.2f})"
        )
        cv2.putText(
            image,
            label,
            (x0, max(20, y0 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
        )


def draw_roi(image, roi, label: str, distance: float, color) -> None:
    height, width = image.shape[:2]
    x0 = int(roi[0] * width)
    x1 = int(roi[1] * width)
    y0 = int(roi[2] * height)
    y1 = int(roi[3] * height)

    cv2.rectangle(image, (x0, y0), (x1, y1), color, 2)
    text = f"{label}: {distance:.2f} m" if np.isfinite(distance) else f"{label}: --"
    cv2.putText(
        image,
        text,
        (x0, max(20, y0 - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        color,
        2,
    )


def send_drive(ser: serial.Serial, steer: float, speed: int) -> None:
    steer_i = int(round(clamp(steer, -STEER_LIMIT, STEER_LIMIT)))
    speed_i = int(clamp(speed, 0, 255))
    ser.write(f"DRIVE {steer_i} {speed_i}\n".encode())


def send_back(ser: serial.Serial, steer: float, speed: int) -> None:
    """
    Reverse command for the fail-recovery maneuver.
    Requires the ESP32 firmware to support "BACK <steerDeg> <speed>" in
    addition to the existing "DRIVE <steerDeg> <speed>".
    """
    steer_i = int(round(clamp(steer, -STEER_LIMIT, STEER_LIMIT)))
    speed_i = int(clamp(speed, 0, 255))
    ser.write(f"BACK {steer_i} {speed_i}\n".encode())


def stop_robot(ser: serial.Serial) -> None:
    for _ in range(3):
        try:
            ser.write(b"DRIVE 0 0\n")
            time.sleep(0.05)
        except Exception:
            pass


def _parse_ultrasonic_payload(payload: str) -> float:
    """
    Parse a single "USL"/"USR" line's numeric payload into a validated cm
    reading, or NaN if the payload should be discarded (a "NO_ECHO" report,
    unparsable text, or a value outside the sane 1-300 cm sensor range).
    Shared by both the left and right update paths so the validation rule
    can't drift between them.
    """
    if payload == "NO_ECHO":
        return float("nan")

    try:
        val = float(payload)
    except ValueError:
        return float("nan")

    if not (1.0 < val < 300.0):
        return float("nan")

    return val


def update_usl_reading(payload: str) -> None:
    """
    Handle one "USL <cm>" line from the ESP32: validate the payload, fold
    it into the left ultrasonic's own median-filter history, and publish
    the filtered value/timestamp for the outer-wall guard. Left and right
    readings are updated independently so each side's filtering/staleness
    state can never leak into the other.
    """
    global usl_cm, usl_time

    val = _parse_ultrasonic_payload(payload)
    if not np.isfinite(val):
        return

    now_t = time.time()
    with us_lock:
        usl_hist.append(val)
        usl_cm = float(np.median(usl_hist))
        usl_time = now_t


def update_usr_reading(payload: str) -> None:
    """
    Handle one "USR <cm>" line from the ESP32: validate the payload, fold
    it into the right ultrasonic's own median-filter history, and publish
    the filtered value/timestamp for the inner-wall guard. Mirrors
    update_usl_reading() but keeps the right-side state fully separate.
    """
    global usr_cm, usr_time

    val = _parse_ultrasonic_payload(payload)
    if not np.isfinite(val):
        return

    now_t = time.time()
    with us_lock:
        usr_hist.append(val)
        usr_cm = float(np.median(usr_hist))
        usr_time = now_t


def serial_reader(ser: serial.Serial) -> None:
    """
    Background thread: read lines from the ESP32 and dispatch "USL <cm>" /
    "USR <cm>" lines to their own independent update function. Any other
    line (e.g. an "OK DRIVE"/"OK BACK" acknowledgement) is silently
    ignored.
    """
    while running:
        try:
            line = ser.readline().decode(errors="ignore").strip()
        except Exception:
            time.sleep(0.05)
            continue

        if not line:
            continue

        parts = line.split()
        if len(parts) != 2:
            continue

        sensor, payload = parts[0], parts[1]

        if sensor == "USL":
            update_usl_reading(payload)
        elif sensor == "USR":
            update_usr_reading(payload)


def handle_stop_signal(_sig, _frame) -> None:
    global running
    running = False


# ---------------------------------------------------------------------------
# WEB VIEW
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return (
        '<html><body style="background:#111;text-align:center">'
        '<h2 style="color:#eee">Depth-only Left Wall Test</h2>'
        '<img src="/video" style="width:90%;max-width:900px">'
        "</body></html>"
    )


@app.route("/video")
def video():
    def generate():
        while running:
            with frame_lock:
                jpg = frame_jpg
            if jpg is not None:
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                    + jpg
                    + b"\r\n"
                )
            time.sleep(1.0 / 20.0)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


def start_web_server() -> None:
    thread = threading.Thread(
        target=lambda: app.run(
            host="0.0.0.0",
            port=WEB_PORT,
            debug=False,
            use_reloader=False,
            threaded=True,
        ),
        daemon=True,
    )
    thread.start()


# ---------------------------------------------------------------------------
# MAIN CONTROL LOOP
# ---------------------------------------------------------------------------
def main() -> None:
    global frame_jpg, running

    signal.signal(signal.SIGINT, handle_stop_signal)
    signal.signal(signal.SIGTERM, handle_stop_signal)

    ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=0.1)
    time.sleep(2.0)

    us_reader_thread = threading.Thread(target=serial_reader, args=(ser,), daemon=True)
    us_reader_thread.start()
    print("[US] ultrasonic reader thread started (USL/USR)")

    imu = BNO055Yaw(
        address=IMU_ADDRESS,
        busnum=IMU_BUS,
        calibration_file=IMU_CALIBRATION_FILE,
    )
    # Whatever direction the robot faces now becomes relative yaw 0 degrees.
    imu.set_zero()
    time.sleep(0.25)
    print("[IMU] startup direction set as relative 0 degrees")
    print(f"[IMU] calibration status: {imu.get_calibration_status()}")

    print(f"[AI] loading obstacle-colour model from {AI_MODEL_PATH} ...")
    ai_model = YOLO(AI_MODEL_PATH)
    print(f"[AI] model classes: {ai_model.names}")
    color_map = build_color_map(ai_model)

    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.depth, DEPTH_W, DEPTH_H, rs.format.z16, FPS)
    config.enable_stream(rs.stream.color, DEPTH_W, DEPTH_H, rs.format.bgr8, FPS)

    profile = pipeline.start(config)
    depth_scale = profile.get_device().first_depth_sensor().get_depth_scale()
    align = rs.align(rs.stream.color)

    start_web_server()
    print(f"[WEB] http://<jetson-ip>:{WEB_PORT}")
    print("[RUN] depth-only left-wall following; Ctrl+C to stop")
    print(
        f"[LAP] waiting for 0 -> 90 -> 180 -> 270 -> 0, "
        f"then stop after {LAPS_TO_COMPLETE} laps"
    )

    lap_count = 0
    lap_checkpoint_index = 0
    delayed_stop_time = None

    # Prevent repeated counting while the IMU remains inside one checkpoint zone.
    checkpoint_zone_latched = False

    previous_error = 0.0
    previous_time = time.time()
    turning_right = False

    # Rate-limited left-wall reading used only by the FOLLOW LEFT WALL term
    # (see update_smoothed_left_distance() / LEFT_WALL_MAX_STEP above).
    smoothed_left_distance = float("nan")

    # ---- Pillar tracking state (ported from the v6 field script) --------
    pillar = None            # {"class_name", "cx", "distance", "t"} or None
    hold_until = 0.0
    hold_steer = 0.0
    hold_color = None

    # Same-colour handover (two close pillars of the same colour).
    same_color_target_until = 0.0
    same_color_target_cx = float("nan")
    same_color_target_dist = float("nan")

    # Corner lock: pillar seen mid front-wall-turn takes priority over the turn.
    obstacle_corner_lock_until = 0.0
    last_pillar_seen_t = 0.0
    last_pillar_color = None
    last_pillar_cx = float("nan")
    last_pillar_dist = float("nan")

    # Fail recovery: short STOP, then BACK, if things get too close mid-avoid.
    recovery_stop_until = 0.0
    recovery_back_until = 0.0
    recovery_back_started = 0.0
    recovery_cooldown_until = 0.0
    recovery_reason = ""
    recovery_danger_since = 0.0

    frame_counter = 0
    obstacles = []
    wall_depth = None

    try:
        while running:
            frames = align.process(pipeline.wait_for_frames())
            depth_frame = frames.get_depth_frame()
            color_frame = frames.get_color_frame()

            if not depth_frame or not color_frame:
                continue

            now = time.time()
            dt = max(now - previous_time, 1e-3)
            previous_time = now

            depth_m = (
                np.asanyarray(depth_frame.get_data()).astype(np.float32)
                * depth_scale
            )
            image = np.asanyarray(color_frame.get_data())

            # ---- AI obstacle detection (red/green boxes) -------------------
            # wall_depth has any detected red/green box zeroed out, so a
            # pillar sitting inside the FRONT/LEFT ROI isn't read as a wall.
            frame_counter += 1
            if frame_counter % AI_INFER_EVERY_N_FRAMES == 0:
                obstacles, wall_depth = detect_obstacles(
                    ai_model, image, depth_m, color_map
                )
            else:
                wall_depth = depth_m

            front_distance = roi_distance(wall_depth, FRONT_ROI)
            left_distance = roi_distance(wall_depth, LEFT_ROI)
            # RIGHT_ROI is monitoring-only for wall-follow (this is a
            # left-wall follower) but is computed/drawn so the video feed
            # shows all three ROIs, and it's used by the inner-wall guard.
            right_distance = roi_distance(wall_depth, RIGHT_ROI)

            # Rate-limited copy of left_distance for the FOLLOW LEFT WALL
            # term only -- see update_smoothed_left_distance(). The raw
            # left_distance above is untouched and still feeds
            # limit_steer_for_outer_wall() immediately below.
            smoothed_left_distance = update_smoothed_left_distance(
                smoothed_left_distance, left_distance
            )

            with us_lock:
                usl_val, usl_age = usl_cm, now - usl_time
                usr_val, usr_age = usr_cm, now - usr_time
            usl_valid = np.isfinite(usl_val) and usl_age < US_STALE_S
            usr_valid = np.isfinite(usr_val) and usr_age < US_STALE_S

            # ---- 1. engage list: pillars close enough to actively track ----
            engaged = [o for o in obstacles if o["distance"] < ENGAGE_DIST]
            best = min(engaged, key=lambda o: o["distance"]) if engaged else None

            # ---- 2. same-colour handover -----------------------------------
            # If the closest tracked pillar has visibly slid to its "passed"
            # side of the frame (or is basically alongside us), and another
            # same-colour pillar is still ahead, switch to it immediately.
            handover_active = False
            if best is not None:
                same_color = sorted(
                    [o for o in engaged if o["class_name"] == best["class_name"]],
                    key=lambda o: o["distance"],
                )
                if len(same_color) >= 2:
                    first = same_color[0]
                    next_options = [
                        o for o in same_color[1:]
                        if o["distance"] >= first["distance"] + SAME_COLOR_MIN_GAP_M
                    ]
                    first_is_passed = (
                        same_color_pillar_passed(first["class_name"], first["cx"])
                        or first["distance"] <= PASS_DIST
                    )
                    if first_is_passed and next_options:
                        best = min(next_options, key=lambda o: o["distance"])
                        handover_active = True
                        same_color_target_until = now + SAME_COLOR_HOLD_S
                        same_color_target_cx = best["cx"]
                        same_color_target_dist = best["distance"]
                        hold_until = 0.0
                        hold_color = None
            elif now < same_color_target_until and engaged:
                # Through a brief YOLO flicker, prefer a pillar still near the
                # stored handover target rather than falling back to nothing.
                candidates = [
                    o for o in engaged
                    if not same_color_pillar_passed(o["class_name"], o["cx"])
                ]
                if candidates:
                    best = min(
                        candidates,
                        key=lambda o: (
                            abs(o["cx"] - same_color_target_cx)
                            + 0.35 * abs(o["distance"] - same_color_target_dist)
                        ),
                    )
                    handover_active = True
                    same_color_target_cx = best["cx"]
                    same_color_target_dist = best["distance"]

            # ---- 3. update / expire the tracked pillar ---------------------
            if best is not None:
                pillar = {
                    "class_name": best["class_name"],
                    "cx": best["cx"],
                    "distance": best["distance"],
                    "t": now,
                }
            elif pillar is not None and now - pillar["t"] > MEMORY_TTL:
                if pillar["distance"] < HOLD_ARM_DIST:
                    hold_until = now + HOLD_TIME
                    hold_color = pillar["class_name"]
                pillar = None

            # ---- 4. lookahead front-wall trigger (checked BEFORE corner-lock
            # memory below, so a pillar arriving on the SAME frame the front
            # wall closes below FRONT_STOP is still caught) -----------------
            will_turn_this_frame = (
                np.isfinite(front_distance) and front_distance <= FRONT_STOP
            )

            # ---- 4b. red-red tight-turn corner: two RED pillars engaged
            # close together while a right turn is happening or about to
            # happen. TURN_STEER and RED-avoidance steer are both rightward
            # here, so this is a "combine and slow down" case rather than a
            # "cancel the turn" case (contrast with obstacle_corner_lock_until
            # in step 5, which is for conflicting-direction pillars). -------
            red_engaged = sorted(
                [o for o in engaged if o["class_name"] == RED_LABEL],
                key=lambda o: o["distance"],
            )
            red_red_corner = (
                len(red_engaged) >= 2
                and (red_engaged[1]["distance"] - red_engaged[0]["distance"])
                <= RED_RED_CORNER_GAP_M
                and (turning_right or will_turn_this_frame)
            )

            # ---- 5. corner-lock memory: remember the closest pillar even if
            # the tracked "pillar" state above has switched targets ----------
            best_for_memory = (
                pillar if pillar is not None
                else (min(engaged, key=lambda o: o["distance"]) if engaged else None)
            )
            if best_for_memory is not None:
                # Snapshot the colour we were tracking/avoiding BEFORE this
                # frame's update overwrites it, so the corner-lock check
                # below can compare "the pillar we just saw" against "the
                # pillar we were dealing with previously" (e.g. RED at one
                # corner, then RED again at the next corner).
                previous_pillar_color = last_pillar_color

                last_pillar_seen_t = now
                last_pillar_color = best_for_memory["class_name"]
                last_pillar_cx = best_for_memory["cx"]
                last_pillar_dist = best_for_memory["distance"]

                # Only re-arm the corner lock if this pillar is the SAME
                # colour as the one we were previously tracking/avoiding —
                # e.g. avoiding RED while turning at one corner, then seeing
                # RED again at the next corner. A DIFFERENT colour (e.g.
                # GREEN right after RED) is treated as a fresh obstacle and
                # does not lock the turn out.
                same_color_as_previous = (
                    previous_pillar_color is not None
                    and previous_pillar_color == best_for_memory["class_name"]
                )

                # If a pillar appears while turning (or about to start
                # turning this very frame) at the front-wall corner, cancel
                # the turn and lock into avoidance instead of alternating
                # between "turn" and "avoid" every frame. Checking
                # will_turn_this_frame (not just the OLD turning_right flag)
                # closes the one-frame gap where turning_right flips True in
                # the hysteresis block further down but this memory block
                # already ran with the stale value.
                if (turning_right or will_turn_this_frame) and same_color_as_previous:
                    print(
                        f"[TRANSITION] pillar seen during turn -> corner-lock set "
                        f"({best_for_memory['class_name']}@"
                        f"{best_for_memory['distance']:.2f}m, "
                        f"was turning_right={turning_right}, "
                        f"will_turn_this_frame={will_turn_this_frame}, "
                        f"same_color_as_previous={same_color_as_previous})"
                    )
                    obstacle_corner_lock_until = now + CORNER_LOCK_S
                    turning_right = False
                    hold_color = best_for_memory["class_name"]
                    hold_until = max(hold_until, now + 0.25)

            # ---- 6. fail-recovery trigger (stop, then back up) -------------
            pillar_recent = (
                (now - last_pillar_seen_t) <= RECOVERY_MEMORY_S
                and np.isfinite(last_pillar_dist)
            )
            pillar_too_close = pillar_recent and last_pillar_dist <= FAIL_PILLAR_M
            front_too_close_with_pillar = (
                pillar_recent
                and np.isfinite(front_distance)
                and front_distance <= FAIL_FRONT_M
            )
            front_hard_during_corner_lock = (
                now < obstacle_corner_lock_until
                and np.isfinite(front_distance)
                and front_distance <= FAIL_FRONT_M
            )
            should_recover = (
                pillar_too_close
                or front_too_close_with_pillar
                or front_hard_during_corner_lock
            )

            # Require continuous danger briefly so one noisy depth frame
            # can't trigger a full stop/reverse sequence.
            if should_recover:
                if recovery_danger_since <= 0.0:
                    recovery_danger_since = now
            else:
                recovery_danger_since = 0.0

            recovery_confirmed = (
                recovery_danger_since > 0.0
                and (now - recovery_danger_since) >= RECOVERY_TRIGGER_HOLD
            )

            if recovery_confirmed and now >= recovery_cooldown_until:
                recovery_stop_until = now + RECOVERY_STOP_S
                recovery_back_until = recovery_stop_until + RECOVERY_BACK_S
                recovery_back_started = recovery_stop_until
                recovery_cooldown_until = recovery_back_until + RECOVERY_COOLDOWN_S
                recovery_danger_since = 0.0

                if pillar_too_close:
                    recovery_reason = (
                        f"{last_pillar_color} danger d={last_pillar_dist:.2f}m"
                    )
                elif front_too_close_with_pillar:
                    recovery_reason = (
                        f"front {front_distance:.2f}m with recent "
                        f"{last_pillar_color}"
                    )
                else:
                    recovery_reason = (
                        f"front {front_distance:.2f}m during corner lock"
                    )

                turning_right = False
                obstacle_corner_lock_until = 0.0
                hold_until = 0.0
                hold_color = None
                pillar = None

                print(f"[RECOVERY] {recovery_reason}: STOP then BACK")

            # ---- 7. cancel the reverse early once enough space is created --
            back_active = now >= recovery_stop_until and now < recovery_back_until
            back_min_done = (
                recovery_back_started > 0.0
                and (now - recovery_back_started) >= RECOVERY_BACK_MIN_S
            )
            exit_space = (
                np.isfinite(front_distance) and front_distance >= RECOVERY_EXIT_FRONT_M
            )
            if back_active and back_min_done and exit_space:
                recovery_back_until = now
                recovery_cooldown_until = max(
                    recovery_cooldown_until, now + RECOVERY_COOLDOWN_S
                )
                print("[RECOVERY] early exit: enough forward clearance")

            relative_yaw = imu.read_relative_yaw()

            if relative_yaw is not None and delayed_stop_time is None:
                target_yaw = LAP_YAW_CHECKPOINTS[lap_checkpoint_index]
                inside_target_zone = yaw_in_checkpoint_zone(
                    relative_yaw,
                    target_yaw,
                )

                # Count only when entering the next expected zone.
                if inside_target_zone and not checkpoint_zone_latched:
                    print(
                        f"[LAP] entered {target_yaw:.0f}-degree zone "
                        f"at yaw={relative_yaw:.1f}"
                    )
                    checkpoint_zone_latched = True
                    lap_checkpoint_index += 1

                    if lap_checkpoint_index >= len(LAP_YAW_CHECKPOINTS):
                        lap_count += 1
                        lap_checkpoint_index = 0
                        print(f"[LAP] completed {lap_count}/{LAPS_TO_COMPLETE}")

                        if lap_count >= LAPS_TO_COMPLETE:
                            delayed_stop_time = now + STOP_DELAY_AFTER_LAPS
                            print(
                                f"[LAP] three laps complete — continuing for "
                                f"{STOP_DELAY_AFTER_LAPS:.1f} seconds before stopping"
                            )

                # Rearm only after leaving the zone that was just counted.
                elif not inside_target_zone:
                    checkpoint_zone_latched = False

            # After lap 3, continue normal driving for the configured delay.
            if delayed_stop_time is not None and now >= delayed_stop_time:
                print("[LAP] stop delay complete — stopping robot")
                stop_robot(ser)
                running = False
                break

            # Hysteresis prevents repeated switching near exactly 0.70 m.
            if not turning_right:
                if np.isfinite(front_distance) and front_distance <= FRONT_STOP:
                    turning_right = True
                    print(
                        f"[TRANSITION] turning_right -> True "
                        f"(front={front_distance:.2f}m <= {FRONT_STOP:.2f}m, "
                        f"right={right_distance if np.isfinite(right_distance) else float('nan'):.2f}m)"
                    )
            else:
                if not np.isfinite(front_distance) or front_distance >= FRONT_CLEAR:
                    print(
                        f"[TRANSITION] turning_right -> False "
                        f"(front={front_distance if np.isfinite(front_distance) else float('nan'):.2f}m)"
                    )
                    turning_right = False

            # Corner lock: don't let the front-wall turn resume while we're
            # committed to avoiding a pillar seen at the corner.
            if now < obstacle_corner_lock_until and turning_right:
                print(
                    f"[TRANSITION] corner-lock overrides turning_right -> False "
                    f"(lock remaining={obstacle_corner_lock_until - now:.2f}s)"
                )
                turning_right = False

            # ---- Steering priority: recovery-stop > recovery-back >
            #      front turn > pillar avoidance > hold > wall follow -------
            in_recovery = now < recovery_back_until  # covers STOP and BACK phases

            if now < recovery_stop_until:
                steer, speed = 0.0, 0
                mode = f"RECOVERY STOP {recovery_reason}"
                previous_error = 0.0
                turning_right = False
                pillar = None
                hold_until = 0.0
                hold_color = None

            elif now < recovery_back_until:
                steer, speed = RECOVERY_BACK_STEER, RECOVERY_BACK_SPEED
                mode = f"RECOVERY BACK {recovery_reason}"
                previous_error = 0.0
                turning_right = False
                pillar = None
                hold_until = 0.0
                hold_color = None

            elif red_red_corner:
                # Both the tight-turn front-wall logic and RED-pillar
                # avoidance want to steer RIGHT here — take whichever wants
                # MORE right, rather than picking one and discarding the
                # other, and track the nearer of the two REDs for the
                # proportional column term.
                nearest_red = red_engaged[0]
                tx = target_column(RED_LABEL, nearest_red["cx"])
                error = nearest_red["cx"] - tx
                pillar_steer = clamp(KP_PILLAR * error, -STEER_LIMIT, STEER_LIMIT)
                steer = clamp(max(RED_RED_CORNER_STEER, pillar_steer), -STEER_LIMIT, STEER_LIMIT)
                speed = RED_RED_CORNER_SPEED
                mode = (
                    f"TIGHT CORNER RED-RED "
                    f"{red_engaged[0]['distance']:.2f}/{red_engaged[1]['distance']:.2f}m"
                )
                pillar = {
                    "class_name": RED_LABEL,
                    "cx": nearest_red["cx"],
                    "distance": nearest_red["distance"],
                    "t": now,
                }
                hold_steer = steer
                hold_color = RED_LABEL
                previous_error = 0.0

            elif turning_right:
                # Ease TURN_STEER down as the inner wall gets close instead
                # of firing a fixed +30 deg and relying purely on the
                # post-hoc guard below to save it after the fact.
                turn_steer = TURN_STEER
                if np.isfinite(right_distance):
                    if right_distance <= INNER_WALL_HARD_CLEAR:
                        turn_steer = 0.0
                    elif right_distance < INNER_WALL_SOFT_CLEAR:
                        frac = (right_distance - INNER_WALL_HARD_CLEAR) / (
                            INNER_WALL_SOFT_CLEAR - INNER_WALL_HARD_CLEAR
                        )
                        turn_steer = frac * TURN_STEER
                steer = turn_steer
                speed = TURN_SPEED
                mode = "TURN RIGHT"
                previous_error = 0.0

            elif pillar is not None:
                tx = target_column(pillar["class_name"], pillar["cx"])
                error = pillar["cx"] - tx
                steer = clamp(KP_PILLAR * error, -STEER_LIMIT, STEER_LIMIT)
                speed = AVOID_SPEED
                mode = (
                    f"AVOID {pillar['class_name'].upper()} "
                    f"{pillar['distance']:.2f}m"
                )
                if handover_active:
                    mode += " HANDOVER"
                if now < obstacle_corner_lock_until:
                    mode += " CORNER-LOCK"
                hold_steer = steer
                previous_error = 0.0

            elif now < hold_until:
                steer = hold_steer
                speed = AVOID_SPEED
                mode = f"HOLD {(hold_color or '').upper()}".strip()
                previous_error = 0.0

            else:
                speed = BASE_SPEED

                # Use the RATE-LIMITED left reading here so a one-frame
                # jump can't instantly saturate the PD term (see
                # update_smoothed_left_distance() / LEFT_WALL_MAX_STEP).
                # A reading that's still far beyond a plausible wall
                # distance even after smoothing is treated as "wall lost"
                # (opening/corner/lost lock) rather than driving a
                # maxed-out correction toward open space.
                wall_present = (
                    np.isfinite(smoothed_left_distance)
                    and smoothed_left_distance <= (LEFT_TARGET * LEFT_WALL_LOST_MULT)
                )

                if wall_present:
                    # Too far from the left wall:
                    # left_distance > target -> negative error -> steer LEFT.
                    #
                    # Too close to the left wall:
                    # left_distance < target -> positive error -> steer RIGHT.
                    error = clamp(
                        LEFT_TARGET - smoothed_left_distance,
                        -LEFT_ERROR_CLAMP,
                        LEFT_ERROR_CLAMP,
                    )
                    error_rate = (error - previous_error) / dt
                    steer = KP_STEER * error + KD_STEER * error_rate
                    steer = clamp(steer, -STEER_LIMIT, STEER_LIMIT)
                    previous_error = error
                    mode = "FOLLOW LEFT WALL"
                else:
                    # Wall missing entirely, or the smoothed reading is far
                    # beyond a plausible wall-follow distance (an opening,
                    # a corner, or a lost lock) -- search gently instead of
                    # demanding a maxed-out PD correction toward a reading
                    # that almost certainly isn't the actual wall.
                    steer = SEARCH_LEFT_STEER
                    previous_error = 0.0
                    mode = "SEARCH LEFT WALL"

            # ---- Wall safety guards (skipped during the fixed recovery
            # manoeuvre, which is a deliberate near-straight reverse) --------
            # NOTE: these guards intentionally use the RAW left_distance /
            # right_distance (not the smoothed left value above), so a real
            # close-in hazard is never delayed by the wall-follow smoothing.
            if not in_recovery:
                steer_before_guard = steer
                corner_locked = now < obstacle_corner_lock_until
                steer = limit_steer_for_inner_wall(
                    steer, right_distance, usr_valid, usr_val, locked=corner_locked
                )
                steer = limit_steer_for_outer_wall(steer, left_distance, usl_valid, usl_val)
                if steer != steer_before_guard:
                    mode += " [WALL-GUARD]"

            if now < recovery_back_until and now >= recovery_stop_until:
                send_back(ser, steer, speed)
            else:
                send_drive(ser, steer, speed)

            # ---- Per-loop debug print: which branch fired, and the state
            # that decided it, so unexpected steer commands (e.g. a stray
            # +30 TURN RIGHT into the inner wall) can be traced after the
            # fact from the console log. ---------------------------------
            front_txt = f"{front_distance:.2f}" if np.isfinite(front_distance) else "--"
            left_txt = f"{left_distance:.2f}" if np.isfinite(left_distance) else "--"
            smooth_txt = (
                f"{smoothed_left_distance:.2f}"
                if np.isfinite(smoothed_left_distance) else "--"
            )
            right_txt = f"{right_distance:.2f}" if np.isfinite(right_distance) else "--"
            pillar_txt = (
                f"{pillar['class_name']}@{pillar['distance']:.2f}m"
                if pillar is not None else "none"
            )
            lock_txt = (
                f"{obstacle_corner_lock_until - now:.2f}s"
                if now < obstacle_corner_lock_until else "off"
            )
            print(
                f"[LOOP] mode={mode:<28} steer={steer:+6.1f} speed={speed:3d} "
                f"| front={front_txt:>5} left={left_txt:>5} lsmooth={smooth_txt:>5} "
                f"right={right_txt:>5} "
                f"| turning_right={turning_right!s:<5} corner_lock={lock_txt:<6} "
                f"pillar={pillar_txt}"
            )

            display = image.copy()
            draw_roi(display, FRONT_ROI, "FRONT", front_distance, (0, 0, 255))
            draw_roi(display, LEFT_ROI, "LEFT", left_distance, (0, 255, 0))
            draw_roi(display, RIGHT_ROI, "RIGHT", right_distance, (255, 200, 0))
            draw_obstacles(display, obstacles)
            if pillar is not None:
                tx = target_column(pillar["class_name"], pillar["cx"])
                target_x = int(tx * display.shape[1])
                cv2.line(display, (target_x, 0), (target_x, display.shape[0]), (255, 255, 0), 1)

            cv2.putText(
                display,
                f"{mode}  steer={steer:+.1f}  speed={speed}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2,
            )
            us_text = (
                f"USL={usl_val:.1f}cm" if usl_valid else "USL=--"
            ) + "  " + (
                f"USR={usr_val:.1f}cm" if usr_valid else "USR=--"
            )
            cv2.putText(
                display,
                us_text,
                (10, 112),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (200, 200, 255),
                2,
            )
            yaw_text = f"{relative_yaw:.1f} deg" if relative_yaw is not None else "--"

            if delayed_stop_time is not None:
                remaining_stop_delay = max(0.0, delayed_stop_time - now)
                lap_status_text = (
                    f"yaw={yaw_text}  lap={lap_count}/{LAPS_TO_COMPLETE}  "
                    f"stopping in {remaining_stop_delay:.1f}s"
                )
            else:
                next_checkpoint = LAP_YAW_CHECKPOINTS[lap_checkpoint_index]
                lap_status_text = (
                    f"yaw={yaw_text}  lap={lap_count}/{LAPS_TO_COMPLETE}  "
                    f"next zone={next_checkpoint:.0f} deg"
                )

            cv2.putText(
                display,
                lap_status_text,
                (10, 58),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (255, 255, 255),
                2,
            )
            cv2.putText(
                display,
                f"left target={LEFT_TARGET:.2f} m  front turn={FRONT_STOP:.2f} m  "
                f"engage<{ENGAGE_DIST:.2f} m",
                (10, 86),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (255, 255, 255),
                2,
            )

            ok, jpg = cv2.imencode(
                ".jpg", display, [cv2.IMWRITE_JPEG_QUALITY, 75]
            )
            if ok:
                with frame_lock:
                    frame_jpg = jpg.tobytes()

    finally:
        running = False
        stop_robot(ser)
        try:
            pipeline.stop()
        except Exception:
            pass
        ser.close()
        print("[DONE] robot stopped and resources closed")


if __name__ == "__main__":
    main()