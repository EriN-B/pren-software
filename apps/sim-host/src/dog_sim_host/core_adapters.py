"""The camera the core sees in the simulator, and where objects appear in its image.

With ``--core`` the simulator replaces only hardware. The core's own models (YOLO,
MediaPipe gestures, Vosk speech) run unchanged on what they get:

| Core opens                | In the simulator                                         |
| ------------------------- | -------------------------------------------------------- |
| ``cv2.VideoCapture``      | `SimCamera`: the dog's camera rendered by MuJoCo, and the laptop webcam for gestures |
| ``sd.RawInputStream``     | the laptop microphone, untouched                         |
| serial port               | the virtual serial port of the emulated Pico             |
"""

import logging
import threading
import time

import numpy as np

from dog_sim_host.world import Snapshot

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 640, 480  # pixels, like the core's camera frames
FRAME_RATE = 30.0
MIN_BOX_PIXELS = 3  # smaller boxes are not "seen"
#: Name of the core's gesture thread (``dog_core.command_recognition``).
GESTURE_THREAD = "Gesture recognition"


class Webcam:
    """The laptop camera, read in the background; `frame` is always the newest image.

    Args:
        index: OpenCV camera index, usually 0 for the built-in camera.

    Raises:
        RuntimeError: The camera cannot be opened (missing, or no camera permission).
    """

    def __init__(self, index: int) -> None:
        import cv2  # only installed in the core environment

        self._capture = cv2.VideoCapture(index)
        if not self._capture.isOpened():
            raise RuntimeError(f"cannot open webcam {index}; check camera permission")
        size = (
            self._capture.get(cv2.CAP_PROP_FRAME_WIDTH),
            self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT),
        )
        log.info(
            "Webcam %d opened for gestures (%d x %d); --webcam picks another",
            index,
            *size,
        )
        #: Newest BGR image, or None until the first one arrives.
        self.frame: np.ndarray | None = None
        threading.Thread(target=self._run, name="webcam", daemon=True).start()

    def _run(self) -> None:
        while True:
            ok, frame = self._capture.read()
            if ok:
                self.frame = frame
            else:
                time.sleep(0.1)


class SimCamera:
    """Behaves like an open ``cv2.VideoCapture`` for the core.

    The core's gesture thread gets the laptop webcam, so your hand gives the commands.
    Every other caller (the states looking for the bone, the person and shoes) gets the
    dog's view of the simulated world, which the simulator renders into `rendered`.

    Args:
        webcam: The laptop camera, or None to give the gesture thread the dog's view too.
    """

    def __init__(self, webcam: Webcam | None) -> None:
        self.webcam = webcam
        #: Newest rendered dog's-eye image (BGR), set by the simulator.
        self.rendered: np.ndarray | None = None
        self._last: dict[str, float] = {}

    def isOpened(self) -> bool:
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        """Return the next frame, paced like a real 30 fps camera for each reader."""
        thread = threading.current_thread().name
        wait = self._last.get(thread, 0.0) + 1 / FRAME_RATE - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last[thread] = time.monotonic()
        # shortcut: picks the image by the core's thread name, because the core reads
        # one camera for two jobs; if the core renames the thread, gestures see the world.
        frame = self.rendered
        if thread == GESTURE_THREAD and self.webcam and self.webcam.frame is not None:
            frame = self.webcam.frame
        return frame is not None, frame

    def release(self) -> None:
        pass


def project(
    snapshot: Snapshot, geom_names: tuple[str, ...]
) -> tuple[float, float, float, float] | None:
    """Pixel box (x1, y1, x2, y2) around some geoms as the dog's camera sees them.

    The true position of an object in the image, for the viewer to compare with what
    the core's detector finds. Uses a pinhole camera with the field of view from
    ``dog.xml``. Returns None when the object is behind the camera, outside the image
    or too small. Objects hiding behind other objects are still returned.

    Args:
        snapshot: Camera pose and geom poses.
        geom_names: Geoms that together form one object.
    """
    # shortcut: no occlusion; fine for an overlay, not for judging what is visible
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
