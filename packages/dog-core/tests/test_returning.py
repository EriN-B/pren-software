"""Close the return controller's loop with measured wheel/IMU samples."""

import math
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from dog_core.odometry import Odometry
from dog_core.states import returning
from dog_core.uart import Uart


class Robot:
    def __init__(self, monkeypatch, *, origin_heading=350):
        self.path = Odometry()
        self.now = 0.0
        self.yaw = origin_heading
        self.left = 10.0
        self.right = 20.0
        self.speed = self.angle = 0.0
        self.turn_target = None
        self.stalled = False
        self.lose_odometry_at = math.inf
        self.commands = []
        self.positions = []
        self.sample(0, 0, 0)
        self.uart = Mock(spec=Uart)
        self.uart.stop.side_effect = self.stop
        self.uart.rotate.side_effect = self.rotate
        self.uart.drive.side_effect = self.drive
        self.uart.require_odometry.side_effect = self.require_odometry
        self.machine = SimpleNamespace(
            shared=SimpleNamespace(
                odometry=self.path, uart=self.uart, logger=Mock()
            ),
            returned=Mock(side_effect=lambda: self.commands.append(("returned",))),
        )
        monkeypatch.setattr(
            returning,
            "time",
            SimpleNamespace(monotonic=lambda: self.now, sleep=self.step),
        )

    def sample(self, distance, turn, elapsed=0.1):
        # A 20 cm differential drivetrain; the production recorder integrates
        # these cumulative encoders and wrapped IMU yaw, not the commands.
        self.left += distance + 0.1 * math.radians(turn)
        self.right += distance - 0.1 * math.radians(turn)
        self.yaw += turn
        self.now += elapsed
        self.path.record(
            timestamp=self.now,
            left_distance_m=self.left,
            right_distance_m=self.right,
            heading_deg=self.yaw % 360,
        )
        self.positions.append(self.path.pose)

    def outbound(self, distance=0, turn=0):
        steps = max(1, math.ceil(abs(distance) / 0.02), math.ceil(abs(turn) / 15))
        for _ in range(steps):
            self.sample(distance / steps, turn / steps)

    def stop(self):
        self.commands.append(("stop",))
        self.speed = self.angle = 0.0
        self.turn_target = None

    def rotate(self, degrees):
        self.commands.append(("rotate", degrees))
        self.speed = 0.0
        self.turn_target = self.yaw + degrees

    def drive(self, speed, angle):
        self.commands.append(("drive", speed, angle))
        self.speed, self.angle = speed, angle
        self.turn_target = None

    def require_odometry(self):
        if self.now >= self.lose_odometry_at:
            raise RuntimeError("No fresh odometry")

    def step(self, elapsed):
        assert self.now < 120, "Controller did not terminate"
        distance = turn = 0.0
        if not self.stalled:
            if self.turn_target is not None:
                turn = max(
                    -60 * elapsed, min(60 * elapsed, self.turn_target - self.yaw)
                )
            else:
                distance = self.speed * elapsed
                turn = self.angle * 2 * elapsed
        self.sample(distance, turn, elapsed)

    def assert_home(self):
        pose = self.path.pose
        assert math.hypot(pose.x, pose.y) <= returning.POSITION_TOLERANCE
        assert abs(pose.heading) <= returning.HEADING_TOLERANCE
        assert self.commands[-2:] == [("stop",), ("returned",)]
        self.machine.returned.assert_called_once_with()
        self.machine.shared.logger.exception.assert_not_called()


@pytest.mark.parametrize(
    "motions",
    [
        [(0.6, 0)],
        [(-0.6, 0)],
        [(0, 180), (0.6, 0)],
        [(0.5, 0), (0, 90), (0.5, 0)],
        [(0.5, 0), (0, -90), (0.5, 0)],
        [(0.5, 45), (0.5, -90)],
    ],
)
def test_returns_along_measured_route_and_restores_startup_heading(
    monkeypatch, motions
):
    robot = Robot(monkeypatch)
    for distance, turn in motions:
        robot.outbound(distance, turn)
    original_points = len(robot.path.waypoints)

    returning.enter(robot.machine)

    robot.assert_home()
    # Tracking continues during return, without extending the route being followed.
    assert len(robot.path.waypoints) > original_points
    assert all(
        0 < call.args[0] <= returning.MAX_SPEED
        for call in robot.uart.drive.call_args_list
    )


def test_follows_corner_instead_of_shortcutting_to_home(monkeypatch):
    robot = Robot(monkeypatch)
    robot.outbound(0.6)
    robot.outbound(turn=90)
    robot.outbound(0.6)
    robot.positions.clear()

    returning.enter(robot.machine)

    robot.assert_home()
    assert any(math.hypot(p.x - 0.6, p.y) < 0.06 for p in robot.positions)
    assert all(min(abs(p.x - 0.6), abs(p.y)) < 0.06 for p in robot.positions)


def test_already_home_checks_tracking_and_stays_stopped(monkeypatch):
    robot = Robot(monkeypatch)

    returning.enter(robot.machine)

    robot.assert_home()
    robot.uart.require_odometry.assert_called_once_with()
    robot.uart.rotate.assert_not_called()
    robot.uart.drive.assert_not_called()


def test_at_home_with_wrong_heading_only_turns(monkeypatch):
    robot = Robot(monkeypatch)
    robot.outbound(turn=170)

    returning.enter(robot.machine)

    robot.assert_home()
    robot.uart.rotate.assert_called_once_with(pytest.approx(-170))
    robot.uart.drive.assert_not_called()


def test_second_trip_stops_at_home_without_retracing_first_trip(monkeypatch):
    robot = Robot(monkeypatch)
    robot.outbound(0.5)
    returning.enter(robot.machine)
    robot.assert_home()
    robot.outbound(turn=90)
    robot.outbound(0.5)
    robot.machine.returned.reset_mock()
    robot.commands.clear()
    robot.positions.clear()

    returning.enter(robot.machine)

    robot.assert_home()
    assert max(abs(p.x) for p in robot.positions) < 0.06


@pytest.mark.parametrize("path", [None, Odometry()])
def test_missing_baseline_stops_without_claiming_returned(monkeypatch, path):
    robot = Robot(monkeypatch)
    robot.machine.shared.odometry = path

    returning.enter(robot.machine)

    robot.uart.drive.assert_not_called()
    robot.uart.rotate.assert_not_called()
    robot.machine.returned.assert_not_called()
    assert robot.commands[-1] == ("stop",)
    robot.machine.shared.logger.error.assert_called_once()


@pytest.mark.parametrize("turn_first", [False, True])
def test_fresh_but_stationary_odometry_times_out(monkeypatch, turn_first):
    robot = Robot(monkeypatch)
    robot.outbound(0.5)
    if not turn_first:
        robot.outbound(turn=180)
    robot.stalled = True
    started = robot.now

    returning.enter(robot.machine)

    robot.machine.returned.assert_not_called()
    robot.machine.shared.logger.exception.assert_called_once()
    assert robot.commands[-1] == ("stop",)
    assert robot.now - started < returning.PROGRESS_TIMEOUT + 0.2
    if turn_first:
        robot.uart.rotate.assert_called_once()
        robot.uart.drive.assert_not_called()
    else:
        robot.uart.rotate.assert_not_called()
        robot.uart.drive.assert_called()


@pytest.mark.parametrize("already_home", [False, True])
def test_lost_tracking_stops_without_claiming_returned(monkeypatch, already_home):
    robot = Robot(monkeypatch)
    if not already_home:
        robot.outbound(0.5)
    robot.lose_odometry_at = robot.now + (0 if already_home else 0.3)

    returning.enter(robot.machine)

    robot.machine.returned.assert_not_called()
    robot.machine.shared.logger.exception.assert_called_once()
    assert robot.commands[-1] == ("stop",)
    robot.uart.drive.assert_not_called()
    assert robot.uart.rotate.call_count == (0 if already_home else 1)


def test_exit_stops_motors(monkeypatch):
    robot = Robot(monkeypatch)
    returning.exit(robot.machine)
    assert robot.commands == [("stop",)]
