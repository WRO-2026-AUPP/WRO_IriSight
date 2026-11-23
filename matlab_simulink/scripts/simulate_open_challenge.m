function R = simulate_open_challenge(corridor, overrides, tEnd)
%SIMULATE_OPEN_CHALLENGE Closed-loop simulation of the Open Challenge program.
%   R = simulate_open_challenge([s e n w], overrides, tEnd) drives the robot
%   counter-clockwise on a track with the given corridor widths (metres) for
%   up to tEnd seconds (default 200) and returns a results struct.
%   overrides is an optional struct of robot_parameters() fields to change,
%   for example struct('vMax', 0.8, 'steerRatio', 1.2).
%
%   Model
%     vehicle    kinematic bicycle model at the rear axle (no wheel slip)
%     steering   servo turns toward the command at P.servoRate;
%                wheel angle = P.steerRatio * servo angle
%     speed      P.vMax * PWM / 255 (no acceleration lag)
%     LiDAR      ray casting against the walls every P.lidarPeriod (lidar_scan)
%     control    open_challenge_controller every P.controlPeriod
%     laps       the program's IMU lap counter, fed with the simulated heading
%
%   R fields: laps, finished, fault, reason, minClearance (m, smallest gap
%   between the robot body and a wall; negative = touching), turnTimes (s),
%   t (end time) and log (time histories for plotting).

if nargin < 2 || isempty(overrides), overrides = struct(); end
if nargin < 3, tEnd = 200; end
[P, C] = robot_parameters();
for f = fieldnames(overrides)'
    P.(f{1}) = overrides.(f{1});
end

walls = make_track(corridor);
dt = 0.005;
% Start in the middle of the south straight, heading east, LiDAR 0.35 m from the inner wall.
x = 1.2; y = corridor(1) - C.targetLeft; heading = 0;
delta = 0;                                   % front wheel angle (deg, positive = left)
[~, S] = open_challenge_controller();
lap = 0; lapArmed = false; finished = false;
nextScan = 0; nextControl = 0;
cmd = struct('drive', false, 'steer', 0, 'pwm', 0, 'reason', 'Start');
scan = lidar_scan(walls, x, y, heading, P, 0);
minClearance = Inf;
nLog = ceil(tEnd / (20 * dt)) + 1;
log = struct('t', nan(nLog, 1), 'x', nan(nLog, 1), 'y', nan(nLog, 1), 'heading', nan(nLog, 1), ...
             'wheel', nan(nLog, 1), 'left', nan(nLog, 1), 'lap', nan(nLog, 1));
k = 0; step = 0; t = 0;

while t < tEnd
    if t >= nextScan
        scan = lidar_scan(walls, x, y, heading, P, t);
        nextScan = nextScan + P.lidarPeriod;
    end
    if t >= nextControl
        % IMU lap counter (IMULapCounter.update in the program)
        yaw = mod(rad2deg(heading), 360);
        zeroError = min(yaw, 360 - yaw);
        if ~lapArmed
            lapArmed = zeroError >= C.rearmAngleDeg;
        elseif zeroError <= C.startZoneDeg
            lap = lap + 1; lapArmed = false;
        end
        if lap >= C.targetLaps
            finished = true;
            cmd = struct('drive', false, 'steer', 0, 'pwm', 0, 'reason', 'Three laps complete');
        else
            [cmd, S] = open_challenge_controller(S, scan, t, C);
        end
        nextControl = nextControl + P.controlPeriod;
    end

    % Actuators. The program's positive steering means "turn right" (negative wheel angle here).
    target = 0; v = 0;
    if cmd.drive
        target = -cmd.steer * P.steerRatio;
        v = P.vMax * cmd.pwm / 255;
    end
    delta = delta + max(-P.servoRate * dt, min(P.servoRate * dt, target - delta));
    x = x + v * cos(heading) * dt;
    y = y + v * sin(heading) * dt;
    heading = heading + v * tand(delta) / P.wheelbase * dt;

    if mod(step, 20) == 0                    % log and check clearance every 0.1 s
        minClearance = min(minClearance, body_clearance(walls, x, y, heading, P));
        k = k + 1;
        log.t(k) = t; log.x(k) = x; log.y(k) = y; log.heading(k) = rad2deg(heading);
        log.wheel(k) = delta; log.left(k) = scan.left; log.lap(k) = lap;
    end
    if (finished && v == 0) || ~isempty(S.fault) || (~cmd.drive && startsWith(cmd.reason, 'Front'))
        break
    end
    t = t + dt; step = step + 1;
end

for f = fieldnames(log)'
    log.(f{1}) = log.(f{1})(1:k);
end
R = struct('laps', lap, 'finished', finished, 'fault', S.fault, 'reason', cmd.reason, ...
           'minClearance', minClearance, 'turnTimes', S.turnTimes, 't', t, 'log', log, ...
           'corridor', corridor, 'walls', walls);
end

function d = body_clearance(walls, x, y, heading, P)
%BODY_CLEARANCE Smallest distance from the robot's outline to a wall (negative = overlap).
c = cos(heading); s = sin(heading);
a = linspace(-P.bodyRear, P.bodyFront, 13)';
b = linspace(-P.halfWidth, P.halfWidth, 5)';
local = [a, -P.halfWidth * ones(13, 1); a, P.halfWidth * ones(13, 1);
         -P.bodyRear * ones(5, 1), b; P.bodyFront * ones(5, 1), b];
pts = [x + local(:, 1) * c - local(:, 2) * s, y + local(:, 1) * s + local(:, 2) * c];
d = Inf;
for k = 1:size(walls, 1)
    A = walls(k, 1:2); B = walls(k, 3:4); AB = B - A;
    tt = max(0, min(1, ((pts - A) * AB') / (AB * AB')));
    d = min(d, min(vecnorm(pts - (A + tt * AB), 2, 2)));
end
if any(pts(:) <= 0 | pts(:) >= 3)
    d = -d;
end
end
