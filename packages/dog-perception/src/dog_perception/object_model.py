from pathlib import Path

import numpy as np
from ultralytics import YOLO


class ObjectModel:
    def __init__(self):
        model_path = (
            Path(__file__).resolve().parent
            / "yoloe26n_model"
            / "bone-yoloe26n-detect-384x512_ncnn_model"
        )

        self.object_model = YOLO(str(model_path), task="detect")

    def get_objects(self, frame: np.ndarray):
        result = self.object_model.predict(
            source=frame,
            conf=0.001,
            imgsz=(384, 512),
            rect=False,
            device="cpu",
            max_det=300,
            verbose=False,
        )[0]

        if result.boxes is not None:
            labels = {"bone", "dog bone", "dog chew bone", "chew toy"}

            keep = [
                i for i, box in enumerate(result.boxes)
                if float(box.conf.item()) >= 0.30
                and result.names[int(box.cls.item())] in labels
            ]

            result.boxes = result.boxes[keep]

        return result