"""Runs the real dog core inside the simulator; only its hardware is simulated.

The core's state machine and all its models (YOLO, MediaPipe gestures, Vosk speech) run
unchanged. The simulator hands it a camera (`SimCamera`) and the virtual serial port;
the microphone is the laptop's. Needs the core installed, see ``scripts/core-env.sh``.
"""

import importlib
import logging
import re
import threading
import time
from collections import deque
from pathlib import Path
from types import SimpleNamespace

from dog_sim_host.core_adapters import SimCamera, Webcam

log = logging.getLogger(__name__)

#: What the core's states log for every box their detector finds (searching, perform_hier).
DETECTION_LINE = re.compile(
    r"(Bone|Person|Shoe) bounding box: x1=([-\d.]+), y1=([-\d.]+), "
    r"x2=([-\d.]+), y2=([-\d.]+), confidence=([\d.]+)"
)
DETECTION_MAX_AGE = 0.4  # s; older boxes are gone from the core's view


class CoreRunner:
    """Starts the core's state machine in a background thread.

    Args:
        port: Path of the virtual serial port the core's ``Uart`` opens.
        webcam: OpenCV index of the laptop camera for gestures, or None for none.
    """

    def __init__(self, port: Path, webcam: int | None) -> None:
        self._port = port
        self._machine = None
        self.error: str | None = None
        self._detections: deque[tuple[float, dict]] = deque(maxlen=50)
        # Read the core's own log; a logger filter sees every record and changes nothing.
        logging.getLogger("state_machine").addFilter(self._record_detection)
        try:
            camera = Webcam(webcam) if webcam is not None else None
        except (
            RuntimeError
        ) as error:  # gestures then see the dog's view: no hand, no command
            log.warning("No webcam for gestures: %s", error)
            camera = None
        #: The camera the core reads; the simulator puts the rendered view into it.
        self.camera = SimCamera(camera)

    def start(self) -> None:
        """Import the core, swap in the simulated devices and start it."""
        threading.Thread(target=self._run, name="dog core", daemon=True).start()

    def detections(self) -> list[dict]:
        """Boxes the core's detector reported in the last moment, newest last."""
        now = time.monotonic()
        return [box for seen, box in self._detections if now - seen < DETECTION_MAX_AGE]

    def _record_detection(self, record: logging.LogRecord) -> bool:
        match = DETECTION_LINE.match(record.getMessage())
        if match:
            label, *numbers = match.groups()
            *box, confidence = (float(n) for n in numbers)
            entry = {"label": label.lower(), "box": box, "confidence": confidence}
            self._detections.append((time.monotonic(), entry))
        return True  # never drop the core's log line

    @property
    def state(self) -> str | None:
        """Id of the core's current state, e.g. ``"searching"``, or None if not running."""
        try:
            return self._machine.current_state.id
        except AttributeError:  # not started yet
            return None

    def _run(self) -> None:
        try:
            # Imported by name: dog_core.machine only exists on the dev-core branch.
            machine = importlib.import_module("dog_core.machine")
            startup = importlib.import_module("dog_core.states.startup")
            uart = importlib.import_module("dog_core.uart")
            # shortcut: replaces names inside dog_core.states.startup instead of passing
            # devices in; replace once the core accepts its devices from outside.
            startup.cv2 = SimpleNamespace(VideoCapture=lambda index: self.camera)
            startup.Uart = lambda logger: uart.Uart(port=str(self._port), logger=logger)
            self._machine = machine.PrenMachine()
            self._machine.activate_initial_state()
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            log.exception("The dog core could not start")
