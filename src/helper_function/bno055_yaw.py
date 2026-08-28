import json
import os
import time
from Adafruit_BNO055 import BNO055


class BNO055Yaw:
    def __init__(
        self,
        address=0x28,
        busnum=1,
        calibration_file="bno055_calibration.json",
        stabilization_time=2.0
    ):
        self._bno = BNO055.BNO055(
            address=address,
            busnum=busnum,
            rst=None
        )

        if not self._bno.begin():
            raise RuntimeError("BNO055 initialization failed")

        # Look for calibration file beside this module
        module_directory = os.path.dirname(os.path.abspath(__file__))

        if not os.path.isabs(calibration_file):
            calibration_file = os.path.join(
                module_directory,
                calibration_file
            )

        self._load_calibration(calibration_file)

        print("Keep the BNO055 still...")
        time.sleep(stabilization_time)

        self._zero_yaw = None

    def _load_calibration(self, calibration_file):
        try:
            with open(calibration_file, "r") as file:
                calibration_data = json.load(file)

            self._bno.set_calibration(calibration_data)
            print(f"Calibration loaded from: {calibration_file}")

        except FileNotFoundError:
            print(f"Calibration file not found: {calibration_file}")
            print("Continuing without saved calibration.")

        except (ValueError, TypeError) as error:
            print(f"Invalid calibration data: {error}")
            print("Continuing without saved calibration.")

    def read_yaw(self):
        """Return absolute yaw from 0 to 360 degrees."""
        yaw, _, _ = self._bno.read_euler()
        return yaw

    def set_zero(self):
        """Set the current direction as relative yaw zero."""
        yaw = self.read_yaw()

        if yaw is None:
            raise RuntimeError("Yaw data is unavailable")

        self._zero_yaw = yaw

    def read_relative_yaw(self):
        """Return relative yaw from 0 to 360 degrees."""
        yaw = self.read_yaw()

        if yaw is None:
            return None

        if self._zero_yaw is None:
            self._zero_yaw = yaw

        return (yaw - self._zero_yaw) % 360

    def get_calibration_status(self):
        """Return system, gyro, accelerometer and magnetometer status."""
        return self._bno.get_calibration_status()