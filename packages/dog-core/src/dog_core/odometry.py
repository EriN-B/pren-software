"""Wheel/IMU odometry in a fixed coordinate frame whose origin is home."""

import math
from dataclasses import dataclass
from threading import Event, Lock


@dataclass(frozen=True)
class Pose:
    """Startup-relative metres (x forwards, y right) and clockwise heading degrees."""

    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0


class Odometry:
    """Keep the startup origin, current pose and a trail of measured waypoints.

    Call record() for every sensor sample, in every state. Distances must be
    signed cumulative metres, increasing forwards on both wheels. Heading must
    be IMU yaw in clockwise degrees. Timestamp is the sensor's monotonic time
    in seconds. The first sample establishes the encoder and heading offsets;
    it must arrive while the robot is still at its startup position.
    """

    def __init__(self) -> None:
        self._pose = Pose()
        self._waypoints = [self._pose]
        self._previous: tuple[float, float, float, float] | None = None
        self._origin_heading = 0.0
        self._lock = Lock()
        self._ready = Event()

    @property
    def home(self) -> Pose:
        return self._waypoints[0]

    @property
    def pose(self) -> Pose:
        with self._lock:
            return self._pose

    @property
    def initialized(self) -> bool:
        with self._lock:
            return self._previous is not None

    def wait_until_initialized(self, timeout: float) -> bool:
        """Wait for the first sensor baseline before the robot may move."""
        return self._ready.wait(timeout)

    @property
    def waypoints(self) -> tuple[Pose, ...]:
        """An immutable snapshot including home and the exact current endpoint."""
        with self._lock:
            points = tuple(self._waypoints)
            return points if points[-1] == self._pose else (*points, self._pose)

    def record(
        self,
        *,
        timestamp: float,
        left_distance_m: float,
        right_distance_m: float,
        heading_deg: float,
    ) -> Pose:
        """Integrate one measured sample; reject invalid/out-of-order samples.

        Encoder totals must not reset during a run. Heading may wrap at 360
        degrees; samples must be frequent enough that each turn is under 180
        degrees. No movement is inferred from requested motor commands.
        """
        sample = (timestamp, left_distance_m, right_distance_m, heading_deg)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in sample
        ):
            raise ValueError("Odometry values must be finite numbers")
        with self._lock:
            if self._previous is None:
                self._previous = sample
                self._origin_heading = heading_deg
                self._ready.set()
                return self._pose

            previous_time, previous_left, previous_right, previous_heading = (
                self._previous
            )
            if timestamp <= previous_time:
                raise ValueError("Odometry timestamps must strictly increase")

            distance = (
                (left_distance_m - previous_left) + (right_distance_m - previous_right)
            ) / 2
            turn = (heading_deg - previous_heading + 180) % 360 - 180
            half_turn = math.radians(turn) / 2
            # Exact constant-curvature integration, including straight travel.
            chord = distance * (math.sin(half_turn) / half_turn if half_turn else 1.0)
            middle_heading = math.radians(self._pose.heading) + half_turn
            pose = Pose(
                self._pose.x + chord * math.cos(middle_heading),
                self._pose.y + chord * math.sin(middle_heading),
                (heading_deg - self._origin_heading + 180) % 360 - 180,
            )
            if not all(
                math.isfinite(value) for value in (pose.x, pose.y, pose.heading)
            ):
                raise ValueError("Odometry update must produce a finite pose")
            self._pose = pose
            self._previous = sample

            last = self._waypoints[-1]
            heading_change = (pose.heading - last.heading + 180) % 360 - 180
            if (
                math.hypot(pose.x - last.x, pose.y - last.y) >= 0.05
                or abs(heading_change) >= 5
            ):
                self._waypoints.append(pose)
            return pose
