function R = run_open_challenge(corridor, overrides)
%RUN_OPEN_CHALLENGE Simulate one Open Challenge run and plot it.
%   R = run_open_challenge() runs the default case: 1.0 m corridors on all
%   four sides and a top speed of 0.8 m/s.
%   R = run_open_challenge([s e n w], overrides) runs another layout or
%   parameter set, e.g. run_open_challenge([1 0.6 1 0.6], struct('vMax', 0.6)).
%   Saves results/open_challenge_run.png.

if nargin < 1 || isempty(corridor), corridor = [1 1 1 1]; end
if nargin < 2, overrides = struct('vMax', 0.8); end
R = simulate_open_challenge(corridor, overrides);

fprintf('Corridors [%s] m: %d laps, finished = %d, %.1f s, end reason: %s\n', ...
        num2str(corridor), R.laps, R.finished, R.t, R.reason);
fprintf('Smallest body-to-wall clearance: %.0f mm; longest corner: %.2f s (limit 2.0 s)\n', ...
        1000 * R.minClearance, max([R.turnTimes, 0]));

blue = [42 120 214] / 255; orange = [235 104 52] / 255; grey = [82 81 78] / 255;
fig = figure('Color', 'w', 'Position', [80 80 1200 520]);

subplot(2, 2, [1 3]); hold on; axis equal; box on;
for k = 1:size(R.walls, 1)
    plot(R.walls(k, [1 3]), R.walls(k, [2 4]), 'k', 'LineWidth', 2);
end
plot(R.log.x, R.log.y, 'Color', blue, 'LineWidth', 1.5);
plot(R.log.x(1), R.log.y(1), 'o', 'MarkerSize', 8, 'MarkerFaceColor', orange, 'MarkerEdgeColor', 'w');
xlim([-0.05 3.05]); ylim([-0.05 3.05]); xlabel('x (m)'); ylabel('y (m)');
title(sprintf('Path of the rear-axle centre (%d laps)', R.laps));

subplot(2, 2, 2); hold on; grid on; box off;
plot(R.log.t, R.log.left, 'Color', blue, 'LineWidth', 1.5);
yline(0.35, '--', 'target 0.35 m', 'Color', grey);
ylim([0 1.5]); ylabel('Left LiDAR distance (m)'); title('Wall following');

subplot(2, 2, 4); hold on; grid on; box off;
plot(R.log.t, R.log.wheel, 'Color', orange, 'LineWidth', 1.5);
xlabel('Time (s)'); ylabel('Wheel angle (deg, + = left)'); title('Steering');

out = fullfile(fileparts(mfilename('fullpath')), '..', 'results');
if ~exist(out, 'dir'), mkdir(out); end
print(fig, fullfile(out, 'open_challenge_run.png'), '-dpng', '-r200');
end
