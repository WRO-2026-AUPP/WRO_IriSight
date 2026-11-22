🎥 Video Demonstration
====

This section provides video demonstrations of our autonomous vehicle during the **WRO Future Engineers 2026** competition challenges. The videos showcase the robot's autonomous navigation, obstacle detection and avoidance, wall following, corner turning, and overall performance on the competition field.

### Open Challenge

The Open Challenge demonstrates the robot's autonomous navigation on the competition field without obstacles. The robot follows the course, maintains its position relative to the wall, performs corner turns, and completes the course autonomously.

### Obstacle Challenge

The Obstacle Challenge demonstrates the robot's ability to complete 3 laps around a field with red and green pillars, then park. The robot loads the pillar layout (colors and order for each side) from a map file and uses the LiDAR distance to decide when to swerve around each pillar. The IMU holds and recovers its heading, and a YOLO camera model helps it tell pillars apart from walls. After the third lap, it reverses into the parking space using the rear distance sensor.

| Challenge Type | YouTube Link |
|---|---|
| **Open Challenge** | [Watch on YouTube](https://youtu.be/8kb7vfMW33Q) |
| **Obstacle Challenge** | [Watch on YouTube](https://youtu.be/Gv9RtIQvm2Q) |
