"""Measure a detector on labelled real frames, the way the core uses it.

Runs the core's ``ObjectModel`` (same calls and thresholds as on the robot) on a YOLO
folder of 640 x 480 frames (``0 bone, 1 person, 2 shoe``) and counts, per class, how many
labelled objects were found (recall) and how many detections were right (precision). A
detection is right when it overlaps an unmatched label of its class by IoU >= 0.5.

    .venv-core/bin/python apps/sim-host/scripts/evaluate_detector.py datasets/real-396/images/val
    .venv-core/bin/python apps/sim-host/scripts/evaluate_detector.py datasets/real-396/images/val \
        --model runs/detect/train/weights/best_ncnn_model
"""

import argparse
from pathlib import Path

import cv2  # in the core environment
from dog_perception.object_model import ObjectModel

NAMES = ("bone", "person", "shoe")


def iou(a, b) -> float:
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - w * h
    return w * h / union if union else 0.0


def match(truth, found) -> int:
    """Number of found boxes that each match a different true box (best confidence first)."""
    free, hits = list(truth), 0
    for box in found:
        best = max(free, key=lambda t: iou(t, box), default=None)
        if best is not None and iou(best, box) >= 0.5:
            free.remove(best)
            hits += 1
    return hits


def read_labels(path: Path, width=640, height=480):
    boxes = {name: [] for name in NAMES}
    for line in path.read_text().split("\n"):
        if line.strip():
            cls, cx, cy, w, h = (float(v) for v in line.split())
            x1, y1 = (cx - w / 2) * width, (cy - h / 2) * height
            boxes[NAMES[int(cls)]].append((x1, y1, x1 + w * width, y1 + h * height))
    return boxes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("images", type=Path)
    parser.add_argument("--model", type=Path, default=None, help="default: the core's")
    args = parser.parse_args()

    model = ObjectModel(args.model)
    labels, found, hits = (
        dict.fromkeys(NAMES, 0),
        dict.fromkeys(NAMES, 0),
        dict.fromkeys(NAMES, 0),
    )
    frames, bone_frames, bone_frames_found = 0, 0, 0
    for path in sorted(args.images.glob("*.jpg")):
        image = cv2.imread(str(path))
        truth = read_labels(
            path.parents[2] / "labels" / path.parent.name / f"{path.stem}.txt"
        )
        detections = {name: [] for name in NAMES}
        for result in (model.get_objects(image), model.get_people_and_shoes(image)):
            order = result.boxes.conf.argsort(descending=True).tolist()
            for i in order:
                name = result.names[int(result.boxes.cls[i])]
                name = name if name in NAMES else "bone"  # "dog bone", "chew toy", ...
                detections[name].append(result.boxes.xyxy[i].tolist())
        for name in NAMES:
            labels[name] += len(truth[name])
            found[name] += len(detections[name])
            hits[name] += match(truth[name], detections[name])
        frames += 1
        if truth["bone"]:
            bone_frames += 1
            bone_frames_found += match(truth["bone"], detections["bone"]) > 0

    print(f"{frames} frames, model: {args.model or 'core default'}")
    for name in NAMES:
        recall = hits[name] / labels[name] if labels[name] else 0.0
        precision = hits[name] / found[name] if found[name] else 0.0
        print(
            f"  {name:6}  found {hits[name]:3}/{labels[name]:3} labelled ({recall:4.0%})"
            f"   {hits[name]:3}/{found[name]:3} detections right ({precision:4.0%})"
        )
    print(f"  bone found in {bone_frames_found}/{bone_frames} frames that show one")


if __name__ == "__main__":
    a, far = (0, 0, 10, 10), (50, 50, 60, 60)
    assert match([a, far], [a, a, (1, 1, 11, 11)]) == 1  # one true box matches once
    assert match([a, far], [far, a]) == 2
    main()
