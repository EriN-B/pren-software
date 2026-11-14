from __future__ import annotations
from typing import TYPE_CHECKING
import cv2
import sounddevice as sd
from dog_perception import GestureModel
from dog_perception import ObjectModel
from dog_recorder import AudioModel
from dog_core.uart import Uart
import logging
import sys

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine
    
def enter(machine: PrenMachine):
    # Setup camera
    machine.shared.camera = cv2.VideoCapture(1) # TODO: set to 0, use 1 for testing on mac
    if not machine.shared.camera.isOpened():
        machine.shared.camera.release()
        raise RuntimeError(
            "Could not open camera 0. Check camera availability and camera permissions."
        )

    # Setup mic
    machine.shared.microphone = sd.RawInputStream(samplerate=16000, blocksize=4000, dtype="int16", channels=1)
    # Setup audio_model
    machine.shared.audio_model = AudioModel()
    # Setup gesture_model
    machine.shared.gesture_model = GestureModel()
    # Setup object_model
    machine.shared.object_model = ObjectModel()
    # Setup coordinate system
    machine.shared.path_to_here = None
    
    # Setup logger
    logger = logging.getLogger("state_machine")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(message)s")
        )
        logger.addHandler(handler)

    machine.shared.logger = logger

    # Share the state machine logger with the UART connection.
    machine.shared.uart = Uart(logger=logger).open()
    
    machine.go_to_standing_idle()

def exit(machine: PrenMachine):
    machine.shared.logger.info("Startup initialization successful")
