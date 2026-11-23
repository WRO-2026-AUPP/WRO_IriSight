# MATLAB modelling

This folder holds our MathWorks Modeling Award work for WRO 2026 Future
Engineers. We use MATLAB to answer two questions about the International
robot that are slow or hard to answer on the real track:

1. **How good is our Ackermann steering?** The steering linkage was designed in
   CAD. We wanted to know how close it comes to ideal Ackermann steering.
2. **Under which conditions does our Open Challenge program finish three laps?**
   The corridor widths are drawn at random before each round (1.0 m or 0.6 m on
   each side), and practice time on a full field is limited. A simulation can
   try every layout and every speed.

## What's in this folder

```text
matlab_simulink/
└── scripts/
    ├── robot_parameters.m          every robot value, with its source
    ├── steering_geometry.m         Ackermann linkage analysis
    ├── make_track.m                WRO track walls from the corridor widths
    ├── lidar_scan.m                simulated LiDAR and the program's three sectors
    ├── open_challenge_controller.m MATLAB copy of the Open Challenge program
    ├── simulate_open_challenge.m   closed-loop simulation of a run
    ├── run_open_challenge.m        one run, with plots
    └── sweep_open_challenge.m      all speed and steering combinations
```

The scripts write their plots and tables to `results/`.

## Problem context and strategy

The robot has rear-wheel drive through a LEGO differential and Ackermann front
steering driven by an MG996R servo. A Jetson Orin Nano runs the Python
programs and sends steering and speed commands to an ESP32. In the Open
Challenge the robot uses:

- the **Hokuyo UST-30LX LiDAR** to keep 0.35 m from the inner wall and to
  detect corners;
- the **BNO055 IMU** heading to count laps.

The Open Challenge program is a small state machine: follow the wall → corner
opening seen → turn → next wall found → follow again, with a 2.0 s limit on
each corner and a stop after three laps.

**Why MATLAB:**
- `fzero` solves the steering linkage exactly, at every angle.
- Matrix operations cast all 1,081 LiDAR beams against the walls at once.
- One script turns the results into plots and tables.
- With Simulink and Stateflow, the program's state machine can be drawn and
  simulated as a chart, which is the next step (see below).

Every value lives in [`robot_parameters.m`](scripts/robot_parameters.m) with
its source:
- **CAD:** measured from the STEP files in [`models/`](../models/).
- **Measured:** taken on the assembled robot.
- **Program:** copied from the Python program.
- **Estimate:** not measured yet.

The two estimates are the top speed (0.21 m/s at full PWM, from the motor's
listed 100 RPM, the 28:20 gear pair and the 56 mm wheels) and the steering
ratio between servo angle and wheel angle (1.0).

## Models

### Steering linkage

The two steering knuckles and the steering link form a four-bar linkage. The
CAD dimensions:

| Value | CAD |
| --- | ---: |
| Kingpin spacing | 106.30 mm |
| Link-pin spacing | 96.00 mm |
| Link pins behind the kingpins | 16.00 mm |
| Steering-arm angle | 17.84° |
| Wheelbase (kingpin axis to rear axle) | 169.04 mm |

For each inner-wheel angle, `steering_geometry` finds the outer-wheel angle
that keeps the link at its fixed length. It then compares that with ideal
Ackermann steering, where `cot(outer) − cot(inner) = track / wheelbase`.

### Open Challenge simulation

| Part | Model |
| --- | --- |
| Track | 3 × 3 m outer walls; inner walls set by the corridor width of each side (General Rules 13.1, Open Challenge layout) |
| Vehicle | Kinematic bicycle model at the rear axle, 169.04 mm wheelbase |
| Steering | Servo turns toward the command at 353°/s (MG996R data sheet); wheel angle = steering ratio × servo angle |
| Speed | Top speed × PWM / 255 |
| LiDAR | 40 scans per second, a beam every 0.25° from −135° to +135°, 231.5 mm ahead of the rear axle (CAD); median of the front, front-left and left sectors, as in the program |
| Controller | [`open_challenge_controller.m`](scripts/open_challenge_controller.m), a line-by-line copy of the program's `InnerWallFollower`, run every 0.05 s |
| Laps | The program's IMU lap counter, fed with the simulated heading |
| Safety check | Smallest gap between the robot's 298 × 159 mm body and any wall |

## Results

### Steering geometry (MATLAB Online, 23 November 2026)

| Inner wheel | Outer wheel | Ideal inner | Error | Share of ideal Ackermann | Turn radius at rear axle |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 5° | 4.85° | 5.12° | −0.12° | 56 % | 1,962 mm |
| 10° | 9.41° | 10.48° | −0.48° | 56 % | 989 mm |
| 15° | 13.68° | 16.03° | −1.03° | 56 % | 661 mm |
| 20° | 17.66° | 21.71° | −1.71° | 58 % | 496 mm |
| 25° | 21.34° | 27.38° | −2.38° | 61 % | 395 mm |
| 29° | 24.06° | 31.83° | −2.83° | 64 % | 339 mm |
| 35° | 27.71° | 38.11° | −3.11° | 70 % | 277 mm |

**What we learned:** the textbook design rule for this kind of linkage says
the steering-arm lines should meet at the rear axle. Ours meet 165.1 mm behind
the kingpins, which is 97.7 % of the 169.0 mm wheelbase, so the rule is met
almost exactly. The full linkage model shows that this still gives only
**56–70 % of ideal Ackermann**. The inner wheel always turns more than the
outer wheel, but less than ideal. In other words, the textbook rule is only an
approximation for a linkage with short steering arms.

### Open Challenge simulation

`run_open_challenge` and `sweep_open_challenge` produce
`results/open_challenge_run.png` (the path on the track and the steering
signals) and `results/open_challenge_sweep.png`. The sweep shows which top
speeds and steering ratios finish three laps on all-1.0 m and all-0.6 m
corridors.

First results from the same model, with the estimated speed and steering
ratio, which are both still to be measured:

- **Corner timing:** the program's 2.0 s corner limit needs a top speed of
  about 0.8 m/s or more on 1.0 m corridors. At lower speeds, the 0.35 m the
  robot drives from detecting a corner opening to passing the wall end already
  uses most of the 2 s.
- **Narrow corridors:** with 0.6 m corridors, the model shows a corner can end
  early, at about 60°, when the robot cuts close to the inner wall. The
  diagonal heading then makes the front-left sector see open space and start a
  second turn.

## Test and verification

- **Steering model, checked by hand.** For small angles, the linkage gives an
  inner-minus-outer difference of `(u/h)·(1 + 2u/T)·θ²`, with `u` = 5.15 mm
  (arm inset), `h` = 16.00 mm (arm length front to back) and `T` = 96.00 mm
  (link length). Ideal Ackermann gives `(track/wheelbase)·θ²`. Their ratio is
  56.7 %, which matches the 55.7 % that MATLAB computes at 5°.
- **Controller copy.** The MATLAB controller keeps the program's names,
  thresholds and order of checks, so each simulated decision can be traced to a
  line of the Python program.
- **Validation against the robot.** We will:
  - time the robot over 2 m at full PWM to replace the 0.21 m/s estimate;
  - measure both front-wheel angles at steering commands of +29 and −29 to set
    the steering ratio;
  - compare simulated and real corner times and wall distances, using the
    values the robot's web dashboard shows during a run.
- **Use on the robot.** The robot keeps running its Python program. The model
  is where we try a change first, such as a different corner time limit or
  wall distance, before changing the program on the robot.

## How to run it

The scripts need MATLAB only (desktop or MATLAB Online); no toolboxes are used.

```matlab
cd matlab_simulink/scripts
steering_geometry                        % linkage table and plot
run_open_challenge                       % one run: 1.0 m corridors, 0.8 m/s
run_open_challenge([1 0.6 1 0.6])        % any layout: [south east north west] in metres
sweep_open_challenge                     % all speeds and steering ratios (a few minutes)
```

Change a robot value in one place, `robot_parameters.m`, or for a single run:
`run_open_challenge([1 1 1 1], struct('vMax', 0.6, 'steerRatio', 1.2))`.

## Next steps with Simulink and Stateflow

- Build the Open Challenge model in Simulink, with the vehicle and LiDAR as
  blocks.
- Draw the program as a Stateflow chart with the states Follow, Armed, Turn
  and Fault. The transitions are the conditions already written in
  `open_challenge_controller.m`.
- Model the Obstacle Challenge sequence (parking exit, pillar sections, final
  parking) as a second Stateflow chart.

## Feedback for MathWorks

- Our competition licence from last season had expired when we started. A
  reminder before a competition licence ends would have saved time.
- It was not clear whether the free MATLAB Online plan includes Simulink and
  Stateflow. A clear product list for that plan would help student teams plan
  their work.
