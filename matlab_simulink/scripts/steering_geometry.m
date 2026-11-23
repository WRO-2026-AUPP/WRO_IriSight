function T = steering_geometry()
%STEERING_GEOMETRY Inner/outer front-wheel angles of the Ackermann steering linkage.
%   T = steering_geometry() solves the four-bar steering linkage built from
%   the CAD dimensions (two knuckle arms + one steering link), compares the
%   result with ideal Ackermann steering for the robot's wheelbase, and saves
%   results/steering_geometry.png and results/steering_geometry.csv.
%
%   Linkage (top view, x = left, y = backward, origin on the kingpin axis):
%     left kingpin  (+K, 0)    left link pin  (+A, OFF)
%     right kingpin (-K, 0)    right link pin (-A, OFF)
%   Turning the left knuckle by an angle moves its pin; the right knuckle angle
%   is the one that keeps the two pins exactly one link length apart.

[P, ~] = robot_parameters();
K   = P.kingpinTrack / 2;          % 53.15 mm
A   = P.armPinTrack / 2;           % 48.00 mm
OFF = P.armOffset;                 % 16.00 mm
L   = P.wheelbase;                 % 169.04 mm
linkLength = P.armPinTrack;        % the link joins the two pins

armLeft  = [A - K; OFF];           % kingpin -> pin, left knuckle (points inward and back)
armRight = [K - A; OFF];
rot = @(deg) [cosd(deg), -sind(deg); sind(deg), cosd(deg)];
pinLeft  = @(deg) [ K; 0] + rot(deg) * armLeft;
pinRight = @(deg) [-K; 0] + rot(deg) * armRight;

armAngle  = atand((K - A) / OFF);              % 17.84 deg
meetPoint = OFF * K / (K - A);                 % where the two arm lines cross, behind the kingpins
fprintf(['Arm angle %.2f deg. Textbook rule: the arm lines should meet at the rear axle;\n' ...
         'they meet %.1f mm behind the kingpins, %.1f %% of the %.1f mm wheelbase.\n' ...
         'The full linkage below shows how much of ideal Ackermann that really gives (ackermann_pct).\n'], ...
        armAngle, meetPoint * 1000, 100 * meetPoint / L, L * 1000);

% Turning left: the left wheel is the inner wheel.
inner = (1:35)';
outer = zeros(size(inner));
for i = 1:numel(inner)
    gap = @(d) norm(pinLeft(inner(i)) - pinRight(d)) - linkLength;
    outer(i) = fzero(gap, 0.9 * inner(i));
end
idealInner = acotd(cotd(outer) - P.kingpinTrack / L);   % cot(outer) - cot(inner) = track / wheelbase
errorDeg   = inner - idealInner;
ackermannPct = 100 * (inner - outer) ./ (idealInner - outer);
turnRadius = L ./ tand((inner + outer) / 2);            % at the rear-axle centre, bicycle approximation

T = table(inner, outer, idealInner, errorDeg, ackermannPct, turnRadius * 1000, ...
    'VariableNames', {'inner_deg', 'outer_deg', 'ideal_inner_deg', 'error_deg', 'ackermann_pct', 'turn_radius_mm'});
disp(T([5 10 15 20 25 29 35], :));

% ---- plots
blue = [42 120 214] / 255; orange = [235 104 52] / 255; grey = [82 81 78] / 255;
fig = figure('Color', 'w', 'Position', [100 100 1100 420]);
subplot(1, 2, 1); hold on; grid on; box off;
plot(outer, inner, 'Color', blue, 'LineWidth', 2);
plot(outer, idealInner, '--', 'Color', orange, 'LineWidth', 2);
plot(outer, outer, ':', 'Color', grey, 'LineWidth', 1.5);
xlabel('Outer wheel angle (deg)'); ylabel('Inner wheel angle (deg)');
title('Inner vs outer wheel angle');
legend({'Robot linkage (CAD)', 'Ideal Ackermann', 'Parallel steering'}, 'Location', 'northwest', 'Box', 'off');
subplot(1, 2, 2); hold on; grid on; box off;
plot(inner, turnRadius * 1000, 'Color', blue, 'LineWidth', 2);
xline(29, ':', 'Open Challenge limit 29 deg', 'Color', grey, 'LabelVerticalAlignment', 'top');
xlabel('Inner wheel angle (deg)'); ylabel('Turn radius at rear axle (mm)');
title('Turn radius');

out = fullfile(fileparts(mfilename('fullpath')), '..', 'results');
if ~exist(out, 'dir'), mkdir(out); end
print(fig, fullfile(out, 'steering_geometry.png'), '-dpng', '-r200');
writetable(T, fullfile(out, 'steering_geometry.csv'));
fprintf('Saved steering_geometry.png and steering_geometry.csv in %s\n', out);
end
