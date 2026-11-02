from __future__ import annotations
from typing import TYPE_CHECKING
import threading

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine

import cv2
import time
import sounddevice as sd
from dog_perception import GestureModel
from dog_recorder import AudioModel
import logging
from dog_perception.enum_prediction_type import PredictionType

class WaitingForCommand():
    def __init__(self):
        self.stop_event = threading.Event()
        self.command_semaphore = threading.Semaphore(1)
        self.audio_thread = None
        self.gesture_thread = None
        super().__init__()

    def enter(self, machine: PrenMachine):
        self.stop_event = threading.Event()
        self.command_semaphore = threading.Semaphore(1)
        
        def audio_worker():
            while not self.stop_event.is_set():
                # audio detection
                audio_command = self.listen_for_audio_command(
                    machine.shared.microphone,
                    machine.shared.audio_model,
                    self.stop_event
                )
                if audio_command and self.command_semaphore.acquire(blocking=False):
                    self.stop_event.set()
                    machine.shared.logger.info("Audio command: " + audio_command)
                    machine.send(audio_command)

        def gesture_worker():
            while not self.stop_event.is_set():
                # gesture detection
                gesture_command = self.look_for_gesture_command(
                    machine.shared.logger,
                    machine.shared.camera,
                    machine.shared.gesture_model,
                    self.stop_event
                )
                if gesture_command and self.command_semaphore.acquire(blocking=False):
                    self.stop_event.set()
                    machine.shared.logger.info("Gesture command: %s", gesture_command)
                    machine.send(gesture_command.value)

        self.audio_thread = threading.Thread(target=audio_worker, daemon=True)
        self.gesture_thread = threading.Thread(target=gesture_worker, daemon=True)

        self.audio_thread.start()
        self.gesture_thread.start()


    def listen_for_audio_command(self, mic: sd.RawInputStream, model: AudioModel, stop_event: threading.Event) -> str | None:
        commands = ["hier", "sitz", "platz", "auf", "such", "brav"]

        itr = model.get_transcription_stream(mic)

        while not stop_event.is_set():
            output = next(itr, None)
            if output in commands:
                model.stop_transcription_stream()
                return output
        model.stop_transcription_stream()
        return None


    def look_for_gesture_command(self, logger: logging.Logger, camera: cv2.VideoCapture, model: GestureModel, stop_event: threading.Event) -> str | None:
        commands = [PredictionType.AUF, PredictionType.SITZ, PredictionType.PLATZ]
        start = time.monotonic()
        while not stop_event.is_set():
            success, frame = camera.read()

            if not success:
                logger.error("Couldn't read from Camera")
                break

            # Timestamp in milliseconds
            timestamp_ms = int((time.monotonic() - start) * 1000)
            gesture = model.get_gesture(frame, timestamp_ms)
            if gesture in commands:
                return gesture
        return None 


    def exit(self):
        self.stop_event.set()

        for thread in (self.audio_thread, self.gesture_thread):
            if thread and thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=1.0)
