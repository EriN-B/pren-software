import mediapipe as mp
from mediapipe.tasks.python.vision.hand_landmarker import HandLandmarker
import cv2
from pathlib import Path
import joblib
from sklearn.neighbors import KNeighborsClassifier
from dog_perception.enum_prediction_type import PredictionType

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
    
    def get_gesture(self, frame, timestamp_ms) -> str:
        hand = self._get_hand(frame, timestamp_ms)
        prediction = self.knn.predict()[0]

        distances, _ = self.knn.kneighbors(hand)
        mean_distance = distances[0].mean()

        if mean_distance > 2.0:
            return PredictionType.NONE
        
        match prediction:
            case "auf":
                return PredictionType.AUF
            case "sitz":
                return PredictionType.SITZ
            case "platz":
                return PredictionType.PLATZ
    
    def _get_hand(self, frame, timestamp_ms: int):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb
        )

        return self.hand_model.detect_for_video(
            image, timestamp_ms
        )