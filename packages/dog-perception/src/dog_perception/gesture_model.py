import mediapipe as mp
from mediapipe.tasks.python.vision.hand_landmarker import HandLandmarker, HandLandmarkerResult
import cv2
from pathlib import Path
import joblib
from sklearn.neighbors import KNeighborsClassifier
from dog_perception.enum_gesture_type import GestureType
import pandas as pd
import numpy as np

class GestureModel():
    def __init__(self):
        options = mp.tasks.vision.GestureRecognizerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(Path(__file__).parent / "mediapipe_model/hand_landmarker.task")
                ),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=1
        )
        
        self.hand_model: HandLandmarker = (
            mp.tasks.vision.HandLandmarker.create_from_options(options)
        )
        self.knn: KNeighborsClassifier = joblib.load(str(Path(__file__).parent / "knn_classifier_model/knn_model.pkl"))
    
    def get_gesture(self, frame, timestamp_ms) -> GestureType | None:
        frame = cv2.flip(frame, 1)
        hand: HandLandmarkerResult = self._get_hand(frame, timestamp_ms)
        
        if hand is None:
            return None
        
        features = self._create_features(hand, frame)
        
        distances, indices = self.knn.kneighbors(features)

        labels = self.knn._y[indices[0]]
        confidences = np.bincount(labels)

        confidence = confidences.max() / len(labels)

        if distances[0].mean() > 2.0 or confidence < 0.8:
            return GestureType.NONE

        winner = confidences.argmax()
        return GestureType(self.knn.classes_[winner])
    
    def _get_hand(self, frame, timestamp_ms: int):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb
        )

        result = self.hand_model.detect_for_video(image, timestamp_ms)

        if not result.hand_landmarks:
            return None

        return result.hand_landmarks[0]
    
    def _create_features(self, hand, frame) -> pd.DataFrame | None:
        height, width = frame.shape[:2]

        # Correct for image aspect ratio
        points = np.array(
            [(p.x * width / height, p.y) for p in hand],
            dtype=np.float64
        )

        if points.shape != (21, 2):
            return None

        # Wrist-relative normalization
        wrist = points[0]
        palm_size = max(
            float(np.linalg.norm(points[9] - wrist)),
            1e-6
        )

        relative = ((points - wrist) / palm_size).reshape(-1)

        # Same column names and order as training
        columns = [
            part
            for i in range(21)
            for part in (f"rel_x{i}", f"rel_y{i}")
        ]

        return pd.DataFrame([relative], columns=columns)