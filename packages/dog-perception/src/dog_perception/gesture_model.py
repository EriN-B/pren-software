import mediapipe as mp
import cv2
from pathlib import Path
import joblib

class GestureModel():
    def __init__(self):
        options = mp.tasks.vision.GestureRecognizerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(Path(__file__).parent / "mediapipe_model/hand_landmarker.task")
                ),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=1
        )
        
        self.hand_model = (
            mp.tasks.vision.HandLandmarker.create_from_options(options)
        )
        self.knn = joblib.load(str(Path(__file__).parent / "knn_classifier_model/knn_model.pkl"))
    
    def get_gesture(self) -> str:
        # Implement KNN Classifier
        pass
    
    def _get_hands(self, frame, timestamp_ms: int):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb
        )

        return self.hand_model.detect_for_video(
            image, timestamp_ms
        )