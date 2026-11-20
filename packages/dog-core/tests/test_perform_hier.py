"""Exercise person-to-shoe approach with recorded detections and a fake clock."""

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
    monkeypatch.setattr(perform_hier.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(
        perform_hier.time, "sleep", lambda delay: now.__setitem__(0, now[0] + delay)
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
    machine = SimpleNamespace(
        shared=SimpleNamespace(
            camera=camera, object_model=model, uart=uart, logger=Mock()
        ),
        go_to_standing_idle=Mock(side_effect=lambda: commands.append(("idle",))),
    )
    return machine, commands


def test_approach_person_then_shoes_then_stop_before_idle(clock):
    machine, commands = machine_for(
        detections(PERSON),
        detections(CROPPED, [SHOE]),
        detections(shoes=[CLOSE_SHOE]),
        detections(shoes=[CLOSE_SHOE]),
        detections(shoes=[CLOSE_SHOE]),
    )
    perform_hier.enter(machine)
    assert commands[0] == ("stop",)
    assert commands[1][0] == "drive" and commands[1][1] > 0 and commands[1][2] < 0
    assert commands[2] == pytest.approx(("drive", 0.03, -6))
    assert commands[3:] == [("stop",)] * 4 + [("idle",)]
    machine.shared.uart.rotate.assert_not_called()
    machine.shared.logger.exception.assert_not_called()


@pytest.mark.parametrize(
    "person,sign", [([20, 10, 80, 90], -1), ([120, 10, 180, 90], 1)]
)
def test_steers_toward_person_while_driving_forward(clock, person, sign):
    machine, commands = machine_for(detections(person))
    perform_hier.enter(machine)
    speed, angle = machine.shared.uart.drive.call_args.args
    assert speed > 0
    assert angle * sign > 0
    assert commands[-2:] == [("stop",), ("idle",)]


def test_no_person_waits_stopped_and_times_out(clock):
    machine, commands = machine_for(repeat_empty=True)
    perform_hier.enter(machine)
    machine.shared.uart.drive.assert_not_called()
    machine.shared.uart.rotate.assert_not_called()
    assert clock[0] >= perform_hier.TARGET_LOST_TIMEOUT
    assert commands[-2:] == [("stop",), ("idle",)]


def test_cropped_person_without_shoes_does_not_drive_blindly(clock):
    machine, _ = machine_for(detections(CROPPED), repeat_empty=True)
    perform_hier.enter(machine)
    machine.shared.uart.drive.assert_not_called()


def test_unrelated_shoes_are_not_followed(clock):
    unrelated = [170, 80, 198, 98]
    machine, _ = machine_for(detections(CROPPED, [unrelated]), repeat_empty=True)
    perform_hier.enter(machine)
    machine.shared.uart.drive.assert_not_called()


def test_shoes_must_be_near_persons_lower_body(clock):
    shoe_above_feet = [70, 20, 90, 35]
    machine, _ = machine_for(detections(CROPPED, [shoe_above_feet]), repeat_empty=True)
    perform_hier.enter(machine)
    machine.shared.uart.drive.assert_not_called()


def test_person_target_does_not_jump_to_a_distant_detection(clock):
    distant = [155, 10, 195, 90]
    machine, _ = machine_for(detections(PERSON), detections(distant), repeat_empty=True)
    perform_hier.enter(machine)
    machine.shared.uart.drive.assert_called_once()


def test_shoes_alone_do_not_establish_an_unseen_person(clock):
    machine, _ = machine_for(detections(shoes=[CLOSE_SHOE]), repeat_empty=True)
    perform_hier.enter(machine)
    machine.shared.uart.drive.assert_not_called()


def test_losing_shoes_stops_immediately_and_resets_close_confirmation(clock):
    machine, commands = machine_for(
        detections(CROPPED, [CLOSE_SHOE]),
        detections(shoes=[CLOSE_SHOE]),
        detections(),
        detections(shoes=[CLOSE_SHOE]),
        detections(shoes=[CLOSE_SHOE]),
        detections(shoes=[CLOSE_SHOE]),
    )
    perform_hier.enter(machine)
    assert machine.shared.camera.read.call_count == 6
    machine.shared.uart.drive.assert_not_called()
    assert commands[-2:] == [("stop",), ("idle",)]


def test_steers_between_shoes_but_size_threshold_uses_one_shoe(clock):
    left, right = [50, 80, 70, 95], [130, 80, 150, 95]
    machine, _ = machine_for(detections(CROPPED, [left, right]))
    perform_hier.enter(machine)
    machine.shared.uart.drive.assert_called_once_with(0.03, 0)


def test_can_handoff_to_associated_shoes_when_person_detection_disappears(clock):
    machine, _ = machine_for(detections(PERSON), detections(shoes=[SHOE]))
    perform_hier.enter(machine)
    assert machine.shared.uart.drive.call_count == 2
    assert machine.shared.uart.drive.call_args.args[0] == 0.03


def test_model_failure_stops_and_returns_idle(clock):
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
