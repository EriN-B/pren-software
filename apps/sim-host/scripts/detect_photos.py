"""Run the core's own object detector on photos, to compare real and rendered images.

For each photo it prints what YOLO finds (the same call and thresholds as the core's
search) and writes a copy with the boxes drawn in, next to the photo as ``*_detected.jpg``.

    .venv-core/bin/python apps/sim-host/scripts/detect_photos.py photos/*.jpg
"""

import sys
from pathlib import Path

import cv2  # in the core environment
from dog_perception.object_model import ObjectModel


def main() -> None:
    model = ObjectModel()
    for name in sys.argv[1:]:
        path = Path(name)
        image = cv2.imread(str(path))
        if image is None:
            print(f"{path}: cannot read")
            continue
        # Crop to the camera's 4:3, then scale to its size.
        height, width = image.shape[:2]
        keep_w, keep_h = min(width, height * 4 // 3), min(height, width * 3 // 4)
        top, left = (height - keep_h) // 2, (width - keep_w) // 2
        image = cv2.resize(image[top : top + keep_h, left : left + keep_w], (640, 480))
        result = model.get_objects(image)
        boxes = list(
            zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist(), strict=True)
        )
        for (x1, y1, x2, y2), confidence in boxes:
            cv2.rectangle(
                image, (int(x1), int(y1)), (int(x2), int(y2)), (67, 159, 255), 2
            )
            cv2.putText(
                image,
                f"bone {confidence:.2f}",
                (int(x1), max(12, int(y1) - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (67, 159, 255),
                1,
            )
        out = path.with_name(f"{path.stem}_detected.jpg")
        cv2.imwrite(str(out), image)
        found = ", ".join(f"{c:.2f}" for _, c in boxes) or "nothing"
        print(f"{path.name}: bone {found} -> {out.name}")


if __name__ == "__main__":
    main()
