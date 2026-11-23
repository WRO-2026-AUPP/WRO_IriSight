function [P, C] = robot_parameters()
%ROBOT_PARAMETERS Physical robot values (P) and Open Challenge program values (C).
%   [P, C] = robot_parameters() returns two structs used by every script in
%   this folder. Each value names its source, so the models stay traceable:
%     CAD      - measured from the STEP files in models/
%     measured - measured on the assembled robot (models/README.md)
%     program  - copied from src/main_controller/open_challenge/open_counter_clockwise.py
%     datasheet/estimate - not yet measured on the robot; change it here when measured
%
%   Units: metres, seconds, degrees unless stated.

%% Vehicle geometry
P.wheelbase      = 0.16904;  % CAD: kingpin axis (chassis holes C1-C3) to rear-axle bore
P.kingpinTrack   = 0.10630;  % CAD: distance between the two kingpins
P.armPinTrack    = 0.09600;  % CAD: distance between the two steering-link pins
P.armOffset      = 0.01600;  % CAD: link pins sit 16.00 mm behind the kingpin axis
P.lidarAhead     = 0.2315;   % CAD: LiDAR centre ahead of the rear axle
P.bodyFront      = 0.2562;   % CAD + measured: body front ahead of the rear axle (298 mm long)
P.bodyRear       = 0.0418;   % CAD + measured: body rear behind the rear axle
P.halfWidth      = 0.0795;   % measured: 159 mm overall width / 2
P.wheelDiameter  = 0.056;    % LEGO 39367 wheel, 56 mm

%% Drive and steering
P.gearRatio      = 28 / 20;  % LEGO 32269 (20 teeth) driving the 28-tooth differential ring
P.motorRPM       = 100;      % estimate: motor listed as 12 V / 100 RPM; exact model not confirmed
P.vMax           = P.motorRPM / P.gearRatio * pi * P.wheelDiameter / 60;  % m/s at PWM 255 (= 0.21)
P.steerRatio     = 1.0;      % estimate: wheel angle per commanded servo degree, until measured
P.servoRate      = 60 / 0.17;% datasheet: MG996R no-load speed 0.17 s per 60 deg (deg/s)

%% Sensors and timing
P.lidarPeriod    = 0.025;    % datasheet: Hokuyo UST-30LX scan period (40 Hz)
P.lidarRes       = 0.25;     % datasheet: angular resolution (deg)
P.lidarFov       = 135;      % program: beams used from -135 to +135 deg
P.controlPeriod  = 0.05;     % program: CONTROL_INTERVAL

%% Open Challenge program (counter-clockwise version: follows the LEFT inner wall)
C.targetLeft         = 0.35;  % m, wall distance measured from the LiDAR
C.frontLeftOpen      = 0.80;  % m, 40-50 deg sector reading that means "corner opening"
C.frontLeftWall      = 0.75;  % m, re-arm / reacquire threshold
C.leftDepart         = 0.50;  % m, old wall no longer alongside
C.cornerEntrySteer   = 10;    % deg, gentle early left turn
C.leftReacquire      = 0.45;  % m
C.leftTooClose       = 0.25;  % m
C.recentLeftWall     = 1.5;   % s
C.gapConfirmScans    = 2;
C.reacquireScans     = 2;
C.minTurnTime        = 0.25;  % s
C.maxTurnTime        = 2.0;   % s, a longer corner is a fault: the robot stops
C.frontStop          = 0.20;  % m
C.frontLimit         = 0.75;  % m
C.kp                 = 1.0;   % rad of steering per metre of wall-distance error
C.maxSteer           = 29;    % deg
C.forwardPwm         = 255;
C.turnPwm            = 240;
C.targetLaps         = 3;
C.startZoneDeg       = 18;    % lap counts when heading returns within 18 deg of the start
C.rearmAngleDeg      = 45;    % ...after first turning more than 45 deg away
C.scanTimeout        = 0.5;   % s
end
