from dataclasses import dataclass

@dataclass
class SharedContext:
    """Objects shared between states; add fields as needed."""
    camera: object | None = None
    gesture_model: object | None = None
    audio_model: object | None = None
    object_model: object | None = None
