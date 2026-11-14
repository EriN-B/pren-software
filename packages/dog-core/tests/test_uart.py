"""Exercise the real POSIX transport through a pseudo-terminal, without GPIO."""

import json
import os
import select
import struct
import termios
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from dog_core.states import (
    auf_before_brav,
    auf_before_hier,
    auf_before_such,
    found,
    perform_auf,
    perform_brav,
    perform_hier,
    platz,
    sitz,
)
from dog_core.uart import Uart


@pytest.fixture
def serial_pair():
    master, slave = os.openpty()
    try:
        yield master, slave, Uart(os.ttyname(slave), timeout=0.05)
    finally:
        os.close(master)
        os.close(slave)


def test_binary_round_trip_and_configuration(serial_pair):
    master, slave, uart = serial_pair
    payload = bytes(range(256))
    assert not uart.is_open
    with uart:
        assert uart.is_open
        settings = termios.tcgetattr(slave)
        assert settings[4:6] == [termios.B115200, termios.B115200]
        assert settings[2] & termios.CSIZE == termios.CS8
        assert not settings[2] & (termios.PARENB | termios.CSTOPB)
        assert not settings[0] & (termios.IXON | termios.IXOFF | termios.IXANY)
        assert not settings[3] & (termios.ICANON | termios.ECHO)

        assert uart._write(payload) == len(payload)
        assert select.select([master], [], [], 1)[0]
        assert os.read(master, len(payload)) == payload
        os.write(master, payload)
        assert uart._read(len(payload)) == payload
    assert not uart.is_open


def test_read_timeout_returns_partial_or_empty_data(serial_pair):
    master, _, uart = serial_pair
    with uart:
        os.write(master, b"OK")
        assert uart._read(10) == b"OK"
        assert uart._read() == b""


def test_read_collects_fragments_while_writes_can_proceed(serial_pair):
    master, _, uart = serial_pair
    with uart, ThreadPoolExecutor(max_workers=1) as pool:
        os.write(master, b"O")
        pending = pool.submit(uart._read, 2)
        assert uart._write(b"PING") == 4
        assert select.select([master], [], [], 1)[0]
        assert os.read(master, 4) == b"PING"
        os.write(master, b"K")
        assert pending.result(timeout=1) == b"OK"


def test_zero_timeout_reads_available_data_without_waiting(serial_pair):
    master, slave, _ = serial_pair
    with Uart(os.ttyname(slave), timeout=0) as uart:
        os.write(master, b"OK")
        assert select.select([slave], [], [], 1)[0]
        assert uart._read(10) == b"OK"
        assert uart._read() == b""


def test_close_and_reopen_are_safe(serial_pair):
    _, _, uart = serial_pair
    uart.close()
    with uart:
        uart.open()
        assert uart._read(0) == b""
        assert uart._write(b"") == 0
    uart.close()
    with uart:
        assert uart.is_open


def test_context_closes_on_error(serial_pair):
    _, _, uart = serial_pair
    with pytest.raises(ValueError, match="application error"), uart:
        raise ValueError("application error")
    assert not uart.is_open


@pytest.mark.parametrize("operation", [lambda u: u._read(), lambda u: u._write(b"x")])
def test_io_requires_open_port(operation):
    with pytest.raises(RuntimeError, match="closed"):
        operation(Uart())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"baudrate": 0},
        {"baudrate": 12345},
        {"baudrate": 115200.0},
        {"timeout": -1},
        {"timeout": float("inf")},
        {"timeout": float("nan")},
        {"write_timeout": -1},
    ],
)
def test_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        Uart(**kwargs)


def test_bad_arguments(serial_pair):
    _, _, uart = serial_pair
    with uart:
        with pytest.raises(ValueError):
            uart._read(-1)
        with pytest.raises(ValueError):
            uart._read(1.5)
        with pytest.raises(TypeError):
            uart._write("text must be encoded explicitly")


def test_missing_port(tmp_path):
    uart = Uart(str(tmp_path / "missing-uart"))
    with pytest.raises(FileNotFoundError):
        uart.open()
    assert not uart.is_open


def test_configuration_error_closes_descriptor(serial_pair):
    _, _, uart = serial_pair
    real_close = os.close
    with (
        patch("dog_core.uart.termios.tcsetattr", side_effect=OSError("config failed")),
        patch("dog_core.uart.os.close", wraps=real_close) as close,
    ):
        with pytest.raises(OSError, match="config failed"):
            uart.open()
        close.assert_called_once()
        closed_fd = close.call_args.args[0]
    with pytest.raises(OSError):
        os.fstat(closed_fd)
    assert not uart.is_open


def test_partial_writes_send_entire_payload(serial_pair):
    master, _, uart = serial_pair
    real_write = os.write
    with (
        uart,
        patch(
            "dog_core.uart.os.write",
            side_effect=lambda fd, data: real_write(fd, data[:2]),
        ),
    ):
        assert uart._write(bytearray(b"HELLO")) == 5
    assert select.select([master], [], [], 1)[0]
    assert os.read(master, 5) == b"HELLO"


def test_write_timeout_when_output_buffer_fills(serial_pair):
    _, slave, _ = serial_pair
    with (
        Uart(os.ttyname(slave), write_timeout=0.01) as uart,
        pytest.raises(TimeoutError, match="write timed out"),
    ):
        uart._write(b"x" * 1_000_000)


def test_read_uses_one_deadline_for_all_fragments(serial_pair):
    _, _, uart = serial_pair
    with (
        uart,
        patch("dog_core.uart.time.monotonic", side_effect=[0, 0, 0.03, 0.03]),
        patch(
            "dog_core.uart.select.select", side_effect=[([0], [], []), ([], [], [])]
        ) as wait,
        patch("dog_core.uart.os.read", return_value=b"x"),
    ):
        assert uart._read(2) == b"x"
        assert wait.call_args_list[0].args[3] == pytest.approx(0.05)
        assert wait.call_args_list[1].args[3] == pytest.approx(0.02)


@pytest.mark.parametrize(
    ("method", "arguments", "expected"),
    [
        ("rotate", (180,), {"command": "rotate", "degrees": 180}),
        ("rotate", (-90.5,), {"command": "rotate", "degrees": -90.5}),
        ("rotate", (720,), {"command": "rotate", "degrees": 720}),
        ("drive", (0.5, 15), {"command": "drive", "speed": 0.5, "angle": 15}),
        ("drive", (-1,), {"command": "drive", "speed": -1, "angle": 0}),
        ("drive", (1, -30), {"command": "drive", "speed": 1, "angle": -30}),
        ("drive", (2.5, 10), {"command": "drive", "speed": 2.5, "angle": 10}),
        ("drive", (-2.5,), {"command": "drive", "speed": -2.5, "angle": 0}),
        ("drive", (0,), {"command": "drive", "speed": 0, "angle": 0}),
        ("stop", (), {"command": "stop"}),
        ("sitz", (), {"command": "sitz"}),
        ("platz", (), {"command": "platz"}),
        ("auf", (), {"command": "auf"}),
        ("brav", (), {"command": "brav"}),
        ("signal_found", (), {"command": "signal_found"}),
    ],
)
def test_movement_commands_are_newline_delimited_json(
    serial_pair, method, arguments, expected
):
    master, _, uart = serial_pair
    with uart:
        assert getattr(uart, method)(*arguments) is None
        assert select.select([master], [], [], 1)[0]
        message = os.read(master, 1024)
        assert message.endswith(b"\n")
        assert message.count(b"\n") == 1
        assert json.loads(message.decode("ascii")) == expected


@pytest.mark.parametrize(
    ("method", "arguments"),
    [
        ("rotate", (float("nan"),)),
        ("rotate", (float("inf"),)),
        ("rotate", ("180",)),
        ("rotate", (True,)),
        ("drive", (float("nan"),)),
        ("drive", (float("inf"),)),
        ("drive", (float("-inf"),)),
        ("drive", (0.5, float("inf"))),
        ("drive", (0.5, "right")),
        ("drive", (False,)),
        ("drive", (0.5, True)),
    ],
)
def test_invalid_movement_commands_send_nothing(serial_pair, method, arguments):
    master, _, uart = serial_pair
    with uart:
        with pytest.raises(ValueError):
            getattr(uart, method)(*arguments)
        assert not select.select([master], [], [], 0)[0]


def test_multiple_commands_preserve_message_boundaries(serial_pair):
    master, _, uart = serial_pair
    with uart:
        uart.rotate(180)
        uart.drive(0.5)
        uart.stop()
        assert select.select([master], [], [], 1)[0]
        messages = os.read(master, 4096).splitlines()
        assert [json.loads(message) for message in messages] == [
            {"command": "rotate", "degrees": 180},
            {"command": "drive", "speed": 0.5, "angle": 0},
            {"command": "stop"},
        ]


@pytest.mark.parametrize(
    ("method", "arguments"),
    [
        ("rotate", (180,)),
        ("drive", (0.5,)),
        ("stop", ()),
        ("sitz", ()),
        ("platz", ()),
        ("auf", ()),
        ("brav", ()),
        ("signal_found", ()),
    ],
)
def test_movement_commands_require_open_port(method, arguments):
    with pytest.raises(RuntimeError, match="closed"):
        getattr(Uart(), method)(*arguments)


def test_movement_command_propagates_write_failure(serial_pair):
    _, _, uart = serial_pair
    with (
        uart,
        patch.object(uart, "_write", side_effect=TimeoutError("buffer full")),
        pytest.raises(TimeoutError, match="buffer full"),
    ):
        uart.stop()


def test_protocol_can_be_replaced_with_binary_without_changing_movement_calls(
    serial_pair,
):
    class BinaryProtocol:
        def encode_rotate(self, degrees: float) -> bytes:
            return struct.pack("<Bf", 0x01, degrees)

        def encode_drive(self, speed: float, angle: float) -> bytes:
            return struct.pack("<Bff", 0x02, speed, angle)

        def encode_stop(self) -> bytes:
            return b"\x03"

        def encode_sitz(self) -> bytes:
            return b"\x04"

        def encode_platz(self) -> bytes:
            return b"\x05"

        def encode_auf(self) -> bytes:
            return b"\x06"

        def encode_brav(self) -> bytes:
            return b"\x07"

        def encode_signal_found(self) -> bytes:
            return b"\x08"

    master, slave, _ = serial_pair
    with Uart(os.ttyname(slave), protocol=BinaryProtocol()) as uart:
        uart.rotate(180)
        uart.drive(2.5, -15)
        uart.stop()
        uart.sitz()
        uart.platz()
        uart.auf()
        uart.brav()
        uart.signal_found()
        assert select.select([master], [], [], 1)[0]
        # No JSON or newline may be added by the UART transport.
        assert os.read(master, 1024) == (
            b"\x01"
            + struct.pack("<f", 180)
            + b"\x02"
            + struct.pack("<ff", 2.5, -15)
            + b"\x03"
            + b"\x04\x05\x06\x07\x08"
        )


@pytest.mark.parametrize(
    ("state", "expected", "continuation"),
    [
        (sitz, ["sitz"], "recognition"),
        (platz, ["platz"], "recognition"),
        (perform_auf, ["auf"], "idle"),
        (perform_brav, ["brav"], "idle"),
        (auf_before_such, ["auf"], "searching"),
        (auf_before_hier, ["auf"], "idle"),
        (auf_before_brav, ["auf", "brav"], "idle"),
        (found, ["signal_found"], "return"),
    ],
)
def test_states_send_commands_before_continuing(
    serial_pair, state, expected, continuation
):
    master, _, uart = serial_pair
    machine = SimpleNamespace(
        shared=SimpleNamespace(uart=uart, logger=Mock()),
        command_recognition=Mock(),
        go_to_standing_idle=Mock(),
        go_to_searching=Mock(),
        return_back=Mock(),
    )
    machine.go_to_perform_brav = lambda: perform_brav.enter(machine)
    machine.go_to_perform_hier = lambda: perform_hier.enter(machine)

    def commands_received(*args):
        assert select.select([master], [], [], 1)[0]
        messages = os.read(master, 4096).splitlines()
        assert [json.loads(message) for message in messages] == [
            {"command": command} for command in expected
        ]

    callback = {
        "recognition": machine.command_recognition.start,
        "idle": machine.go_to_standing_idle,
        "searching": machine.go_to_searching,
        "return": machine.return_back,
    }[continuation]
    callback.side_effect = commands_received
    with uart:
        state.enter(machine)
    callback.assert_called_once()
