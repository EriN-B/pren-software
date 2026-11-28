"""Crop real photos to the camera's image and pre-label bone, person and shoe with YOLOE.

Each photo is cropped to 4:3 (as ``detect_photos.py`` does). YOLOE-26L, told the class names
in words, looks for the objects at full resolution, where far bones are still big enough to
find, and the boxes are scaled to the 640 x 480 image that is saved. Output is a YOLO set
(``0 bone, 1 person, 2 shoe``, the shared detector's classes) to check in Label Studio
before training. Copies with the boxes drawn in go to ``preview/``.

    .venv-core/bin/python apps/sim-host/scripts/prelabel_photos.py \
        ~/Desktop/"Bone Images"/frames/*.jpg --out datasets/real-bone

The weights (yoloe-26l-seg.pt, mobileclip2_b.ts) are downloaded into --weights on first use.
"""

import argparse
import os
from pathlib import Path

import cv2  # in the core environment
from ultralytics import YOLOE

# Prompt -> class, in two passes: YOLO26 has no NMS and gives each box only its best
# class, so with all prompts at once the bone often comes out as "person" or "shoe".
# Two prompts for the bone: each finds bones the other misses.
PASSES = (
    {"dog bone": 0, "white chew bone": 0},
    {"person": 1, "shoe": 2},
)
NAMES = ("bone", "person", "shoe")
# Lowest confidence kept per class: YOLOE is unsure of the bone even when it is right.
MIN_CONF = (0.05, 0.25, 0.10)
COLOURS = ((67, 159, 255), (80, 200, 80), (240, 140, 40))


def crop_to_camera(image):
    height, width = image.shape[:2]
    keep_w, keep_h = min(width, height * 4 // 3), min(height, width * 3 // 4)
    top, left = (height - keep_h) // 2, (width - keep_w) // 2
    return image[top : top + keep_h, left : left + keep_w]


def yolo_line(cls, x1, y1, x2, y2, width=640, height=480) -> str:
    cx, cy = (x1 + x2) / 2 / width, (y1 + y2) / 2 / height
    return f"{cls} {cx:.6f} {cy:.6f} {(x2 - x1) / width:.6f} {(y2 - y1) / height:.6f}"


def iou(a, b) -> float:
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - w * h
    return w * h / union if union else 0.0


def pick(detections):
    """Keep each class above its threshold and only the best bone (one per photo).

    The person/shoe pass often also finds the bone, as a person or shoe; those boxes on
    top of the bone are dropped, so the bone keeps its class.
    """
    kept = [d for d in detections if d[1] >= MIN_CONF[d[0]]]
    bone = sorted((d for d in kept if d[0] == 0), key=lambda d: -d[1])[:1]
    others = [
        d for d in kept if d[0] != 0 and not any(iou(d[2], b[2]) > 0.5 for b in bone)
    ]
    return others + bone


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("photos", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--weights", type=Path, default=Path.home() / ".cache" / "ultralytics"
    )
    args = parser.parse_args()
    photos = [p.resolve() for p in args.photos]
    out = args.out.resolve()
    for sub in ("images", "labels", "preview"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    args.weights.mkdir(parents=True, exist_ok=True)
    os.chdir(args.weights)  # Ultralytics finds and downloads the text model in the cwd
    models = []
    for prompts in PASSES:
        model = YOLOE("yoloe-26l-seg.pt")
        model.set_classes(list(prompts))
        models.append((model, list(prompts.values())))

    counts = [0, 0, 0]
    for path in photos:
        image = cv2.imread(str(path))
        if image is None:
            print(f"{path}: cannot read")
            continue
        image = crop_to_camera(image)
        scale = 640 / image.shape[1]
        found = []
        for model, prompt_class in models:
            boxes = model.predict(image, imgsz=1280, conf=min(MIN_CONF), verbose=False)
            boxes = boxes[0].boxes
            found += [
                (prompt_class[int(c)], conf, [v * scale for v in xyxy])
                for c, conf, xyxy in zip(
                    boxes.cls.tolist(),
                    boxes.conf.tolist(),
                    boxes.xyxy.tolist(),
                    strict=True,
                )
            ]
        detections = pick(found)
        small = cv2.resize(image, (640, 480))
        preview = small.copy()
        for cls, conf, (x1, y1, x2, y2) in detections:
            counts[cls] += 1
            cv2.rectangle(
                preview, (int(x1), int(y1)), (int(x2), int(y2)), COLOURS[cls], 2
            )
            cv2.putText(
                preview,
                f"{NAMES[cls]} {conf:.2f}",
                (int(x1), max(12, int(y1) - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                COLOURS[cls],
                1,
            )
        cv2.imwrite(str(out / "images" / f"{path.stem}.jpg"), small)
        cv2.imwrite(str(out / "preview" / f"{path.stem}.jpg"), preview)
        (out / "labels" / f"{path.stem}.txt").write_text(
            "".join(f"{yolo_line(c, *box)}\n" for c, _, box in detections)
        )
    print(
        f"{len(photos)} photos, boxes: "
        + ", ".join(f"{n} {k}" for n, k in zip(NAMES, counts, strict=True))
        + f" -> {out}"
    )


if __name__ == "__main__":
    assert yolo_line(0, 0, 0, 640, 480) == "0 0.500000 0.500000 1.000000 1.000000"
    box, other = [0, 0, 10, 10], [20, 20, 30, 30]
    assert pick(
        [
            (0, 0.2, other),
            (0, 0.6, box),
            (1, 0.9, box),
            (1, 0.3, other),
            (2, 0.05, other),
        ]
    ) == [(1, 0.3, other), (0, 0.6, box)]
    main()
