from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine

TURN_WAIT_SECONDS = 3.0
CLOSE_FRAME_FRACTION = 0.75
# Keep the last drive command through brief detection dropouts.
LOST_BONE_STOP_FRAMES = 6
MISSING_CONFIRMATION_FRAMES = 3


def enter(machine: PrenMachine) -> None:
    machine.shared.logger.info("Currently in state: searching (such)")
    creep_started = None
    bone_seen = False
    previous_center_y = None
    downward_movements = 0
    bone_close = False
    missing_frames = 0

    try:
        machine.shared.logger.info("Turning 180 degrees before searching")
        machine.shared.uart.rotate(180)
        time.sleep(TURN_WAIT_SECONDS)
        machine.shared.uart.stop()

        while True:
            if creep_started is not None and time.monotonic() - creep_started >= 8:
                machine.shared.logger.info("No bone found after 8 seconds; stopping")
                return

            success, frame = machine.shared.camera.read()
            if not success or frame is None:
                machine.shared.logger.error("Could not read camera frame")
                return

            result = machine.shared.object_model.get_objects(frame)
            boxes = result.boxes.xyxy.tolist() if result.boxes is not None else []
            confidences = result.boxes.conf.tolist() if result.boxes is not None else []
            for box, confidence in zip(boxes, confidences):
                machine.shared.logger.info(
                    "Bone bounding box: x1=%.1f, y1=%.1f, x2=%.1f, y2=%.1f, confidence=%.3f",
                    *box,
                    confidence,
                )

            if creep_started is not None and time.monotonic() - creep_started >= 8:
                machine.shared.logger.info("No bone found after 8 seconds; stopping")
                return

            if not boxes:
                if bone_seen:
                    missing_frames += 1
                    stop_after = (
                        MISSING_CONFIRMATION_FRAMES
                        if bone_close
                        else LOST_BONE_STOP_FRAMES
                    )
                    if missing_frames >= stop_after:
                        machine.shared.uart.stop()
                    if missing_frames == stop_after:
                        machine.shared.logger.info(
                            "Bone missing for %d frames; stopping (previously close: %s)",
                            missing_frames,
                            bone_close,
                        )
                    if bone_close and missing_frames >= MISSING_CONFIRMATION_FRAMES:
                        machine.shared.logger.info(
                            "Close bone has left the frame; transitioning to found"
                        )
                        break
                elif creep_started is None:
                    machine.shared.logger.info("No bone visible; creeping forward")
                    creep_started = time.monotonic()
                    machine.shared.uart.drive(0.03, 0.0)
                time.sleep(0.1)
                continue

            bone_seen = True
            creep_started = None
            if missing_frames:
                # Reacquisition starts a fresh movement history.
                previous_center_y = None
                downward_movements = 0
            missing_frames = 0
            box, _ = max(zip(boxes, confidences), key=lambda detection: detection[1])
            x1, y1, x2, y2 = box
            height, width = frame.shape[:2]

            error = ((x1 + x2) / 2 - width / 2) / (width / 2)
            center_y = (y1 + y2) / (2 * height)
            if abs(error) <= 0.08 and center_y >= CLOSE_FRAME_FRACTION:
                if previous_center_y is not None:
                    # Ignore vertical jitter smaller than 0.5% of frame height.
                    if center_y > previous_center_y + 0.005:
                        downward_movements += 1
                    elif center_y < previous_center_y - 0.005:
                        downward_movements = 0
            else:
                downward_movements = 0
            close_now = downward_movements >= 2
            if close_now and not bone_close:
                machine.shared.logger.info(
                    "Bone is centered, low in frame, and moving down"
                )
            bone_close = close_now
            previous_center_y = center_y

            angle = 0.0 if abs(error) <= 0.08 else error * 30
            speed = max(0.03, 0.1 * (1 - (x2 - x1) / width))
            machine.shared.uart.drive(speed, angle)
            time.sleep(0.1)
    except Exception:
        machine.shared.logger.exception("Search failed")
        return
    finally:
        machine.shared.uart.stop()

    machine.signal()


def exit(machine: PrenMachine) -> None:
    machine.shared.uart.stop()
