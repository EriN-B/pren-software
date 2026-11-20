"""Verify startup ordering without loading camera/audio/model dependencies."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from dog_core.odometry import Odometry, Pose


@pytest.fixture
def startup():
    source = Path(__file__).resolve().parents[1] / "src/dog_core/states/startup.py"
    spec = importlib.util.spec_from_file_location("_startup_path_test", source)
    module = importlib.util.module_from_spec(spec)
    dependencies = {
        "cv2": SimpleNamespace(VideoCapture=Mock()),
        "sounddevice": SimpleNamespace(RawInputStream=Mock()),
        "dog_perception": SimpleNamespace(GestureModel=Mock(), ObjectModel=Mock()),
        "dog_recorder": SimpleNamespace(AudioModel=Mock()),
    }
    with patch.dict("sys.modules", dependencies):
        spec.loader.exec_module(module)
    return module


def test_home_is_established_before_idle_and_survives_later_updates(startup):
    machine = SimpleNamespace(shared=SimpleNamespace(), go_to_standing_idle=Mock())
    uart = Mock()
    uart.open.return_value = uart

    def baseline(path):
        machine.go_to_standing_idle.assert_not_called()
        assert isinstance(path, Odometry)
        path.record(
            timestamp=100, left_distance_m=30, right_distance_m=40, heading_deg=123
        )

    uart.start_path_recording.side_effect = baseline
    with patch.object(startup, "Uart", return_value=uart):
        startup.enter(machine)
    machine.go_to_standing_idle.assert_called_once()
    path = machine.shared.odometry
    assert path.home == path.pose == Pose()
    assert machine.shared.uart is uart
    path.record(timestamp=101, left_distance_m=31, right_distance_m=41, heading_deg=123)
    assert path.pose == Pose(1, 0, 0)
    assert path.home == Pose()
    assert path.waypoints[0] == Pose()


def test_no_sensor_baseline_closes_uart_without_entering_idle(startup):
    machine = SimpleNamespace(shared=SimpleNamespace(), go_to_standing_idle=Mock())
    uart = Mock()
    uart.open.return_value = uart
    with (
        patch.object(startup, "Uart", return_value=uart),
        patch.object(Odometry, "wait_until_initialized", return_value=False),
        pytest.raises(RuntimeError, match="cannot establish home"),
    ):
        startup.enter(machine)
    machine.go_to_standing_idle.assert_not_called()
    uart.close.assert_called_once()
