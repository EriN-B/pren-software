"""A virtual serial port: the simulator's end of the Pi 4 <-> Pico UART cable.

The simulator opens a pseudo-terminal (pty) and keeps the "master" end. The core opens
the other end exactly like the real serial port, e.g. ``Uart(port="/tmp/pren-uart-pi")``.
Messages are one JSON object per line, matching ``JsonUartProtocol`` in dog_core.
"""

import json
import logging
import os
import termios
import tty
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_LINK = Path("/tmp/pren-uart-pi")
MAX_LINE = 4096  # same limit as the core's protocol


class PtyLink:
    """One end of a virtual serial cable.

    Args:
        link: A symlink to the port is created here so the core has a fixed path.
            ``None`` skips the symlink (tests use `port` directly).
    """

    def __init__(self, link: Path | None = DEFAULT_LINK) -> None:
        self._master, self._slave = os.openpty()
        # Raw mode: no echo, so what we write is never read back as a command.
        tty.setraw(self._slave)
        os.set_blocking(self._master, False)
        #: Device path of the core's end, e.g. /dev/ttys004.
        self.port = os.ttyname(self._slave)
        self.link = link
        if link is not None:
            link.unlink(missing_ok=True)
            link.symlink_to(self.port)
        self._buffer = bytearray()
        self._unsent = bytearray()  # rest of a line the pty only took part of

    def read_messages(self) -> list[dict]:
        """Every complete message received since the last call. Never blocks."""
        try:
            while chunk := os.read(self._master, 4096):
                self._buffer += chunk
        except BlockingIOError:
            pass
        messages = []
        while (end := self._buffer.find(b"\n")) >= 0:
            line = bytes(self._buffer[:end])
            del self._buffer[: end + 1]
            try:
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise TypeError("not a JSON object")
                messages.append(message)
            except (ValueError, TypeError) as error:
                log.warning("Dropping bad UART line %r: %s", line[:80], error)
        if len(self._buffer) > MAX_LINE:
            log.warning("Dropping %d bytes without a newline", len(self._buffer))
            self._buffer.clear()
        return messages

    def send(self, message: dict) -> None:
        """Write one message, always as whole lines on the wire.

        When nobody reads the port the pty buffer fills up. Then the stale lines are
        thrown away, so a core that connects later starts at a line boundary.
        """
        self._unsent += (json.dumps(message, separators=(",", ":")) + "\n").encode()
        try:
            written = os.write(self._master, self._unsent)
            del self._unsent[:written]
        except BlockingIOError:
            termios.tcflush(self._slave, termios.TCIFLUSH)
            self._unsent.clear()

    def close(self) -> None:
        """Close both ends and remove the symlink."""
        os.close(self._master)
        os.close(self._slave)
        if self.link is not None:
            self.link.unlink(missing_ok=True)
