"""Robot movement commands over UART on Raspberry Pi OS."""

import copy
import logging
import math
import os
import select
import termios
import time
import tty
from queue import Queue
from threading import Event, Lock, RLock, Thread, current_thread
from typing import Self

from dog_core.odometry import Odometry
from dog_core.uart_protocol import JsonUartProtocol, UartProtocol


class Uart:
    """Movement commands over serial using 8N1 with no flow control.

    Construction does not access hardware. Call ``open()`` or use a ``with``
    block. Timeouts are finite seconds; zero means non-blocking. Reads and
    writes may run concurrently, but calls in the same direction are serialized.
    Path recording stops automatically on close. Stop other I/O workers first.

    States use ``rotate()``, ``drive()`` and ``stop()``. The replaceable protocol
    defines their byte representation; the default is JSON with newlines.
    Calls queue requests without waiting for acknowledgement or movement
    completion. The byte transport is kept internal to this class.
    """

    def __init__(
        self,
        port: str = "/dev/ttys002",  # TODO: change to /dev/serial0 when running on raspberry pi
        baudrate: int = 115200,
        *,
        timeout: float = 1.0,
        write_timeout: float = 1.0,
        odometry_timeout: float = 1.0,
        protocol: UartProtocol | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if not isinstance(baudrate, int) or baudrate <= 0:
            raise ValueError("baudrate must be a positive integer")
        self._speed = getattr(termios, f"B{baudrate}", None)
        if self._speed is None:
            raise ValueError(f"Unsupported baud rate on this system: {baudrate}")
        for name, value in (("timeout", timeout), ("write_timeout", write_timeout)):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if not math.isfinite(odometry_timeout) or odometry_timeout <= 0:
            raise ValueError("odometry_timeout must be finite and positive")

        self._port = port
        self._timeout = timeout
        self._write_timeout = write_timeout
        self._log = logger if logger is not None else logging.getLogger(__name__)
        # TODO: Swap the encoder to change the wire format without changing states.
        self._protocol = JsonUartProtocol() if protocol is None else protocol
        self._fd: int | None = None
        self._read_lock = Lock()
        self._write_lock = RLock()
        self._path: Odometry | None = None
        self._receiver: Thread | None = None
        self._receiver_stop = Event()
        self._odometry_timeout = odometry_timeout
        self._last_odometry = 0.0
        self._odometry_error: str | None = None
        self._routing_lock = Lock()
        self._subscribers: dict[str, list[Queue[dict[str, object]]]] = {}

    @property
    def is_open(self) -> bool:
        """Whether this object currently owns an open serial port."""
        return self._fd is not None

    def open(self) -> Self:
        """Open/configure the port and return this instance, even if already open.

        OS errors (including missing devices and permission errors) propagate.
        If configuration fails, the newly opened descriptor is closed.
        """
        with self._read_lock, self._write_lock:
            if self.is_open:
                return self
            fd = os.open(self._port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            try:
                settings = termios.tcgetattr(fd)
                # Preserve bytes exactly instead of treating UART as a text terminal.
                tty.cfmakeraw(settings)
                settings[0] &= ~(termios.IXON | termios.IXOFF | termios.IXANY)
                settings[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
                settings[4] = settings[5] = self._speed
                settings[6][termios.VMIN] = 1
                settings[6][termios.VTIME] = 0
                termios.tcsetattr(fd, termios.TCSANOW, settings)
            except BaseException:
                os.close(fd)
                raise
            self._fd = fd
        return self

    def close(self) -> None:
        """Close the port after active I/O finishes; safe to call repeatedly."""
        self._receiver_stop.set()
        if self._receiver is not None and self._receiver is not current_thread():
            self._receiver.join(timeout=1.0)
            if self._receiver.is_alive():
                raise RuntimeError("UART receiver has not stopped")
        self._receiver = None
        with self._read_lock, self._write_lock:
            if self._fd is not None:
                fd, self._fd = self._fd, None
                os.close(fd)

    def start_path_recording(self, path: Odometry) -> None:
        """Continuously record sensor telemetry across all states.

        Start once, immediately after open(), while still at home. Until the
        first reading arrives, movement is refused. Missing telemetry stops
        the robot and prevents further movement; stop() always stays available.
        Other components subscribe to messages; they never read the port.
        """
        self._require_open()
        if self._receiver is not None:
            raise RuntimeError("Path recording has already started")
        if path.initialized:
            raise ValueError("Path recording must start with a new home baseline")
        self._path = path
        self._odometry_error = None
        self._last_odometry = time.monotonic()
        self.start_receiving()

    def start_receiving(self) -> None:
        """Start the single serial reader, optionally without path recording."""
        with self._read_lock:
            self._require_open()
            if self._receiver is not None:
                raise RuntimeError("UART receiver has already started")
            self._receiver_stop.clear()
            self._receiver = Thread(
                target=self._receive_messages, name="UART receiver", daemon=True
            )
            self._receiver.start()

    def subscribe(self, message_type: str) -> Queue[dict[str, object]]:
        """Create a component's inbox for this type, independent of other inboxes.

        Keep the inbox across state changes and use inbox.get(timeout=...) to
        receive messages. Every subscriber gets its own copy of future messages.
        Subscribe before sending a command or expecting a response: messages
        without a consumer are discarded. Consumers must drain their inboxes.
        """
        if not isinstance(message_type, str) or not message_type:
            raise ValueError("message_type must be a non-empty string")
        inbox: Queue[dict[str, object]] = Queue()
        with self._routing_lock:
            self._subscribers.setdefault(message_type, []).append(inbox)
        return inbox

    def unsubscribe(self, message_type: str, inbox: Queue[dict[str, object]]) -> None:
        """Stop future delivery; messages already in the inbox remain available."""
        with self._routing_lock:
            self._subscribers[message_type].remove(inbox)
            if not self._subscribers[message_type]:
                del self._subscribers[message_type]

    def _dispatch_message(self, message: dict[str, object]) -> None:
        message_type = message["type"]
        records_path = (
            message_type == "odometry"
            and self._path is not None
            and self._odometry_error is None
        )
        with self._routing_lock:
            inboxes = self._subscribers.get(message_type, [])
            for inbox in inboxes:
                inbox.put(copy.deepcopy(message))
        if records_path:
            self._path.record(
                timestamp=message["timestamp"],
                left_distance_m=message["left_distance_m"],
                right_distance_m=message["right_distance_m"],
                heading_deg=message["heading_deg"],
            )
            self._last_odometry = time.monotonic()

    def _receive_messages(self) -> None:
        buffer = bytearray()
        try:
            while not self._receiver_stop.is_set():
                with self._read_lock:
                    fd = self._require_open()
                    readable = select.select([fd], [], [], 0.05)[0]
                    if readable:
                        chunk = os.read(fd, 4096)
                        if not chunk:
                            raise OSError("UART disconnected while receiving messages")
                        buffer.extend(chunk)
                while buffer:
                    try:
                        message = self._protocol.extract_message(buffer)
                        if message is None:
                            break
                        self._dispatch_message(self._protocol.decode_message(message))
                    except (ValueError, TypeError, KeyError) as exc:
                        self._log.warning("Invalid incoming UART message: %s", exc)
                if (
                    self._path is not None
                    and self._odometry_error is None
                    and time.monotonic() - self._last_odometry >= self._odometry_timeout
                ):
                    self._fail_odometry(
                        "No fresh odometry received; home tracking is lost"
                    )
        except Exception as exc:  # noqa: BLE001 - any receiver failure must stop the robot
            self._log.exception("UART receiver failed")
            self._fail_odometry(str(exc))

    def _fail_odometry(self, reason: str) -> None:
        # Latch the fault and stop, but keep routing other messages after a timeout.
        with self._write_lock:
            if self._odometry_error is not None:
                return
            self._odometry_error = reason
            self._log.error("Home tracking stopped: %s", reason)
            try:
                self.stop()
            except Exception:  # noqa: BLE001 - report failure of the emergency stop
                self._log.exception("Stopping after odometry failure failed")

    def _require_odometry(self) -> None:
        if self._path is not None and (
            self._odometry_error is not None
            or self._receiver is None
            or not self._receiver.is_alive()
            or self._receiver_stop.is_set()
            or not self._path.initialized
            or time.monotonic() - self._last_odometry >= self._odometry_timeout
        ):
            raise RuntimeError(
                self._odometry_error or "No fresh odometry; movement refused"
            )

    def require_odometry(self) -> None:
        """Require healthy path recording, including while waiting for a turn."""
        with self._write_lock:
            if self._path is None:
                raise RuntimeError("Path recording has not started")
            self._require_odometry()

    def _require_open(self) -> int:
        if self._fd is None:
            raise RuntimeError("UART is closed; call open() first")
        return self._fd

    @staticmethod
    def _validate_number(name: str, value: float) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{name} must be a finite number")

    def rotate(self, degrees: float) -> None:
        """Request a relative turn in place; positive degrees turn clockwise.

        Negative degrees turn counterclockwise. The angle must be finite;
        full revolutions are allowed. Returns once the command is queued,
        without waiting for the turn to finish.
        """
        self._validate_number("degrees", degrees)
        with self._write_lock:
            self._require_odometry()
            self._write(self._protocol.encode_rotate(degrees))

    def drive(self, speed: float, angle: float = 0.0) -> None:
        """Request driving at a speed in metres per second with a steering angle.

        Positive speed is forwards, negative is reverse, zero requests no
        driving. Angle is in degrees: zero is straight, positive
        steers right, negative steers left. Both values must be finite. The
        Pico defines the robot's physical speed and steering limits.

        Driving continues until superseded by another movement command; this
        method only queues the request. Use ``stop()`` to request a stop.
        """
        self._validate_number("speed", speed)
        self._validate_number("angle", angle)
        with self._write_lock:
            self._require_odometry()
            self._write(self._protocol.encode_drive(speed, angle))

    def stop(self) -> None:
        """Request that the Pico stop both driving and rotation."""
        self._write(self._protocol.encode_stop())

    def sitz(self) -> None:
        """Queue the sit command without waiting for completion."""
        self._write(self._protocol.encode_sitz())

    def platz(self) -> None:
        """Queue the lie-down command without waiting for completion."""
        self._write(self._protocol.encode_platz())

    def auf(self) -> None:
        """Queue the stand-up command without waiting for completion."""
        self._write(self._protocol.encode_auf())

    def brav(self) -> None:
        """Queue the brav command without waiting for completion."""
        self._write(self._protocol.encode_brav())

    def signal_found(self) -> None:
        """Queue the bone-found signal without waiting for completion."""
        self._write(self._protocol.encode_signal_found())

    def _read(self, size: int = 1) -> bytes:
        """Read up to ``size`` bytes within one overall read timeout.

        Returns partial data on timeout, or ``b''`` if no bytes arrive. This
        does not imply a complete message. A detected hangup raises OSError.
        """
        if not isinstance(size, int) or size < 0:
            raise ValueError("size must be a non-negative integer")
        with self._read_lock:
            if self._receiver is not None:
                raise RuntimeError("UART receiver owns incoming data; use subscribe()")
            fd = self._require_open()
            # All received fragments share one timeout, rather than restarting it.
            deadline = time.monotonic() + self._timeout
            data = bytearray()
            try:
                while len(data) < size:
                    remaining = max(0.0, deadline - time.monotonic())
                    if not select.select([fd], [], [], remaining)[0]:
                        break
                    try:
                        chunk = os.read(fd, size - len(data))
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            break
                        continue
                    if not chunk:
                        raise OSError("UART connection closed while reading")
                    data.extend(chunk)
                    if time.monotonic() >= deadline:
                        break
            finally:
                # Log raw bytes safely, including partial reads and empty timeouts.
                self._log.info(
                    "UART read %s: received %d/%d bytes; payload=%r",
                    self._port,
                    len(data),
                    size,
                    bytes(data),
                )
            return bytes(data)

    def _write(self, data: bytes | bytearray | memoryview) -> int:
        """Queue all bytes for transmission and return their count.

        Raises TimeoutError if the port cannot accept the entire payload within
        one write timeout. Some bytes may already have been transmitted: blindly
        retrying can duplicate a command. Success is not a Pico acknowledgement.
        """
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data must be bytes, bytearray or memoryview")
        payload_bytes = bytes(data)
        payload = memoryview(payload_bytes)
        # Keep each complete command together when callers send concurrently.
        with self._write_lock:
            fd = self._require_open()
            deadline = time.monotonic() + self._write_timeout
            sent = 0
            try:
                while sent < len(payload):
                    remaining = max(0.0, deadline - time.monotonic())
                    if not select.select([], [fd], [], remaining)[1]:
                        raise TimeoutError(f"UART write timed out after {sent} bytes")
                    try:
                        # Continue after short writes without duplicating earlier bytes.
                        count = os.write(fd, payload[sent:])
                    except BlockingIOError:
                        count = 0
                    sent += count
                    if sent < len(payload) and time.monotonic() >= deadline:
                        raise TimeoutError(f"UART write timed out after {sent} bytes")
            finally:
                self._log.info(
                    "UART write %s: queued %d/%d bytes; payload=%r",
                    self._port,
                    sent,
                    len(payload),
                    payload_bytes,
                )
            return sent

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
