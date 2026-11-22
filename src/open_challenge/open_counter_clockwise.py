#!/usr/bin/env python3

"""Inner-left wall follower with front-left opening detection.

Starts driving automatically with valid scans. Ctrl+C requests STOP.

Requires ESP32 command watchdog for process/USB failure protection.

No lap counter; stop manually. Validate steering and angles with wheels lifted.

Corner timing and 0.30 m offset are approximate, not guaranteed geometry.

"""



import math

import threading

import time



import numpy as np

import serial

from flask import Flask, jsonify, render_template_string

from hokuyolx import HokuyoLX
from smbus2 import SMBus





# =========================================================

# CONFIGURATION

# =========================================================



LIDAR_IP = "192.168.0.10"

LIDAR_PORT = 10940



ESP32_PORT = "/dev/ttyUSB0"

ESP32_BAUD = 115200



WEB_PORT = 5000

# BNO055 IMU
IMU_BUS = 7
IMU_ADDRESS = 0x28
OPR_MODE = 0x3D
CONFIG_MODE = 0x00
NDOF_MODE = 0x0C
EUL_HEADING_LSB = 0x1A
EUL_HEADING_MSB = 0x1B

# Lap counting
TARGET_LAPS = 3
START_ZONE_DEG = 18.0
REARM_ANGLE_DEG = 45.0



# Preserve the angle mapping from your working LiDAR code:

# +90 = left, 0 = front, -90 = right

RAW_ANGLE_MIN = -135.0

RAW_ANGLE_MAX = 135.0



VIEW_ANGLE_MIN = -90.0

VIEW_ANGLE_MAX = 90.0



MIN_DISTANCE_M = 0.05

MAX_DISTANCE_M = 3.0



# Wall-following parameters

TARGET_LEFT = 0.35

# Distance is measured from the LiDAR, not the side of the body.

FRONT_LEFT_OPEN_DISTANCE = 0.80  # 40–50 degree sector, metres

FRONT_LEFT_WALL_DISTANCE = 0.75  # lower threshold to re-arm/reacquire

LEFT_DEPART_DISTANCE = 0.50     # evidence the old wall is no longer alongside

CORNER_ENTRY_STEERING = 10      # gentle early left turn; tune on track

LEFT_REACQUIRE_DISTANCE = 0.45

LEFT_TOO_CLOSE = 0.25

RECENT_LEFT_WALL_SECONDS = 1.5

GAP_CONFIRM_SCANS = 2

REACQUIRE_SCANS = 2

MIN_TURN_TIME = 0.25

MAX_TURN_TIME = 2.0

FRONT_STOP_DISTANCE = 0.20

# Control retains valid distant returns; viewer still displays only 3 m.

CONTROL_MAX_DISTANCE_M = 30.0

FRONT_LIMIT = 0.75



# Same gain interpretation as your simulation: radians/metre

KP = 1.0

MAX_STEERING_DEG = 29



# ESP32 motor PWM: 0–255

FORWARD_PWM = 255

TURN_PWM = 240



CONTROL_INTERVAL = 0.05

SCAN_TIMEOUT = 0.50





# =========================================================

# FLASK AND SHARED DATA

# =========================================================



app = Flask(__name__)



data_lock = threading.Lock()

stop_event = threading.Event()



latest_data = {

    "connected": False,

    "error": "Waiting for LiDAR...",

    "received_at": 0.0,

    "timestamp": 0,

    "angles": [],

    "distances": [],

    "front": None,

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





# =========================================================
# BNO055 IMU + LAP COUNTER
# =========================================================

class IMULapCounter:
    def __init__(self):
        self.bus = SMBus(IMU_BUS)
        self.zero_yaw = 0.0
        self.lap_count = 0
        self.armed = False

        self.write_reg(OPR_MODE, CONFIG_MODE)
        time.sleep(0.1)

        self.write_reg(OPR_MODE, NDOF_MODE)
        time.sleep(0.7)

        # Keep the robot still and pointed in the desired start direction here.
        time.sleep(1.0)
        self.zero_yaw = self.read_raw_yaw()

        print(f"IMU initial heading: {self.zero_yaw:.2f} deg")
        print("IMU yaw initialized to 0 deg")

    def write_reg(self, reg, value):
        self.bus.write_byte_data(IMU_ADDRESS, reg, value)

    def read_raw_yaw(self):
        lsb = self.bus.read_byte_data(IMU_ADDRESS, EUL_HEADING_LSB)
        msb = self.bus.read_byte_data(IMU_ADDRESS, EUL_HEADING_MSB)
        raw = (msb << 8) | lsb
        return raw / 16.0

    def read_yaw(self):
        current_yaw = self.read_raw_yaw()
        return (current_yaw - self.zero_yaw) % 360.0

    @staticmethod
    def distance_from_zero(yaw):
        return min(yaw, 360.0 - yaw)

    def update(self):
        yaw = self.read_yaw()
        zero_error = self.distance_from_zero(yaw)

        # Starting at 0 deg must NOT count as lap 1.
        # First leave the start heading by at least REARM_ANGLE_DEG.
        if not self.armed:
            if zero_error >= REARM_ANGLE_DEG:
                self.armed = True

        # Returning near 0 deg after that completes one lap.
        elif zero_error <= START_ZONE_DEG:
            self.lap_count += 1
            self.armed = False
            print(
                f">>> LAP {self.lap_count}/{TARGET_LAPS} COMPLETE "
                f"| Yaw: {yaw:.2f} deg"
            )

        finished = self.lap_count >= TARGET_LAPS
        return yaw, self.lap_count, finished

    def close(self):
        try:
            self.bus.close()
        except Exception:
            pass


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



                valid = (

                    (raw_angles >= VIEW_ANGLE_MIN)

                    & (raw_angles <= VIEW_ANGLE_MAX)

                    & (raw_scan >= MIN_DISTANCE_M)

                    & (raw_scan <= CONTROL_MAX_DISTANCE_M)

                    & np.isfinite(raw_scan)

                )



                angles = raw_angles[valid]

                scan = raw_scan[valid]



                front = get_median_distance(

                    scan, angles, -5, 5

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

                    "distances": np.round(scan[scan <= MAX_DISTANCE_M], 3).tolist(),

                    "front": front,

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

# WALL-FOLLOWING METHOD

# =========================================================



class InnerWallFollower:

    """Front-left opening starts a corner; left distance controls clearance.



    The early-turn and clearance settings are track-tuning parameters, not a

    collision-free trajectory guarantee. Positive steering commands turn right.

    """



    def __init__(self):

        self.turning = False

        self.turn_started = 0.0

        self.gap_count = 0

        self.reacquire_count = 0

        self.armed = False

        self.departed_old_wall = False

        self.last_left_wall_at = None

        self.last_scan = None

        self.last_command = ("STOP", 0, 0, "Waiting for inner wall")

        self.fault = None



    def stop(self, reason):

        self.last_command = ("STOP", 0, 0, reason)

        return self.last_command



    def drive(self, steering, speed, reason):

        steering = int(round(max(-MAX_STEERING_DEG,

                                 min(MAX_STEERING_DEG, steering))))

        self.last_command = (f"DRIVE {steering} {speed}",

                             steering, speed, reason)

        return self.last_command



    def update(self, data, now=None):

        if now is None:

            now = time.monotonic()

        if self.fault:

            return self.stop(self.fault)

        if self.turning and now - self.turn_started > MAX_TURN_TIME:

            self.fault = "Corner timeout: restart script after repositioning"

            return self.stop(self.fault)



        stamp = data.get("received_at", 0.0)

        if not data.get("connected") or now - stamp > SCAN_TIMEOUT:

            self.gap_count = self.reacquire_count = 0

            return self.stop("LiDAR disconnected or stale")



        front = data.get("front")

        left = data.get("left")

        front_left = data.get("front_left")

        for name, value in (("front", front), ("front-left", front_left)):

            if value is None or not math.isfinite(value):

                self.gap_count = self.reacquire_count = 0

                return self.stop(f"No valid {name} reading: unknown, not open")

        if front < FRONT_STOP_DISTANCE:

            return self.stop("Front too close")



        # Fresh scan confirmation must run before handling a missing side.

        if stamp == self.last_scan:

            return self.last_command

        self.last_scan = stamp



        left_valid = left is not None and math.isfinite(left)

        if left_valid and left <= LEFT_REACQUIRE_DISTANCE:

            self.last_left_wall_at = stamp

        recent_wall = (self.last_left_wall_at is not None

                       and now - self.last_left_wall_at <= RECENT_LEFT_WALL_SECONDS)



        if not left_valid:

            self.reacquire_count = 0

            clear = (front >= FRONT_LIMIT

                     and front_left >= FRONT_LEFT_OPEN_DISTANCE)

            if not clear:

                self.gap_count = 0

                return self.stop("Left missing: front/front-left clearance insufficient")

            if not self.turning:

                if not recent_wall:

                    self.gap_count = 0

                    return self.stop("Left missing: no recent inner wall; reposition beside wall")

                self.gap_count += 1

                if self.gap_count < GAP_CONFIRM_SCANS:

                    return self.stop("Confirming corner opening after left return disappeared")

                self.turning = True

                self.turn_started = now

                self.armed = False

            # Inferred departure based on recent wall and confirmed +45 opening.

            self.departed_old_wall = True

            return self.drive(-MAX_STEERING_DEG, TURN_PWM,

                              "Confirmed corner: left return lost, continue left")



        correction = math.degrees(KP * (TARGET_LEFT - left))



        if not self.turning:

            if (left <= LEFT_REACQUIRE_DISTANCE

                    and front_left <= FRONT_LEFT_WALL_DISTANCE):

                self.armed = True



            if self.armed and front_left >= FRONT_LEFT_OPEN_DISTANCE:

                self.gap_count += 1

                if self.gap_count >= GAP_CONFIRM_SCANS:

                    self.turning = True

                    self.turn_started = now

                    self.departed_old_wall = False

                    self.reacquire_count = 0

                    self.armed = False

                else:

                    return self.drive(correction, TURN_PWM,

                                      "Confirming front-left opening")

            else:

                self.gap_count = 0



        if self.turning:

            if left >= LEFT_DEPART_DISTANCE:

                self.departed_old_wall = True



            # Do not count the original wall as the next face of the island.

            next_wall = (self.departed_old_wall

                         and now - self.turn_started >= MIN_TURN_TIME

                         and left <= LEFT_REACQUIRE_DISTANCE

                         and front_left <= FRONT_LEFT_WALL_DISTANCE)

            self.reacquire_count = self.reacquire_count + 1 if next_wall else 0



            if self.reacquire_count >= REACQUIRE_SCANS:

                self.turning = False

                self.gap_count = self.reacquire_count = 0

                self.armed = True

            elif left < LEFT_TOO_CLOSE:

                return self.drive(max(0, correction), TURN_PWM,

                                  "Corner: inner wall close, correct right")

            elif next_wall:

                return self.drive(correction, TURN_PWM,

                                  "Confirming next inner wall")

            elif not self.departed_old_wall:

                return self.drive(-CORNER_ENTRY_STEERING, TURN_PWM,

                                  "Front-left opening: gentle left entry")

            else:

                return self.drive(-MAX_STEERING_DEG, TURN_PWM,

                                  "Turning left around inner corner")



        if front < FRONT_LIMIT:

            return self.stop("Front blocked without a confirmed corner")

        # Corner detection arming must not block ordinary wall following.

        # Approach the target distance while waiting to see a wall at +45 deg.

        state = ("Following left inner wall" if self.armed

                 else "Following left wall; waiting to arm corner detection")

        return self.drive(correction, FORWARD_PWM, state)





# =========================================================

# ESP32 CONTROL THREAD

# =========================================================



def wall_follow_worker():

    esp = None
    imu = None
    follower = InnerWallFollower()

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

        # Initialize IMU before allowing motion.
        imu = IMULapCounter()

        with data_lock:
            control_data.update({
                "serial_connected": True,
                "state": "Waiting for valid LiDAR data",
                "yaw": 0.0,
                "lap": 0
            })

        print("ESP32 connected")
        print("Left inner-wall follower started")
        print(f"Race target: {TARGET_LAPS} laps")

        while not stop_event.is_set():
            with data_lock:
                data = dict(latest_data)

            # IMU only counts laps. LiDAR still controls steering.
            yaw, lap_count, finished = imu.update()

            if finished:
                command = "STOP"
                steering = 0
                speed = 0
                state = (
                    f"FINISHED: {TARGET_LAPS} laps complete "
                    f"near 0 deg (yaw {yaw:.1f} deg)"
                )
            else:
                command, steering, speed, state = follower.update(data)

            message = (command + "\n").encode("ascii")

            if esp.write(message) != len(message):
                raise RuntimeError("Incomplete serial command write")

            if esp.in_waiting:
                esp.read(esp.in_waiting)

            with data_lock:
                control_data.update({
                    "serial_connected": True,
                    "command": command,
                    "state": state,
                    "steering": steering,
                    "speed": speed,
                    "yaw": yaw,
                    "lap": lap_count
                })

            front = data.get("front")
            left = data.get("left")
            front_left = data.get("front_left")

            front_text = "--" if front is None else f"{front:.2f}"
            left_text = "--" if left is None else f"{left:.2f}"
            fl_text = "--" if front_left is None else f"{front_left:.2f}"

            print(
                f"Yaw: {yaw:6.2f} deg | Lap: {lap_count}/{TARGET_LAPS} | "
                f"Front: {front_text} m | "
                f"Left: {left_text} m | Front-left: {fl_text} m | "
                f"{command} | {state}"
            )

            if finished:
                print(
                    f">>> {TARGET_LAPS} LAPS COMPLETE. "
                    f"ROBOT STOPPED AT YAW {yaw:.2f} deg <<<"
                )
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

    <title>LiDAR Inner Left Wall Follower</title>



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

    <h1>LiDAR Inner Left Wall Follower</h1>

    <p>Front 180° view | Range 3 m | Target left distance 0.30 m</p>

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

            <div>Lap: <span id="lap">0</span>/3</div>

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
        show("lap", data.control.lap);



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

</body>

</html>

"""





# =========================================================

# FLASK ROUTES

# =========================================================



@app.route("/")

def index():

    return render_template_string(HTML_PAGE)





@app.route("/scan")

def scan_endpoint():

    with data_lock:

        data = dict(latest_data)

        data["control"] = dict(control_data)



    data["fresh"] = bool(

        data["connected"]

        and time.monotonic() - data["received_at"] <= SCAN_TIMEOUT

    )



    return jsonify(data)





# =========================================================

# MAIN

# =========================================================



def main():

    lidar_thread = threading.Thread(

        target=lidar_worker,

        daemon=True

    )



    control_thread = threading.Thread(

        target=wall_follow_worker,

        daemon=True

    )



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

        print("Application stopped")





if __name__ == "__main__":

    main()



