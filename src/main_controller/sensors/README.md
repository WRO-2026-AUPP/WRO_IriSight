# Sensor code

Each program contains its own copy of the sensor code; there are no separate
sensor modules yet. This table shows where each sensor is handled, so it can be
found in any of the four programs.

| Sensor | Code (function or class) | Library | Connection and settings |
| --- | --- | --- | --- |
| Hokuyo UST-30LX LiDAR | `lidar_worker()`, `get_median_distance()` | `hokuyolx` | Ethernet, `LIDAR_IP = 192.168.0.10`, `LIDAR_PORT = 10940`. Scan used from −135° to +135°; +90° = left, 0° = front, −90° = right. Each distance is the median of a small angle sector. |
| BNO055 IMU | `IMULapCounter` (open programs), `IMUHeading` (obstacle programs) | `smbus2` | I2C bus 7, address `0x28`, NDOF fusion mode; reads the Euler heading registers. |
| USB camera (1 MP) | `camera_worker()` (obstacle programs) | `opencv-python`, `ultralytics` | Video device `CAMERA_INDEX = 0`, frame width 640, YOLOv8n model `traffic_sign_detector.pt`, confidence 0.65. |
| VL53L0X rear distance sensor | `final_parking()` (obstacle programs) | `adafruit-circuitpython-vl53l0x`, `adafruit-extended-bus` | I2C bus 1, address `0x29`, facing backward. Used only during final parking. |

## Calibration status

| Sensor | Status |
| --- | --- |
| BNO055 | The heading is set to zero at the start of each run. No saved calibration profile is loaded by the programs. |
| Camera | `CAMERA_FOV_DEG = 70.0` and `CAMERA_YAW_OFFSET_DEG = 0.0` are default values, **not calibrated**. They should be calibrated with a target at a known position. |
| LiDAR | Used as delivered; no calibration in the code. Distances are measured from the LiDAR, not from the side of the robot. |
| VL53L0X | Used as delivered; no calibration in the code. |

## Previous version

The National BNO055 helper and its calibration file are archived in
[`other/legacy_national/src/helper_function/`](../../../other/legacy_national/src/helper_function/).
