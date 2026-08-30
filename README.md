# IriSight — WRO Future Engineers 2026

_Repository of Team IriSight competing in the CRO 2026, Future Engineers category._


<div align="center">
  <img src="./media/banner.png" width="420" alt="IriSight project banner">
  <p><em>"Break, Fix, Repeat"</em></p>
</div>

## Quick Link - Explore the project

<table width="100%">
  <tr>
    <td width="33.33%" align="center" valign="top">
      <a href="src/"><strong>💻 Code</strong></a><br>
      <sub>Jetson and ESP32 control code</sub>
    </td>
    <td width="33.33%" align="center" valign="top">
      <a href="schemes/"><strong>🔌 Schematics</strong></a><br>
      <sub>Wiring, power, and electronics</sub>
    </td>
    <td width="33.33%" align="center" valign="top">
      <a href="models/"><strong>🧩 CAD models &amp; Mechanics</strong></a><br>
      <sub>Mechanical design and printable files</sub>
    </td>
  </tr>
  <tr>
    <td width="33.33%" align="center" valign="top">
      <a href="v-photos/"><strong>🚗 Vehicle Photos</strong></a><br>
      <sub>Required views of the final robot</sub>
    </td>
    <td width="33.33%" align="center" valign="top">
      <a href="t-photos/"><strong>👥 Team Photos</strong></a><br>
      <sub>Official and informal team photos</sub>
    </td>
    <td width="33.33%" align="center" valign="top">
      <a href="video/video.md"><strong>🎥 Videos</strong></a><br>
      <sub>Autonomous challenge demonstrations</sub>
    </td>
  </tr>
</table>

## Contents

- [Repository Structure](#repository-structure)
- [Meet the team](#meet-the-team)
- [Meet the vehicle](#meet-the-vehicle)
  - [Final vehicle gallery](#final-vehicle-gallery)
  - [Key specifications](#key-specifications)
- [Performance videos](#performance-videos)
- [How IriSight works](#how-irisight-works)
  - [System architecture](#system-architecture)
- [Our engineering journey](#our-engineering-journey)
  - [Final engineering blueprints](#final-engineering-blueprints)
- [Mobility and mechanical design](#mobility-and-mechanical-design)
  - [Chassis and component mounting](#chassis-and-component-mounting)
  - [Rear drive system](#rear-drive-system)
  - [Parallel steering](#parallel-steering)
  - [Mechanical iterations](#mechanical-iterations)
- [Power and sensor architecture](#power-and-sensor-architecture)
  - [Power architecture](#power-architecture)
  - [Component and interface map](#component-and-interface-map)
    - [Jetson](#jetson)
    - [Custom ESP32 Board](#custom-esp32-board)
    - [Motor Driver](#motor-driver)
    - [Steering Servo](#steering-servo)
    - [D455](#d455)
    - [IMU](#imu)
    - [Left/Right Ultrasonic](#leftright-ultrasonic)
    - [Jetson Battery](#jetson-battery)
    - [Motor Battery](#motor-battery)
    - [Buck-Boost Converter at 11V](#buck-boost-converter-at-11v)
    - [Buck Converter at 5V](#buck-converter-at-5v)
  - [Sensor placement and calibration](#sensor-placement-and-calibration)
- [Software and challenge strategy](#software-and-challenge-strategy)
  - [Architecture and communication](#architecture-and-communication)
  - [Open Challenge](#open-challenge)
    - [Current Control Value](#current-control-value)
    - [Test Results](#test-results)
  - [AI Model and Computer Vision Pipeline](#ai-model-and-computer-vision-pipeline)
    - [Detection Model](#detection-model)
    - [Dataset and Training Workflow](#dataset-and-training-workflow)
    - [How the Model Output Is Used in Control](#how-the-model-output-is-used-in-control)
  - [Obstacle Challenge](#obstacle-challenge)
    - [Current Control Values](#current-control-values)
    - [Test Results](#test-results-1)
- [System integration, testing, and risk](#system-integration-testing-and-risk)
  - [Subsystem interaction](#subsystem-interaction)
  - [Final regression results](#final-regression-results)
  - [Key decisions](#key-decisions)
  - [Risk register](#risk-register)
- [Reproducing IriSight](#reproducing-irisight)
  - [Required files and tools](#required-files-and-tools)
  - [Mechanical assembly](#mechanical-assembly)
  - [Wiring and power-on](#wiring-and-power-on)
  - [Software Installation](#software-installation)
  - [Calibration](#calibration)
  - [Start an Autonomous Run](#start-an-autonomous-run)
  - [Pre-flight and acceptance test](#pre-flight-and-acceptance-test)
- [Current limitations and next improvements](#current-limitations-and-next-improvements)
- [MIT License](#mit-license)

## Repository Structure

This repository is organized as follows:

```
📦 WRO_IriSight
├── 📁 media                    # Images and media assets
│
├── 📁 models                   # Contains 3D design files for the robot's components
│
├── 📁 other                    # 
│
├── 📁 schemes                  # Schematics and electrical documentation
│   └── 📁 photos               # Photos related to the schematics
│
├── 📁 src                      # Main source code for the robot
│   ├── 📁 ai_model             # AI model and detection code
│   ├── 📁 esp32_code           # ESP32 control and communication code
│   ├── 📁 obs_challenge        # Obstacle challenge code
│   └── 📁 open_challenge       # Open challenge code
│
├── 📁 t-photos                 # Team photos
│
├── 📁 v-photos                 # Visual documentation
│   ├── 📁 robot_photo          # Photos of the robot
│   └── 📁 video                # Recorded robot testing videos
│              
└── 📄 README.md                # Main documentation for the project
```

## Meet the team

<div align="center">
  <img src="./t-photos/team-photo-ft-coach.png" width="700" alt="Meet the team">
  <p><em>Team Photo - From left to right: Kimchour, Panha (Coach), Nita, and Muyleang.</em></p>
</div>

<table style="border: 1px solid #ccc; width: 100%; border-collapse: collapse; margin-bottom: 20px;">
  <tr>
    <td width="30%" align="center" valign="top" style="padding: 15px; border-right: 1px solid #ccc;">
      <strong>Ponlork Ponita</strong><br><br>
      <img src="t-photos/nita.png" width="170" alt="Team member 1">
    </td>
    <td width="70%" valign="top" style="padding: 15px;">
      <strong>Role:</strong> 3D Design & Mechanical Engineer (CAD, Mounts, Blueprints)<br><br>
      <strong>Origin:</strong> Phnom Penh<br><br>
      <strong>Email:</strong> 2024352ponlork@aupp.edu.kh<br><br>
      <strong>Bio:</strong> A junior student at the American University of Phnom Penh (AUPP), she led the CAD design of the team's 3D-printed structural parts. Including the Jetson & Battery Container, the rear Motor Mount, and the RealSense Camera Mount. She carried each component through multiple print-and-test-fit iterations to achieve a LEGO-compatible, chassis-mounted final version, meticulously documenting dimensions and material properties in her blueprint sheets.
    </td>
  </tr>
</table>

<table style="border: 1px solid #ccc; width: 100%; border-collapse: collapse; margin-bottom: 20px;">
  <tr>
    <td width="70%" valign="top" style="padding: 15px; border-right: 1px solid #ccc;">
      <strong>Role:</strong> Electrical & Sensor Engineer (Wiring, Power, Sensors)<br><br>
      <strong>Origin:</strong> Phnom Penh<br><br>
      <strong>Email:</strong> 2024355taing@aupp.edu.kh<br><br>
      <strong>Bio:</strong> Serving as the hardware integration lead, she managed the vehicle's electrical infrastructure. She mapped the custom wiring schematics, engineered a stable power distribution system for the compute and motor payloads, and rigorously tested and calibrated sensor placements to guarantee accurate real-time data collection for the system's navigation stack.
    </td>
    <td width="30%" align="center" valign="top" style="padding: 15px;">
      <strong>Taing Muyleang</strong><br><br>
      <img src="t-photos/muyleang.png" width="170" alt="Team member 2">
    </td>
  </tr>
</table>

<table style="border: 1px solid #ccc; width: 100%; border-collapse: collapse; margin-bottom: 20px;">
  <tr>
    <td width="30%" align="center" valign="top" style="padding: 15px; border-right: 1px solid #ccc;">
      <strong>Luy Kimchour</strong><br><br>
      <img src="t-photos/kimchour.png" width="170" alt="Team member 3">
    </td>
    <td width="70%" valign="top" style="padding: 15px;">
      <strong>Role:</strong> Embedded & Software Engineer (ESP32, Jetson, Protocols)<br><br>
      <strong>Origin:</strong> Phnom Penh<br><br>
      <strong>Email:</strong> 2025136luy@aupp.edu.kh<br><br>
      <strong>Bio:</strong> As the team's software lead, he developed the core system architecture, writing the ESP32 firmware and the Jetson control software. Backed by an extensive commit history in the project repository, his work focused on designing robust communication protocols to bridge the microcontrollers and compute modules, ensuring seamless data flow and reliable system execution.
    </td>
  </tr>
</table>

<table style="border: 1px solid #ccc; width: 100%; border-collapse: collapse; margin-bottom: 20px;">
  <tr>
    <td width="70%" valign="top" style="padding: 15px; border-right: 1px solid #ccc;">
      <strong>Role:</strong> Team Coach<br><br>
      <strong>Origin:</strong> Battambang<br><br>
      <strong>Email:</strong> 2024033chamroeun@aupp.edu.kh<br><br>
      <strong>Bio:</strong> A senior student majored in Information and Communication Technology at the American University of Phnom Penh, with experience in 3D modeling, CAD, vehicle design, and autonomous-vehicle software. In the previous season, he helped design and optimize the robot's custom parts and mechanical structure while also contributing to software, planning, coordination, and technical documentation. As IriSight's coach for the 2026 season, he uses that hands-on competition experience to guide the team through mechanical design, software development, system integration, testing, and documentation while keeping the engineering work student-led.
    </td>
    <td width="30%" align="center" valign="top" style="padding: 15px;">
      <strong>Chamroeun Vireakpanha</strong><br><br>
      <img src="t-photos/panha(coach).png" width="170" alt="Team coach">
    </td>
  </tr>
</table>

## Meet the vehicle
<div>
  <img src="./v-photos/robot_photo/vehicle-360-view.gif" alt="Meet the vehicle" width="600">
  <p><em>Vehicle 360º view (GIF)</em></p>
</div>

### Final vehicle gallery
| <img src="./v-photos/robot_photo/top.png" alt="Top photo" width="100%"> | <img src="./v-photos/robot_photo/bottom.png" alt="Bottom photo" width="100%"> |
| :---: | :---: |
| **Top** | **Bottom** |

| <img src="./v-photos/robot_photo/left.png" alt="Left photo" width="100%"> | <img src="./v-photos/robot_photo/right.png" alt="Right photo" width="100%"> |
| :---: | :---: |
| **Left** | **Right** |

| <img src="./v-photos/robot_photo/front.png" alt="Front photo" width="100%"> | <img src="./v-photos/robot_photo/back.png" alt="Back photo" width="100%"> |
| :---: | :---: |
| **Front** | **Back** |
### Key specifications

| Specification | Final value |
| --- | --- |
| Length × width × height | 26.3 x 15.2 x 21.2 (cm) |
| Mass | 1.38 KG |
| Wheelbase / track width | 15.3 cm |
| Ground clearance | 2.8 cm |
| Drive layout | One motor, two gears, one drive shaft, two driven back wheels |
| Steering layout | LEGO-based parallel front steering system|
| Main computer | NVIDIA Jetson Orin Nano, Ubuntu 22.04 LTS |
| Microcontroller | ESP32 |
| Primary camera | Intel RealSense D455 |
| IMU | BNO055 breakout |
| Additional sensors | Two side ultrasonic sensors |
| Chassis Type | Custom chassis |
| Front wheels | LEGO SPIKE blue wheels, part `39367` |
| Back wheels | RC Car Tires Wheels |
| Batteries | Separate Jetson and motor/actuator batteries |

## Performance videos

| Challenge | Video | 
| --- | --- | 
| Open Challenge | [Watch on Youtube](https://youtu.be/7jsuhlpw6mA) | 
| Obstacle Challenge | [Watch on Youtube](https://youtu.be/TGH4JoCRx5o) | 


## How IriSight works

IriSight is a self-driving LEGO/3D-printed chassis robot built for WRO Future Engineers 2026. An NVIDIA Jetson Orin Nano runs the main perception and decision loop, reading depth/color from an Intel RealSense D455 and heading from a BNO055 IMU over I2C (plus two HC-SR04 ultrasonics wired to the ESP32 for close-range backup). The Jetson computes a steering angle and speed command and sends it over USB (power + serial) to an ESP32, which drives the rear motor through a TB6612FNG driver and turns the front wheels via a parallel-linkage steering servo. A Flask web stream exposes live diagnostics (mode, depth ROIs, steering, yaw, lap count) for tuning and debugging.

### System architecture

<div align="center">
<img src="./schemes/photos/system_architecture.jpg" width="700" alt="System architecture">
</div>

| Flow | Summary |
| --- | --- |
| Power | Two isolated LiPo domains (TCB 1100mAh 3S each). One battery powers the Jetson directly. Its 9–20V DC input accepts raw 3S voltage with no regulation needed. The second battery splits into a 5V buck converter (servo power, TB6612 logic) and an 11V buck-boost converter (TB6612 motor supply), keeping motor-driver noise off the Jetson's rail. |
| Perception | RealSense D455 feeds 640×480 depth+color at 30 FPS to the Jetson over USB for wall distance, corner detection, and (planned) obstacle/pillar recognition via YOLOv8. BNO055 reports relative yaw to the Jetson over I2C for heading and lap-checkpoint tracking. Two HC-SR04 ultrasonics report to the ESP32 for side-facing close-range backup. |
| Decision | The Jetson runs a PD controller holding a 0.60 m side-wall target from depth ROIs, switches into a fixed-steering corner state using front-distance hysteresis (0.60 m entry / 0.80 m exit), and tracks laps via 90°±10° yaw checkpoints. Obstacle Challenge logic (YOLOv8-based) is in development. |
| Actuation | The Jetson sends DRIVE <steerDeg> <speed> over USB serial to the ESP32. The ESP32 converts this into PWM/enable signals for the TB6612FNG (driving the rear DC motor) and PWM for the LD-1501MG steering servo, limited to ±35°. |
| Feedback and safety | Depth readings outside 0.15–4.00 m or below a minimum valid-pixel count are rejected to avoid noisy control input. Corner-state hysteresis prevents mode flapping near threshold. A Flask diagnostic stream on port 5000 gives live visibility into control state for tuning and fault-spotting. |

## Our engineering journey

The mechanical layout was decided first: a LEGO-based chassis so geometry and mounting points could change without machining a new frame each time, driven by a DC motor at the rear and steered at the front. We attempted a LEGO Ackermann steering linkage, but couldn't get a working mechanism built in the available time, so parallel steering was selected for the current vehicle (see [Mobility and mechanical design](#mobility-and-mechanical-design)).

<div align="center">
  <img src="./media/initialrobot.JPG" width="500" alt="First rolling prototype of IriSight">
  <p><em>The very first rolling prototype — LEGO Technic chassis, steering servo, rear DC motor, and the rough-draft V1 Jetson &amp; battery container before it had any LEGO-native mounting.</em></p>
</div>

Once the chassis, steering, and drivetrain could be assembled and rolled by hand, the rest of the build became a sequence of small, testable 3D-printed parts rather than one big redesign. Each part went through its own print → test-fit → fix cycle, documented in full (renders, STL/STEP files, and final blueprints) in [`models/`](models/). The table below is the condensed version of that history:

| Version/date | Problem or goal | Change | Evidence | Result and next decision |
| --- | --- | --- | --- | --- |
| Concept | Steering mechanism | Attempted a LEGO Ackermann steering linkage | A working Ackermann mechanism could not be completed within the available build time | Parallel steering selected for the current vehicle |
| 2026-May-26 | Rear motor had no chassis mount | Designed Motor Mount V1 — a basic block cradle for the motor body, no LEGO connection yet | Established the core motor-holding shape | Chassis-attachment method still needed to be designed |
| 2026-May-27 | Jetson + battery had no housing | Designed Jetson & Battery Container V1, then printed a small test cut (P1) of it before committing to a full print | P1 came back with a small dimensional error against the real components | Adjust V1's compartment dimensions before the next full print (see photo above — V1 mounted on the first rolling prototype) |
| 2026-May-29 | Motor mount couldn't connect to the LEGO chassis | Redesigned to Motor Mount V2 with two LEGO Technic arms on a vertical axis, inspired by the LEGO Angle Beam | Printed and test-fit on the real robot: the vertical-axis arms misaligned with the front wheel/steering assembly and affected turning | Reorient the arms — a dimensional tweak alone would not fix a directional alignment problem |
| 2026-Jun-02 | Container had no LEGO-native mount | Redesigned to Jetson & Battery Container V2 with LEGO-pin-spaced holes, inspired by the LEGO Beam Frame | Container could now pin directly onto the chassis like any other LEGO part | Round over the exposed edges and add more mounting points |
| 2026-Jun-03 | Sharp edges and a mount that needed to be more rigid | Refined to Container V3: rounded corners/edges, extra LEGO-pin holes | Cleaner prints, more mounting points | Jetson & Battery Container finalized (V3) |
| 2026-Jun-05 | Camera needed a chassis mount | Designed RealSense Camera Mount V1: three LEGO pin arms, hole direction matching the camera's facing direction | Baseline design to compare against an alternative hole orientation | Print a second orientation and compare |
| 2026-Jun-09 | Compare mounting-hole orientations | Designed Camera Mount V2 with the pin holes rotated to face each other instead | Printed and tested both V1 and V2 on the robot: V2 mounted more easily and held more robustly | RealSense Camera Mount finalized (V2) |
| 2026-Jun-12 | Motor mount still misaligned with the front wheel | Reoriented Motor Mount V3's LEGO arms away from the vertical axis used in V2 | Fixed the front-wheel misalignment found with V2; arms also became easier to mount in general | Add a place to mount the rear electronics |
| 2026-Jun-14 | Rear electronics (ESP32, buck converter) had no mount | Finalized Motor Mount V4: reworked LEGO mounting plus a flat top plate as an electronics shelf | Motor cradle, LEGO mounting, and electronics shelf all fit together on one part | Motor Mount finalized (V4) and selected for the final robot |

### Final engineering blueprints

Each finalized 3D-printed part has a full blueprint sheet (orthographic views, dimensions, material, volume, and mass), generated from the final CAD model:

<div align="center">
  <img src="./models/png/JetsonAndBattery_blueprint.png" width="700" alt="Jetson and Battery Container engineering blueprint">
  <p><em>Jetson &amp; Battery Container — final blueprint (V3)</em></p>
</div>

<div align="center">
  <img src="./models/png/MotorMount_blueprint.png" width="700" alt="Motor Mount engineering blueprint">
  <p><em>Rear Motor Mount — final blueprint (V4)</em></p>
</div>

<div align="center">
  <img src="./models/png/RealSense_blueprint.png" width="700" alt="RealSense Camera Mount engineering blueprint">
  <p><em>RealSense Camera Mount — final blueprint (V2)</em></p>
</div>

**Full detail for every version above** — renders, STL/STEP files, and final engineering blueprints with dimensions and material properties — is in [`models/README.md`](models/README.md).

## Mobility and mechanical design

### Chassis and component mounting

IriSight uses a LEGO-based chassis so the team can change the geometry and component positions without manufacturing an entirely new frame. The Jetson is protected by a custom 3D-printed enclosure designed to connect directly to LEGO parts. The final dimensions, mass, mounting coordinates, rigidity checks, and center-of-mass measurements will be added after the mechanical configuration is frozen.

<!-- ### Torque and speed summary

| Result | Final value | Evidence |
| --- | ---: | --- |
| Gear ratio | [TODO] | [TODO] |
| Calculated no-load speed | [TODO] | [TODO] |
| Measured vehicle speed | [TODO] | [TODO] |
| Required wheel torque | [TODO] | [TODO] |
| Available wheel torque | [TODO] | [TODO] |
| Torque margin | [TODO] | [TODO] |
| Stopping distance | [TODO] | [TODO] | -->

### Rear drive system

One DC motor drives two rear wheels. Its output passes through a two-gear transmission to a drive shaft connecting the rear wheels. The motor and rear-wheel models are carried over from the previous vehicle, but their exact identifiers, gear tooth counts, ratio, mounting, and measured performance remain to be documented for the 2026 build.

### Parallel steering 

<img src="./schemes/photos/steering.gif" alt="Parallel steering" width="600">

The two front LEGO SPIKE `39367` wheels are steered by a larger servo through a LEGO parallel linkage. Ackermann steering was the original plan, but a suitable LEGO mechanism could not be completed within the available development time. The parallel mechanism was selected for the current vehicle; the final documentation will compare its geometry, steering play, turning radius, build complexity, and tire scrub with the attempted Ackermann design.

### Mechanical iterations

<table width="100%">
  <tr>
    <td width="50%" align="center"><img src="./models/png/MotorMountV2.png" width="100%"><br><sub>Motor Mount V2 — vertical-axis LEGO arms (failed fit test)</sub></td>
    <td width="50%" align="center"><img src="./models/png/MotorMountV4.png" width="100%"><br><sub>Motor Mount V4 — reoriented arms + electronics shelf (final)</sub></td>
  </tr>
</table>

The full print → test-fit → fix history for every part is in the [Our engineering journey](#our-engineering-journey) table and in [`models/README.md`](models/README.md). The single largest lesson from that history came from the Motor Mount: V2's vertical-axis LEGO arms looked correct in CAD but, once test-fit on the real robot, misaligned with the front-wheel/steering assembly and affected turning. Reorienting the arms' axis in V3 (not just resizing them) is what actually fixed it — a reminder that a directional/alignment problem needs a geometry change, not a dimensional tweak. That is also why every structural part in this project is physically printed and test-fit on the robot before being called final, rather than approved from the CAD viewport alone.

**Detailed evidence:** [mechanical design, calculations, CAD, assembly, and validation](models/)

## Power and sensor architecture

### Power architecture

<img src="./schemes/photos/PCB_Schematics.png" alt="Power architecture" width="800">

The vehicle uses two battery domains: one battery supplies the Jetson and its logic/sensing system, while a second battery supplies the motor-driver side. A regulator provides the required stable voltage. Exact battery, regulator, motor-driver, connector, protection, and current ratings are still being identified and will be verified against measured typical and peak current.

| Power domain | Purpose | Voltage | Typical current |Power Consumption |
| --- | --- | ---: | ---: | --- |
| Jetson Orin Nano | Main Computing | 19V | 0.8A  | 15W | 
| Intel RealSense D4555 | Vision and depth-sensing | 5V | 0.4A | 2W |
| BMU BNO055 | Relative yaw | 3.3V | 0.02A | 0.2W |
| DC Motors | Driving the rear axle of the vehicle | 11.1V | 2.5A | 27.75W |
| LD-1501MG Servo | Control the steering mechanism | 6V | 0.3A | 1.85W |
| Miscellaneous | For miscalculation | 6V | 0.6A | 3W |

### Component and interface map
### Jetson

| Component <img width=150 height=0> | Exact model <img width=250 height=0> | Interface <img width=100 height=0> | Purpose <img width=150 height=0> | Details <img width=100 height=0> |
| :--- | :--- | :--- | :--- | :--- |
| <p align="center"><img src="./schemes/photos/jetson.png" width="130"></p> | NVIDIA Jetson Orin Nano | NaN | Main processing | [LINK](https://www.amazon.com/dp/B0BZJTQ5YP) |

### Custom ESP32 Board

| Component <img width=150 height=0> | Exact model <img width=250 height=0> | Interface <img width=100 height=0> | Purpose <img width=150 height=0> | Details <img width=100 height=0> |
| :--- | :--- | :--- | :--- | :--- |
| <p align="center"><img src="./schemes/photos/custom_esp32_board.png" width="130"></p> | ESP32 WROOM Chip | Serial | Actuator control | [LINK](https://www.amazon.com/DORHEA-ESP-WROOM-32D-Bluetooth-integrates-ESP32-D0WD/dp/B08XXH9RMT?th=1) |

### Motor Driver

| Component <img width=150 height=0> | Exact model <img width=250 height=0> | Interface <img width=100 height=0> | Purpose <img width=150 height=0> | Details <img width=100 height=0> |
| :--- | :--- | :--- | :--- | :--- |
| <p align="center"><img src="./schemes/photos/TB6612FNG.png" width="130"></p> | TB6612FNG | PWM | Drive-motor control | [LINK](https://www.amazon.com/Sparkfun-PID-14451-Motor-Driver/dp/B01MF67DX6) |

### Steering Servo

| Component <img width=150 height=0> | Exact model <img width=250 height=0> | Interface <img width=100 height=0> | Purpose <img width=150 height=0> | Details <img width=100 height=0> |
| :--- | :--- | :--- | :--- | :--- |
| <p align="center"><img src="./schemes/photos/servo.jpg" width="130"></p> | LD-1501MG Servo | PWM | Front steering | [LINK](https://www.ebay.com/itm/362680017196) |

### D455

| Component <img width=150 height=0> | Exact model <img width=250 height=0> | Interface <img width=100 height=0> | Purpose <img width=150 height=0> | Details <img width=100 height=0> |
| :--- | :--- | :--- | :--- | :--- |
| <p align="center"><img src="./schemes/photos/realsense.png" width="130"></p> | Intel RealSense D455 | USB | Depth perception | [LINK](https://www.amazon.com/dp/B08KJCRCGG?) |

### IMU

| Component <img width=150 height=0> | Exact model <img width=250 height=0> | Interface <img width=100 height=0> | Purpose <img width=150 height=0> | Details <img width=100 height=0> |
| :--- | :--- | :--- | :--- | :--- |
| <p align="center"><img src="./schemes/photos/IMU.png" width="130"></p> | BNO055 | I²C | Relative yaw | [LINK](https://bdelectronics.xyz/product/bno055-intelligent-9axis-attitude-sensor-module) |

### Left/Right Ultrasonic

| Component <img width=150 height=0> | Exact model <img width=250 height=0> | Interface <img width=100 height=0> | Purpose <img width=150 height=0> | Details <img width=100 height=0> |
| :--- | :--- | :--- | :--- | :--- |
| <p align="center"><img src="./schemes/photos/ultrasonic.jpg" width="130"></p> | Generic HC-SR04 ultrasonic sensors | GPIO | Detect Wall | [LINK](https://www.amazon.com/MTDELE-HC-SR04-Ultrasonic-Mounting-Bracket/dp/B0G6ZDBTWR?) |

### Jetson Battery

| Component <img width=150 height=0> | Exact model <img width=250 height=0> | Interface <img width=100 height=0> | Purpose <img width=150 height=0> | Details <img width=100 height=0> |
| :--- | :--- | :--- | :--- | :--- |
| <p align="center"><img src="./schemes/photos/battery.jpg" width="130"></p> | TCB 1100mAh 3S 25C battery | Power | Logic power | [LINK](https://rcdrone.top/products/tcb-2s-3s-4s-5s-6s-7s-8s-1100mah-25c-lipo-battery-with-xt60-plug-for-rc-planes-fpv-drones-helicopters-cars) |

### Motor Battery

| Component <img width=150 height=0> | Exact model <img width=250 height=0> | Interface <img width=100 height=0> | Purpose <img width=150 height=0> | Details <img width=100 height=0> |
| :--- | :--- | :--- | :--- | :--- |
| <p align="center"><img src="./schemes/photos/battery.jpg" width="130"></p> | TCB 1100mAh 3S 25C battery | Power | Actuator power | [LINK](https://rcdrone.top/products/tcb-2s-3s-4s-5s-6s-7s-8s-1100mah-25c-lipo-battery-with-xt60-plug-for-rc-planes-fpv-drones-helicopters-cars) |

### Buck-Boost Converter at 11V

| Component <img width=150 height=0> | Exact model <img width=250 height=0> | Interface <img width=100 height=0> | Purpose <img width=150 height=0> | Details <img width=100 height=0> |
| :--- | :--- | :--- | :--- | :--- |
| <p align="center"><img src="./schemes/photos/converter_11V.jpg" width="130"></p> | XL4016 300W buck-boost converter | Power | Actuator power | [LINK](https://ampere-electronics.com/product/xl4016-dc-dc-step-down-converter-module-12a-300w/) |

### Buck Converter at 5V

| Component <img width=150 height=0> | Exact model <img width=250 height=0> | Interface <img width=100 height=0> | Purpose <img width=150 height=0> | Details <img width=100 height=0> |
| :--- | :--- | :--- | :--- | :--- |
| <p align="center"><img src="./schemes/photos/converter_5V.jpg" width="130"></p> | XL4015 50W buck converter | Power | Actuator power | [LINK](https://www.jacobsparts.com/items/DCMOD-B) |


### Sensor placement and calibration

| Sensor | Placement | Selection reason | Calibration | Limitation and mitigation |
| --- | --- | --- | --- | --- |
| D455 | Mounted at the front/top of the robot, facing forward with a clear view of the track | Provides RGB and depth data for obstacle detection, pillar detection, wall following, and distance measurement | Mounted level and securely; depth readings are tested at known distances and filtered | Depth can be noisy on reflective, dark, or very close surfaces. ROI averaging/filtering and fallback control logic are used |
| BNO055 | Mounted on the upper section of the robot chassis, near the center and away from motors and power wiring as much as possible | Provides orientation and heading data for more stable navigation and turning | Calibrated according to the sensor's required motion/orientation procedure before operation | Magnetic interference and vibration can affect accuracy. The sensor is mounted securely, kept away from high-current components where possible, and readings are validated |
| Left ultrasonic | Mounted on the left side of the robot chassis, facing outward toward the left | Provides additional close-range obstacle and wall detection on the left side | Tested using objects at known distances; the detection threshold is adjusted based on test results | Can give inaccurate readings on angled, soft, or irregular surfaces. Used as an additional safety sensor with threshold-based filtering |
| Right ultrasonic | Mounted on the right side of the robot chassis, facing outward toward the right | Provides additional close-range obstacle and wall detection on the right side | Tested using objects at known distances; the detection threshold is adjusted based on test results | Can give inaccurate readings on angled, soft, or irregular surfaces. Used as an additional safety sensor with threshold-based filtering |

**Detailed evidence:** [electrical architecture, wiring, power budget, sensor placement, calibration, and safety](schemes/)

## Software and challenge strategy

### Architecture and communication

The current Open Challenge system runs on the Jetson. It reads the RealSense D455 and BNO055, calculates steering and speed, and sends `DRIVE <steerDeg> <speed>` commands to the ESP32 through a 115200-baud serial connection. The ESP32-side firmware that converts these commands into motor-driver and steering-servo signals still needs to be added to the repository.

| **Module** | **Responsibility** | **Inputs** | **Outputs** |
|---|---|---|---|
| [`src/clockWise.py`](https://github.com/WRO-2026-AUPP/WRO_IriSight/blob/main/src/clockWise.py) | Left-wall depth following with counter-clockwise yaw checkpoints | D455 depth/color, BNO055 yaw | ESP32 drive command, web diagnostics |
| [`src/counterClockWise.py`](https://github.com/WRO-2026-AUPP/WRO_IriSight/blob/main/src/counterClockWise.py) | Right-wall depth following with clockwise yaw checkpoints | D455 depth/color, BNO055 yaw | ESP32 drive command, web diagnostics |
| `src/bno055_yaw.py` | BNO055 yaw reading, calibration, and relative-heading tracking | BNO055, `bno055_calibration.json` | Relative yaw and calibration status |
| `bno055_calibration.json` | Stores the saved BNO055 calibration offsets used to restore sensor calibration | Saved calibration values | Calibration data for `bno055_yaw.py` |
| ESP32 firmware | Receives Jetson drive commands and controls the motors and steering servo | Jetson serial command | Motor-driver and servo control |

### Open Challenge

**Status:** Implemented for both directions.

Both programs align 640×480 depth and color frames at 30 FPS. They calculate the median of valid depth pixels inside front and side regions of interest, rejecting depths outside 0.15–4.00 m and requiring at least 50 valid pixels. On a straight, a PD controller maintains a 0.60 m side-wall target. If the side wall becomes unavailable, the program applies a small search steering command toward the missing wall.

When the median front distance reaches 0.60 m, the controller enters a fixed-steering corner state. It remains in that state until the front opens to 0.80 m, providing hysteresis so noise near one threshold does not repeatedly switch modes. Straight and corner speed commands are currently 200 and 180 on the program's 0–255 command scale. Steering is limited to ±35 degrees.

The BNO055 heading is zeroed at startup. Each program accepts the next expected 90-degree checkpoint within a ±10-degree zone, counts a lap only after all four checkpoints arrive in order, and stops after three laps plus a 0.5-second delay. A Flask diagnostic stream on port 5000 overlays the active mode, depth regions, steering, speed, yaw, lap count, and next checkpoint.

#### Current Control Value

| **Control value** | **Value** |
| --- | ---: |
| Side-wall target | 0.60 m |
| Front corner entry | 0.60 m |
| Front corner exit | 0.80 m |
| Proportional gain | 38.0 steering degrees/m |
| Derivative gain | 4.0 |
| Steering limit | ±35° |
| Straight/corner speed command | 200 / 180 |
| D455 stream | 640×480 at 30 FPS |
| Yaw checkpoint tolerance | ±10° |
| Required laps | 3 |

#### Test Results

| **Metric** | **Clockwise** | **Counter-clockwise** | 
| --- | ---: | ---: | 
| Trials | 30 | 30 | 
| Successful three-lap runs | 28/30| 27/30| 
| Success rate | 93.33% | 90%|
| Best/average completion time | 44s| 44s| 

### AI Model and Computer Vision Pipeline

IriSight's perception stack combines depth-based geometric sensing with a trained computer vision pipeline running on the **Jetson Orin Nano**. The **Intel RealSense D455** provides aligned depth and color frames at **640 × 480 resolution and 30 FPS**.

The perception system uses two complementary approaches:

- **Depth processing** for wall following and distance measurement
- **YOLOv8n object detection** for pillar and parking-lot recognition

#### Detection Model

- **Model:** YOLOv8n (nano) — chosen for its speed/accuracy tradeoff, allowing it to run in real time on the Jetson alongside the depth-processing pipeline.
- **Classes:** `greenbox`, `redbox`, `xparking`
- **Input size:** 640 × 640
- **Inference:** Runs on the Jetson Orin Nano using `ultralytics`, consuming the RealSense D455 color stream.
- **Depth integration:** YOLO bounding boxes are combined with the aligned depth frame to estimate the real-world distance and lateral offset to each detected object, rather than relying only on its position in the 2D image.
- **Training run:** 100 epochs, batch size 8, auto optimizer, `lr0 = 0.01`.
- **Validation performance:** Precision ≈ 0.997, recall ≈ 0.985, mAP@50 ≈ 0.995, mAP@50–95 ≈ 0.928.
- **Weights file:** `best1.pt` — the best checkpoint by validation fitness, used directly for inference on the robot.

### AI Model and Computer Vision Pipeline

IriSight's perception stack combines depth-based geometric sensing with a trained computer vision pipeline running on the **Jetson Orin Nano**. The **Intel RealSense D455** provides aligned depth and color frames at **640 × 480 resolution and 30 FPS**.

The perception system uses two complementary approaches:

- **Depth processing** for wall following and distance measurement
- **YOLOv8n object detection** for pillar and parking-lot recognition

#### Detection Model

- **Model:** YOLOv8n (nano) — chosen for its speed/accuracy tradeoff, allowing it to run in real time on the Jetson alongside the depth-processing pipeline.
- **Classes:** `greenbox`, `redbox`, `xparking`
- **Input size:** 640 × 640
- **Inference:** Runs on the Jetson Orin Nano using `ultralytics`, consuming the RealSense D455 color stream.
- **Depth integration:** YOLO bounding boxes are combined with the aligned depth frame to estimate the real-world distance and lateral offset to each detected object, rather than relying only on its position in the 2D image.
- **Training run:** 100 epochs, batch size 8, auto optimizer, `lr0 = 0.01`.
- **Validation performance:** Precision ≈ 0.997, recall ≈ 0.985, mAP@50 ≈ 0.995, mAP@50–95 ≈ 0.928.
- **Weights file:** `best1.pt` — the best checkpoint by validation fitness, used directly for inference on the robot.

#### Dataset and Training Workflow

The training dataset was developed using a **semi-supervised annotation workflow**. The full labeled dataset is browsable on [Roboflow](https://app.roboflow.com/join/eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ3b3Jrc3BhY2VJZCI6ImFaSVNnTTJTbE1jSkVhcUlBbzFTbHdnRERyTzIiLCJyb2xlIjoib3duZXIiLCJpbnZpdGVyIjoiY2hhbXJvZXVudmlyZWFrcGFuaGFAZ21haWwuY29tIiwiaWF0IjoxNzY1MTkyMDQ4fQ.lXhd1NW9soBeRpH6j9ojgWP6qgS9P-lTWvRfnBAHKKQ).

1. **Manual annotation** — Approximately 300 images were manually annotated using **CVAT** to create the initial training set.
2. **Pseudo-labeling** — The trained model was used to automatically generate labels for additional unlabeled images.
3. **Manual correction** — The predicted labels were reviewed and corrected in CVAT.
4. **Dataset expansion** — The corrected annotations were added back into the training dataset, and the process was repeated to improve the model without manually annotating every frame from scratch.

Supporting scripts are used to:

- Organize images and labels
- Split the dataset into training and validation sets
- Test trained model checkpoints
- Run inference using a webcam
- Run inference directly on the Jetson Orin Nano

This workflow allows new model checkpoints to be validated before deployment into the competition control programs.

> **Note:** [`src/ai_model/README.md`](src/ai_model/README.md) documents the model checkpoint itself (`conf=0.5`, `imgsz=640`) for standalone testing (e.g. `yolo detect predict`). The live Obstacle Challenge scripts (`obs_clockwise.py` / `obs_counterclockwise.py`) load the same `best1.pt` weights but call it with the tuned in-competition settings listed under [Current Control Values](#current-control-values) — `imgsz=416` and a colour-dependent `conf` range of 0.35–0.70 — for faster, more responsive inference on the Jetson during a run.

#### How the Model Output Is Used in Control

The vision model does **not directly control the robot**. Instead, its output is passed to the existing **PD wall-following and checkpoint state machine**.

The main uses of the model output are:

- **Pillar distance:** The depth distance to a detected pillar determines when the robot should begin avoidance and how aggressively it should react.
- **Obstacle avoidance:** Separate control gains for green and red pillars allow the robot to apply different steering responses depending on the detected obstacle. Green pillars are passed on one side, while red pillars are passed on the other.
- **Error clamping:** Steering errors are constrained to prevent excessive corrections and reduce oversteering.
- **Parking maneuver:** Once `xparking` is detected and the required laps are complete, detections of this class are used to align the robot with the parking space and trigger the final parking sequence.
- **Ultrasonic backup:** Ultrasonic sensors provide redundant close-range confirmation so a missed or late detection does not immediately result in a collision.

The system therefore separates **perception** from **control**:

```text
RealSense D455
      │
      ├── Color Frame ──► YOLOv8n
      │                     │
      │                     ├── Object Class
      │                     └── Bounding Box
      │
      └── Depth Frame ───────┐
                             │
                             ▼
                    Object Distance
                             │
                             ▼
                  PD / State Machine
                             │
                             ▼
                     Steering + Speed
                             │
                             ▼
                           ESP32
```
### Obstacle Challenge

**Status:** Implemented for both directions.

Both programs run a YOLO detector (`best1.pt`) on the color frame to detect red and green pillars. Detection uses a confidence threshold of **0.35–0.70** and an inference size of **416 px**.

Detected bounding boxes are masked out of the depth image before the front and side wall ROIs are calculated. This prevents a pillar from being mistaken for the wall behind it. Each pillar's distance is calculated using the median depth from the center region of its bounding box.

Once a pillar is closer than its configured **engage distance**, the program begins tracking it and calculates steering from the pillar's horizontal position relative to a target column. The target position changes depending on the pillar colour and which third of the frame contains the pillar. Green-pillar targets steer the robot left past the pillar, while red-pillar targets steer it right. The steering correction is scaled using a proportional gain.

If a pillar is detected while the robot is performing a corner turn, the corner turn is cancelled and pillar avoidance takes priority for a short **lock window**. This prevents the controller from rapidly switching between corner-turning and pillar avoidance.

Independent wall-clearance guards are applied after the pillar-avoidance steering is calculated. These guards can reduce or override the avoidance steering as the relevant side-wall distance becomes too small. Ultrasonic sensors provide a second clearance check.

The robot also reduces its speed while actively avoiding a pillar. The more cautious program can additionally perform a slow stop-and-reverse maneuver if the front wall or pillar becomes dangerously close before the pass is complete.

#### Current Control Values

| **Control Value** | **Current Value** |
| --- | --- |
| Detector | `best1.pt`, `imgsz=416`, confidence 0.35–0.70 |
| Pillar engage distance | 1.6–2.2 m, colour-dependent |
| Pillar pass distance | 0.25–0.70 m |
| Steering gain (pillar column error) | 35–100 deg/unit, colour-dependent |
| Target column (front zone) | Green: ~0.75–0.80 / Red: ~0.08–0.42 |
| Avoid speed command | 110–160 |
| Corner-lock window on pillar-during-turn | 0–0.5 s |
| Wall guard clearance (soft / hard) | ~0.45–0.55 m / ~0.15–0.22 m |
| Ultrasonic backup clearance (soft / hard) | 20–25 cm / 15 cm |
| D455 stream | 640×480 @ 30 FPS |

#### Test Results

| **Metric** | **Clockwise** | **Counter-Clockwise** | 
| --- | --- | --- | 
| Trials | 30 | 30 | 
| Successful runs | 25/30| 26/30| 
| Success rate | 83.33% | 86.66% | 
| Best / average completion time | 68s | 68s |

## System integration, testing, and risk

### Subsystem interaction

For the current Open Challenge, the D455 depth and BNO055 yaw enter the Jetson control loop. Depth determines wall-distance steering and corner transitions, while yaw independently advances the heading checkpoints used for lap counting. The Jetson sends the resulting steering and speed command to the ESP32, which controls the drive and steering hardware. The final system documentation will add measured sensor-to-actuator latency, ESP32 timeout behavior, power-fault behavior, and validation results.

### Final regression results

| Test | Configuration / Commit | Trials | Acceptance Target | Result | 
|---|---|---:|---|---|
| Open Challenge - clockwise | Final `clockWise.py` configuration | 3 | Complete 3 laps without navigation failure | 3 | 
| Open Challenge - Counterclockwise | Final `counterClockWise.py` configuration | 3 | Complete 3 laps without navigation failure | 3 |
| Obstacle Challenge - Clockwise| Final `obs_clockwise.py` configuration | 3 | Complete obstacle avoidance and navigation | 3 | 
| Obstacle Challenge - Counterclockwise | Final `obs_counterclockwise.py` configuration | 3 | Complete obstacle avoidance and navigation | 3 | 

### Key decisions

| Decision | Alternatives | Trade-off |
| --- | --- | --- |
| Parallel steering | Ackermann steering | Parallel steering is mechanically simpler (fewer linkage points, single servo drives both wheels at equal angle) and easier to build reliably with LEGO Technic parts, but it causes tire scrub in tight turns since both wheels follow arcs of the same radius instead of geometrically correct ones, costing a bit of grip/precision at the sharp corners on the WRO track. |
| LEGO chassis with printed Jetson enclosure | Fully custom 3D-printed chassis / fully LEGO (no custom parts) | Hybrid gives fast, tool-free iteration on the drivetrain/mounting layout (LEGO's modularity) while the printed enclosure protects and rigidly seats the Jetson and its heatsink/fan. But it adds weight and two build systems to keep aligned (LEGO tolerances vs printed tolerances), and the enclosure locks in dimensions once printed. |
| D455 depth wall following | Ultrasonic (HC-SR04 array) | One D455 gives dense depth + RGB across a wide FOV, so wall distance and pillar/obstacle color detection come from a single sensor with clean data. But it's heavier, pricier, and needs meaningfully more compute (USB3 bandwidth + depth processing) than a handful of cheap, lightweight ultrasonic sensors that update faster with near-zero CPU cost. |
| Separate power sources | Single shared 3S battery/single converter feeding both servo and motors | Running two batteries and two converters (buck for servo, buck-boost for motors) adds weight, cost, and wiring/BOM complexity versus one shared source. But it buys electrical isolation (motor noise/current draw can't disturb steering) and, crucially, the buck-boost keeps motor voltage nearly constant across the battery's discharge curve, so PWM-to-speed mapping stays predictable instead of degrading as the pack drains, which matters for consistent and repeatable driving behavior over a full run. | 

### Risk register

| Risk/failure mode | Detection | Mitigation |
| --- | --- | --- |
| Loose LEGO/printed mounting | Found through the print → test-fit → fix cycle on the real robot (e.g. Motor Mount V2's misalignment, see [Our engineering journey](#our-engineering-journey)) | Reoriented/added LEGO-pin mounting points across mount versions (Motor Mount V2→V4, Jetson & Battery Container V2→V3); rounded edges and extra pins added for a more rigid fit | 
| Missing or invalid depth | `roi_distance()` rejects depth outside 0.15–4.00 m and requires ≥50 valid pixels per ROI, returning NaN otherwise; the obstacle-challenge builds additionally track a low-pixel-count flag to distinguish "no data" from "wall too close to resolve" | A NaN/invalid side-wall reading falls back to a gentle search steer (`SEARCH_LEFT_STEER`/`SEARCH_RIGHT_STEER`) instead of driving on a corrupted value; the obstacle builds add rate-limiting (`update_smoothed_left_distance`), EMA smoothing, and hold-last-good logic (`LastGoodHold`) on top | 
| IMU drift/interference | `get_calibration_status()` reports system/gyroscope/accelerometer/magnetometer calibration state at startup; the BNO055 is mounted near chassis center, away from motors and power wiring | Saved calibration offsets are loaded from `bno055_calibration.json` at startup (`bno055_yaw.py`), and heading is zeroed relative to the robot's own start orientation each run rather than assuming a fixed absolute heading | 
| Jetson–ESP32 communication loss | The `ResilientSerial` wrapper (obstacle-challenge code) catches `SerialException`/`OSError` on every serial write and read | On any serial failure, `ResilientSerial` automatically closes and reopens the port in a retry loop until the connection succeeds again, instead of letting the control loop crash | 
| Power sag or actuator stall | Motor/actuator and Jetson/logic loads are supplied from two isolated LiPo + regulator domains (see [Power architecture](#power-architecture)), so a motor-side voltage sag under load cannot brown out the Jetson | Separate power paths prevent actuator current demand from affecting the Jetson/ESP32 logic supply. The servo uses **3S Battery (~11.1V) → XL4015 Buck → 5V → Servo**, while the motors use **3S Battery → XL4016 Buck-Boost → ~11V → TB6612 → DC Motors**. The buck-boost converter maintains approximately 11V, reducing motor-speed variation as battery voltage drops and making PWM-to-speed behavior more predictable. | 

**Detailed evidence:** [Engineering Journal, raw and processed tests, decisions, risks, and final regression results](other/)

## Reproducing IriSight

### Required files and tools

**Hardware** — the full bill of materials with exact models and purchase links is in [Component and interface map](#component-and-interface-map); the three structural 3D-printed parts (STL for printing, STEP for editing) are in [`models/`](models/).

**Software/tools:**
- NVIDIA Jetson Orin Nano flashed with JetPack (Ubuntu 22.04 LTS) and Python 3
- Intel RealSense SDK (`librealsense`) so `pyrealsense2` can talk to the D455
- Arduino IDE (or `arduino-cli`) with the `ESP32Servo` library, to flash [`src/helper_function/ultrasonic_arduino_v2.ino`](src/helper_function/ultrasonic_arduino_v2.ino) onto the ESP32
- The Python packages listed in [Software Installation](#software-installation) below
- `git`, to clone this repository

### Mechanical assembly

1. Build the LEGO Technic chassis with the parallel front-steering linkage and rear drive shaft described in [Mobility and mechanical design](#mobility-and-mechanical-design).
2. Print the three finalized structural parts from [`models/`](models/) at the settings in [`models/README.md`](models/README.md#-print-settings) (PLA, 0.2 mm layers, 20–30% infill): the **Jetson & Battery Container (V3)**, **Rear Motor Mount (V4)**, and **RealSense Camera Mount (V2)**.
3. Pin all three onto the chassis using their LEGO-compatible mounting arms — no screws or brackets are needed for the printed parts themselves.
4. Mount the rear DC motor in the Motor Mount V4 cradle, and use its flat top plate as the shelf for the ESP32 board and buck converter.
5. Mount the two HC-SR04 ultrasonics facing outward on the left/right sides, and the BNO055 near chassis center, away from the motor and high-current wiring — see [Sensor placement and calibration](#sensor-placement-and-calibration).

### Wiring and power-on

Wire every component exactly as shown in the diagram embedded in [Power architecture](#power-architecture) (full source in [`schemes/`](schemes/)), keeping the Jetson/logic battery and the motor/actuator battery on their own separate circuits — do not tie their grounds/rails together except where the diagram shows a shared reference. Double-check the TB6612FNG (IN1=D26, IN2=D25, PWM=D33), servo (D17), and ultrasonic pins (left TRIG=D13/ECHO=D39, right TRIG=D4/ECHO=D16) against the ESP32 firmware before powering on.

Recommended first power-on order: (1) connect the Jetson's battery and confirm the Jetson boots normally with the D455 and BNO055 enumerated; (2) flash and power the ESP32 on its own USB link first and confirm it prints `ESP32 ready` over serial without the motor battery connected; (3) only then connect the motor/actuator battery, and immediately confirm the wheels are off the ground or the vehicle is on a stand before sending any `DRIVE` command.

### Software Installation

The robot's control software runs on the NVIDIA Jetson Orin Nano. The required software and Python packages must be installed before running the vehicle.

#### 1. Clone the repository

```bash
git clone https://github.com/WRO-2026-AUPP/WRO_IriSight.git
```

#### 2. Navigate to the project directory

```bash
cd WRO_IriSight
```

#### 3. Install the required Python packages 

The following packages are required for numerical processing, computer vision, RealSense D455 depth sensing, YOLOv8 object detection, and Jetson-to-ESP32 serial communication.

```bash
pip install numpy
```
```bash
pip install opencv-python
```
```bash
pip install pyrealsense2
```
```bash
pip install ultralytics
```
```bash
pip install pyserial
```
#### 4. Verify the installation

```bash
python3 -c "import cv2, numpy, pyrealsense2, ultralytics, serial; print('All required packages installed successfully.')"
```

### Calibration

Before starting an autonomous run, calibrate the BNO055 and ensure that the saved calibration data is available.

#### Check the calibration file

The saved BNO055 calibration values are stored in:

```text
bno055_calibration.json
```

The calibration data is automatically loaded by ```bno055_yaw.py``` when the BNO055 is initialized.

The system also provides a calibration-status check for the system, gyroscope, accelerometer, and magnetometer.

If the calibration file is missing or invalid, the program will display a warning and continue without the saved calibration.

### Start an Autonomous Run

Select the appropriate control program based on the competition challenge and driving direction. Ensure that the Jetson Orin Nano, D455, BNO055, and ESP32 are connected and ready before starting the autonomous run.

#### 1. Open Challenge — Clockwise

```bash
python3 src/clockWise.py
```

#### 2. Open Challenge — Counter Clockwise

```bash
python3 src/counterClockWise.py
```

#### 3. Obstacle Avoidance Challenge — Clockwise

```bash
python3 src/obs_clockwise.py
```

#### 4. Obstacle Avoidance Challenge — Counter Clockwise

```bash
python3 src/obs_counterclockwise.py
```

### Pre-flight and acceptance test

Before any competition run or timed trial, the following checklist is completed in order:

**Mechanical checks**
- [x] All three 3D-printed mounts (Jetson & Battery Container V3, Motor Mount V4, RealSense Camera Mount V2) are pinned securely with no play
- [x] Front wheels turn freely through the full ±35° steering range with no binding
- [x] Rear wheels and drive shaft spin freely with the motor disconnected (no mechanical drag)
- [x] Vehicle is on a stand with wheels off the ground before any powered test

**Power and connectivity checks**
- [x] Jetson battery connected first; Jetson boots and D455 + BNO055 both enumerate
- [x] ESP32 flashed and powered independently; prints `ESP32 ready` over serial with motor battery disconnected
- [x] Motor/actuator battery connected last, only after the above two checks pass
- [x] TB6612FNG and servo wiring re-checked against pinout (IN1=D26, IN2=D25, PWM=D33, servo=D17)

**Sensor and calibration checks**
- [x] BNO055 calibration status checked (`get_calibration_status()`); saved offsets loaded from `bno055_calibration.json`
- [x] Left/right ultrasonic sensors tested against a known-distance object
- [x] D455 depth stream confirmed at 640×480 @ 30 FPS with no dropped frames

**Software checks**
- [x] Correct challenge/direction script confirmed before start (`clockWise.py`, `counterClockWise.py`, `obs_clockwise.py`, or `obs_counterclockwise.py`)
- [x] Flask diagnostic stream (port 5000) reachable and showing live mode, steering, yaw, and lap count

**Acceptance criteria**

A build is considered competition-ready only if it meets the targets already demonstrated in [Final regression results](#final-regression-results): 3/3 successful trials for both directions of the Open Challenge, and 3/3 successful trials for both directions of the Obstacle Challenge, each with no navigation failure or collision.

## Current limitations and next improvements

| Limitation | Current effect | Planned improvement | Validation target |
| --- | --- | --- | --- |
| Depth sensing limitations | The RealSense D455 does not provide complete visibility from every position and angle. Some areas of the track or obstacles may fall outside the camera's effective field of view or produce unreliable depth measurements. | Improve camera placement and ROI selection, and combine depth sensing with ultrasonic measurements where appropriate. | Maintain reliable wall and obstacle distance measurements throughout the track. |
| Vision sensitivity | YOLOv8 detection performance can be affected by lighting, shadows, reflections, and changes in object appearance. | Expand and improve the training dataset and tune the detection model and confidence thresholds. | Reliably detect the required colored obstacles and parking signal under different lighting conditions. |
| Reaction distance | Obstacles detected too close to the robot may not leave enough distance for safe avoidance. | Improve detection range and trigger avoidance earlier using depth and vision information. | Consistently avoid obstacles without collision during repeated test runs. |
| BNO055 calibration | Accurate yaw-based navigation depends on proper sensor calibration and saved calibration data. | Improve the calibration procedure and maintain reliable saved calibration values. | Achieve consistent yaw readings and checkpoint detection across repeated runs. |
| Heading error | BNO055 yaw measurements may contain small errors or drift, which can affect turn timing and checkpoint detection. | Add heading correction and further tune yaw-based turning thresholds. | Keep heading error within the required navigation tolerance. |
| Controller tuning | Wall-following and obstacle-avoidance performance depends on manually tuned steering gains, target distances, and detection thresholds. | Further tune PD control parameters and navigation thresholds through track testing. | Achieve stable wall following and repeatable obstacle avoidance across multiple runs. |
| Processing load | Running YOLO inference, depth processing, and navigation simultaneously can increase Jetson CPU/GPU usage and introduce latency. | Optimize image/depth processing and reduce unnecessary computation. | Maintain real-time control without noticeable processing delays. |
| Serial communication | The robot depends on reliable communication between the Jetson and ESP32 for timely motor and steering commands. | Improve serial communication handling and add robust error handling. | Maintain reliable command transmission throughout a complete run. |
| Ultrasonic sensing | Ultrasonic readings can be affected by obstacle angle, surface characteristics, interference, and sensor placement. | Improve sensor placement and combine ultrasonic readings with depth information. | Obtain stable distance readings for close-range obstacle detection. |
| Steering geometry | The current prototype uses parallel steering, which can reduce turning accuracy and stability during sharp turns. | Replace the current mechanism with Ackermann steering. | Achieve more accurate and stable cornering with reduced path deviation. |
| Wheel friction | Differences in friction between the wheels and track surface can cause the robot to deviate from its intended path. Changes in surface conditions can also affect turning, acceleration, and stopping performance. | Improve wheel alignment, weight distribution, and mechanical design, and tune control parameters for different track conditions. | Reduce path deviation and achieve consistent movement across repeated runs. |

## MIT License

```
Copyright (c) 2026 Team IriSight

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
