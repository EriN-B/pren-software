"""Replaceable encoding of movement requests into complete UART messages."""

import json
from typing import Protocol


class UartProtocol(Protocol):
    """An encoder owns the entire message, including framing and checksums.

    Inputs use metres per second and degrees, independent of wire format.
    Implementations should be stateless or safe for concurrent calls.
    """

    def encode_rotate(self, degrees: float) -> bytes:
        """Encode a relative turn; positive degrees mean clockwise."""
        ...

    def encode_drive(self, speed: float, angle: float) -> bytes:
        """Encode speed in m/s and steering angle in degrees."""
        ...

    def encode_stop(self) -> bytes:
        """Encode a request to stop driving and rotation."""
        ...


class JsonUartProtocol:
    """Temporary readable protocol: one ASCII JSON object per line."""

    @staticmethod
    def _encode(command: str, **parameters: float) -> bytes:
        message = json.dumps(
            {"command": command, **parameters}, separators=(",", ":"), allow_nan=False
        )
        # Framing belongs here, so a binary replacement need not use newlines.
        return (message + "\n").encode("ascii")

    def encode_rotate(self, degrees: float) -> bytes:
        return self._encode("rotate", degrees=degrees)

    def encode_drive(self, speed: float, angle: float) -> bytes:
        return self._encode("drive", speed=speed, angle=angle)

    def encode_stop(self) -> bytes:
        return self._encode("stop")
