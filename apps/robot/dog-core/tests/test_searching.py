"""Exercise bone detection dropouts with recorded frames and a fake clock."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from dog_core.states import searching

BONE = [80, 30, 120, 50]
CLOSING_BONES = ([80, 70, 120, 82], [80, 72, 120, 84], [80, 74, 120, 86])


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(
        searching,
        "time",
        SimpleNamespace(
            monotonic=lambda: now[0],
            sleep=lambda delay: now.__setitem__(0, now[0] + delay),
        ),
    )
    return now


def machine_for(*boxes):
    commands = []
    frame_number = [0]
    frame = SimpleNamespace(shape=(100, 200, 3))
    pending = iter(boxes)
    current = [None]

    def read():
        frame_number[0] += 1
        try:
            current[0] = next(pending)
        except StopIteration:
            return False, None
        return True, frame

    def detect(image):
        box = current[0]
        return SimpleNamespace(
            boxes=SimpleNamespace(
                xyxy=SimpleNamespace(tolist=lambda: [box] if box else []),
                conf=SimpleNamespace(tolist=lambda: [0.9] if box else []),
            )
        )

    machine = SimpleNamespace(
        shared=SimpleNamespace(
            camera=Mock(read=Mock(side_effect=read)),
            object_model=Mock(get_objects=Mock(side_effect=detect)),
            uart=Mock(),
            logger=Mock(),
        ),
        signal=Mock(),
    )
    machine.shared.uart.drive.side_effect = lambda speed, angle: commands.append(
        ("drive", frame_number[0])
    )
    machine.shared.uart.stop.side_effect = lambda: commands.append(
        ("stop", frame_number[0])
    )
    return machine, commands


@pytest.mark.parametrize("misses", [1, 2, 3, 4, 5])
def test_brief_dropout_keeps_driving_until_reacquisition(clock, misses):
    machine, commands = machine_for(BONE, *([None] * misses), BONE)

    searching.enter(machine)

    # Stops only after the initial turn and when the camera runs out of frames.
    assert commands == [
        ("stop", 0),
        ("drive", 1),
        ("drive", misses + 2),
        ("stop", misses + 3),
    ]
    machine.signal.assert_not_called()
    machine.shared.logger.exception.assert_not_called()


def test_six_consecutive_misses_stop_without_claiming_far_bone_found(clock):
    machine, commands = machine_for(BONE, *([None] * 6), BONE)

    searching.enter(machine)

    assert commands == [
        ("stop", 0),
        ("drive", 1),
        ("stop", 7),
        ("drive", 8),
        ("stop", 9),
    ]
    machine.signal.assert_not_called()
    machine.shared.logger.exception.assert_not_called()


def test_reacquisition_resets_consecutive_miss_count(clock):
    machine, commands = machine_for(BONE, *([None] * 5), BONE, *([None] * 6))

    searching.enter(machine)

    assert [number for action, number in commands if action == "stop"] == [0, 13, 14]
    machine.signal.assert_not_called()
    machine.shared.logger.exception.assert_not_called()


def test_close_bone_requires_three_misses_before_stopping_and_signalling(clock):
    machine, commands = machine_for(*CLOSING_BONES, None, None, None, BONE)
    machine.signal.side_effect = lambda: commands.append(("found", 6))

    searching.enter(machine)

    assert commands == [
        ("stop", 0),
        ("drive", 1),
        ("drive", 2),
        ("drive", 3),
        ("stop", 6),
        ("stop", 6),
        ("found", 6),
    ]
    assert machine.shared.camera.read.call_count == 6
    machine.signal.assert_called_once_with()
    machine.shared.logger.exception.assert_not_called()


def test_close_history_resets_when_bone_is_reacquired(clock):
    machine, commands = machine_for(
        *CLOSING_BONES, None, CLOSING_BONES[-1], *([None] * 6)
    )

    searching.enter(machine)

    assert [number for action, number in commands if action == "stop"] == [0, 11, 12]
    machine.signal.assert_not_called()
    machine.shared.logger.exception.assert_not_called()


def test_camera_failure_stops_even_during_dropout_tolerance(clock):
    machine, commands = machine_for(BONE, None)

    searching.enter(machine)

    assert commands == [("stop", 0), ("drive", 1), ("stop", 3)]
    machine.signal.assert_not_called()
    machine.shared.logger.error.assert_called_once_with("Could not read camera frame")


def test_detector_failure_stops_immediately(clock):
    machine, commands = machine_for(BONE, None)
    machine.shared.object_model.get_objects.side_effect = [
        SimpleNamespace(boxes=None),
        RuntimeError("detector failed"),
    ]

    searching.enter(machine)

    assert commands[-1] == ("stop", 2)
    machine.signal.assert_not_called()
    machine.shared.logger.exception.assert_called_once_with("Search failed")
