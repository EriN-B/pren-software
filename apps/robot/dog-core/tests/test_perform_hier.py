"""Exercise head-down shoe approach with recorded detections and a fake clock."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from dog_core.states import perform_hier
from dog_core.uart import Uart

PERSON = [40, 10, 120, 90]
CROPPED = [40, 0, 160, 100]
SHOE = [70, 80, 90, 95]
CLOSE_SHOE = [70, 80, 110, 95]


def detections(person=None, shoes=()):
    boxes = ([person] if person is not None else []) + list(shoes)
    return SimpleNamespace(
        names={0: "person", 1: "shoe"},
        boxes=SimpleNamespace(
            xyxy=SimpleNamespace(tolist=lambda: boxes),
            conf=SimpleNamespace(tolist=lambda: [0.9] * len(boxes)),
            cls=SimpleNamespace(
                tolist=lambda: ([0] if person is not None else []) + [1] * len(shoes)
            ),
        ),
    )


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(
        perform_hier,
        "time",
        SimpleNamespace(
            monotonic=lambda: now[0],
            sleep=lambda delay: now.__setitem__(0, now[0] + delay),
        ),
    )
    return now


def machine_for(*frames, repeat_empty=False):
    commands = []
    pending = iter(frames)
    frame = SimpleNamespace(shape=(100, 200, 3))
    model = Mock()
    current = [None]

    def read():
        try:
            current[0] = next(pending)
        except StopIteration:
            if not repeat_empty:
                return False, None
            current[0] = detections()
        return True, frame

    camera = Mock()
    camera.read.side_effect = read
    model.get_people_and_shoes.side_effect = lambda image: current[0]
    uart = Mock(spec=Uart)
    uart.drive.side_effect = lambda speed, angle: commands.append(
        ("drive", speed, angle)
    )
    uart.stop.side_effect = lambda: commands.append(("stop",))
    uart.head_tilt.side_effect = lambda deg: commands.append(("head_tilt", deg))
    machine = SimpleNamespace(
        shared=SimpleNamespace(
            camera=camera, object_model=model, uart=uart, logger=Mock()
        ),
        go_to_standing_idle=Mock(side_effect=lambda: commands.append(("idle",))),
    )
    return machine, commands


def test_lowers_head_and_creeps_until_first_shoe_then_returns_to_command_wait(clock):
    machine, commands = machine_for(
        detections(),
        detections(PERSON),
        detections(shoes=[SHOE]),
        detections(),
    )
    perform_hier.enter(machine)
    assert commands == [
        ("stop",),
        ("head_tilt", 30.0),
        ("drive", 0.03, 0.0),
        ("drive", 0.03, 0.0),
        ("stop",),
        ("idle",),
    ]
    assert machine.shared.camera.read.call_count == 3
    machine.go_to_standing_idle.assert_called_once_with()
    machine.shared.uart.rotate.assert_not_called()
    machine.shared.logger.exception.assert_not_called()


@pytest.mark.parametrize("person", [None, PERSON, CROPPED])
@pytest.mark.parametrize("shoe", [SHOE, CLOSE_SHOE, [170, 80, 175, 90]])
def test_any_shoe_stops_without_needing_person_size_or_confirmation(
    clock, person, shoe
):
    machine, commands = machine_for(detections(person, [shoe]), detections())
    perform_hier.enter(machine)
    assert commands == [("stop",), ("head_tilt", 30.0), ("stop",), ("idle",)]
    assert machine.shared.camera.read.call_count == 1
    machine.shared.uart.drive.assert_not_called()
    machine.shared.logger.exception.assert_not_called()


@pytest.mark.parametrize("person", [PERSON, CROPPED])
def test_person_alone_does_not_stop_or_change_straight_creep(clock, person):
    machine, commands = machine_for(detections(person), detections(shoes=[SHOE]))
    perform_hier.enter(machine)
    machine.shared.uart.drive.assert_called_once_with(0.03, 0.0)
    assert commands[-2:] == [("stop",), ("idle",)]


def test_missing_boxes_keep_creeping(clock):
    machine, commands = machine_for(
        SimpleNamespace(boxes=None), detections(shoes=[SHOE])
    )
    perform_hier.enter(machine)
    machine.shared.uart.drive.assert_called_once_with(0.03, 0.0)
    assert commands[-2:] == [("stop",), ("idle",)]
    machine.shared.logger.exception.assert_not_called()


def test_no_shoes_times_out_and_stops_before_returning_to_command_wait(clock):
    machine, commands = machine_for(repeat_empty=True)
    perform_hier.enter(machine)
    assert machine.shared.uart.drive.call_count > 0
    assert all(
        call.args == (0.03, 0.0) for call in machine.shared.uart.drive.call_args_list
    )
    assert perform_hier.TARGET_LOST_TIMEOUT <= clock[0] < 8.11
    assert commands[-2:] == [("stop",), ("idle",)]
    machine.shared.logger.exception.assert_not_called()


def test_slow_inference_counts_towards_timeout_without_driving(clock):
    machine, commands = machine_for(detections())

    def detect(image):
        clock[0] += 9.0
        return detections()

    machine.shared.object_model.get_people_and_shoes.side_effect = detect
    perform_hier.enter(machine)
    machine.shared.uart.drive.assert_not_called()
    assert commands[-2:] == [("stop",), ("idle",)]


def test_camera_failure_stops_and_returns_to_command_wait(clock):
    machine, commands = machine_for(detections())
    perform_hier.enter(machine)
    machine.shared.uart.drive.assert_called_once_with(0.03, 0.0)
    machine.shared.logger.error.assert_called_once()
    assert commands[-2:] == [("stop",), ("idle",)]


def test_head_is_lowered_before_camera_is_read(clock):
    machine, _ = machine_for(detections(shoes=[SHOE]))
    machine.shared.uart.head_tilt.side_effect = lambda deg: (
        machine.shared.camera.read.assert_not_called()
    )
    perform_hier.enter(machine)
    machine.shared.uart.head_tilt.assert_called_once_with(30.0)
    assert machine.shared.camera.read.call_count == 1


def test_head_command_failure_stops_without_driving(clock):
    machine, commands = machine_for(detections())
    machine.shared.uart.head_tilt.side_effect = RuntimeError("head failed")
    perform_hier.enter(machine)
    machine.shared.uart.drive.assert_not_called()
    machine.shared.camera.read.assert_not_called()
    machine.shared.logger.exception.assert_called_once()
    assert commands[-2:] == [("stop",), ("idle",)]


def test_model_failure_stops_and_returns_to_command_wait(clock):
    machine, commands = machine_for(detections(PERSON))
    machine.shared.object_model.get_people_and_shoes.side_effect = RuntimeError(
        "model failed"
    )
    perform_hier.enter(machine)
    machine.shared.uart.drive.assert_not_called()
    machine.shared.logger.exception.assert_called_once()
    assert commands[-2:] == [("stop",), ("idle",)]


def test_logs_each_person_and_shoe_box(clock):
    machine, _ = machine_for(detections(CROPPED, [SHOE, CLOSE_SHOE]))
    perform_hier.enter(machine)
    boxes = [
        call
        for call in machine.shared.logger.info.call_args_list
        if "bounding box:" in call.args[0]
    ]
    assert len(boxes) == 3
    assert [call.args[1] for call in boxes] == ["Person", "Shoe", "Shoe"]


def test_exit_stops_motors():
    machine, commands = machine_for()
    perform_hier.exit(machine)
    assert commands == [("stop",)]
