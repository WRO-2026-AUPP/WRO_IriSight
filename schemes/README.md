Electromechanical diagrams
====

This directory must contain one or several schematic diagrams in form of JPEG, PNG or PDF of the electromechanical components illustrating all the elements (electronic components and motors) used in the vehicle and how they connect to each other.

---

The electrical components include:

- Custom ESP32 development board
- Jetson nano
- Intel RealSense D455
- Geared DC motor with encoders (TODO: get the gear ratio)
- generic HC-SR04 ultrasonic sensors
- servo

# Custom ESP32 board

![custom esp32 board](./photos/custom_esp32_board.png)

The custom esp32 board features:

- TB6612 H-bridge drivers to control the motors, with pinout as follows:
  - in1: 26
  - in2: 25
  - pwm pin: 33

> [!NOTE]
> the board features 4 motor sockets for DC motors, and our pin definition is for M1

- Servo signal pin at pin 17
- Ultrasonic breakout pins at pin:
  - trigger pin at pin 13
  - echo pin at pin 39

# Jetson nano

![Jetson Nano](./photos/jetson.png)

The Jetson nano board is used for image processing and command generation to the esp32. The esp32 mainly acts as a slave that receive serial commands from the Jetson nano and executes it. The esp32 also occasionally relay the ultrasonic data back to the Jetson nano for further processing and command generation.

The Jetson nano communicates to the esp32 through a USB cable, in which the esp32 break out board has a cp2101 USB to UART converter to convert messages in the USB protocol to the UART protocol.

The Jetson nano is also connected to the Intel realsense D455 camera, and the BNO055 IMU.

# Intel realsense D455 camera

![ntel realsense D455 camera](./photos/realsense.png)

The Intel realsense camera is used because, other than its ability to act as a normal visible light camera, it can also run a proprietary stereo 3d or stereoscopy algorithm in order to estimate the distance from the camera to a particular pixel. This is useful for mapping since it is possible to recover the x, y and z coordinate of a particular pixel. Otherwise, it can simply provide additional information in the decision making process on the Jetson nano.

# Geared DC motor with encoders

The DC geared motors are used to drive the rear axel of the car. The DC motors do come with magnetic encoders, which can be used for odometry, however, we decided not to use them because wheel slip might be an issue, and because we lacked the time to do so.

# Generic HC-SR04 ultrasonic sensors

These ultrasonic sensors were used as a solution to the fact that our main decision process relies on the camera data, and because we don't have any mechanisms to retain memory of previous images, the decision process couldn't take walls to the side of the car in to account, and would occasionally run into it while turning. The HC-SR04 ultrasonic sensor are then placed to the side of the car, to provide the algorithm additonal information as to whether there are walls to the side of the car, such that the car can safely turn.

# LD-1501MG Servo

We used this servo because the generic 9g servos weren't powerful enough.


TODO: draw the rough electrical schematic or similar software
