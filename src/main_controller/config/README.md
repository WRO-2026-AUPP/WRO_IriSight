# Configuration

## Program settings

Each program keeps its settings as constants at the top of its own file. These
include:

- hardware settings: `LIDAR_IP`, `ESP32_PORT`, `IMU_BUS`, `CAMERA_INDEX` and
  `WEB_PORT`;
- control settings: target wall distances, gains, speeds and time limits.

They have not yet been moved into a shared configuration file, so a change must
be made in each program that uses the setting.

## Pillar map files

The obstacle programs read a pillar map, given on the command line, that lists
the colour and order of the pillars:

| File | Used with | Contents |
| --- | --- | --- |
| [`wro_pillar_0_270_180_90.json`](wro_pillar_0_270_180_90.json) | `obstacle_counter_clockwise.py` | Example layout for testing |
| [`pillar_clockwise.json`](pillar_clockwise.json) | `obstacle_clockwise.py` | Example layout for testing |

Both example files are currently written by hand to match a test layout. The
planned competition workflow will create the same schema automatically while
the robot remains stationary in the parking lot:

1. move the camera servo through three calibrated pan positions;
2. run YOLO on the three views;
3. combine repeated detections and assign each pillar to a section/order;
4. validate and save the map once; and
5. freeze that JSON file while the driving controller runs.

The scan/generator stage is not yet present in the repository; see
[`../obstacle_challenge/`](../obstacle_challenge/). The exact servo angles will
be recorded after physical calibration rather than guessed in documentation.

### Format

```json
{
  "image_width": 804,
  "image_height": 815,
  "coordinate_system": "image pixels, origin top-left",
  "pillars": [
    {"x": 526, "y": 130, "color": "red",   "section": "top"},
    {"x": 275, "y": 130, "color": "red",   "section": "top"}
  ]
}
```

| Field | Meaning |
| --- | --- |
| `image_width`, `image_height` | Size of the top-view field image the positions refer to |
| `coordinate_system` | Must be exactly `"image pixels, origin top-left"` |
| `pillars[].section` | `top`, `left`, `bottom` or `right`; exactly two pillars per section |
| `pillars[].color` | `red` or `green` |
| `pillars[].x`, `pillars[].y` | Position in the image, used only to sort the two pillars of a section into driving order |

Sorting order:

- counter-clockwise: top right→left, left top→bottom, bottom left→right, right bottom→top;
- clockwise: top left→right, right top→bottom, bottom right→left, left bottom→top.
