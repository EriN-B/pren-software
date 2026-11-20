import math
from dataclasses import FrozenInstanceError

import pytest
from dog_core.odometry import Odometry, Pose


def record(path, timestamp, distance, heading=0, right=None):
    return path.record(
        timestamp=timestamp,
        left_distance_m=distance,
        right_distance_m=distance if right is None else right,
        heading_deg=heading,
    )


def assert_pose(pose, x, y, heading):
    assert (pose.x, pose.y, pose.heading) == pytest.approx((x, y, heading), abs=1e-10)


def test_first_sample_establishes_home_without_counting_old_encoder_totals():
    path = Odometry()
    assert not path.initialized
    assert not path.wait_until_initialized(0)
    record(path, 100, 123, heading=271, right=456)
    assert path.initialized
    assert path.wait_until_initialized(0)
    assert path.pose == path.home == Pose()
    assert path.waypoints == (Pose(),)
    record(path, 101, 124, heading=271, right=457)
    assert_pose(path.pose, 1, 0, 0)
    assert path.home == Pose()


def test_forward_reverse_and_unequal_wheel_distances():
    path = Odometry()
    record(path, 0, 0)
    record(path, 1, 2, right=1)
    assert_pose(path.pose, 1.5, 0, 0)
    record(path, 2, 0, right=0)
    assert_pose(path.pose, 0, 0, 0)


def test_initial_180_turn_is_recorded_without_resetting_home():
    path = Odometry()
    record(path, 0, 0, 37)
    record(path, 1, 0.1, 127, right=-0.1)
    record(path, 2, 0.2, 217, right=-0.2)
    assert_pose(path.pose, 0, 0, -180)
    record(path, 3, 1.2, 217, right=0.8)
    assert_pose(path.pose, -1, 0, -180)
    assert path.home == Pose()


@pytest.mark.parametrize("start,end,expected", [(359, 1, 2), (1, 359, -2)])
def test_heading_wrap_uses_short_turn(start, end, expected):
    path = Odometry()
    record(path, 0, 0, start)
    pose = record(path, 1, 1, end)
    turn = math.radians(expected)
    assert_pose(pose, math.sin(turn) / turn, (1 - math.cos(turn)) / turn, expected)


@pytest.mark.parametrize("direction", [-1, 1])
def test_quarter_circle_uses_arc_geometry(direction):
    path = Odometry()
    record(path, 0, 0)
    pose = record(path, 1, math.pi / 2, direction * 90)
    assert_pose(pose, 1, direction, direction * 90)


def test_square_returns_to_startup_home_in_same_coordinate_frame():
    path = Odometry()
    record(path, 0, 0, 123)
    timestamp = 0
    for leg in range(4):
        timestamp += 1
        record(path, timestamp, leg + 1, 123 + leg * 90)
        timestamp += 1
        record(path, timestamp, leg + 1, 123 + (leg + 1) * 90)
    assert_pose(path.pose, 0, 0, 0)
    assert path.home == Pose()


def test_waypoints_are_spaced_and_always_include_current_endpoint():
    path = Odometry()
    record(path, 0, 0)
    record(path, 1, 0.03)
    snapshot = path.waypoints
    assert snapshot == (Pose(), Pose(0.03, 0, 0))
    record(path, 2, 0.06)
    assert path.waypoints == (Pose(), Pose(0.06, 0, 0))
    assert snapshot == (Pose(), Pose(0.03, 0, 0))
    record(path, 3, 0.06, 10)
    assert path.waypoints[-1] == Pose(0.06, 0, 10)
    # Freeze this snapshot before following the route home.
    route_back = tuple(reversed(path.waypoints))
    record(path, 4, 0.07, 10)
    assert route_back[-1] == path.home
    assert route_back[0] == Pose(0.06, 0, 10)


def test_home_pose_cannot_be_mutated():
    path = Odometry()
    with pytest.raises(FrozenInstanceError):
        path.home.x = 99
    with pytest.raises(AttributeError):
        path.home = Pose(99, 0, 0)


def test_overflow_does_not_corrupt_pose_or_previous_sample():
    path = Odometry()
    record(path, 0, -1e308)
    with pytest.raises(ValueError, match="finite pose"):
        record(path, 1, 1e308)
    assert path.pose == path.home == Pose()
    record(path, 2, -1e308)
    assert path.pose == Pose()


@pytest.mark.parametrize("timestamp", [9, 10])
def test_stale_sample_is_rejected_without_corrupting_next_update(timestamp):
    path = Odometry()
    record(path, 10, 50)
    with pytest.raises(ValueError, match="timestamps"):
        record(path, timestamp, 1000, 90)
    record(path, 11, 51)
    assert_pose(path.pose, 1, 0, 0)


@pytest.mark.parametrize(
    "field", ["timestamp", "left_distance_m", "right_distance_m", "heading_deg"]
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "12", None])
def test_invalid_readings_do_not_establish_a_baseline(field, value):
    path = Odometry()
    reading = {
        "timestamp": 0,
        "left_distance_m": 0,
        "right_distance_m": 0,
        "heading_deg": 0,
    }
    reading[field] = value
    with pytest.raises(ValueError):
        path.record(**reading)
    assert not path.initialized
    assert path.pose == path.home == Pose()
