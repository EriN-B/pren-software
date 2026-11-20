from __future__ import annotations

import re
import threading
from contextlib import closing
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine

import logging
import time

import cv2
from dog_perception import GestureModel
from dog_perception.enum_gesture_type import GestureType


class CommandRecognition:
    def __init__(self):
        self.stop_event = threading.Event()
        self.audio_thread = None
        self.gesture_thread = None
        self.audio_lock = threading.Lock()
        self.gesture_lock = threading.Lock()

    def start(self, machine: PrenMachine):
        self.stop_event.set()
        stop_event = threading.Event()
        command_semaphore = threading.Semaphore(1)
        ready = threading.Event()
        self.stop_event = stop_event

        def accept(command):
            if stop_event.is_set() or not any(
                event.id == command for event in machine.allowed_events
            ):
                return False
            if not command_semaphore.acquire(blocking=False) or stop_event.is_set():
                return False
            stop_event.set()
            return True

        def audio_worker():
            try:
                ready.wait()
                if not self.audio_lock.acquire(timeout=1.0):
                    if not stop_event.is_set():
                        machine.shared.logger.error(
                            "Audio recognition could not start: microphone is still in use"
                        )
                    return
                try:
                    if stop_event.is_set():
                        return
                    command = None
                    machine.shared.microphone.start()
                    try:
                        with closing(
                            machine.shared.audio_model.get_transcription_stream(
                                machine.shared.microphone,
                                machine.shared.logger,
                                stop_event,
                            )
                        ) as stream:
                            for output in stream:
                                if stop_event.is_set():
                                    break
                                for word in re.findall(r"\w+", output.casefold()):
                                    if word in (
                                        "hier",
                                        "sitz",
                                        "platz",
                                        "auf",
                                        "such",
                                        "brav",
                                    ) and accept(word):
                                        command = word
                                        break
                                if stop_event.is_set():
                                    break
                    finally:
                        try:
                            machine.shared.microphone.stop()
                        except Exception:
                            machine.shared.logger.exception(
                                "Stopping microphone failed"
                            )
                finally:
                    self.audio_lock.release()
                # The next state can start recognition as soon as the command is sent.
                if command and self.stop_event is stop_event:
                    machine.shared.logger.info("Audio command: %s", command)
                    machine.send(command)
            except Exception:
                machine.shared.logger.exception("Audio worker failed")

        def gesture_worker():
            try:
                ready.wait()
                if not self.gesture_lock.acquire(timeout=1.0):
                    if not stop_event.is_set():
                        machine.shared.logger.error(
                            "Gesture recognition could not start: camera is still in use"
                        )
                    return
                try:
                    command = None
                    while not stop_event.is_set():
                        candidate = self.look_for_gesture_command(
                            machine.shared.logger,
                            machine.shared.camera,
                            machine.shared.gesture_model,
                            stop_event,
                        )
                        if candidate and accept(candidate.value):
                            command = candidate.value
                            break
                finally:
                    self.gesture_lock.release()
                if command and self.stop_event is stop_event:
                    machine.shared.logger.info("Gesture command: %s", command)
                    machine.send(command)
            except Exception:
                machine.shared.logger.exception("Gesture worker failed")

        self.audio_thread = threading.Thread(
            target=audio_worker, name="Audio recognition", daemon=True
        )
        self.gesture_thread = threading.Thread(
            target=gesture_worker, name="Gesture recognition", daemon=True
        )
        try:
            self.audio_thread.start()
            self.gesture_thread.start()
        except Exception:
            stop_event.set()
            machine.shared.logger.exception("Starting command recognition failed")
        finally:
            ready.set()

    def stop(self, machine: PrenMachine):
        self.stop_event.set()
        deadline = time.monotonic() + 1.0
        for worker in (self.audio_thread, self.gesture_thread):
            if (
                worker
                and worker is not threading.current_thread()
                and worker.ident is not None
            ):
                worker.join(timeout=max(0.0, deadline - time.monotonic()))
                if worker.is_alive():
                    machine.shared.logger.error(
                        "%s did not stop within one second", worker.name
                    )

    def look_for_gesture_command(
        self,
        logger: logging.Logger,
        camera: cv2.VideoCapture,
        model: GestureModel,
        stop_event: threading.Event,
    ) -> str | None:
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

                while time.monotonic() - start < 0.75 and not stop_event.is_set():
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

                if consistent and checks >= 3 and not stop_event.is_set():
                    return candidate
        return None
