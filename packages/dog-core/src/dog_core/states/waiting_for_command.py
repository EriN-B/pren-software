from __future__ import annotations
from typing import TYPE_CHECKING
import threading
import re

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine

import cv2
import time
import sounddevice as sd
from dog_perception import GestureModel
from dog_recorder import AudioModel
import logging
from dog_perception.enum_gesture_type import GestureType

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
            try:
                machine.shared.microphone.start()
                while not self.stop_event.is_set():
                    # audio detection
                    audio_command = self.listen_for_audio_command(
                        machine.shared.microphone,
                        machine.shared.audio_model,
                        self.stop_event,
                        machine.shared.logger
                    )
                    if audio_command and self.command_semaphore.acquire(blocking=False):
                        self.stop_event.set()
                        machine.shared.microphone.stop()
                        machine.shared.logger.info("Audio command: " + audio_command)
                        machine.send(audio_command)
            except Exception:
                machine.shared.logger.exception("Audio worker failed")
            finally:
                machine.shared.microphone.stop()

        def gesture_worker():
            try:
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
            except Exception:
                machine.shared.logger.exception("Gesture worker failed")

        self.audio_thread = threading.Thread(target=audio_worker, daemon=True)
        self.gesture_thread = threading.Thread(target=gesture_worker, daemon=True)

        self.audio_thread.start()
        self.gesture_thread.start()


    def listen_for_audio_command(self, mic: sd.RawInputStream, model: AudioModel, stop_event: threading.Event, logger: logging.Logger) -> str | None:
        commands = ["hier", "sitz", "platz", "auf", "such", "brav"]

        itr = model.get_transcription_stream(mic, logger)

        try:
            while not stop_event.is_set():
                output = next(itr, None)

                if output is None:
                    return None

                words = re.findall(r"\w+", output.casefold())

                for word in words:
                    if word in commands:
                        return word
            return None
        finally:
            model.stop_transcription_stream()
            itr.close()

    def look_for_gesture_command(self, logger: logging.Logger, camera: cv2.VideoCapture, model: GestureModel, stop_event: threading.Event) -> str | None:
        commands = [GestureType.AUF, GestureType.SITZ, GestureType.PLATZ]
        while not stop_event.is_set():
            success, frame = camera.read()

            if not success:
                logger.error("Couldn't read from Camera")
                break

            # Timestamp in milliseconds
            timestamp_ms = time.monotonic_ns() // 1_000_000
            gesture = model.get_gesture(frame, timestamp_ms)
            
            if gesture in commands:
                candidate = gesture
                start = time.monotonic()
                consistent = True
                checks = 0

                while time.monotonic() - start < 0.75:
                    success, frame = camera.read()

                    if not success:
                        logger.error("Couldn't read from Camera")
                        break
                    
                    timestamp_ms = time.monotonic_ns() // 1_000_000
                    current = model.get_gesture(frame, timestamp_ms)
                    checks += 1

                    if current != candidate:
                        consistent = False
                        break
                    
                if not success:
                    break
                
                if consistent and checks >= 3:
                    return candidate
        return None 


    def exit(self):
        self.stop_event.set()

        for thread in (self.audio_thread, self.gesture_thread):
            if thread and thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=1.0)
