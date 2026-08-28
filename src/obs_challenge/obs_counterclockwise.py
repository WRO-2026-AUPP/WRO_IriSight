#!/usr/bin/env python3
import cv2
import time
import signal
import threading
import re
import json
import os
import numpy as np
import serial
import pyrealsense2 as rs
from flask import Flask, Response
from ultralytics import YOLO
from bno055_yaw import BNO055Yaw


# ══════════════════════════════════════════════════════════════════════════
#  TUNABLES
# ══════════════════════════════════════════════════════════════════════════
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


SERIAL_TIMEOUT = 0.05


# ---- wall following ---------------------------------------------------
RIGHT_TARGET  = 0.90    # m — desired distance to right wall
FRONT_STOP    = 0.8     # m — front wall closer than this -> forced turn
FRONT_CLEAR   = 0.55    # m — front must open past this to leave turn mode
KP_STEER      = 45.0    # deg per m of right-wall error
KD_STEER      = 3.0     # FIX v2.11-b: lowered 6 -> 3, derr itself smoothed
STEER_LIMIT   = 30       # max |steer| deg
BASE_SPEED    = 150      # PWM during normal wall following
TURN_SPEED    = 160      # PWM during the forced turn
TURN_STEER_MAG = 35      # magnitude of hard turn steer; sign picked dynamically




# FIX (v2.24): right-wall follower must ALWAYS corner the same physical
# direction (toward/around the wall it is hugging) instead of "deciding"
# per corner which side looks more open. Comparing l_room/r_room (as the
# old code did) is a "head toward open space" strategy and can pick the
# wrong direction whenever the depth camera misreads an open doorway,
# a reflective surface, a missing wall segment, etc. A pure right-wall
# follower doesn't need that decision at all -- it always turns the same
# way at a blocked front, exactly like the working depth-only reference
# script. Set this to match your track's corner direction.
TURN_DIRECTION = -1   # -1 = turn LEFT at a blocked front, +1 = turn RIGHT




# FIX (v2.11-a): deadband on FOLLOW-mode wall-follow error. Error smaller
# than this (in meters) is treated as exactly 0 before P/D math, so small
# sensor noise around RIGHT_TARGET doesn't flip steer sign every frame.
FOLLOW_ERR_DEADBAND = 0.05   # m




# FIX (v2.11-b): light smoothing on the derivative term itself, separate
# from the EMA already applied to right_d. Keeps a single noisy frame from
# injecting a derivative spike into steer.
DERR_ALPHA = 0.5




# ---- minimum moving speed / startup kick --------------------------
MIN_MOVE_SPEED   = 130
STARTUP_KICK_PWM = 220
STARTUP_KICK_MS  = 150


# ---- predictive front avoidance -----------------------------------
FRONT_WARN          = 0.9
FRONT_RATE_GAIN     = 25.0
FRONT_BIAS_MAX_FRAC = 0.4




# ---- steering smoothing -------------------------------------------
# FIX (v2.11-c): split the single MAX_STEER_DELTA into a gentler
# "normal driving" limit and a faster "urgent/wall-push/turn" limit.
MAX_STEER_DELTA_FOLLOW = 18.0
MAX_STEER_DELTA_URGENT = 24.0


# FIX (v2.12-c): ultrasonic hard-safety clamp gets its OWN, much faster
# slew limit. This is your last line of defense against a physical hit
# and it was previously throttled by the same cap as normal driving.
MAX_STEER_DELTA_US_HARD = 34.0   # close to STEER_LIMIT — near-instant




# FIX (v2.11-e): one more light EMA on the final commanded steer, applied
# after the slew-rate limiter, right before sending to the ESP32.
# FIX (v2.12-b): this smoothing is now SKIPPED entirely whenever
# urgent_now is true (turn / wall clamp / us clamp), since smoothing an
# already-slew-limited emergency correction just adds more lag on top of
# lag. It still applies during normal FOLLOW driving.
STEER_OUT_ALPHA = 0.6   # weight on the new value; 1.0 = no smoothing




# ---- right-wall / left-wall dropout recovery -----------------------------
# FIX (v2.12-a): shortened from 0.5s. At BASE_SPEED the old timeout let the
# robot hold a stale (too-generous) distance for a long time after the
# sensor stopped returning valid data — exactly when the wall was getting
# dangerously close and roi_distance started starving for valid pixels.
RIGHT_HOLD_TIMEOUT = 0.25  # s — how long to trust the last-known distance




UNKNOWN_RIGHT_ROOM_M = 0.30   # m — assume close/unsafe, NOT open
UNKNOWN_LEFT_ROOM_M  = 1.00   # m — neutral, matches turn_dir fallback
US_CONFIRM_CLOSE_CM  = 15.0   # cm — if ultrasonic agrees right is close, trust it directly


# ---- corner detection (front-left / front-right diagonal) ----------
FRONT_LEFT_ROI  = (0.30, 0.42, 0.40, 0.60)
FRONT_RIGHT_ROI = (0.60, 0.80, 0.35, 0.65)


# ---- EMA depth smoothing -------------------------------------------
ALPHA_DEPTH = 0.4


# ---- ultrasonic side-wall safety (independent of depth camera) ------------
US_ENABLED         = True
US_LEFT_AVOID_CM   = 25.0
US_RIGHT_AVOID_CM  = 20.0
US_STALE_TIMEOUT   = 0.5


US_MOUNT_OFFSET_CM = 0.0


US_AUTOCALIB_ENABLED   = True
US_CALIB_ALPHA         = 0.01
US_CALIB_TRUST_MIN_M   = 0.20
US_CALIB_TRUST_MAX_M   = 1.20
US_CALIB_MAX_OFFSET_CM = 40.0
US_CALIB_FILE          = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "us_calib.json")
US_CALIB_SAVE_EVERY_S  = 5.0




# ---- pillar detection / avoidance -----------------------------------------
MODEL_PATH    = "best1.pt"
CONF_THRES    = 0.35
IMG_SIZE      = 416


# FIX (v2.20): ignore any YOLO red/green detection whose box sits mostly
# in the top of the frame -- the wall/ceiling area up there sometimes
# gets misclassified as green (or red), and real pillars on the floor in
# front of the robot never appear that high in the frame anyway. Filtered
# by the box's vertical CENTER, not its top edge, so a tall pillar whose
# top edge pokes above the line but is mostly below it still counts.
DETECT_IGNORE_TOP_FRAC = 0.30   # fraction of frame height, from the top




# FIX (v2.18): split ENGAGE_DIST per color. Shared distance meant red and
# green started reacting at the same range even though only red was
# hitting -- if red is engaging too late for its (higher) gain/steer
# needs, giving it a longer lead distance than green tests that directly
# without changing green's already-working behavior.
ENGAGE_DIST_RED   = 2.20
ENGAGE_DIST_GREEN = 1.80
PASS_DIST     = 0.70
MEMORY_TTL    = 0.3
HOLD_TIME     = 0.2


# FIX (identity-lock): max cx (horizontal frame position, 0..1) drift
# allowed frame-to-frame for a detection to still count as "the same
# pillar" we're already tracking. Prevents a same-colored but genuinely
# different pillar from silently taking over the tracked slot.
CX_MATCH_TOL = 0.25




# FIX (v2.13): split gain per color. Green's target (TX_GREEN=0.85) sits
# further from center than red's (TX_RED=0.15) isn't the issue by itself,
# but the two colors can want different steering aggressiveness on your
# track — tune independently instead of one shared KP_PILLAR.
# FIX (v2.14): green was reacting harder/faster than it needed to, which
# left too little margin before the wall. Lowered green's gain relative
# to red rather than assuming they should match.
KP_PILLAR_GREEN = 35.0
KP_PILLAR_RED   = 90.0


# FIX (v2.15) — ported from the left-wall-follower reference script:
# per-ROI-zone target columns instead of one fixed target. A pillar sitting
# in the ROI zone on its OWN pass-side (RIGHT_ROI for red, LEFT_ROI for
# green) is already close to being passed, so ease its target back toward
# center instead of continuing to demand the full aggressive target — that
# was driving steer hard right when the pillar (and the wall behind it)
# were already close. FRONT_ROI and the "far" side zone keep the full
# target. Zone boundaries reuse FRONT_ROI/RIGHT_ROI/LEFT_ROI (0.33/0.67).
# NOTE: hardcoded to match FRONT_ROI's split points (0.33/0.67), defined
# further down — kept as literals here since this tunables block runs
# before FRONT_ROI exists. If you ever change FRONT_ROI's x-bounds, update
# these two to match.
ZONE_SPLIT_1 = 0.33
ZONE_SPLIT_2 = 0.67


# FIX (v2.19): green was being given too much clearance from the pillar
# -- swinging wide to pass it -- which pushed the robot into the left wall
# it was hugging at the same time. Brought the front-zone target in from
# 0.85 -> 0.73 (less aggressive swing) and lowered KP_PILLAR_GREEN and
# HUG_MAX_GREEN (below) to match, instead of demanding the same wide pass.
TX_GREEN_ZONE = {"left": 0.62, "front": 0.73, "right": 0.80}
TX_RED_ZONE   = {"left": 0.08, "front": 0.08, "right": 0.30}


# kept for anything referencing the old flat constants
TX_GREEN      = 0.85
TX_RED        = 0.15




PILLAR_ERR_TOL   = 0.10
PILLAR_CX_ALPHA  = 0.5
# FIX (v2.14): lowered from 1.3 -> 1.15. This multiplier only applies when
# front_danger is ALSO true during a pillar avoid, but at 1.3 it could
# push steer to full TURN_STEER_MAG almost immediately, right as the
# robot is already close to something (the pillar) — not much room left
# to correct if that swing overshoots toward the wall.
PILLAR_URGENCY   = 1.15




# FIX (v2.14): pillar avoidance now gets its own slew-rate limit, gentler
# than both FOLLOW and URGENT. Previously pillar-avoid steer was subject
# to MAX_STEER_DELTA_FOLLOW (18/frame) same as ordinary driving — fine
# most of the time, but not gentle enough right at pillar engage when cx
# jumps from "not tracked" to "tracked" in one frame, producing a bigger
# single-step err than gradual wall drift ever would. A dedicated slower
# cap smooths just that transition without slowing down real emergencies
# (front_danger during a pillar avoid still escalates through urgent_now).
MAX_STEER_DELTA_PILLAR = 14.0




MIN_WALL_CLEAR = 0.55
SPEED_AVOID    = 160




# FIX (v2.11-d): hysteresis band for the wall-push clamp (step 5). Once
# the clamp engages on a side, it stays engaged until the gap opens back
# up past clear + CLAMP_HYST_M, not just past clear again.
CLAMP_HYST_M = 0.05   # m




# -- red: hug the right wall --
RED_WALL_TARGET = 0.2
KP_HUG_RED      = 45.0
HUG_MAX_RED     = 18.0
RED_WALL_CLEAR  = 0.22


# -- green: hug the left wall --
# FIX (v2.14): HUG_MAX_GREEN lowered 18 -> 12. This term stacks on top of
# the pillar-tracking term (steer -= hug), and at 18 it could add a lot
# of extra steer on top of an already-large pillar correction, right when
# clearance to the wall is already tight (GREEN_WALL_CLEAR=0.22m).
GREEN_WALL_TARGET = 0.45
KP_HUG_GREEN      = 45.0
HUG_MAX_GREEN     = 2.0
GREEN_WALL_CLEAR  = 0.22


DEPTH_W, DEPTH_H, FPS = 640, 480, 30




FRONT_ROI = (0.33, 0.67, 0.45, 0.75)
RIGHT_ROI = (0.67, 1.00, 0.45, 0.75)
LEFT_ROI  = (0.00, 0.33, 0.45, 0.75)




WEB_PORT  = 5000


# ---- IMU lap counting (BNO055) -------------------------------------------
# FIX (v2.16): added. Counts laps via cumulative unwrapped yaw rather than
# checkpoint zones -- robust regardless of whether a given corner turns
# left or right (your turn_dir is picked dynamically per corner based on
# available room), so it doesn't need to assume a fixed CW/CCW direction.
IMU_ENABLED           = True
IMU_ADDRESS           = 0x28
IMU_BUS                = 1
IMU_CALIBRATION_FILE  = "bno055_calibration.json"
LAPS_TO_COMPLETE       = 3
STOP_DELAY_AFTER_LAPS  = 0.5   # s -- keep driving this long after the last lap
                              # closes, instead of stopping mid-corner


# FIX (v2.12-d): harder speed cut specifically when the ultrasonic HARD
# safety clamp is active — this means we are inside the "about to hit
# something" threshold, not just the soft wall-follow threshold, so we
# should be slower than the general side-danger cap.
US_HARD_DANGER_CAP = 90


# ---- corner-turn trigger distance, color-dependent -----------------
# FIX (corner-color): the plain front_danger/FRONT_STOP check is still
# used for pillar urgency and predictive front bias -- untouched. This
# is a SEPARATE distance used only to decide when to START a forced
# corner turn, so it can vary by which pillar (if any) is currently
# locked, without touching FRONT_STOP itself.
CORNER_START_NORMAL = 0.80   # no pillar -- matches original FRONT_STOP
CORNER_START_GREEN  = 1.2   # green pillar -- start the corner earlier
CORNER_START_RED    = 0.20   # red pillar -- do NOT trigger early; let
                             # red-pillar avoidance lead instead

# ══════════════════════════════════════════════════════════════════════════
#  GLOBAL STATE
# ══════════════════════════════════════════════════════════════════════════
running    = True
frame_jpg  = None
frame_lock = threading.Lock()




us_left_cm  = float("inf")
us_right_cm = float("inf")
us_left_t   = 0.0
us_right_t  = 0.0
us_lock     = threading.Lock()




# ══════════════════════════════════════════════════════════════════════════
#  ULTRASONIC AUTO-CALIBRATION
# ══════════════════════════════════════════════════════════════════════════
class USAutoCalib:
  def __init__(self, path: str, seed_offset_cm: float):
      self.path = path
      self.offset_left = seed_offset_cm
      self.offset_right = seed_offset_cm
      self.samples_left = 0
      self.samples_right = 0
      self._last_save = 0.0
      self._load()




  def _load(self):
      try:
          with open(self.path, "r") as f:
              data = json.load(f)
          self.offset_left = float(data.get("offset_left", self.offset_left))
          self.offset_right = float(data.get("offset_right", self.offset_right))
          self.samples_left = int(data.get("samples_left", 0))
          self.samples_right = int(data.get("samples_right", 0))
          print(f"[US-CALIB] loaded {self.path}: "
                f"L_offset={self.offset_left:+.1f}cm "
                f"({self.samples_left} samples), "
                f"R_offset={self.offset_right:+.1f}cm "
                f"({self.samples_right} samples)")
      except Exception:
          print(f"[US-CALIB] no existing calibration at {self.path}, "
                f"starting from seed offset {self.offset_left:+.1f}cm")




  def save(self, now: float, force: bool = False):
      if not force and (now - self._last_save) < US_CALIB_SAVE_EVERY_S:
          return
      self._last_save = now
      try:
          tmp = self.path + ".tmp"
          with open(tmp, "w") as f:
              json.dump({
                  "offset_left": self.offset_left,
                  "offset_right": self.offset_right,
                  "samples_left": self.samples_left,
                  "samples_right": self.samples_right,
              }, f)
          os.replace(tmp, self.path)
      except Exception as e:
          print(f"[US-CALIB] save failed: {e}")




  def update(self, side: str, depth_m: float, us_raw_cm: float):
      if not (US_CALIB_TRUST_MIN_M <= depth_m <= US_CALIB_TRUST_MAX_M):
          return
      if not np.isfinite(us_raw_cm):
          return
      target_offset = (depth_m * 100.0) - us_raw_cm
      target_offset = max(-US_CALIB_MAX_OFFSET_CM,
                           min(US_CALIB_MAX_OFFSET_CM, target_offset))
      if side == "right":
          if self.samples_right == 0:
              self.offset_right = target_offset
          else:
              self.offset_right = (US_CALIB_ALPHA * target_offset
                                    + (1 - US_CALIB_ALPHA) * self.offset_right)
          self.samples_right += 1
      else:
          if self.samples_left == 0:
              self.offset_left = target_offset
          else:
              self.offset_left = (US_CALIB_ALPHA * target_offset
                                   + (1 - US_CALIB_ALPHA) * self.offset_left)
          self.samples_left += 1








us_calib = USAutoCalib(US_CALIB_FILE, US_MOUNT_OFFSET_CM)








# ══════════════════════════════════════════════════════════════════════════
#  SERIAL
# ══════════════════════════════════════════════════════════════════════════
ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=0.05)
ser_write_lock = threading.Lock()
time.sleep(2.0)








def send_drive(steer: int, speed: int):
  steer = int(max(-STEER_LIMIT, min(STEER_LIMIT, steer)))
  speed = int(max(0, min(255, speed)))
  with ser_write_lock:
      ser.write(f"DRIVE {steer} {speed}\n".encode())








def stop_robot():
  for _ in range(3):
      try:
          with ser_write_lock:
              ser.write(b"DRIVE 0 0\n")
          time.sleep(0.05)
      except Exception:
          pass








def handle_sigint(sig, frame):
  global running
  print("\n[CTRL+C] stopping robot ...")
  running = False








signal.signal(signal.SIGINT, handle_sigint)
signal.signal(signal.SIGTERM, handle_sigint)








# ══════════════════════════════════════════════════════════════════════════
#  ULTRASONIC READER (background thread)
# ══════════════════════════════════════════════════════════════════════════
_RE_LEFT  = re.compile(r"USL\s*[:\s]\s*(None|[\d.]+)", re.IGNORECASE)
_RE_RIGHT = re.compile(r"USR\s*[:\s]\s*(None|[\d.]+)", re.IGNORECASE)








def parse_ultrasonic_line(line: str):
  m = _RE_LEFT.search(line)
  if m:
      raw = m.group(1)
      if raw.lower() == "none":
          return "left", None
      try:
          return "left", float(raw)
      except ValueError:
          return None
  m = _RE_RIGHT.search(line)
  if m:
      raw = m.group(1)
      if raw.lower() == "none":
          return "right", None
      try:
          return "right", float(raw)
      except ValueError:
          return None
  return None








def ultrasonic_reader():
  global us_left_cm, us_right_cm, us_left_t, us_right_t
  while running:
      try:
          raw = ser.readline()
          if not raw:
              continue
          line = raw.decode(errors="ignore")
          parsed = parse_ultrasonic_line(line)
          if parsed is None:
              continue
          side, val = parsed
          now = time.time()
          with us_lock:
              if side == "left":
                  if val is not None:
                      us_left_cm = val
                  us_left_t = now
              else:
                  if val is not None:
                      us_right_cm = val
                  us_right_t = now
      except Exception:
          time.sleep(0.05)








def get_ultrasonic_raw():
  if not US_ENABLED:
      return float("inf"), float("inf")
  now = time.time()
  with us_lock:
      l = us_left_cm  if (now - us_left_t)  <= US_STALE_TIMEOUT else float("inf")
      r = us_right_cm if (now - us_right_t) <= US_STALE_TIMEOUT else float("inf")
  return l, r








def get_ultrasonic():
  l, r = get_ultrasonic_raw()
  if np.isfinite(l):
      l += us_calib.offset_left
  if np.isfinite(r):
      r += us_calib.offset_right
  return l, r








# ══════════════════════════════════════════════════════════════════════════
#  DEPTH HELPERS
# ══════════════════════════════════════════════════════════════════════════
def roi_distance(depth_img_m: np.ndarray, roi):
  """Returns (distance_m, valid_pixel_count). Caller decides how to treat
  low-count cases -- distinguishing "occluded / no data" from "too close
  to measure" is the caller's job (see v2.12-a NaN-hold fix)."""
  h, w = depth_img_m.shape
  x0, x1 = int(roi[0] * w), int(roi[1] * w)
  y0, y1 = int(roi[2] * h), int(roi[3] * h)
  patch = depth_img_m[y0:y1, x0:x1]
  valid = patch[(patch > 0.15) & (patch < 6.0)]
  if valid.size < 50:
      return float("nan"), int(valid.size)
  return float(np.median(valid)), int(valid.size)








def bbox_distance(depth_img_m: np.ndarray, x1, y1, x2, y2) -> float:
  bw, bh = x2 - x1, y2 - y1
  cx0 = int(x1 + 0.25 * bw); cx1 = int(x2 - 0.25 * bw)
  cy0 = int(y1 + 0.25 * bh); cy1 = int(y2 - 0.25 * bh)
  patch = depth_img_m[max(cy0, 0):cy1, max(cx0, 0):cx1]
  valid = patch[(patch > 0.15) & (patch < 6.0)]
  if valid.size < 20:
      return float("nan")
  return float(np.median(valid))








def classify_zone(cx_frac: float) -> str:
  """FIX (v2.15): classify a detection's horizontal frame position into
  'left' / 'front' / 'right', reusing the FRONT_ROI split points, so the
  pillar-avoid target column can ease off once a pillar has drifted into
  the zone on its own pass-side."""
  if cx_frac < ZONE_SPLIT_1:
      return "left"
  if cx_frac < ZONE_SPLIT_2:
      return "front"
  return "right"




def target_column(color: str, cx_frac: float) -> float:
  zone = classify_zone(cx_frac)
  table = TX_GREEN_ZONE if color == "green" else TX_RED_ZONE
  return table[zone]








def fmt_m(x):
  """NaN-safe formatter for terminal logging (meters)."""
  return f"{x:.2f}" if np.isfinite(x) else "--"








def draw_roi(img, roi, color, label, dist):
  h, w = img.shape[:2]
  x0, x1 = int(roi[0] * w), int(roi[1] * w)
  y0, y1 = int(roi[2] * h), int(roi[3] * h)
  cv2.rectangle(img, (x0, y0), (x1, y1), color, 2)
  txt = f"{label}: {dist:.2f}m" if np.isfinite(dist) else f"{label}: --"
  cv2.putText(img, txt, (x0, max(y0 - 8, 15)),
              cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)








# ══════════════════════════════════════════════════════════════════════════
#  EMA FILTER — temporal smoothing with hold-last-good-on-NaN
# ══════════════════════════════════════════════════════════════════════════
class EMAFilter:
  def __init__(self, alpha: float):
      self.alpha = alpha
      self.value = float("nan")




  def update(self, raw: float) -> float:
      if not np.isfinite(raw):
          return self.value
      if not np.isfinite(self.value):
          self.value = raw
      else:
          self.value = self.alpha * raw + (1.0 - self.alpha) * self.value
      return self.value








# ══════════════════════════════════════════════════════════════════════════
#  RIGHT/LEFT-WALL DROPOUT HOLD
# ══════════════════════════════════════════════════════════════════════════
class LastGoodHold:
  """FIX (v2.12-a): now takes a `low_count` flag alongside the raw
  distance. If the ROI is returning NaN *because it's starved for valid
  depth pixels* (typical of a wall that has gotten too close — closer
  than the 0.15m depth-sensor floor, or filling/blurring the frame),
  we must NOT hold the last (farther, now-stale) good distance. Instead
  we collapse toward a conservative "assumed close" value so downstream
  clamps still engage. Only genuine dropouts (occlusion, no ROI data at
  all with a *previous* value that was already far away) get the normal
  hold-last-good behavior.
  """
  def __init__(self, timeout: float, assume_close_m: float):
      self.timeout = timeout
      self.assume_close_m = assume_close_m
      self.value = float("nan")
      self.t = 0.0




  def update(self, raw: float, now: float, low_count: bool = False) -> float:
      if np.isfinite(raw):
          self.value = raw
          self.t = now
          return raw


      if low_count:
          # Wall likely too close to resolve — don't trust a stale far
          # reading. Assume close, but don't override real recent
          # confirmed-far data. If we don't have anything let this
          # collapse toward "close" immediately (no grace period).
          if np.isfinite(self.value) and self.value <= self.assume_close_m:
              # We were already close and now lost the signal entirely —
              # stay pinned at close, don't recover to "far" on a timer.
              self.t = now
              return self.value
          self.value = self.assume_close_m
          self.t = now
          return self.value


      # genuine dropout (occlusion etc.) with no low-pixel-count signal —
      # keep the old short grace-period behavior
      if np.isfinite(self.value) and (now - self.t) <= self.timeout:
          return self.value
      return float("nan")








# ══════════════════════════════════════════════════════════════════════════
#  FLASK WEB STREAM
# ══════════════════════════════════════════════════════════════════════════
app = Flask(__name__)








@app.route("/")
def index():
  return ('<html><body style="background:#111;text-align:center">'
          '<h2 style="color:#eee">WRO Wall Follower + Pillar Avoid v2.25</h2>'
          '<img src="/video" style="width:90%;max-width:900px">'
          "</body></html>")








@app.route("/video")
def video():
  def gen():
      while True:
          with frame_lock:
              jpg = frame_jpg
          if jpg is not None:
              yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                     + jpg + b"\r\n")
          time.sleep(1.0 / 20)
  return Response(gen(),
                   mimetype="multipart/x-mixed-replace; boundary=frame")








def start_web():
  t = threading.Thread(
      target=lambda: app.run(host="0.0.0.0", port=WEB_PORT,
                             debug=False, use_reloader=False,
                             threaded=True),
      daemon=True)
  t.start()








# ══════════════════════════════════════════════════════════════════════════
#  YOLO CLASS -> COLOR MAPPING
# ══════════════════════════════════════════════════════════════════════════
def build_color_map(model) -> dict:
  cmap = {}
  for cid, name in model.names.items():
      n = str(name).lower()
      if "red" in n:
          cmap[cid] = "red"
      elif "green" in n:
          cmap[cid] = "green"
  if not cmap:
      print("[WARN] no 'red'/'green' class names found in model — "
            "falling back to id 0=red, 1=green")
      cmap = {0: "red", 1: "green"}
  print(f"[YOLO] class map: {cmap}")
  return cmap








# ══════════════════════════════════════════════════════════════════════════
#  MAIN CONTROL LOOP
# ══════════════════════════════════════════════════════════════════════════
def main():
  global frame_jpg, running




  print("[YOLO] loading", MODEL_PATH)
  model = YOLO(MODEL_PATH)
  color_map = build_color_map(model)




  imu = None
  if IMU_ENABLED:
      imu = BNO055Yaw(
          address=IMU_ADDRESS,
          busnum=IMU_BUS,
          calibration_file=IMU_CALIBRATION_FILE,
      )
      imu.set_zero()
      time.sleep(0.25)
      print("[IMU] startup direction set as relative 0 degrees")
      print(f"[IMU] calibration status: {imu.get_calibration_status()}")




  pipe, cfg = rs.pipeline(), rs.config()
  cfg.enable_stream(rs.stream.depth, DEPTH_W, DEPTH_H, rs.format.z16, FPS)
  cfg.enable_stream(rs.stream.color, DEPTH_W, DEPTH_H, rs.format.bgr8, FPS)
  profile = pipe.start(cfg)
  depth_scale = profile.get_device().first_depth_sensor().get_depth_scale()
  align = rs.align(rs.stream.color)




  start_web()
  threading.Thread(target=ultrasonic_reader, daemon=True).start()
  print(f"[WEB] http://<jetson-ip>:{WEB_PORT}")
  print(f"[US]  ultrasonic clamp {'ENABLED' if US_ENABLED else 'DISABLED'} "
        f"(L<{US_LEFT_AVOID_CM}cm / R<{US_RIGHT_AVOID_CM}cm) "
        f"autocalib={'ON' if US_AUTOCALIB_ENABLED else 'OFF'}")
  print(f"[TURN] fixed corner direction: "
        f"{'RIGHT' if TURN_DIRECTION > 0 else 'LEFT'} "
        f"(TURN_DIRECTION={TURN_DIRECTION:+d})")
  print("[RUN] continuous wall following + pillar avoid v2.25 (identity-locked "
        "pillar tracking, color-aware corner trigger) — Ctrl+C to stop")




  prev_err, prev_t = 0.0, time.time()
  prev_derr_smooth = 0.0     # FIX v2.11-b: smoothed derivative state
  turning = False
  turn_dir = TURN_DIRECTION
  was_turning = False




  pillar = None
  hold_until = 0.0
  hold_steer = 0.0
  hold_color = None
  pillar_cx_smooth = None
  pillar_track_color = None


  # FIX (v2.15) — ported from the left-wall-follower reference: corner
  # lock. If a pillar shows up while the robot is turning (or is about to
  # start turning this same frame), the forced turn used to keep running
  # to completion and simply ignore the pillar until it finished — this
  # is a plausible source of hits when a pillar sits right at a corner.
  # Now that case cancels the turn and commits to avoiding the pillar for
  # CORNER_LOCK_S instead of alternating between the two every frame.
  CORNER_LOCK_S = 0.5
  obstacle_corner_lock_until = 0.0


  # FIX (v2.16): lap-counting state (see IMU tunables above).
  total_yaw = 0.0          # cumulative unwrapped rotation, degrees
  prev_yaw = None
  lap_count = 0
  delayed_stop_time = None




  ema_front  = EMAFilter(ALPHA_DEPTH)
  ema_right  = EMAFilter(ALPHA_DEPTH)
  ema_left   = EMAFilter(ALPHA_DEPTH)
  ema_fleft  = EMAFilter(ALPHA_DEPTH)
  ema_fright = EMAFilter(ALPHA_DEPTH)




  # FIX (v2.12-a): hold classes now know what "close" means for their ROI
  # so a low-pixel-count NaN collapses toward "close" instead of holding
  # a stale far reading.
  right_hold = LastGoodHold(RIGHT_HOLD_TIMEOUT, assume_close_m=MIN_WALL_CLEAR)
  left_hold  = LastGoodHold(RIGHT_HOLD_TIMEOUT, assume_close_m=MIN_WALL_CLEAR)




  prev_front_d = float("nan")
  prev_sent_steer = 0.0
  steer_out_smooth = 0.0   # FIX v2.11-e: final-output EMA state




  # FIX (v2.11-d): hysteresis latch state for the wall-push clamp
  right_clamp_engaged = False
  left_clamp_engaged = False




  was_stopped = True
  move_start_t = 0.0




  try:
      while running:
          frames = align.process(pipe.wait_for_frames())
          depth  = frames.get_depth_frame()
          color  = frames.get_color_frame()
          if not depth or not color:
              continue




          depth_m = np.asanyarray(depth.get_data()).astype(np.float32) \
                    * depth_scale
          img = np.asanyarray(color.get_data())
          H, W = depth_m.shape
          now = time.time()




          # ── 0. IMU lap counting ──────────────────────────────────────
          if IMU_ENABLED and delayed_stop_time is None:
              yaw = imu.read_relative_yaw()
              if yaw is not None:
                  if prev_yaw is not None:
                      # unwrap: shortest signed delta between consecutive
                      # readings, so e.g. 359 -> 1 counts as +2, not -358
                      d = ((yaw - prev_yaw + 180.0) % 360.0) - 180.0
                      total_yaw += d
                  prev_yaw = yaw


                  new_lap_count = int(abs(total_yaw) // 360)
                  if new_lap_count > lap_count:
                      lap_count = new_lap_count
                      print(f"[LAP] completed {lap_count}/{LAPS_TO_COMPLETE} "
                            f"(total_yaw={total_yaw:+.1f} deg)")
                      if lap_count >= LAPS_TO_COMPLETE:
                          delayed_stop_time = now + STOP_DELAY_AFTER_LAPS
                          print(f"[LAP] {LAPS_TO_COMPLETE} laps complete — "
                                f"stopping in {STOP_DELAY_AFTER_LAPS:.1f}s")


          if delayed_stop_time is not None and now >= delayed_stop_time:
              print("[LAP] stop delay complete — stopping robot")
              stop_robot()
              running = False
              break




          # ── 1. YOLO detection on the color frame ───────────────────
          results = model.predict(img, imgsz=IMG_SIZE, conf=CONF_THRES,
                                  verbose=False)[0]




          detections = []
          wall_depth = depth_m.copy()
          for box in results.boxes:
              cid = int(box.cls[0])
              if cid not in color_map:
                  continue
              x1, y1, x2, y2 = [int(v) for v in box.xyxy[0]]
              x1, y1 = max(x1, 0), max(y1, 0)
              x2, y2 = min(x2, W - 1), min(y2, H - 1)


              # FIX (v2.20): ignore detections whose box center sits in
              # the top DETECT_IGNORE_TOP_FRAC of the frame (likely a
              # wall/ceiling misclassification, not a real floor pillar).
              cy_frac = ((y1 + y2) / 2) / H
              if cy_frac < DETECT_IGNORE_TOP_FRAC:
                  continue


              d = bbox_distance(depth_m, x1, y1, x2, y2)
              cx_frac = ((x1 + x2) / 2) / W
              detections.append((color_map[cid], cx_frac, d,
                                 (x1, y1, x2, y2)))
              m = 6
              wall_depth[max(y1-m,0):min(y2+m,H),
                         max(x1-m,0):min(x2+m,W)] = 0.0




          # ── 2. wall distances (pillars excluded), EMA-smoothed ──────
          front_raw, _front_n   = roi_distance(wall_depth, FRONT_ROI)
          right_raw, right_n    = roi_distance(wall_depth, RIGHT_ROI)
          left_raw,  left_n     = roi_distance(wall_depth, LEFT_ROI)
          fleft_raw, _fleft_n   = roi_distance(wall_depth, FRONT_LEFT_ROI)
          fright_raw, _fright_n = roi_distance(wall_depth, FRONT_RIGHT_ROI)


          front_d  = ema_front.update(front_raw)
          right_d  = ema_right.update(right_raw)
          left_d   = ema_left.update(left_raw)
          fleft_d  = ema_fleft.update(fleft_raw)
          fright_d = ema_fright.update(fright_raw)




          # FIX (v2.12-a): pass low-pixel-count flag through so a NaN
          # caused by a too-close wall doesn't hold a stale far reading.
          right_low_count = right_n < 50
          left_low_count  = left_n < 50
          right_d = right_hold.update(right_d, now, low_count=right_low_count)
          left_d  = left_hold.update(left_d, now, low_count=left_low_count)




          us_l_raw, us_r_raw = get_ultrasonic_raw()
          us_l_cm, us_r_cm = get_ultrasonic()




          if US_AUTOCALIB_ENABLED and not turning:
              if np.isfinite(right_d):
                  us_calib.update("right", right_d, us_r_raw)
              if np.isfinite(left_d):
                  us_calib.update("left", left_d, us_l_raw)
              us_calib.save(now)




          dt_rate = max(now - prev_t, 1e-3)
          if np.isfinite(front_d) and np.isfinite(prev_front_d):
              front_rate = (front_d - prev_front_d) / dt_rate
          else:
              front_rate = 0.0
          prev_front_d = front_d




          # ── 3. pick / refresh the active pillar (identity-locked) ────
          # FIX (identity-lock): previously this always re-minimized
          # distance across ALL detections every frame, so a
          # just-passed pillar still lingering close in-frame could keep
          # beating a farther, newly-appearing pillar and block the
          # handoff (only ever showing up at corners where the outgoing
          # pillar stays in view / close longer than at other corners).
          # Now: if we already have an active pillar, first try to keep
          # tracking THAT SAME detection (same color, nearest cx to its
          # last known position) instead of re-minimizing globally. Only
          # fall back to picking a brand-new "closest" pillar once the
          # currently tracked one can no longer be matched at all.
          candidates = []
          for col, cxf, d, bb in detections:
              engage_dist = ENGAGE_DIST_RED if col == "red" else ENGAGE_DIST_GREEN
              if np.isfinite(d) and d < engage_dist:
                  candidates.append((col, cxf, d, bb))


          best = None
          if pillar is not None:
              # try to re-acquire the SAME pillar we were already tracking
              same_color = [c for c in candidates if c[0] == pillar_track_color]
              if same_color:
                  best = min(
                      same_color,
                      key=lambda c: abs(c[1] - pillar["cx"])
                  )
                  if abs(best[1] - pillar["cx"]) > CX_MATCH_TOL:
                      best = None  # drifted too far to be the same pillar


          if best is None:
              # no active pillar, or it's no longer matchable -> free pick
              for c in candidates:
                  if best is None or c[2] < best[2]:
                      best = c


          if best is not None:
              if pillar_cx_smooth is None or pillar_track_color != best[0]:
                  pillar_cx_smooth = best[1]
              else:
                  pillar_cx_smooth = (PILLAR_CX_ALPHA * best[1]
                                       + (1 - PILLAR_CX_ALPHA) * pillar_cx_smooth)
              pillar_track_color = best[0]
              pillar = {"color": best[0], "cx": pillar_cx_smooth,
                        "dist": best[2], "t": now}




              # FIX (v2.15): pillar appearing during (or about to start)
              # a forced turn -> cancel the turn, lock into pillar-avoid.
              will_turn_this_frame = (
                  np.isfinite(front_d) and front_d < FRONT_STOP
              )
              if turning or will_turn_this_frame:
                  obstacle_corner_lock_until = now + CORNER_LOCK_S
                  turning = False
          elif pillar is not None and now - pillar["t"] > MEMORY_TTL:
              if pillar["dist"] < PASS_DIST:
                  hold_until = now + HOLD_TIME
                  hold_color = pillar["color"]
              pillar = None
              pillar_track_color = None




          dt = max(now - prev_t, 1e-3)




          # ── 4. decide mode ───────────────────────────────────────────
          front_danger = (
              (np.isfinite(front_d)  and front_d  < FRONT_STOP) or
              (np.isfinite(fleft_d)  and fleft_d  < FRONT_STOP) or
              (np.isfinite(fright_d) and fright_d < FRONT_STOP)
          )




          # FIX (corner-color): pick the corner-trigger distance based on
          # the currently locked pillar color (set in section 3, above,
          # so it's already valid here). front_danger itself is left
          # alone -- it still drives pillar urgency and predictive bias
          # exactly as before, and FRONT_STOP/FRONT_CLEAR are unchanged.
          if pillar is not None and pillar["color"] == "green":
              corner_start_dist = CORNER_START_GREEN
          elif pillar is not None and pillar["color"] == "red":
              corner_start_dist = CORNER_START_RED
          else:
              corner_start_dist = CORNER_START_NORMAL


          corner_danger = (
              (np.isfinite(front_d)  and front_d  < corner_start_dist) or
              (np.isfinite(fleft_d)  and fleft_d  < corner_start_dist) or
              (np.isfinite(fright_d) and fright_d < corner_start_dist)
          )




          if corner_danger and not turning and now >= obstacle_corner_lock_until:
              # FIX (v2.24): always corner the same fixed direction —
              # see TURN_DIRECTION comment up in TUNABLES. No more
              # l_room/r_room comparison.
              turn_dir = TURN_DIRECTION
              turning = True
          elif turning and (not front_danger) and (
                  (np.isfinite(front_d) and front_d > FRONT_CLEAR) or
                  not np.isfinite(front_d)):
              turning = False




          was_turning = turning




          avoiding_red = False
          avoiding_green = False
          avoiding_pillar_now = False








          if turning:
              steer = turn_dir * TURN_STEER_MAG
              speed = TURN_SPEED
              mode = f"TURN {'RIGHT' if turn_dir > 0 else 'LEFT'}"
              prev_err = 0.0
              pillar = None
              hold_until = 0.0
              hold_color = None




          elif pillar is not None:
              avoiding_pillar_now = True
              # FIX (v2.15): zone-based target column instead of one
              # fixed TX_GREEN/TX_RED. Eases the target back toward
              # center once the pillar has drifted into the ROI zone on
              # its own pass-side (already close to being passed).
              tx  = target_column(pillar["color"], pillar["cx"])
              err = pillar["cx"] - tx




              # FIX (v2.13): symmetric clamp on BOTH sides of err, for
              # BOTH colors. v2.12 only capped one side per color (the
              # "safe" side), leaving the other side of err completely
              # unclamped — a pillar detected far from its target could
              # drive steer to very large values at full KP_PILLAR gain
              # with no ceiling. That was almost certainly the cause of
              # both the too-fast green turns and the red wall hits.
              err = max(-PILLAR_ERR_TOL, min(err, PILLAR_ERR_TOL))




              kp = KP_PILLAR_GREEN if pillar["color"] == "green" else KP_PILLAR_RED
              steer = kp * err




              if pillar["color"] == "red":
                  avoiding_red = True
                  if np.isfinite(right_d):
                      hug = KP_HUG_RED * (right_d - RED_WALL_TARGET)
                      hug = max(0.0, min(hug, HUG_MAX_RED))
                      steer += hug
              elif pillar["color"] == "green":
                  avoiding_green = True
                  if np.isfinite(left_d):
                      hug = KP_HUG_GREEN * (left_d - GREEN_WALL_TARGET)
                      hug = max(0.0, min(hug, HUG_MAX_GREEN))
                      steer -= hug




              if front_danger:
                  urgency = PILLAR_URGENCY
                  steer = max(-TURN_STEER_MAG,
                              min(TURN_STEER_MAG, steer * urgency))
                  speed = TURN_SPEED
                  mode  = f"AVOID {pillar['color'].upper()} " \
                          f"{pillar['dist']:.2f}m (urgent)"
              else:
                  speed = SPEED_AVOID
                  mode  = f"AVOID {pillar['color'].upper()} " \
                          f"{pillar['dist']:.2f}m"




              hold_steer = steer
              prev_err = 0.0




          elif now < hold_until:
              avoiding_pillar_now = True
              steer = hold_steer
              speed = SPEED_AVOID
              mode  = f"HOLD {hold_color or ''}".strip().upper()
              prev_err = 0.0
              if hold_color == "red":
                  avoiding_red = True
              elif hold_color == "green":
                  avoiding_green = True




          else:
              mode = "FOLLOW"
              if np.isfinite(right_d):
                  err = right_d - RIGHT_TARGET
                  if abs(err) < FOLLOW_ERR_DEADBAND:
                      err = 0.0
                  derr_raw = (err - prev_err) / dt
                  prev_derr_smooth = (DERR_ALPHA * derr_raw
                                       + (1 - DERR_ALPHA) * prev_derr_smooth)
                  steer = KP_STEER * err + KD_STEER * prev_derr_smooth
                  prev_err = err
              else:
                  steer = 0
              speed = BASE_SPEED




          # ── 4b. predictive front-wall soft bias (skip during hard turn)
          if not mode.startswith("TURN"):
              front_bias = 0.0
              worst_d = front_d
              for d in (fleft_d, fright_d):
                  if np.isfinite(d) and (not np.isfinite(worst_d) or d < worst_d):
                      worst_d = d
              if np.isfinite(worst_d) and worst_d < FRONT_WARN:
                  span = max(FRONT_WARN - FRONT_STOP, 1e-3)
                  proximity = max(0.0, (FRONT_WARN - worst_d) / span)
                  closing = max(0.0, -front_rate)
                  bias_mag = (TURN_STEER_MAG * FRONT_BIAS_MAX_FRAC) * proximity \
                             + FRONT_RATE_GAIN * closing
                  bias_mag = min(bias_mag, TURN_STEER_MAG)


                  # FIX (v2.24): bias direction now follows the same
                  # fixed TURN_DIRECTION as the hard turn, instead of
                  # comparing l_room/r_room. Keeps the predictive nudge
                  # consistent with which way the robot will actually
                  # corner, rather than occasionally disagreeing with it.
                  front_bias = bias_mag if TURN_DIRECTION > 0 else -bias_mag
              steer += front_bias




          # ── 5. wall clamp (active push, with hysteresis — v2.11-d) ──
          WALL_PUSH_GAIN = 80.0




          right_clear = RED_WALL_CLEAR if avoiding_red else MIN_WALL_CLEAR
          left_clear  = GREEN_WALL_CLEAR if avoiding_green else MIN_WALL_CLEAR




          if np.isfinite(right_d):
              if right_d < right_clear:
                  right_clamp_engaged = True
              elif right_d > right_clear + CLAMP_HYST_M:
                  right_clamp_engaged = False
          if right_clamp_engaged and np.isfinite(right_d):
              intrusion = max(0.0, right_clear - right_d)
              push = -WALL_PUSH_GAIN * intrusion
              steer = min(steer, push)




          if np.isfinite(left_d):
              if left_d < left_clear:
                  left_clamp_engaged = True
              elif left_d > left_clear + CLAMP_HYST_M:
                  left_clamp_engaged = False
          if left_clamp_engaged and np.isfinite(left_d):
              intrusion = max(0.0, left_clear - left_d)
              push = WALL_PUSH_GAIN * intrusion
              steer = max(steer, push)




          wall_clamp_active = right_clamp_engaged or left_clamp_engaged




          # ── 5a. ultrasonic hard safety clamp (independent layer) ─────
          us_clamped = False
          if not turning:
              if us_r_cm < US_RIGHT_AVOID_CM:
                  intrusion_m = (US_RIGHT_AVOID_CM - us_r_cm) / 100.0
                  steer = min(steer, -WALL_PUSH_GAIN * intrusion_m)
                  us_clamped = True
              if us_l_cm < US_LEFT_AVOID_CM:
                  intrusion_m = (US_LEFT_AVOID_CM - us_l_cm) / 100.0
                  steer = max(steer, WALL_PUSH_GAIN * intrusion_m)
                  us_clamped = True




          # ── 5b. speed floor, plus a hard cap in the danger zone ──────
          DANGER_ZONE_CAP = 130
          SIDE_DANGER_CAP = 120
          worst_front = front_d
          for d in (fleft_d, fright_d):
              if np.isfinite(d) and (not np.isfinite(worst_front) or d < worst_front):
                  worst_front = d
          if np.isfinite(worst_front) and worst_front < FRONT_WARN:
              speed = min(speed, DANGER_ZONE_CAP)
          side_close = wall_clamp_active or us_clamped
          if side_close and not turning:
              speed = min(speed, SIDE_DANGER_CAP)
          # FIX (v2.13): red/green hug-avoid runs with a tight clearance
          # margin (RED_WALL_CLEAR/GREEN_WALL_CLEAR = 0.22m) — SPEED_AVOID
          # (160) was too fast for that margin, so by the time the wall
          # clamp engaged there wasn't enough room left to react, which
          # is a likely cause of the red-side hits. Scale speed down as
          # the tracked wall gets close during an active pillar avoid.
          PILLAR_HUG_DANGER_CAP = 110
          PILLAR_HUG_WARN_M     = 0.35
          if avoiding_pillar_now and not turning:
              hug_d = right_d if avoiding_red else (left_d if avoiding_green else float("nan"))
              if np.isfinite(hug_d) and hug_d < PILLAR_HUG_WARN_M:
                  speed = min(speed, PILLAR_HUG_DANGER_CAP)
          # FIX (v2.12-d): extra-hard cap specifically for the ultrasonic
          # hard-safety clamp — this is the "about to hit something" case.
          if us_clamped and not turning:
              speed = min(speed, US_HARD_DANGER_CAP)
          speed = max(MIN_MOVE_SPEED, speed)
          speed = int(speed)




          # ── 5c. steering slew-rate limit (anti-oscillation) ──────────
          # FIX (v2.12-c): ultrasonic hard clamp gets its own much faster
          # slew limit instead of sharing MAX_STEER_DELTA_URGENT with the
          # softer wall-push clamp / turning states.
          urgent_now = turning or wall_clamp_active or us_clamped
          if us_clamped:
              max_delta = MAX_STEER_DELTA_US_HARD
          elif urgent_now:
              max_delta = MAX_STEER_DELTA_URGENT
          elif avoiding_pillar_now:
              # FIX (v2.14): gentler cap specifically for pillar avoid
              # (engage-transition smoothing), see MAX_STEER_DELTA_PILLAR
              # comment above. front_danger pillar cases still escalate
              # through urgent_now (wall_clamp/us_clamped) as before.
              max_delta = MAX_STEER_DELTA_PILLAR
          else:
              max_delta = MAX_STEER_DELTA_FOLLOW
          delta = steer - prev_sent_steer
          delta = max(-max_delta, min(max_delta, delta))
          steer = prev_sent_steer + delta
          prev_sent_steer = steer




          # ── 5d. final light output smoothing ──────────────────────────
          # FIX (v2.12-b): skip this extra smoothing entirely when urgent
          # — an emergency correction that already passed through the
          # slew limiter shouldn't be damped a second time before it
          # reaches the motors.
          if urgent_now:
              steer_out_smooth = steer
          else:
              steer_out_smooth = (STEER_OUT_ALPHA * steer
                                   + (1 - STEER_OUT_ALPHA) * steer_out_smooth)
          steer = steer_out_smooth




          # ── 5e. startup kick — brief extra PWM coming off a stop
          if was_stopped:
              move_start_t = now
          if (now - move_start_t) * 1000 < STARTUP_KICK_MS:
              speed = max(speed, STARTUP_KICK_PWM)
          was_stopped = (speed <= 0)




          prev_t = now
          send_drive(int(round(steer)), speed)




          # ── terminal telemetry (added: mirrors what's drawn on-stream) ──
          det_txt = ", ".join(
              f"{col}@{cxf:.2f}={fmt_m(d)}m" for col, cxf, d, _bb in detections
          ) or "none"
          print(
              f"[DATA] mode={mode:<28s} steer={steer:+6.1f} speed={speed:3d}  "
              f"front={fmt_m(front_d)} right={fmt_m(right_d)} left={fmt_m(left_d)} "
              f"fL={fmt_m(fleft_d)} fR={fmt_m(fright_d)}  "
              f"corner_dist={corner_start_dist:.2f}  "
              f"US_L={fmt_m(us_l_cm/100.0) if np.isfinite(us_l_cm) else '--'}m "
              f"US_R={fmt_m(us_r_cm/100.0) if np.isfinite(us_r_cm) else '--'}m  "
              f"sees=[{det_txt}]  "
              f"lap={lap_count}/{LAPS_TO_COMPLETE} yaw={total_yaw:+.0f}deg"
          )




          # ── 6. annotated frame for the web stream ───────────────────
          vis = img.copy()
          ignore_y = int(DETECT_IGNORE_TOP_FRAC * H)
          cv2.line(vis, (0, ignore_y), (W, ignore_y), (0, 165, 255), 1)
          cv2.putText(vis, "ignore above", (5, max(ignore_y - 6, 12)),
                      cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 165, 255), 1)
          draw_roi(vis, FRONT_ROI, (0, 0, 255),   "FRONT", front_d)
          draw_roi(vis, RIGHT_ROI, (0, 255, 0),   "RIGHT", right_d)
          draw_roi(vis, LEFT_ROI,  (255, 200, 0), "LEFT",  left_d)
          for col, cxf, d, (x1, y1, x2, y2) in detections:
              c = (0, 0, 255) if col == "red" else (0, 200, 0)
              cv2.rectangle(vis, (x1, y1), (x2, y2), c, 2)
              txt = f"{col} {d:.2f}m" if np.isfinite(d) else col
              cv2.putText(vis, txt, (x1, max(y1 - 8, 15)),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.55, c, 2)
          if pillar is not None:
              tx = target_column(pillar["color"], pillar["cx"])
              cv2.line(vis, (int(tx * W), 0), (int(tx * W), H),
                       (255, 255, 0), 1)
              # FIX (identity-lock debug): show which pillar is locked
              # (color + tracked cx) so the lock can be visually verified
              # on the stream before trusting it on the track.
              cv2.putText(vis,
                          f"LOCKED: {pillar['color']} cx={pillar['cx']:.2f}",
                          (10, H - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                          (255, 255, 0), 2)
          clamp_txt = f"clampR={right_clear:.2f} clampL={left_clear:.2f}"
          if now < obstacle_corner_lock_until:
              mode += " [CORNER-LOCK]"
          cv2.putText(vis, f"{mode}  steer={steer:+.0f}  spd={speed}  "
                           f"{clamp_txt}  rate={front_rate:+.2f}m/s  "
                           f"cornerD={corner_start_dist:.2f}",
                      (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                      (255, 255, 255), 2)
          us_color = (0, 0, 255) if us_clamped else (0, 255, 255)
          us_l_txt = f"{us_l_cm:.0f}" if np.isfinite(us_l_cm) else "--"
          us_r_txt = f"{us_r_cm:.0f}" if np.isfinite(us_r_cm) else "--"
          cv2.putText(vis, f"US  L={us_l_txt}cm(off{us_calib.offset_left:+.0f})  "
                           f"R={us_r_txt}cm(off{us_calib.offset_right:+.0f})"
                           f"{'  (held-off, turning)' if turning else ''}",
                      (10, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                      us_color, 2)
          cv2.putText(vis, f"{'URGENT SLEW' if urgent_now else 'NORMAL'}"
                           f"{' [US-HARD]' if us_clamped else ''}",
                      (10, 86), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                      (0, 255, 255), 2)
          if IMU_ENABLED:
              lap_txt = f"LAP {lap_count}/{LAPS_TO_COMPLETE}  yaw={total_yaw:+.0f}deg"
              if delayed_stop_time is not None:
                  lap_txt += f"  stopping in {max(0.0, delayed_stop_time-now):.1f}s"
              cv2.putText(vis, lap_txt, (10, 114),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
          ok, jpg = cv2.imencode(".jpg", vis,
                                 [cv2.IMWRITE_JPEG_QUALITY, 70])
          if ok:
              with frame_lock:
                  frame_jpg = jpg.tobytes()




  finally:
      us_calib.save(time.time(), force=True)
      stop_robot()
      try:
          pipe.stop()
      except Exception:
          pass
      ser.close()
      try:
          del model
      except Exception:
          pass
      try:
          import torch
          torch.cuda.empty_cache()
          torch.cuda.ipc_collect()
      except Exception:
          pass
      import gc
      gc.collect()
      print("[DONE] robot stopped, ports closed.")








if __name__ == "__main__":
  main()

