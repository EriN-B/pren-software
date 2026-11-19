"""Runs the real dog core inside the simulator, wired to the simulated devices.

Needs the core from the ``dev-core`` branch installed (``dog_core.machine`` and its
dependencies). On a branch without it, start the simulator without ``--core`` and
drive the robot from the viewer instead.
"""

import importlib
import logging
import threading
from pathlib import Path
from types import SimpleNamespace

from dog_sim_host.core_adapters import (
    CommandInbox,
    SimAudioModel,
    SimCamera,
    SimGestureModel,
    SimMicrophone,
    SimObjectModel,
)
from dog_sim_host.world import World

log = logging.getLogger(__name__)


class CoreRunner:
    """Starts the core's state machine in a background thread.

    Args:
        world: The simulated world the core's camera looks at.
        inbox: Voice words and gestures from the viewer.
        port: Path of the virtual serial port the core's ``Uart`` opens.
    """

    def __init__(self, world: World, inbox: CommandInbox, port: Path) -> None:
        self.object_model = SimObjectModel(world)
        self._inbox = inbox
        self._port = port
        self._machine = None
        self.error: str | None = None

    def start(self) -> None:
        """Import the core, swap in the simulated devices and start it."""
        threading.Thread(target=self._run, name="dog core", daemon=True).start()

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
            gestures = importlib.import_module("dog_perception.enum_gesture_type")
            # shortcut: replaces names inside dog_core.states.startup instead of passing
            # devices in; replace once the core accepts its devices from outside.
            startup.cv2 = SimpleNamespace(VideoCapture=lambda index: SimCamera())
            startup.sd = SimpleNamespace(RawInputStream=lambda **_: SimMicrophone())
            startup.AudioModel = lambda: SimAudioModel(self._inbox)
            startup.GestureModel = lambda: SimGestureModel(
                self._inbox, gestures.GestureType
            )
            startup.ObjectModel = lambda: self.object_model
            startup.Uart = lambda logger: uart.Uart(port=str(self._port), logger=logger)
            self._machine = machine.PrenMachine()
            self._machine.activate_initial_state()
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            log.exception("The dog core could not start")
