"""Emulates the Raspberry Pi Pico 2 firmware: UART commands in, motors and odometry out.

The real Pico receives one JSON object per line from the Pi 4 (see ``JsonUartProtocol``
in ``dog_core.uart_protocol``) and drives the servos and the H-bridge. This module does
the same against the simulated robot, so the core cannot tell the difference.

It speaks two protocols at once, because the core and the team's interface definition
(2026-11-13, raw data up, commands down) do not agree yet:

| command        | parameters                      | effect                                   |
| -------------- | ------------------------------- | ---------------------------------------- |
| `wheels`       | `left_mm_s`, `right_mm_s`       | new: wheel target speeds; expire after `DRIVE_TIMEOUT` |
| `pose`         | `pose`: a key of `POSE_CODES`   | new: move the leg servos to that pose    |
| `drive`        | `speed` m/s, `angle` degrees    | old: drive; expires after `DRIVE_TIMEOUT` |
| `rotate`       | `degrees`, clockwise positive   | old: turn in place using the IMU heading |
| `stop`         |                                 | stop driving and turning                 |
| `auf` / `sitz` / `platz` / `vorderbeine_runter` | | move the leg servos to that posture |
| `brav`         |                                 | wag the tail                             |
| `signal_found` |                                 | shake the head                           |

Sent back: `measurements` (new, raw sensor values, see `measurements`) every 20 ms and
``{"type": "odometry", "timestamp", "left_distance_m", "right_distance_m", "heading_deg"}``
(old) every 50 ms.
"""

import logging
import math
from collections import deque

from dog_sim_host.world import World

log = logging.getLogger(__name__)

#: Leg servo targets in radians per posture. 0 = auf, legs nearly stretched;
#: positive lowers the body. Sitz lowers the rear, platz lowers everything,
#: vorderbeine_runter lowers the front for the bone approach (interface definition
#: 2026-11-13, pose VORDERBEINE_RUNTER).
#: Within the servo range in dog.xml (-0.6 to 0.8); see robot-model docs for the loads.
POSTURES = {
    "auf": {"front": 0.0, "rear": 0.0},
    "sitz": {"front": 0.0, "rear": 0.7},
    "platz": {"front": 0.75, "rear": 0.75},
    "vorderbeine_runter": {"front": 0.75, "rear": 0.0},
}
#: Pose codes of the interface definition and the posture each one moves to.
POSE_CODES = {
    "STEHEN": "auf",
    "SITZ": "sitz",
    "PLATZ": "platz",
    "VORDERBEINE_RUNTER": "vorderbeine_runter",
}
SONAR_RANGE = 4.0  # m; HC-SR04 class sensor, beyond it the Pico reports no distance
SERVO_SPEED = 4.0  # rad/s; hobby servos move about 60 degrees in 0.15-0.25 s
DRIVE_TIMEOUT = 0.5  # s; the dog stops if the core stops sending drive commands
TURN_RATE = math.radians(90)  # rad/s for rotate
TURN_TOLERANCE = 2.0  # degrees
TRICK_SECONDS = 2.0  # how long brav and signal_found move tail or head


class PicoFirmware:
    """The Pico's job, done in simulation.

    Call `handle` for each incoming UART message, `control` before every physics
    step, and `odometry` whenever the Pico would report its sensors.

    Args:
        world: The simulated world whose actuators this firmware drives.
    """

    def __init__(self, world: World) -> None:
        self.world = world
        model = world.model
        # Geometry is read from dog.xml so the model stays the single source of truth.
        self.wheel_radius = float(model.geom("wheel_left").size[0])
        self.track_width = abs(
            world.data.body("wheel_left").xpos[1]
            - world.data.body("wheel_right").xpos[1]
        )
        self.wheelbase = abs(
            world.data.body("wheel_left").xpos[0]
            - world.data.geom("caster_rear_left").xpos[0]
        )
        self._wheels = [model.actuator(n).id for n in ("wheel_left", "wheel_right")]
        self._wheel_gain = float(model.actuator_gainprm[self._wheels[0], 0])
        self._servo_joints = [
            f"servo_{end}_{side}"
            for end in ("front", "rear")
            for side in ("left", "right")
        ]
        self.posture = "auf"
        self.emergency_stop = False
        #: Last messages received, newest last, for the viewer's UART log.
        self.log: deque[dict] = deque(maxlen=12)
        self._servo = {name: 0.0 for name in ("front", "rear")}
        self._drive: tuple[float, float, float] | None = None  # speed, angle, time
        self._wheel_targets: tuple[float, float, float] | None = (
            None  # left, right m/s, time
        )
        self._turn_target: float | None = None  # clockwise heading in degrees
        self._wag_until = 0.0
        self._shake_until = 0.0
        self._time_offset = 0.0  # keeps odometry timestamps increasing across resets

    def handle(self, message: dict) -> None:
        """Act on one decoded UART message from the core (or the viewer).

        Raises:
            KeyError, ValueError, TypeError: A field is missing or has the wrong type.
        """
        self.log.append(message)
        command = message.get("command")
        now = self.world.time
        if command in ("wheels", "drive", "rotate", "stop"):
            self._drive = self._wheel_targets = self._turn_target = None
        if command == "wheels":
            left, right = float(message["left_mm_s"]), float(message["right_mm_s"])
            self._wheel_targets = (left / 1000, right / 1000, now)
        elif command == "pose":
            self.posture = POSE_CODES[message["pose"]]
        elif command == "drive":
            self._drive = (float(message["speed"]), float(message["angle"]), now)
        elif command == "rotate":
            self._turn_target = (
                self.world.heading_cw() + float(message["degrees"])
            ) % 360
        elif command == "stop":
            pass
        elif command in POSTURES:
            self.posture = command
        elif command == "brav":
            self._wag_until = now + TRICK_SECONDS
        elif command == "signal_found":
            self._shake_until = now + TRICK_SECONDS
        else:
            log.warning("Pico ignores unknown message: %s", message)

    def control(self) -> None:
        """Set every actuator target for the next physics step."""
        data, now = self.world.data, self.world.time
        step = SERVO_SPEED * self.world.model.opt.timestep
        legs_moving = any(
            abs(self._servo[leg] - target) > 1e-6
            for leg, target in POSTURES[self.posture].items()
        ) or any(abs(data.joint(name).qvel[0]) > 0.05 for name in self._servo_joints)
        for leg, target in POSTURES[self.posture].items():
            # Servos move at a limited speed instead of jumping to the target.
            current = self._servo[leg]
            self._servo[leg] = current + max(-step, min(step, target - current))
        data.actuator("hip_front_left").ctrl = self._servo["front"]
        data.actuator("hip_front_right").ctrl = self._servo["front"]
        data.actuator("hip_rear_left").ctrl = self._servo["rear"]
        data.actuator("hip_rear_right").ctrl = self._servo["rear"]
        wag = now < self._wag_until
        shake = now < self._shake_until
        data.actuator("tail").ctrl = 0.7 * math.sin(now * 18) if wag else 0.0
        data.actuator("neck").ctrl = 0.5 * math.sin(now * 12) if shake else 0.0

        speed, turn_cw = self._motion(now)
        # H-bridge: coast while the legs move, so the wheels roll as the legs spread
        # (braked, the servos stall); otherwise hold the wheel speed, which brakes at 0.
        coast = legs_moving and not (speed or turn_cw or self.emergency_stop)
        self._set_wheel_gain(0.0 if coast else self._wheel_gain)
        offset = turn_cw * self.track_width / 2
        data.actuator("wheel_left").ctrl = (speed + offset) / self.wheel_radius
        data.actuator("wheel_right").ctrl = (speed - offset) / self.wheel_radius

    def _set_wheel_gain(self, gain: float) -> None:
        """Velocity-control gain of both wheel motors; zero lets them coast."""
        model = self.world.model
        for actuator in self._wheels:
            model.actuator_gainprm[actuator, 0] = gain
            model.actuator_biasprm[actuator, 2] = -gain

    def odometry(self) -> dict:
        """The sensor report the Pico sends back over UART."""
        return {
            "type": "odometry",
            "timestamp": round(self._time_offset + self.world.time, 4),
            "left_distance_m": float(self.world.sensor("encoder_left")[0])
            * self.wheel_radius,
            "right_distance_m": float(self.world.sensor("encoder_right")[0])
            * self.wheel_radius,
            "heading_deg": self.world.heading_cw(),
        }

    def measurements(self) -> dict:
        """The raw sensor packet of the interface definition; the Pico interprets nothing.

        Axes are the torso's: x forwards, y left, z up. Servo positions are the last
        commanded angles, because hobby servos do not report theirs.
        """
        world, data = self.world, self.world.data
        distance = float(world.sensor("sonar")[0])  # -1 when the ray hits nothing
        packet = {
            "type": "measurements",
            "timestamp": round(self._time_offset + world.time, 4),
            "distance_mm": round(distance * 1000)
            if 0 <= distance <= SONAR_RANGE
            else None,
            "accel_m_s2": [round(float(v), 2) for v in world.sensor("imu_accel")],
            "gyro_deg_s": [round(math.degrees(v), 1) for v in world.sensor("imu_gyro")],
        }
        for side in ("left", "right"):
            packet[f"encoder_{side}"] = {
                "rpm": round(
                    float(data.joint(f"wheel_{side}").qvel[0]) * 60 / math.tau, 1
                ),
                "angle_deg": round(math.degrees(world.sensor(f"encoder_{side}")[0]), 1),
            }
        packet["servos_deg"] = {
            name: round(math.degrees(data.actuator(name).ctrl[0]), 1)
            for name in (
                *(j.replace("servo_", "hip_") for j in self._servo_joints),
                "neck",
                "tail",
            )
        }
        packet["emergency_stop"] = self.emergency_stop
        return packet

    def reset_with_world(self) -> None:
        """Reset the world and this firmware together.

        Odometry timestamps keep increasing, but the encoders restart at zero, so a
        running core loses its home tracking: restart the core after a reset.
        """
        offset = self._time_offset + self.world.time
        self.world.reset()
        self.__init__(self.world)
        self._time_offset = offset

    @property
    def status(self) -> dict:
        """What the Pico is doing, for the viewer."""
        speed, turn = self._motion(self.world.time)
        return {
            "posture": self.posture,
            "emergency_stop": self.emergency_stop,
            "speed": round(speed, 3),
            "turn_rate_deg": round(math.degrees(turn), 1),
            "turning_to": self._turn_target,
            "log": list(self.log),
        }

    def _motion(self, now: float) -> tuple[float, float]:
        """Forward speed in m/s and clockwise turn rate in rad/s right now."""
        if self.emergency_stop:
            return 0.0, 0.0
        if self._turn_target is not None:
            error = (self._turn_target - self.world.heading_cw() + 180) % 360 - 180
            if abs(error) <= TURN_TOLERANCE:
                self._turn_target = None
                return 0.0, 0.0
            # Slow down over the last degrees so the turn does not overshoot.
            rate = min(TURN_RATE, math.radians(abs(error)) * 3)
            return 0.0, math.copysign(rate, error)
        if self._wheel_targets is not None:
            left, right, since = self._wheel_targets
            if now - since <= DRIVE_TIMEOUT:
                return (left + right) / 2, (left - right) / self.track_width
            self._wheel_targets = None
        if self._drive is not None:
            speed, angle, since = self._drive
            if now - since <= DRIVE_TIMEOUT:
                # Assumption: angle is a steering angle, like a bicycle with this wheelbase.
                return speed, speed * math.tan(math.radians(angle)) / self.wheelbase
            self._drive = None
        return 0.0, 0.0
