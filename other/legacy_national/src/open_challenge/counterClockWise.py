#!/usr/bin/env python3
"""
Depth-only right-wall-following test for RealSense D455.

Behaviour:
- Keep approximately 0.50 m from the right wall using the depth camera.
- When the front distance is below 0.70 m, turn left.
- Continue turning left until the front opens beyond 0.90 m.
- No YOLO, pillar detection, ultrasonic processing, or reverse recovery.
- Use BNO055 relative yaw to stop after 3 clockwise laps.

Jetson -> ESP32 protocol:
    DRIVE <steerDeg> <speed>\n
Steering convention used by the existing robot code:
    positive = RIGHT
    negative = LEFT
"""

import signal
import threading
import time

import cv2
import numpy as np
import pyrealsense2 as rs
import serial
from flask import Flask, Response

from bno055_yaw import BNO055Yaw


# ---------------------------------------------------------------------------
# TUNABLES
# ---------------------------------------------------------------------------
SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUD = 115200

# BNO055 IMU. Change IMU_ADDRESS to 0x29 if that is your detected address.
IMU_ADDRESS = 0x28
IMU_BUS = 1
IMU_CALIBRATION_FILE = "bno055_calibration.json"

# Clockwise lap sequence for right-wall following:
# Initial direction is always set to relative 0 degrees.
# A checkpoint is accepted when the yaw enters its broad 90-degree zone:
#   270 zone: 225..315
#   180 zone: 135..225
#    90 zone:  45..135
#     0 zone: 315..360 or 0..45
LAP_YAW_CHECKPOINTS = (270.0, 180.0, 90.0, 0.0)
LAP_ZONE_HALF_WIDTH = 10.0
LAPS_TO_COMPLETE = 3
STOP_DELAY_AFTER_LAPS = 0.5  # seconds to continue driving after lap 3

RIGHT_TARGET = 0.60       # m: desired right-wall distance
FRONT_STOP = 0.60         # m: start turning left below this distance
FRONT_CLEAR = 0.80        # m: finish the left turn above this distance

KP_STEER = 38.0           # steering degrees per metre of wall-distance error
KD_STEER = 4.0            # damping; reduce if steering becomes noisy
STEER_LIMIT = 35.0

BASE_SPEED = 200          # reduce for the first test
TURN_SPEED = 180
TURN_STEER = -32.0        # negative means LEFT

# If the right wall is temporarily not visible, search gently to the right.
SEARCH_RIGHT_STEER = 10.0

# Ignore unsafe/noisy depth readings outside this interval.
MIN_VALID_DEPTH = 0.15
MAX_VALID_DEPTH = 4.00
MIN_VALID_PIXELS = 50

DEPTH_W, DEPTH_H, FPS = 640, 480, 30

# ROI format: (x0, x1, y0, y1), as fractions of image width/height.
# Front ROI is centred and slightly lower to detect walls in the driving path.
FRONT_ROI = (0.36, 0.64, 0.38, 0.76)

# Right ROI is kept low and near the right edge so it measures the side wall.
RIGHT_ROI = (0.72, 0.96, 0.42, 0.82)

WEB_PORT = 5000


# ---------------------------------------------------------------------------
# GLOBALS
# ---------------------------------------------------------------------------
running = True
frame_jpg = None
frame_lock = threading.Lock()

app = Flask(__name__)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def yaw_distance_deg(yaw_a: float, yaw_b: float) -> float:
    """Return the shortest circular distance between two yaw angles."""
    return abs((yaw_a - yaw_b + 180.0) % 360.0 - 180.0)


def yaw_in_checkpoint_zone(yaw: float, checkpoint: float) -> bool:
    """Return True when yaw is inside the checkpoint's broad heading zone."""
    return yaw_distance_deg(yaw, checkpoint) <= LAP_ZONE_HALF_WIDTH


def roi_distance(depth_img_m: np.ndarray, roi) -> float:
    """Return the median valid depth inside an ROI, or NaN if unavailable."""
    height, width = depth_img_m.shape
    x0 = int(roi[0] * width)
    x1 = int(roi[1] * width)
    y0 = int(roi[2] * height)
    y1 = int(roi[3] * height)

    patch = depth_img_m[y0:y1, x0:x1]
    valid = patch[
        (patch > MIN_VALID_DEPTH)
        & (patch < MAX_VALID_DEPTH)
        & np.isfinite(patch)
    ]

    if valid.size < MIN_VALID_PIXELS:
        return float("nan")

    return float(np.median(valid))


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


def stop_robot(ser: serial.Serial) -> None:
    for _ in range(3):
        try:
            ser.write(b"DRIVE 0 0\n")
            time.sleep(0.05)
        except Exception:
            pass


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
        '<h2 style="color:#eee">Depth-only Right Wall Test</h2>'
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

    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.depth, DEPTH_W, DEPTH_H, rs.format.z16, FPS)
    config.enable_stream(rs.stream.color, DEPTH_W, DEPTH_H, rs.format.bgr8, FPS)

    profile = pipeline.start(config)
    depth_scale = profile.get_device().first_depth_sensor().get_depth_scale()
    align = rs.align(rs.stream.color)

    start_web_server()
    print(f"[WEB] http://<jetson-ip>:{WEB_PORT}")
    print("[RUN] depth-only right-wall following; Ctrl+C to stop")
    print(
        f"[LAP] waiting for 0 -> 270 -> 180 -> 90 -> 0, "
        f"then stop after {LAPS_TO_COMPLETE} laps"
    )

    lap_count = 0
    lap_checkpoint_index = 0
    delayed_stop_time = None

    # Prevent repeated counting while the IMU remains inside one checkpoint zone.
    checkpoint_zone_latched = False

    previous_error = 0.0
    previous_time = time.time()
    turning_left = False

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

            front_distance = roi_distance(depth_m, FRONT_ROI)
            right_distance = roi_distance(depth_m, RIGHT_ROI)

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
            if not turning_left:
                if np.isfinite(front_distance) and front_distance <= FRONT_STOP:
                    turning_left = True
            else:
                if not np.isfinite(front_distance) or front_distance >= FRONT_CLEAR:
                    turning_left = False

            if turning_left:
                steer = TURN_STEER
                speed = TURN_SPEED
                mode = "TURN LEFT"
                previous_error = 0.0
            else:
                speed = BASE_SPEED

                if np.isfinite(right_distance):
                    # Too far from right wall -> positive error -> steer RIGHT.
                    # Too close to right wall -> negative error -> steer LEFT.
                    error = right_distance - RIGHT_TARGET
                    error_rate = (error - previous_error) / dt
                    steer = KP_STEER * error + KD_STEER * error_rate
                    steer = clamp(steer, -STEER_LIMIT, STEER_LIMIT)
                    previous_error = error
                    mode = "FOLLOW RIGHT WALL"
                else:
                    # The wall may disappear briefly at an opening/corner.
                    steer = SEARCH_RIGHT_STEER
                    previous_error = 0.0
                    mode = "SEARCH RIGHT WALL"

            send_drive(ser, steer, speed)

            display = image.copy()
            draw_roi(display, FRONT_ROI, "FRONT", front_distance, (0, 0, 255))
            draw_roi(display, RIGHT_ROI, "RIGHT", right_distance, (0, 255, 0))

            cv2.putText(
                display,
                f"{mode}  steer={steer:+.1f}  speed={speed}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
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
                f"right target={RIGHT_TARGET:.2f} m  front turn={FRONT_STOP:.2f} m",
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


