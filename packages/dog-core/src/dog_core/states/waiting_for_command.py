from __future__ import annotations
from typing import TYPE_CHECKING
import threading

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine

import cv2
import sounddevice as sd
from dog_perception import GestureModel
from dog_recorder import AudioModel

class WaitingForCommand():
    def __init__(self):
        self.stop_event = threading.Event()
        self.audio_thread = None
        self.gesture_thread = None
        super().__init__()

    def enter(self, machine: PrenMachine):
        self.stop_event = threading.Event()
        
        def audio_worker():
            while not self.stop_event.is_set():
                # audio detection
                audio_command = self.listen_for_audio_command(
                    machine.shared.microphone,
                    machine.shared.audio_model,
                    self.stop_event
                )
                if audio_command and not self.stop_event.is_set():
                    self.stop_event.set()
                    
                    machine.send(audio_command)

        def gesture_worker():
            while not self.stop_event.is_set():
                # gesture detection
                gesture_command = self.look_for_gesture_command(
                    machine.shared.camera,
                    machine.shared.gesture_model,
                    self.stop_event
                )
                if gesture_command and not self.stop_event.is_set():
                    self.stop_event.set()
                    machine.send(gesture_command)

        self.audio_thread = threading.Thread(target=audio_worker, daemon=True)
        self.gesture_thread = threading.Thread(target=gesture_worker, daemon=True)

        self.audio_thread.start()
        self.gesture_thread.start()


    def listen_for_audio_command(self, mic: sd.RawInputStream, model: AudioModel, stop_event: threading.Event) -> str | None:
        # TODO check if these are all possible commands
        commands = ["hier", "sitz", "platz", "auf", "such", "brav"]

        itr = model.get_transcription_stream(mic)

        while not stop_event.is_set():
            output = next(itr, None)
            if output in commands:
                model.stop_transcription_stream()
                return output
        model.stop_transcription_stream()
        return None


    def look_for_gesture_command(self, camera: cv2.VideoCapture, model: GestureModel, stop_event: threading.Event) -> str | None:
        # TODO check if these are all possible commands
        commands = ["auf", "sitz", "platz"]

        while not stop_event.is_set():
            gesture = model.get_gesture()
            if gesture in commands:
                return gesture
        return None 


    def exit(self, machine: PrenMachine):
        self.stop_event.set()

        for thread in (self.audio_thread, self.gesture_thread):
            if thread and thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=1.0)
