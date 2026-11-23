function walls = make_track(corridor)
%MAKE_TRACK Wall segments of a WRO Future Engineers track.
%   walls = make_track([south east north west]) returns an 8-by-4 matrix of
%   wall segments [x1 y1 x2 y2] in metres. The outer walls form the fixed
%   3000 x 3000 mm square (General Rules 13.1). The inner walls form a
%   rectangle whose distance to each outer side is the corridor width of that
%   side: 1.0 or 0.6 m in the Open Challenge, 1.0 m in the Obstacle Challenge.
%   Origin: bottom-left corner of the track, x to the east, y to the north.

s = corridor(1); e = corridor(2); n = corridor(3); w = corridor(4);
outerPts = [0 0; 3 0; 3 3; 0 3];
innerPts = [w s; 3-e s; 3-e 3-n; w 3-n];
walls = zeros(8, 4);
for k = 1:4
    j = mod(k, 4) + 1;
    walls(k, :)     = [outerPts(k, :), outerPts(j, :)];
    walls(k + 4, :) = [innerPts(k, :), innerPts(j, :)];
end
end
