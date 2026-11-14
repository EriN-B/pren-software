"""Robot movement commands over UART on Raspberry Pi OS."""

import logging
import math
import os
import select
import termios
import time
import tty
from threading import Lock
from typing import Self

from dog_core.uart_protocol import JsonUartProtocol, UartProtocol


class Uart:
    """Movement commands over serial using 8N1 with no flow control.

    Construction does not access hardware. Call ``open()`` or use a ``with``
    block. Timeouts are finite seconds; zero means non-blocking. Reads and
    writes may run concurrently, but calls in the same direction are serialized.
    Stop your I/O workers before closing the connection.

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

        self._port = port
        self._timeout = timeout
        self._write_timeout = write_timeout
        self._log = logger if logger is not None else logging.getLogger(__name__)
        # TODO: Swap the encoder to change the wire format without changing states.
        self._protocol = JsonUartProtocol() if protocol is None else protocol
        self._fd: int | None = None
        self._read_lock = Lock()
        self._write_lock = Lock()

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
        with self._read_lock, self._write_lock:
            if self._fd is not None:
                fd, self._fd = self._fd, None
                os.close(fd)

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
