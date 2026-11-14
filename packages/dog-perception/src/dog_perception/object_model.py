from pathlib import Path

import numpy as np
from ultralytics import YOLO


class ObjectModel:
    def __init__(self, model_path: str | Path | None = None):
        if model_path is None:
            model_path = (
                Path(__file__).resolve().parent
                / "yoloe26n_model"
                / "dog-yoloe26n-detect-384x512_ncnn_model"
            )
        self.object_model = YOLO(str(model_path), task="detect")
        names = self.object_model.names
        bone_labels = {"bone", "dog bone", "dog chew bone", "chew toy"}
        self.bone_classes = [
            class_id for class_id, label in names.items() if label in bone_labels
        ]
        self.hier_classes = {
            class_id: label
            for class_id, label in names.items()
            if label in {"person", "shoe"}
        }
        if not self.bone_classes or not {"person", "shoe"}.issubset(
            self.hier_classes.values()
        ):
            raise ValueError(
                "Shared detector must include bone, person and shoe classes"
            )

    def get_objects(self, frame: np.ndarray):
        """Use the shared detector with only the bone classes enabled."""
        result = self.object_model.predict(
            source=frame,
            conf=0.001,
            classes=self.bone_classes,
            imgsz=(384, 512),
            rect=False,
            device="cpu",
            max_det=300,
            verbose=False,
        )[0]
        if result.boxes is not None:
            keep = [
                i
                for i, box in enumerate(result.boxes)
                if float(box.conf.item()) >= 0.30
                and int(box.cls.item()) in self.bone_classes
            ]
            result.boxes = result.boxes[keep]
        return result

    def get_people_and_shoes(self, frame: np.ndarray):
        """Use the same model instance with only the Hier classes enabled."""
        result = self.object_model.predict(
            source=frame,
            conf=0.20,
            classes=list(self.hier_classes),
            imgsz=(384, 512),
            rect=False,
            device="cpu",
            max_det=30,
            verbose=False,
        )[0]
        if result.boxes is not None:
            keep = [
                i
                for i, box in enumerate(result.boxes)
                if int(box.cls.item()) in self.hier_classes
                and float(box.conf.item())
                >= (
                    0.40 if self.hier_classes[int(box.cls.item())] == "person" else 0.20
                )
            ]
            result.boxes = result.boxes[keep]
        result.names = dict(self.hier_classes)
        return result
