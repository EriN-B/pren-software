from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine

APPROACH_SPEED = 0.03
HEAD_TILT_DEG = 30.0
TARGET_LOST_TIMEOUT = 8.0


def enter(machine: PrenMachine) -> None:
    machine.shared.logger.info("Currently in state: perform_hier")

    try:
        machine.shared.uart.stop()
        machine.shared.uart.head_tilt(HEAD_TILT_DEG)
        started = time.monotonic()

        while time.monotonic() - started < TARGET_LOST_TIMEOUT:
            success, frame = machine.shared.camera.read()
            if not success or frame is None:
                machine.shared.logger.error("Could not read camera frame for Hier")
                break

            result = machine.shared.object_model.get_people_and_shoes(frame)
            shoes_visible = False
            if result.boxes is not None:
                for box, confidence, class_id in zip(
                    result.boxes.xyxy.tolist(),
                    result.boxes.conf.tolist(),
                    result.boxes.cls.tolist(),
                ):
                    label = result.names[int(class_id)]
                    machine.shared.logger.info(
                        "%s bounding box: x1=%.1f, y1=%.1f, x2=%.1f, y2=%.1f, confidence=%.3f",
                        label.capitalize(),
                        *box,
                        confidence,
                    )
                    if label == "shoe":
                        shoes_visible = True

            if shoes_visible:
                machine.shared.logger.info("Shoes visible; stopping Hier approach")
                break

            # Inference counts towards the timeout, too.
            if time.monotonic() - started >= TARGET_LOST_TIMEOUT:
                machine.shared.logger.info("No shoes found within 8 seconds; stopping")
                break

            machine.shared.uart.drive(APPROACH_SPEED, 0.0)
            time.sleep(0.1)
        else:
            machine.shared.logger.info("No shoes found within 8 seconds; stopping")
    except Exception:
        machine.shared.logger.exception("Hier approach failed")
    finally:
        machine.shared.uart.stop()

    machine.go_to_standing_idle()


def exit(machine: PrenMachine) -> None:
    machine.shared.uart.stop()
