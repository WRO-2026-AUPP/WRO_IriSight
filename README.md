# IriSight — WRO Future Engineers 2026

*Repository of Team IriSight competing in the WRO 2026 International Final, Future Engineers category.*

<div align="center">

<!-- Add International Round project banner here -->

<img src="./media/banner.png" width="420" alt="IriSight project banner">

<p><em>"[Add team slogan here]"</em></p>
</div>

## Quick Links — Explore the Project

| Code | Schematics | CAD Models & Mechanics |
|---|---|---|
| [💻 Code](src/) | [🔌 Schematics](schemes/) | [🧩 CAD Models](models/) |
| [Add description] | [Add description] | [Add description] |

| Vehicle Photos | Team Photos | Videos |
|---|---|---|
| [🚗 Vehicle Photos](v-photos/) | [👥 Team Photos](t-photos/) | [🎥 Videos](video/) |
| [Add description] | [Add description] | [Add description] |

## Contents

- [Repository Structure](#repository-structure)
- [Meet the Team](#meet-the-team)
- [Meet the Vehicle](#meet-the-vehicle)
  - [Final Vehicle Gallery](#final-vehicle-gallery)
  - [Key Specifications](#key-specifications)
- [Performance Videos](#performance-videos)
- [How IriSight Works](#how-irisight-works)
  - [System Architecture](#system-architecture)
- [Our Engineering Journey](#our-engineering-journey)
  - [Engineering Design and Iterations](#engineering-design-and-iterations)
  - [Final Engineering Blueprints](#final-engineering-blueprints)
- [Mobility and Mechanical Design](#mobility-and-mechanical-design)
  - [Chassis and Component Mounting](#chassis-and-component-mounting)
  - [Drive System](#drive-system)
  - [Steering System](#steering-system)
  - [Mechanical Iterations](#mechanical-iterations)
- [Power and Sensor Architecture](#power-and-sensor-architecture)
  - [Power Architecture](#power-architecture)
  - [Component and Interface Map](#component-and-interface-map)
  - [Sensor Placement and Calibration](#sensor-placement-and-calibration)
- [Software and Challenge Strategy](#software-and-challenge-strategy)
  - [Software Architecture and Communication](#software-architecture-and-communication)
  - [AI Model and Computer Vision Pipeline](#ai-model-and-computer-vision-pipeline)
  - [Navigation and Control Strategy](#navigation-and-control-strategy)
  - [Challenge Implementation](#challenge-implementation)
  - [Test Results](#test-results)
- [System Integration, Testing, and Risk](#system-integration-testing-and-risk)
  - [Subsystem Interaction](#subsystem-interaction)
  - [Final Regression Results](#final-regression-results)
  - [Key Engineering Decisions](#key-engineering-decisions)
  - [Risk Register](#risk-register)
- [Reproducing IriSight](#reproducing-irisight)
  - [Required Files and Tools](#required-files-and-tools)
  - [Mechanical Assembly](#mechanical-assembly)
  - [Wiring and Power-On](#wiring-and-power-on)
  - [Software Installation](#software-installation)
  - [Calibration](#calibration)
  - [Starting an Autonomous Run](#starting-an-autonomous-run)
  - [Pre-flight and Acceptance Test](#pre-flight-and-acceptance-test)
- [Current Limitations and Future Improvements](#current-limitations-and-future-improvements)
- [National Round Archive](#national-round-archive)
- [License](#license)

---

## Repository Structure

This repository is organized as follows:

```text
IriSight/
├── media/                  # Project banner and media
├── models/                 # International Round CAD models
├── schemes/                # Electrical diagrams and schematics
├── src/
│   ├── ai_model/           # AI and computer vision
│   ├── main_controller/    # Main robot control software
│   └── microcontroller/    # Microcontroller firmware
├── t-photos/               # Team photos
├── v-photos/               # Vehicle photos
├── video/                  # Competition and testing videos
├── other/
│   └── legacy_national/    # Complete National Round archive
├── CHANGELOG.md
├── LICENSE.txt
└── README.md
```

## Meet the Team

[Fill in team introduction and member information.]

### Team Photo

<!-- Add team photo here -->

![Team Photo](./t-photos/team-photo.png)

### Team Members

#### [Team Member 1 Name]

- **Role:** [Fill in role]
- **Responsibilities:** [Describe responsibilities]
- **Introduction:** [Write short biography]
- **Photo:** [Add member photo]

#### [Team Member 2 Name]

- **Role:** [Fill in role]
- **Responsibilities:** [Describe responsibilities]
- **Introduction:** [Write short biography]
- **Photo:** [Add member photo]

#### Coach

- **Name:** [Fill in coach name]
- **Role:** Team Coach
- **Responsibilities:** [Describe coaching responsibilities]
- **Introduction:** [Write short biography]
- **Photo:** [Add coach photo]

---

## Meet the Vehicle

[Describe the International Round robot and its main features.]

<!-- Add vehicle overview image or GIF here -->

![Vehicle Overview](./v-photos/vehicle-overview.png)

### Final Vehicle Gallery

| View | Image |
|---|---|
| Top | [Add top-view photo] |
| Bottom | [Add bottom-view photo] |
| Left | [Add left-view photo] |
| Right | [Add right-view photo] |
| Front | [Add front-view photo] |
| Back | [Add back-view photo] |

### Key Specifications

| Specification | Final Value |
|---|---|
| Length × Width × Height | [Fill in dimensions] |
| Mass | [Fill in mass] |
| Wheelbase | [Fill in value] |
| Ground Clearance | [Fill in value] |
| Drive Layout | [Fill in configuration] |
| Steering Layout | [Fill in configuration] |
| Main Computer | [Fill in model] |
| Microcontroller | [Fill in model] |
| Camera | [Fill in model] |
| IMU | [Fill in model] |
| Additional Sensors | [Fill in sensors] |
| Battery Configuration | [Fill in configuration] |

## Performance Videos

| Challenge / Test | Video |
|---|---|
| Open Challenge | [Watch on YouTube](https://youtu.be/8kb7vfMW33Q) |
| Obstacle Avoidance Challenge | [Watch on YouTube](https://youtu.be/Gv9RtIQvm2Q) |

---

## How IriSight Works

[Explain how the robot operates, including perception, decision-making, navigation, and actuation.]

### System Architecture

<!-- Add system architecture diagram here -->

![System Architecture](./schemes/system-architecture.png)

| Subsystem | Description |
|---|---|
| Power | [Explain the power distribution system] |
| Perception | [Explain cameras and sensor inputs] |
| Processing | [Explain the main computing system] |
| Decision | [Explain navigation and decision-making] |
| Actuation | [Explain motor and steering control] |
| Communication | [Explain communication between components] |
| Safety | [Explain safety and failure-handling mechanisms] |

---

## Our Engineering Journey

[Describe the development process for the International Round, including the problems encountered and solutions implemented.]

### Engineering Design and Iterations

| Version / Date | Problem or Goal | Design Change | Testing / Evidence | Result |
|---|---|---|---|---|
| [Version 1] | [Describe problem] | [Describe change] | [Add evidence] | [Describe result] |
| [Version 2] | [Describe problem] | [Describe change] | [Add evidence] | [Describe result] |
| [Version 3] | [Describe problem] | [Describe change] | [Add evidence] | [Describe result] |

### Final Engineering Blueprints

[Add descriptions of the finalized mechanical components and their engineering specifications.]

<!-- Add engineering blueprint images here -->

![Blueprint 1](./models/blueprint-1.png)

![Blueprint 2](./models/blueprint-2.png)

**Detailed documentation:** [Add link to models documentation.]

---

## Mobility and Mechanical Design

[Explain the overall mechanical design and how the robot moves.]

### Chassis and Component Mounting

[Describe the chassis structure, mounting system, materials, and component positioning.]

### Drive System

[Explain the drivetrain, motors, transmission, wheels, and relevant calculations.]

### Steering System

[Explain the steering mechanism, servo configuration, steering angles, and turning performance.]

### Mechanical Iterations

| Version | Design / Modification | Reason for Change | Testing Results |
|---|---|---|---|
| [Version 1] | [Fill in details] | [Fill in reason] | [Fill in results] |
| [Version 2] | [Fill in details] | [Fill in reason] | [Fill in results] |

**Detailed evidence:** [Add CAD files, calculations, renders, and assembly documentation.]

---

## Power and Sensor Architecture

### Power Architecture

[Describe the battery configuration, voltage regulation, power distribution, and protection mechanisms.]

<!-- Add power architecture diagram here -->

![Power Architecture](./schemes/power-architecture.png)

| Power Domain | Component | Voltage | Current | Power Consumption |
|---|---|---|---|---|
| [Domain 1] | [Component] | [Value] | [Value] | [Value] |
| [Domain 2] | [Component] | [Value] | [Value] | [Value] |

### Component and Interface Map

Document every major electronic component used in the robot.

| Component | Exact Model | Interface | Purpose | Documentation / Reference |
|---|---|---|---|---|
| Main Computer | [Model] | [Interface] | [Purpose] | [Link] |
| Microcontroller | [Model] | [Interface] | [Purpose] | [Link] |
| Motor Driver | [Model] | [Interface] | [Purpose] | [Link] |
| Steering Servo | [Model] | [Interface] | [Purpose] | [Link] |
| Camera | [Model] | [Interface] | [Purpose] | [Link] |
| IMU | [Model] | [Interface] | [Purpose] | [Link] |
| Additional Sensors | [Model] | [Interface] | [Purpose] | [Link] |
| Battery | [Model] | [Interface] | [Purpose] | [Link] |
| Voltage Converter | [Model] | [Interface] | [Purpose] | [Link] |

### Sensor Placement and Calibration

| Sensor | Placement | Purpose | Calibration Method | Limitations |
|---|---|---|---|---|
| [Sensor 1] | [Location] | [Purpose] | [Method] | [Limitations] |
| [Sensor 2] | [Location] | [Purpose] | [Method] | [Limitations] |

**Detailed evidence:** [Add wiring diagrams, component documentation, power calculations, and calibration results.]

---

## Software and Challenge Strategy

### Software Architecture and Communication

[Describe the software architecture, programming languages, libraries, communication protocols, and responsibilities of each software module.]

| Module | Responsibility | Inputs | Outputs |
|---|---|---|---|
| AI Model | [Fill in] | [Fill in] | [Fill in] |
| Main Controller | [Fill in] | [Fill in] | [Fill in] |
| Microcontroller Firmware | [Fill in] | [Fill in] | [Fill in] |

### AI Model and Computer Vision Pipeline

[Describe the computer vision system and how it contributes to autonomous navigation.]

#### Detection Model

- **Model:** [Fill in model]
- **Framework:** [Fill in framework]
- **Detection Classes:** [Fill in classes]
- **Input Resolution:** [Fill in resolution]
- **Inference Platform:** [Fill in hardware]
- **Training Configuration:** [Fill in configuration]
- **Validation Metrics:** [Fill in results]
- **Model Weights:** [Add model file location]

<!-- Add sample detection images here -->

![Detection Example](./src/ai_model/detection-example.png)

#### Dataset and Training Workflow

[Describe the dataset source, collection process, annotation, preprocessing, training, validation, and testing.]

1. **Dataset Collection:** [Fill in details]
2. **Annotation:** [Fill in details]
3. **Preprocessing:** [Fill in details]
4. **Model Training:** [Fill in details]
5. **Validation:** [Fill in details]
6. **Deployment:** [Fill in details]

#### How the Model Output Is Used in Control

[Explain how model predictions are converted into useful navigation or control decisions.]

```text
[Sensor Input]
      |
      v
[Perception / AI Model]
      |
      v
[Object or Environment Information]
      |
      v
[Decision-Making / Controller]
      |
      v
[Motor and Steering Commands]
      |
      v
[Robot Movement]
```

### Navigation and Control Strategy

[Explain the navigation algorithm, control method, path planning, obstacle handling, and decision logic.]

### Challenge Implementation

#### Challenge 1: [Fill in challenge name]

- **Status:** [Not Started / In Progress / Completed]
- **Objective:** [Describe objective]
- **Approach:** [Describe strategy]
- **Control Parameters:** [Add values]
- **Implementation:** [Link relevant source files]

#### Challenge 2: [Fill in challenge name]

- **Status:** [Not Started / In Progress / Completed]
- **Objective:** [Describe objective]
- **Approach:** [Describe strategy]
- **Control Parameters:** [Add values]
- **Implementation:** [Link relevant source files]

### Test Results

| Metric | Challenge 1 | Challenge 2 |
|---|---|---|
| Number of Trials | [Value] | [Value] |
| Successful Runs | [Value] | [Value] |
| Success Rate | [Value] | [Value] |
| Best Completion Time | [Value] | [Value] |
| Average Completion Time | [Value] | [Value] |

---

## System Integration, Testing, and Risk

### Subsystem Interaction

[Explain how the mechanical, electrical, sensing, computing, and software subsystems work together.]

### Final Regression Results

| Test | Configuration | Trials | Acceptance Criteria | Result |
|---|---|---:|---|---|
| [Test 1] | [Configuration] | [Number] | [Criteria] | [Result] |
| [Test 2] | [Configuration] | [Number] | [Criteria] | [Result] |

### Key Engineering Decisions

| Decision | Alternatives Considered | Reason for Selection | Trade-offs |
|---|---|---|---|
| [Decision 1] | [Alternatives] | [Reason] | [Trade-offs] |
| [Decision 2] | [Alternatives] | [Reason] | [Trade-offs] |

### Risk Register

| Risk / Failure Mode | Detection Method | Mitigation |
|---|---|---|
| [Risk 1] | [How it is detected] | [How it is mitigated] |
| [Risk 2] | [How it is detected] | [How it is mitigated] |
| [Risk 3] | [How it is detected] | [How it is mitigated] |

**Detailed evidence:** [Add engineering journal, testing records, risk analysis, and validation documentation.]

---

## Reproducing IriSight

### Required Files and Tools

**Hardware:**

- [List required hardware]
- [List electronic components]
- [List mechanical components]

**Software and Tools:**

- [Operating system]
- [Development environment]
- [Required libraries and frameworks]
- [Additional software]

### Mechanical Assembly

[Provide step-by-step instructions for assembling the robot.]

1. [Assembly step 1]
2. [Assembly step 2]
3. [Assembly step 3]
4. [Assembly step 4]

### Wiring and Power-On

[Explain the wiring process, pin configurations, power connections, and safe startup sequence.]

### Software Installation

#### 1. Clone the Repository

```bash
git clone https://github.com/WRO-2026-AUPP/WRO_IriSight.git
```

#### 2. Navigate to the Project Directory

```bash
cd WRO_IriSight
```

#### 3. Install Dependencies

```bash
# Add installation commands here
```

#### 4. Verify Installation

```bash
# Add verification commands here
```

### Calibration

[Explain sensor calibration, camera configuration, motor calibration, and other required setup procedures.]

### Starting an Autonomous Run

[Explain how to launch the robot's software and start an autonomous run.]

```bash
# Add execution commands here
```

### Pre-flight and Acceptance Test

**Mechanical Checks**

- [ ] [Mechanical inspection]
- [ ] [Wheel and steering inspection]
- [ ] [Mounting inspection]

**Power and Connectivity Checks**

- [ ] [Battery inspection]
- [ ] [Power distribution inspection]
- [ ] [Communication check]

**Sensor and Calibration Checks**

- [ ] [Sensor inspection]
- [ ] [Calibration verification]
- [ ] [Data validation]

**Software Checks**

- [ ] [Software startup check]
- [ ] [Controller check]
- [ ] [Emergency stop check]

**Acceptance Criteria**

[Define the requirements that must be satisfied before the robot is considered competition-ready.]

---

## Current Limitations and Future Improvements

| Limitation | Current Effect | Planned Improvement | Validation Target |
|---|---|---|---|
| [Limitation 1] | [Effect] | [Improvement] | [Target] |
| [Limitation 2] | [Effect] | [Improvement] | [Target] |
| [Limitation 3] | [Effect] | [Improvement] | [Target] |

## National Round Archive

The complete National Round project has been preserved in:

`other/legacy_national/`

This archive contains the original source code, AI model, CAD designs, electrical diagrams, photographs, and supporting documentation.

It is retained as a reference for the International Round development.

## License

[Specify the project license and include the full license text here.]

---

**Team IriSight — AUPP, Cambodia**

*World Robot Olympiad 2026 — International Final*
