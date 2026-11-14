from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine

POSITION_TOLERANCE = 0.03  # metres
HEADING_TOLERANCE = 5.0  # degrees
TURN_THRESHOLD = 30.0  # turn in place above this heading error
TURN_TIMEOUT = 5.0  # seconds
PROGRESS_TIMEOUT = 8.0  # seconds without approaching the current waypoint
MAX_SPEED = 0.10  # metres per second
MIN_SPEED = 0.03
CONTROL_INTERVAL = 0.10


def enter(machine: PrenMachine) -> None:
    machine.shared.logger.info("Currently in state: returning")
    reached_home = False
    try:
        machine.shared.uart.stop()
        path = machine.shared.path_to_here
        if path is None or not path.initialized:
            machine.shared.logger.error(
                "Cannot return home without initialized odometry"
            )
            return

        home = path.home
        # Freeze the latest trip; the recorder also retains earlier returns.
        route = []
        for point in reversed(path.waypoints):
            if math.hypot(point.x - home.x, point.y - home.y) <= POSITION_TOLERANCE:
                break
            route.append(point)
        route.append(home)
        index = 0
        previous_index = -1
        best_distance = math.inf
        last_progress = time.monotonic()
        turn_target = None
        turn_started = 0.0
        machine.shared.logger.info("Returning along %d recorded waypoints", len(route))

        while True:
            machine.shared.uart.require_odometry()
            pose = path.pose
            now = time.monotonic()
            home_distance = math.hypot(home.x - pose.x, home.y - pose.y)
            at_home = home_distance <= POSITION_TOLERANCE

            if at_home:
                # Restore the startup heading once the position is close enough.
                desired_heading = home.heading
                heading_error = (desired_heading - pose.heading + 180) % 360 - 180
                if abs(heading_error) <= HEADING_TOLERANCE:
                    reached_home = True
                    break
            else:
                # Ignore duplicate positions recorded during turns in place.
                while (
                    index < len(route)
                    and math.hypot(route[index].x - pose.x, route[index].y - pose.y)
                    <= POSITION_TOLERANCE
                ):
                    index += 1
                target = route[index] if index < len(route) else home
                distance = math.hypot(target.x - pose.x, target.y - pose.y)
                if index != previous_index:
                    previous_index = index
                    best_distance = distance
                    last_progress = now
                    machine.shared.logger.info(
                        "Return waypoint %d/%d: x=%.3f, y=%.3f",
                        min(index + 1, len(route)),
                        len(route),
                        target.x,
                        target.y,
                    )
                if distance < best_distance - 0.005:
                    best_distance = distance
                    last_progress = now
                if now - last_progress >= PROGRESS_TIMEOUT:
                    raise TimeoutError("No progress towards return waypoint")
                desired_heading = math.degrees(
                    math.atan2(target.y - pose.y, target.x - pose.x)
                )
                heading_error = (desired_heading - pose.heading + 180) % 360 - 180

            if turn_target is not None:
                remaining = (turn_target - pose.heading + 180) % 360 - 180
                if abs(remaining) <= HEADING_TOLERANCE:
                    machine.shared.uart.stop()
                    turn_target = None
                elif now - turn_started >= TURN_TIMEOUT:
                    raise TimeoutError("Return turn did not reach its target heading")
                else:
                    time.sleep(CONTROL_INTERVAL)
                    continue

            if at_home or abs(heading_error) > TURN_THRESHOLD:
                machine.shared.logger.info(
                    "Turning %.1f degrees for return", heading_error
                )
                machine.shared.uart.rotate(heading_error)
                turn_target = desired_heading
                turn_started = now
            else:
                speed = max(MIN_SPEED, min(MAX_SPEED, distance * 2))
                angle = max(-TURN_THRESHOLD, min(TURN_THRESHOLD, heading_error))
                machine.shared.uart.drive(speed, angle)
            time.sleep(CONTROL_INTERVAL)
    except Exception:
        machine.shared.logger.exception("Return to home failed")
    finally:
        machine.shared.uart.stop()

    if reached_home:
        machine.shared.logger.info(
            "Returned home: x=%.3f, y=%.3f, heading=%.1f",
            pose.x,
            pose.y,
            pose.heading,
        )
        machine.returned()


def exit(machine: PrenMachine) -> None:
    machine.shared.uart.stop()
