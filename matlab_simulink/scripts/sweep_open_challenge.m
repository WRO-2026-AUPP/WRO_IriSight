function results = sweep_open_challenge()
%SWEEP_OPEN_CHALLENGE Which top speeds and steering ratios complete 3 laps?
%   results = sweep_open_challenge() simulates every combination of top speed
%   and steering ratio on two layouts (all corridors 1.0 m, all 0.6 m) and
%   saves results/open_challenge_sweep.png and results/open_challenge_sweep.csv.
%   Speed and steering ratio are the two values not yet measured on the robot,
%   so this shows which real values the current program needs.

speeds = 0.2:0.1:1.0;          % m/s at PWM 255
ratios = [0.7 1.0 1.3];        % wheel deg per servo deg
layouts = {[1 1 1 1], [0.6 0.6 0.6 0.6]};
names = {'1.0 m corridors', '0.6 m corridors'};

rows = {};
fig = figure('Color', 'w', 'Position', [80 80 1100 420]);
for L = 1:numel(layouts)
    laps = zeros(numel(ratios), numel(speeds));
    for i = 1:numel(ratios)
        for j = 1:numel(speeds)
            R = simulate_open_challenge(layouts{L}, struct('vMax', speeds(j), 'steerRatio', ratios(i)));
            laps(i, j) = R.laps + R.finished;          % 4 = three laps and stopped
            rows(end + 1, :) = {names{L}, speeds(j), ratios(i), R.laps, R.finished, ...
                                char(R.fault), 1000 * R.minClearance, max([R.turnTimes, 0])}; %#ok<AGROW>
        end
    end
    subplot(1, 2, L);
    imagesc(speeds, 1:numel(ratios), laps, [0 4]);
    colormap(gca, [0.95 0.95 0.94; 0.85 0.89 0.96; 0.62 0.74 0.92; 0.36 0.56 0.88; 0.16 0.47 0.84]);
    set(gca, 'YDir', 'normal', 'YTick', 1:numel(ratios), 'YTickLabel', string(ratios));
    xlabel('Top speed at PWM 255 (m/s)'); ylabel('Steering ratio (wheel / servo)');
    title(names{L});
    for i = 1:numel(ratios)
        for j = 1:numel(speeds)
            label = sprintf('%d', min(laps(i, j), 3));
            if laps(i, j) == 4, label = '3 ✓'; end
            text(speeds(j), i, label, 'HorizontalAlignment', 'center', 'FontSize', 9);
        end
    end
end
sgtitle('Laps completed by the Open Challenge program in simulation (✓ = finished and stopped)');

results = cell2table(rows, 'VariableNames', {'layout', 'vmax_mps', 'steer_ratio', 'laps', ...
                     'finished', 'fault', 'min_clearance_mm', 'longest_corner_s'});
out = fullfile(fileparts(mfilename('fullpath')), '..', 'results');
if ~exist(out, 'dir'), mkdir(out); end
print(fig, fullfile(out, 'open_challenge_sweep.png'), '-dpng', '-r200');
writetable(results, fullfile(out, 'open_challenge_sweep.csv'));
end
