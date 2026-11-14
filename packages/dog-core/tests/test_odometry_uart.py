"""Receive real fragmented/coalesced serial input without robot hardware."""

import json
import os
import select
import struct
import time
from queue import Empty

import pytest
from dog_core.path_to_home import PathToHome
from dog_core.uart import Uart
from dog_core.uart_protocol import JsonUartProtocol


def message(timestamp, left, right=None, heading=0):
    return (
        json.dumps(
            {
                "type": "odometry",
                "timestamp": timestamp,
                "left_distance_m": left,
                "right_distance_m": left if right is None else right,
                "heading_deg": heading,
            }
        )
        + "\n"
    ).encode()


@pytest.fixture
def connection():
    master, slave = os.openpty()
    uart = Uart(os.ttyname(slave), odometry_timeout=1.0)
    try:
        with uart:
            yield master, uart, PathToHome()
    finally:
        os.close(master)
        os.close(slave)


def wait_for(predicate):
    deadline = time.monotonic() + 1
    while not predicate():
        assert time.monotonic() < deadline, "Receiver did not process the input"
        time.sleep(0.005)


def test_require_odometry_needs_active_recording_and_fresh_baseline(connection):
    master, uart, path = connection
    with pytest.raises(RuntimeError, match="recording has not started"):
        uart.require_odometry()
    uart.start_path_recording(path)
    with pytest.raises(RuntimeError, match="odometry"):
        uart.require_odometry()
    os.write(master, message(0, 0))
    assert path.wait_until_initialized(1)
    uart.require_odometry()
    assert not select.select([master], [], [], 0)[0]


def test_sensor_data_updates_path_without_any_state_or_camera_loop(connection):
    master, uart, path = connection
    uart.start_path_recording(path)
    with pytest.raises(RuntimeError, match="odometry"):
        uart.drive(0.1)
    os.write(master, message(10, 100, heading=270))
    assert path.wait_until_initialized(1)
    assert path.pose == path.home
    os.write(master, message(11, 101, heading=270))
    wait_for(lambda: path.pose.x > 0)
    assert path.pose.x == pytest.approx(1)
    assert path.pose.y == pytest.approx(0)
    uart.drive(0.1)
    assert select.select([master], [], [], 1)[0]
    assert json.loads(os.read(master, 4096)) == {
        "command": "drive",
        "speed": 0.1,
        "angle": 0,
    }


def test_fragments_and_multiple_messages_are_not_lost(connection):
    master, uart, path = connection
    uart.start_path_recording(path)
    baseline = message(0, 50)
    os.write(master, baseline[:10])
    assert not path.wait_until_initialized(0.02)
    os.write(master, baseline[10:] + message(1, 51) + message(2, 52))
    wait_for(lambda: path.pose.x == 2)
    assert path.home.x == path.home.y == 0


def test_bad_odometry_does_not_corrupt_path_or_discard_other_messages(connection):
    master, uart, path = connection
    statuses = uart.subscribe("status")
    uart.start_path_recording(path)
    os.write(
        master,
        b'garbage\n[]\n{"type":"status"}\n{"type":"odometry"}\n'
        + message(10, 100)
        + message(9, 999, heading=90)
        + message(11, 101)
        + message(12, float("nan"))
        + message(13, 102),
    )
    wait_for(lambda: path.pose.x == 2)
    assert path.pose.y == 0
    assert path.pose.heading == 0
    assert statuses.get(timeout=1) == {"type": "status"}


def test_no_baseline_refuses_rotation_and_timeout_requests_stop():
    master, slave = os.openpty()
    try:
        with Uart(os.ttyname(slave), odometry_timeout=0.05) as uart:
            path = PathToHome()
            uart.start_path_recording(path)
            with pytest.raises(RuntimeError, match="odometry"):
                uart.rotate(180)
            assert select.select([master], [], [], 1)[0]
            assert json.loads(os.read(master, 4096)) == {"command": "stop"}
            with pytest.raises(RuntimeError, match="tracking is lost"):
                uart.drive(0.1)
            assert not path.initialized
    finally:
        os.close(master)
        os.close(slave)


def test_telemetry_loss_after_moving_stops_and_latches_fault():
    master, slave = os.openpty()
    try:
        with Uart(os.ttyname(slave), odometry_timeout=0.1) as uart:
            path = PathToHome()
            statuses = uart.subscribe("status")
            uart.start_path_recording(path)
            os.write(master, message(0, 0))
            assert path.wait_until_initialized(1)
            uart.drive(0.1)
            assert select.select([master], [], [], 1)[0]
            assert json.loads(os.read(master, 4096))["command"] == "drive"
            assert select.select([master], [], [], 1)[0]
            assert json.loads(os.read(master, 4096))["command"] == "stop"
            with pytest.raises(RuntimeError):
                uart.rotate(180)
            with pytest.raises(RuntimeError):
                uart.require_odometry()
            # A late message cannot silently resume tracking after a gap.
            os.write(master, message(1, 1))
            with pytest.raises(RuntimeError):
                uart.drive(0.1)
            assert path.pose == path.home
            os.write(master, b'{"type":"status","battery":80}\n')
            assert statuses.get(timeout=1) == {"type": "status", "battery": 80}
    finally:
        os.close(master)
        os.close(slave)


def test_close_stops_receiver_before_closing_port(connection):
    _, uart, path = connection
    uart.start_path_recording(path)
    worker = uart._receiver
    uart.close()
    assert not worker.is_alive()
    assert not uart.is_open


def test_reopening_port_does_not_allow_unrecorded_movement(connection):
    master, uart, path = connection
    uart.start_path_recording(path)
    os.write(master, message(0, 0))
    assert path.wait_until_initialized(1)
    uart.close()
    uart.open()
    with pytest.raises(RuntimeError, match="odometry"):
        uart.drive(0.1)


def test_cannot_start_a_second_reader_or_replace_home_while_recording(connection):
    _, uart, path = connection
    uart.start_path_recording(path)
    with pytest.raises(RuntimeError, match="already started"):
        uart.start_path_recording(PathToHome())


def test_cannot_reuse_old_baseline_after_recording_was_interrupted(connection):
    _, uart, path = connection
    path.record(timestamp=0, left_distance_m=0, right_distance_m=0, heading_deg=0)
    with pytest.raises(ValueError, match="new home baseline"):
        uart.start_path_recording(path)


def test_interleaved_messages_route_to_subscribers_and_discard_unhandled_types(
    connection,
):
    master, uart, path = connection
    acknowledgements = uart.subscribe("ack")
    statuses = uart.subscribe("status")
    uart.start_path_recording(path)
    stream = (
        message(0, 0)
        + b'{"type":"status","battery":90}\n'
        + b'{"type":"ack","id":7}\n'
        + message(1, 1)
        + b'{"type":"future_sensor","reading":42}\n'
        + b'{"type":"status","battery":89}\n'
        + message(2, 2)
    )
    os.write(master, stream[:11])
    os.write(master, stream[11:])
    wait_for(lambda: path.pose.x == 2)
    assert statuses.get(timeout=1) == {"type": "status", "battery": 90}
    assert statuses.get(timeout=1) == {"type": "status", "battery": 89}
    assert acknowledgements.get(timeout=1) == {"type": "ack", "id": 7}
    future_sensor = uart.subscribe("future_sensor")
    with pytest.raises(Empty):
        future_sensor.get_nowait()
    os.write(master, b'{"type":"future_sensor","reading":43}\n')
    assert future_sensor.get(timeout=1) == {
        "type": "future_sensor",
        "reading": 43,
    }
    with pytest.raises(Empty):
        acknowledgements.get_nowait()


def test_subscribers_receive_independent_copies_without_competing_for_messages(
    connection,
):
    master, uart, _ = connection
    first, second = uart.subscribe("status"), uart.subscribe("status")
    uart.start_receiving()
    os.write(master, b'{"type":"status","details":{"battery":90}}\n')
    received = first.get(timeout=1)
    received["details"]["battery"] = 0
    assert second.get(timeout=1) == {"type": "status", "details": {"battery": 90}}
    with pytest.raises(Empty):
        first.get_nowait()


def test_odometry_is_available_to_other_consumers_while_path_records(connection):
    master, uart, path = connection
    measurements = uart.subscribe("odometry")
    uart.start_path_recording(path)
    os.write(master, message(0, 0) + message(1, 1))
    assert measurements.get(timeout=1)["timestamp"] == 0
    assert measurements.get(timeout=1)["timestamp"] == 1
    wait_for(lambda: path.pose.x == 1)


def test_slow_consumer_does_not_block_odometry_or_lose_messages(connection):
    master, uart, path = connection
    statuses = uart.subscribe("status")
    uart.start_path_recording(path)
    statuses_data = b"".join(
        (json.dumps({"type": "status", "sequence": i}) + "\n").encode()
        for i in range(100)
    )
    os.write(master, message(0, 0) + statuses_data + message(1, 1))
    wait_for(lambda: path.pose.x == 1)
    assert [statuses.get(timeout=1)["sequence"] for _ in range(100)] == list(range(100))


def test_raw_reads_cannot_steal_bytes_from_the_message_receiver(connection):
    master, uart, path = connection
    uart.start_path_recording(path)
    with pytest.raises(RuntimeError, match="use subscribe"):
        uart._read(1)
    os.write(master, message(0, 0) + message(1, 1))
    wait_for(lambda: path.pose.x == 1)


def test_unsubscribe_preserves_existing_inbox_and_discards_future_messages(connection):
    master, uart, _ = connection
    original = uart.subscribe("ack")
    barrier = uart.subscribe("barrier")
    uart.start_receiving()
    os.write(master, b'{"type":"ack","id":1}\n{"type":"barrier"}\n')
    barrier.get(timeout=1)
    uart.unsubscribe("ack", original)
    os.write(master, b'{"type":"ack","id":2}\n{"type":"barrier"}\n')
    barrier.get(timeout=1)
    assert original.get(timeout=1)["id"] == 1
    with pytest.raises(Empty):
        original.get_nowait()
    new_subscriber = uart.subscribe("ack")
    with pytest.raises(Empty):
        new_subscriber.get_nowait()
    os.write(master, b'{"type":"ack","id":3}\n')
    assert new_subscriber.get(timeout=1)["id"] == 3


def test_binary_framing_and_decoding_can_replace_json(connection):
    class BinaryProtocol(JsonUartProtocol):
        def extract_message(self, buffer):
            if len(buffer) < 32:
                return None
            frame = bytes(buffer[:32])
            del buffer[:32]
            return frame

        def decode_message(self, data):
            timestamp, left, right, heading = struct.unpack("<dddd", data)
            return {
                "type": "odometry",
                "timestamp": timestamp,
                "left_distance_m": left,
                "right_distance_m": right,
                "heading_deg": heading,
            }

    master, uart, path = connection
    uart._protocol = BinaryProtocol()
    uart.start_path_recording(path)
    os.write(master, struct.pack("<dddd", 0, 10, 10, 123))
    os.write(master, struct.pack("<dddd", 1, 11, 11, 123))
    wait_for(lambda: path.pose.x == 1)
    assert path.pose.y == 0


def test_json_framer_bounds_incomplete_and_complete_messages():
    protocol = JsonUartProtocol()
    for data in (b"x" * 4097, b"x" * 4097 + b"\n"):
        buffer = bytearray(data)
        with pytest.raises(ValueError, match="4096"):
            protocol.extract_message(buffer)
        assert not buffer


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_odometry_timeout_must_be_finite_and_positive(timeout):
    with pytest.raises(ValueError):
        Uart(odometry_timeout=timeout)
