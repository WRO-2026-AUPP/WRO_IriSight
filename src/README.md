Control software
====
This directory contains the control software used by our vehicle to participate in the WRO 2026 Future Engineer competition, developed entirely by our team. It includes all code, trained models, and dependency information required to build and run the robot's autonomous behavior for both the Open Challenge and Obstacle Avoidance rounds.

## Our Approach

Our robot navigates using the Intel RealSense D455 depth camera as its primary spatial sensor, supplemented by the BNO055 IMU for heading and, in the obstacle round, ultrasonic sensors for redundant close-range sensing.

We chose wall following as our core navigation strategy for a simple reason: with a camera as the primary spatial sensor, walls are the most consistent and reliable reference we can measure. They give a stable, low-noise signal that doesn't depend on track markings or lighting conditions the way pure visual line-following would. This choice also produces smooth, repeatable paths and keeps the robot at a safe, predictable standoff from the track boundary, even with small variations in how the track is physically built.

Because our entire navigation strategy rests on a single depth signal, most of our engineering effort went into making that signal as clean and responsive as possible — filtering noisy depth readings, using median sampling instead of raw pixel reads, and tuning a PD controller so the robot reacts quickly to error without oscillating. The Jetson handles all sensing, vision, and decision-making; it then sends simple, low-level drive commands to an ESP32 over serial, which is responsible only for actually driving the motors and steering servo.

### Open Challenge
Challenge Requirements

The Open Challenge requires the robot to autonomously complete 3 laps around the track, staying within track boundaries and avoiding contact with the walls. There are no pillars or fixed obstacles in this round — the only challenge is smooth, accurate navigation and reliable lap counting.

Since the direction of travel (clockwise or counter-clockwise) is only revealed just before the run starts, our robot needs to be able to run in either direction. We solved this by building two interchangeable driving programs:
