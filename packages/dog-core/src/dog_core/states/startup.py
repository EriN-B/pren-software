from __future__ import annotations
from typing import TYPE_CHECKING
import cv2
import sounddevice as sd
from dog_perception import GestureModel
from dog_perception import ObjectModel
from dog_recorder import AudioModel
import logging
import sys

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine
    
def enter(machine: PrenMachine):
    machine.shared.camera = cv2.VideoCapture(0)
    if not machine.shared.camera.isOpened():
        machine.shared.camera.release()
        raise RuntimeError(
            "Could not open camera 0. Check camera availability and camera permissions."
        )
    machine.shared.microphone = sd.RawInputStream(samplerate=16000, blocksize=4000, dtype="int16", channels=1)
    machine.shared.audio_model = AudioModel()
    machine.shared.gesture_model = GestureModel()
    machine.shared.object_model = ObjectModel()
    machine.shared.path_to_here = None
    
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
    
    machine.wait_for_command()

def exit(machine: PrenMachine):
    machine.shared.logger.info("Startup initialization successful")
