import cv2
import sounddevice as sd
from dog_perception import GestureModel
from dog_perception import ObjectModel
from dog_recorder import AudioModel

class SharedContext:
    """Objects shared between states; add fields as needed."""
    def __init__(self):
        self.camera: cv2.VideoCapture | None
        self.microphone: sd.RawInputStream | None
        self.gesture_model: GestureModel | None
        self.audio_model: AudioModel | None
        self.object_model: ObjectModel | None
        self.path_to_here: object | None
