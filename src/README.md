Control software
====

This directory must contain code for control software which is used by the vehicle to participate in the competition and which was developed by the participants.

All artifacts required to resolve dependencies and build the project must be included in this directory as well.

// Our Approach

Our robot navigates using the Intel RealSense D455 depth camera as its primary spatial sensor, supplemented by the BNO055 IMU for heading and, in the obstacle round, ultrasonic sensors for redundant close-range sensing.

We chose wall following as our core navigation strategy for a simple reason: with a camera as the primary spatial sensor, walls are the most consistent and reliable reference we can measure. They give a stable, low-noise signal that doesn't depend on track markings or lighting conditions the way pure visual line-following would. This choice also produces smooth, repeatable paths and keeps the robot at a safe, predictable standoff from the track boundary, even with small variations in how the track is physically built.

Because our entire navigation strategy rests on a single depth signal, most of our engineering effort went into making that signal as clean and responsive as possible — filtering noisy depth readings, using median sampling instead of raw pixel reads, and tuning a PD controller so the robot reacts quickly to error without oscillating. The Jetson handles all sensing, vision, and decision-making; it then sends simple, low-level drive commands to an ESP32 over serial, which is responsible only for actually driving the motors and steering servo.
