function [cmd, S] = open_challenge_controller(S, scan, now, C)
%OPEN_CHALLENGE_CONTROLLER One control step of the Open Challenge program.
%   [cmd, S] = open_challenge_controller(S, scan, now, C) is a line-by-line
%   MATLAB copy of InnerWallFollower.update() in
%   src/main_controller/open_challenge/open_counter_clockwise.py
%   (counter-clockwise: the robot follows the LEFT inner wall).
%
%   S     controller state; create it with open_challenge_controller() (no inputs)
%   scan  struct from lidar_scan (front, front_left, left, stamp)
%   cmd   struct: drive (true = DRIVE, false = STOP), steer (deg, positive =
%         right, as sent to the ESP32), pwm (0..255) and reason (text)
%
%   The program in states (later drawn as a Stateflow chart):
%     FOLLOW   proportional wall following at C.targetLeft
%     ARMED    the inner wall is beside the robot: corners can now be detected
%     TURN     opening confirmed: gentle entry, then full left turn
%     FAULT    a corner took longer than C.maxTurnTime: stop

if nargin == 0                      % initial state
    cmd = [];
    S = struct('turning', false, 'turnStarted', 0, 'gapCount', 0, 'reacquireCount', 0, ...
        'armed', false, 'departedOldWall', false, 'lastLeftWallAt', -Inf, 'lastScan', -Inf, ...
        'lastCmd', stopCmd('Waiting for inner wall'), 'fault', '', 'turnTimes', []);
    return
end

if ~isempty(S.fault)
    cmd = stopCmd(S.fault); S.lastCmd = cmd; return
end
if S.turning && now - S.turnStarted > C.maxTurnTime
    S.fault = 'Corner timeout';
    cmd = stopCmd(S.fault); S.lastCmd = cmd; return
end
if now - scan.stamp > C.scanTimeout
    cmd = stopCmd('LiDAR data stale'); S.lastCmd = cmd; return
end
front = scan.front; left = scan.left; frontLeft = scan.front_left;
if front < C.frontStop
    cmd = stopCmd('Front too close'); S.lastCmd = cmd; return
end
if scan.stamp == S.lastScan          % no new scan since the last step: repeat the command
    cmd = S.lastCmd; return
end
S.lastScan = scan.stamp;
if left <= C.leftReacquire
    S.lastLeftWallAt = scan.stamp;
end

correction = rad2deg(C.kp * (C.targetLeft - left));   % positive = steer right, away from the wall

if ~S.turning
    if left <= C.leftReacquire && frontLeft <= C.frontLeftWall
        S.armed = true;
    end
    if S.armed && frontLeft >= C.frontLeftOpen
        S.gapCount = S.gapCount + 1;
        if S.gapCount >= C.gapConfirmScans
            S.turning = true; S.turnStarted = now; S.departedOldWall = false;
            S.reacquireCount = 0; S.armed = false;
        else
            [cmd, S] = drive(S, correction, C.turnPwm, 'Confirming front-left opening', C); return
        end
    else
        S.gapCount = 0;
    end
end

if S.turning
    if left >= C.leftDepart
        S.departedOldWall = true;
    end
    nextWall = S.departedOldWall && now - S.turnStarted >= C.minTurnTime ...
        && left <= C.leftReacquire && frontLeft <= C.frontLeftWall;
    if nextWall
        S.reacquireCount = S.reacquireCount + 1;
    else
        S.reacquireCount = 0;
    end
    if S.reacquireCount >= C.reacquireScans
        S.turning = false; S.gapCount = 0; S.reacquireCount = 0; S.armed = true;
        S.turnTimes(end + 1) = now - S.turnStarted;
    elseif left < C.leftTooClose
        [cmd, S] = drive(S, max(0, correction), C.turnPwm, 'Corner: inner wall close, correct right', C); return
    elseif nextWall
        [cmd, S] = drive(S, correction, C.turnPwm, 'Confirming next inner wall', C); return
    elseif ~S.departedOldWall
        [cmd, S] = drive(S, -C.cornerEntrySteer, C.turnPwm, 'Front-left opening: gentle left entry', C); return
    else
        [cmd, S] = drive(S, -C.maxSteer, C.turnPwm, 'Turning left around inner corner', C); return
    end
end

if front < C.frontLimit
    cmd = stopCmd('Front blocked without a confirmed corner'); S.lastCmd = cmd; return
end
[cmd, S] = drive(S, correction, C.forwardPwm, 'Following left inner wall', C);
end

function [cmd, S] = drive(S, steer, pwm, reason, C)
steer = round(max(-C.maxSteer, min(C.maxSteer, steer)));
cmd = struct('drive', true, 'steer', steer, 'pwm', pwm, 'reason', reason);
S.lastCmd = cmd;
end

function cmd = stopCmd(reason)
cmd = struct('drive', false, 'steer', 0, 'pwm', 0, 'reason', reason);
end
