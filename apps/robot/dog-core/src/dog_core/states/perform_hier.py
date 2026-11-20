from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine

SHOE_STOP_WIDTH = 0.20
CLOSE_CONFIRMATION_FRAMES = 3
TARGET_LOST_TIMEOUT = 8.0


def enter(machine: PrenMachine) -> None:
    machine.shared.logger.info("Currently in state: perform_hier")
    machine.shared.uart.stop()
    person_box = None
    following_shoes = False
    close_frames = 0
    last_seen = time.monotonic()

    try:
        while True:
            success, frame = machine.shared.camera.read()
            if not success or frame is None:
                machine.shared.logger.error("Could not read camera frame for Hier")
                break

            result = machine.shared.object_model.get_people_and_shoes(frame)
            height, width = frame.shape[:2]
            people, shoes = [], []
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
                    if label == "person":
                        people.append((box, confidence))
                    elif label == "shoe":
                        shoes.append(box)

            person_visible = False
            if people:
                if person_box is None:
                    person_box = max(people, key=lambda detection: detection[1])[0]
                    person_visible = True
                else:
                    previous_x = (person_box[0] + person_box[2]) / 2
                    nearest = min(
                        people,
                        key=lambda detection: abs(
                            (detection[0][0] + detection[0][2]) / 2 - previous_x
                        ),
                    )[0]
                    if abs((nearest[0] + nearest[2]) / 2 - previous_x) <= width * 0.25:
                        person_box = nearest
                        person_visible = True

            related_shoes = []
            person_clipped = False
            if person_box is not None:
                x1, y1, x2, y2 = person_box
                margin = (x2 - x1) * 0.10
                related_shoes = [
                    shoe
                    for shoe in shoes
                    if x1 - margin <= (shoe[0] + shoe[2]) / 2 <= x2 + margin
                    and (shoe[1] + shoe[3]) / 2 >= y1 + (y2 - y1) * 0.60
                ]
                person_clipped = (
                    x1 <= width * 0.02
                    or x2 >= width * 0.98
                    or y1 <= height * 0.02
                    or y2 >= height * 0.98
                )

            shoe_width = (
                max((shoe[2] - shoe[0] for shoe in related_shoes), default=0) / width
            )
            if (
                related_shoes
                and not following_shoes
                and (
                    person_clipped
                    or not person_visible
                    or shoe_width >= SHOE_STOP_WIDTH
                )
            ):
                following_shoes = True
                machine.shared.logger.info("Switching Hier from person to shoes")

            target_x = None
            if following_shoes and related_shoes:
                # Aim between the associated shoes; size uses one shoe, not the pair.
                target_x = (
                    min(shoe[0] for shoe in related_shoes)
                    + max(shoe[2] for shoe in related_shoes)
                ) / 2
                speed = 0.03
            elif not following_shoes and person_visible and not person_clipped:
                target_x = (person_box[0] + person_box[2]) / 2
                person_height = (person_box[3] - person_box[1]) / height
                speed = max(0.03, 0.10 * (1 - person_height))

            if target_x is None:
                machine.shared.uart.stop()
                close_frames = 0
                if time.monotonic() - last_seen >= TARGET_LOST_TIMEOUT:
                    machine.shared.logger.info(
                        "Hier target not visible for 8 seconds; stopping"
                    )
                    break
                time.sleep(0.1)
                continue

            last_seen = time.monotonic()
            if following_shoes and shoe_width >= SHOE_STOP_WIDTH:
                machine.shared.uart.stop()
                close_frames += 1
                if close_frames >= CLOSE_CONFIRMATION_FRAMES:
                    machine.shared.logger.info(
                        "Person reached: shoes meet the configured size"
                    )
                    break
                time.sleep(0.1)
                continue

            close_frames = 0
            error = (target_x - width / 2) / (width / 2)
            angle = 0.0 if abs(error) <= 0.08 else error * 30
            machine.shared.uart.drive(speed, angle)
            time.sleep(0.1)
    except Exception:
        machine.shared.logger.exception("Hier approach failed")
    finally:
        machine.shared.uart.stop()

    machine.go_to_standing_idle()


def exit(machine: PrenMachine) -> None:
    machine.shared.uart.stop()
