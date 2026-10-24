from __future__ import annotations
from typing import TYPE_CHECKING
import cv2
import sounddevice as sd
from dog_perception import GestureModel
from dog_perception import ObjectModel
from dog_recorder import AudioModel

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine
    
def enter(machine: PrenMachine):
    machine.shared.camera = cv2.VideoCapture(0)
    machine.shared.microphone = sd.RawInputStream(samplerate=16000, blocksize=4000, dtype="int16", channels=1)
    machine.shared.gesture_model = GestureModel()
    machine.shared.audio_model = AudioModel()
    machine.shared.object_model = ObjectModel()
    machine.shared.path_to_here = None
    
    machine.wait_for_command()

def exit(machine: PrenMachine):
    pass
