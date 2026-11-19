"""Stand-ins for the camera, microphone and recognition models the core uses.

The core's states only touch a few methods and attributes of these objects (see
``dog_core.states`` on the dev-core branch). Each class here offers exactly those,
fed from the simulated world or from the viewer instead of real hardware:

| Core expects                 | Stand-in          | Fed by                                |
| ---------------------------- | ----------------- | ------------------------------------- |
| ``cv2.VideoCapture``         | `SimCamera`       | blank frames at camera size and rate  |
| ``sd.RawInputStream``        | `SimMicrophone`   | nothing (audio is skipped)            |
| ``dog_perception.ObjectModel`` | `SimObjectModel` | boxes projected from the world        |
| ``dog_perception.GestureModel`` | `SimGestureModel` | gesture picked in the viewer       |
| ``dog_recorder.AudioModel``  | `SimAudioModel`   | words clicked in the viewer           |
"""

import queue
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from dog_sim_host.world import DETECTABLE, Snapshot, World

WIDTH, HEIGHT = 640, 480  # pixels, like the core's camera frames
FRAME_RATE = 30.0
CONFIDENCE = 0.9
MIN_BOX_PIXELS = 3  # smaller boxes are not "seen"


class CommandInbox:
    """Voice words and the current gesture, set by the viewer and read by the core."""

    def __init__(self) -> None:
        self.words: queue.Queue[str] = queue.Queue()
        #: Gesture currently shown to the camera: "auf", "sitz", "platz" or None.
        self.gesture: str | None = None

    def say(self, word: str) -> None:
        """Speak a word to the dog."""
        self.words.put(word)


class SimCamera:
    """Behaves like an open ``cv2.VideoCapture``; frames are black.

    The core only uses the frame's shape; what it "sees" comes from `SimObjectModel`.
    """

    def __init__(self) -> None:
        self._frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        self._last = 0.0

    def isOpened(self) -> bool:
        return True

    def read(self) -> tuple[bool, np.ndarray]:
        """Return the next frame, paced like a real 30 fps camera."""
        wait = self._last + 1 / FRAME_RATE - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        return True, self._frame

    def release(self) -> None:
        pass


class SimMicrophone:
    """Behaves like ``sounddevice.RawInputStream``; records nothing."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


class _Column(list):
    """A list with ``.tolist()``, like the tensors in an ultralytics result."""

    def tolist(self) -> list:
        return list(self)


@dataclass
class _Boxes:
    xyxy: _Column = field(default_factory=_Column)
    conf: _Column = field(default_factory=_Column)
    cls: _Column = field(default_factory=_Column)


@dataclass
class DetectionResult:
    """Just the parts of an ultralytics ``Results`` the core reads."""

    boxes: _Boxes
    names: dict[int, str]


class SimObjectModel:
    """Detects objects by projecting the world into the dog's camera.

    Args:
        world: The world to look at.
    """

    def __init__(self, world: World) -> None:
        self.world = world

    def get_objects(self, frame: np.ndarray) -> DetectionResult:
        """Find the bone."""
        return self._detect({0: "bone"}, {"bone": 0})

    def get_people_and_shoes(self, frame: np.ndarray) -> DetectionResult:
        """Find the person and each shoe."""
        return self._detect(
            {0: "person", 1: "shoe"}, {"person": 0, "shoe_left": 1, "shoe_right": 1}
        )

    def _detect(self, names: dict[int, str], labels: dict[str, int]) -> DetectionResult:
        snapshot = self.world.snapshot
        boxes = _Boxes()
        for label, class_id in labels.items():
            box = project(snapshot, DETECTABLE[label])
            if box is not None:
                boxes.xyxy.append(list(box))
                boxes.conf.append(CONFIDENCE)
                boxes.cls.append(float(class_id))
        return DetectionResult(boxes, names)


class SimGestureModel:
    """Reports the gesture picked in the viewer.

    Args:
        inbox: Where the viewer puts the current gesture.
        gesture_type: The core's ``GestureType`` enum; its values are the gesture names.
    """

    def __init__(self, inbox: CommandInbox, gesture_type: type[Enum]) -> None:
        self.inbox = inbox
        self.gesture_type = gesture_type

    def get_gesture(self, frame: np.ndarray, timestamp_ms: int) -> Enum:
        """The selected gesture as the core's enum, ``NONE`` when nothing is shown."""
        gesture = self.inbox.gesture
        return self.gesture_type(gesture) if gesture else self.gesture_type.NONE


class SimAudioModel:
    """Hands words clicked in the viewer to the core as if they were transcribed speech.

    Args:
        inbox: Where the viewer puts spoken words.
    """

    def __init__(self, inbox: CommandInbox) -> None:
        self.inbox = inbox

    def get_transcription_stream(
        self, microphone, logger, stop_event: threading.Event
    ) -> Iterator[str]:
        """Yield each word as it arrives until `stop_event` is set."""
        while not stop_event.is_set():
            try:
                yield self.inbox.words.get(timeout=0.1)
            except queue.Empty:
                continue


def project(
    snapshot: Snapshot, geom_names: tuple[str, ...]
) -> tuple[float, float, float, float] | None:
    """Pixel box (x1, y1, x2, y2) around some geoms as the dog's camera sees them.

    Uses a pinhole camera with the field of view from ``dog.xml``. Returns None when
    the object is behind the camera, outside the image or too small. Objects hiding
    behind other objects are still seen.

    Args:
        snapshot: Camera pose and geom poses.
        geom_names: Geoms that together form one object.
    """
    # shortcut: no occlusion and no lens distortion; add them if detection tests need it
    focal = (HEIGHT / 2) / np.tan(np.radians(48.8) / 2)
    corners = []
    for name in geom_names:
        geom = snapshot.geoms[name]
        signs = np.array(np.meshgrid([-1, 1], [-1, 1], [-1, 1])).reshape(3, -1).T
        corners.append(geom.pos + (signs * geom.half_size) @ geom.mat.T)
    points = np.vstack(corners)
    camera = (points - snapshot.camera_pos) @ snapshot.camera_mat  # into camera axes
    depth = -camera[:, 2]
    if np.any(depth < 0.05):
        return None
    u = WIDTH / 2 + focal * camera[:, 0] / depth
    v = HEIGHT / 2 - focal * camera[:, 1] / depth
    x1, x2 = np.clip([u.min(), u.max()], 0, WIDTH)
    y1, y2 = np.clip([v.min(), v.max()], 0, HEIGHT)
    if x2 - x1 < MIN_BOX_PIXELS or y2 - y1 < MIN_BOX_PIXELS:
        return None
    return float(x1), float(y1), float(x2), float(y2)
