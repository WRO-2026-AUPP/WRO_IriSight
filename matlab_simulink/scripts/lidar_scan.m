function scan = lidar_scan(walls, x, y, heading, P, stamp)
%LIDAR_SCAN Simulated Hokuyo UST-30LX scan reduced to the program's three sectors.
%   scan = lidar_scan(walls, x, y, heading, P, stamp) casts one beam every
%   P.lidarRes degrees from -P.lidarFov to +P.lidarFov around the robot's
%   heading (radians), from a LiDAR mounted P.lidarAhead in front of the rear
%   axle at (x, y). Like the robot program, it returns the MEDIAN distance of
%   three sectors (angles relative to the robot, +90 = left):
%     front       -5 ... +5 deg
%     front_left  40 ... 50 deg
%     left        80 ... 90 deg

lx = x + P.lidarAhead * cos(heading);
ly = y + P.lidarAhead * sin(heading);
rel = (-P.lidarFov:P.lidarRes:P.lidarFov)';           % beam angles relative to the robot (deg)
ang = heading + deg2rad(rel);

% Ray / segment intersection for every beam against every wall (vectorised).
dx = cos(ang);  dy = sin(ang);                         % N x 1
ax = walls(:, 1)'; ay = walls(:, 2)';                  % 1 x S
ex = walls(:, 3)' - ax; ey = walls(:, 4)' - ay;
den = dx .* ey - dy .* ex;                             % N x S
t = ((ax - lx) .* ey - (ay - ly) .* ex) ./ den;        % distance along the beam
u = ((ax - lx) .* dy - (ay - ly) .* dx) ./ den;        % position along the wall (0..1)
hit = abs(den) > 1e-12 & t > 0 & u >= 0 & u <= 1;
t(~hit) = Inf;
range = min(t, [], 2);

sector = @(a, b) median(range(rel >= a & rel <= b));
scan.front      = sector(-5, 5);
scan.front_left = sector(40, 50);
scan.left       = sector(80, 90);
scan.stamp      = stamp;
end
