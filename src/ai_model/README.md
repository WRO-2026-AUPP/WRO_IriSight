🤖 AI Model — Object Detection
====
This document describes the custom object detection model used by our robot to identify obstacles and the parking marker during the WRO 2026 Future Engineer Obstacle Avoidance round. It covers what the model detects, how it was trained, how it fits into the robot's control pipeline, and how to run it yourself.

## 📦 Overview

| | |
|---|---|
| **Framework** | [Ultralytics YOLOv8](https://docs.ultralytics.com/) |
| **Base architecture** | YOLOv8n (nano) |
| **Weights file** | `best1.pt` |
| **Input size** | 640 × 640 |
| **Classes** | 3 — `greenbox`, `redbox`, `xparking` |
| **Training epochs** | 100 |
| **Batch size** | 8 |
| **Optimizer** | Auto (Ultralytics auto-selects SGD/AdamW) |
| **Initial learning rate** | 0.01 |
| **Runs on** | NVIDIA Jetson (onboard, real time) |

We chose YOLOv8n specifically because it is the smallest/fastest variant in the YOLOv8 family, which matters a lot on Jetson-class hardware where the depth-processing wall-following loop already consumes a significant share of compute. Nano gives us real-time inference without needing to drop frame rate on the RealSense pipeline.

## 🎯 What the Model Detects

| Class ID | Label | Meaning | Robot Behavior |
|----------|-------|---------|-----------------|
| `0` | `greenbox` | Green obstacle pillar | Pass on the **right** side |
| `1` | `redbox` | Red obstacle pillar | Pass on the **left** side |
| `2` | `xparking` | Parking lot marker | Align and execute the parking maneuver |

The model only needs to distinguish these three classes, so we deliberately kept the dataset and label set narrow — this keeps training fast and inference accuracy very high, since the model isn't wasting capacity on classes it will never see on the competition field.

## 🏋️ Training Details

- **Dataset:** Custom-labeled images collected from our own track builds, captured at multiple distances, angles, and lighting conditions to make the model robust to venue lighting differences on competition day.
- **Labeling format:** YOLO format (`data.yaml` + per-image `.txt` label files), labeled with bounding boxes around each pillar/marker.
- **Augmentation:** Standard Ultralytics training-time augmentations (mosaic, HSV jitter, flips, scale/translate) were used to improve generalization from a relatively small custom dataset.
- **Hardware used for training:** trained on a CUDA GPU (`device=0`) using the Ultralytics training loop.

### 📊 Validation Performance

| Metric | Value |
|--------|-------|
| Precision | 0.997 |
| Recall | 0.985 |
| mAP@50 | 0.995 |
| mAP@50-95 | 0.928 |
| Box loss | 0.393 |
| Class loss | 0.172 |
| DFL loss | 0.791 |

These numbers come directly from the checkpoint's stored training metrics. The high precision/recall reflects the fact that the three target objects are visually distinct (solid red, solid green, and a printed "X" marker) and the dataset was collected under conditions close to the actual competition field.

## 🗂️ Files

```
ai_model/
└── best1.pt      # Trained YOLOv8n weights (best checkpoint by validation fitness)
```

`best1.pt` is a full Ultralytics checkpoint (not just raw weights) — it also stores the class names, training args, EMA weights, and training metrics, so it's self-describing and can be loaded directly without needing a separate `data.yaml` at inference time.

## ⚙️ Installation

The model requires the `ultralytics` package (which pulls in `torch` and `torchvision`):

```bash
pip install ultralytics
```

On the Jetson, install the Jetson-optimized PyTorch/TorchVision build first (per NVIDIA's Jetson PyTorch instructions for your JetPack version), then install `ultralytics` on top without letting it reinstall a non-Jetson torch build:

```bash
pip install ultralytics --no-deps
pip install opencv-python pyyaml pillow  # remaining ultralytics deps, torch/torchvision already installed
```

## ▶️ How to Use It

### 1. Quick test — run inference on an image or folder

```bash
yolo detect predict model=best1.pt source=path/to/image_or_folder conf=0.5
```

This saves annotated output images with bounding boxes under `runs/detect/predict/`.

### 2. Run inference from Python

```python
from ultralytics import YOLO

# Load the trained model
model = YOLO("best1.pt")

# Run inference on a single image
results = model("test_image.jpg", conf=0.5)

# Inspect detections
for r in results:
    for box in r.boxes:
        cls_id = int(box.cls[0])
        label = model.names[cls_id]       # 'greenbox' / 'redbox' / 'xparking'
        confidence = float(box.conf[0])
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        print(f"{label} ({confidence:.2f}) at [{x1:.0f}, {y1:.0f}, {x2:.0f}, {y2:.0f}]")
```

### 3. Live inference on the robot (RealSense color stream)

This is how the model is actually used on the robot during the Obstacle Avoidance round — run continuously on each incoming color frame, with detections then fused against the aligned depth frame to get real-world distance/offset:

```python
import pyrealsense2 as rs
import numpy as np
from ultralytics import YOLO

model = YOLO("best1.pt")

pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
pipeline.start(config)
align = rs.align(rs.stream.color)

while True:
    frames = pipeline.wait_for_frames()
    frames = align.process(frames)
    color_frame = frames.get_color_frame()
    depth_frame = frames.get_depth_frame()
    if not color_frame or not depth_frame:
        continue

    color_image = np.asanyarray(color_frame.get_data())
    results = model(color_image, conf=0.5, verbose=False)

    for r in results[0].boxes:
        cls_id = int(r.cls[0])
        label = model.names[cls_id]
        x1, y1, x2, y2 = map(int, r.xyxy[0])
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2   # box center pixel

        # Look up real-world distance at the box center from the depth frame
        distance_m = depth_frame.get_distance(cx, cy)

        print(f"{label} at {distance_m:.2f}m, pixel center ({cx},{cy})")
        # -> feed (label, distance_m, cx) into the steering/decision logic
```

### 4. Useful inference parameters

| Parameter | Purpose | Typical value on our robot |
|-----------|---------|------------------------------|
| `conf` | Minimum confidence to keep a detection | `0.5` |
| `iou` | NMS IoU threshold for overlapping boxes | `0.45` (default) |
| `imgsz` | Inference resolution | `640` (matches training size) |
| `device` | Run on GPU (`0`) or CPU (`'cpu'`) | `0` (Jetson GPU) |
| `half` | FP16 inference for speed | `True` on Jetson |

Example with FP16 for faster Jetson inference:

```python
results = model(color_image, conf=0.5, imgsz=640, device=0, half=True, verbose=False)
```

## 🔗 How It Fits Into the Robot's Pipeline

1. **Color frame in →** YOLOv8n runs inference on each RealSense color frame, returning class, confidence, and bounding box for every detected `greenbox`, `redbox`, or `xparking` instance.
2. **Depth fusion →** the pixel center of each box is looked up in the depth frame to get a real-world distance and lateral offset, turning a 2D detection into an actionable 3D position.
3. **Decision logic →** the robot computes a steering correction so it passes green pillars on the right and red pillars on the left, layered on top of the existing wall-following PD controller.
4. **Parking →** once the lap requirement is met, `xparking` detections are used to center and align the robot with the parking bay before triggering the parking sequence.
5. **Redundancy →** ultrasonic sensors back up the vision pipeline at close range in case a frame is missed or a detection comes in late.

YOLO inference is only enabled during the Obstacle Avoidance round — it's switched off entirely for the Open Challenge, since there are no pillars to detect and disabling it frees up Jetson compute for the depth-based navigation loop.

## ⚠️ Limitations & Notes

- The model was trained on our own track builds; if lighting or pillar material at the competition differs significantly from our test conditions, confidence may drop and `conf` may need re-tuning on the day.
- `xparking` detection assumes the marker is unobstructed and roughly frontal — steep viewing angles reduce detection reliability, which is why the robot only starts looking for it once it's already aligned along the expected approach path.
- The model does not track objects across frames (no built-in tracker); temporal smoothing/debouncing of detections is handled in the decision logic layer, not inside the model itself.
