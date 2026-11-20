"""Replaceable UART framing, movement encoding and sensor decoding."""

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

    def encode_sitz(self) -> bytes:
        """Encode the sit command."""
        ...

    def encode_platz(self) -> bytes:
        """Encode the lie-down command."""
        ...

    def encode_auf(self) -> bytes:
        """Encode the stand-up command."""
        ...

    def encode_brav(self) -> bytes:
        """Encode the praise/reward command."""
        ...

    def encode_signal_found(self) -> bytes:
        """Encode the signal that the bone has been found."""
        ...

    def extract_message(self, buffer: bytearray) -> bytes | None:
        """Remove and return one complete incoming frame, or None if incomplete."""
        ...

    def decode_message(self, message: bytes) -> dict[str, object]:
        """Decode any incoming message, including its non-empty string type."""
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

    def encode_sitz(self) -> bytes:
        return self._encode("sitz")

    def encode_platz(self) -> bytes:
        return self._encode("platz")

    def encode_auf(self) -> bytes:
        return self._encode("auf")

    def encode_brav(self) -> bytes:
        return self._encode("brav")

    def encode_signal_found(self) -> bytes:
        return self._encode("signal_found")

    def extract_message(self, buffer: bytearray) -> bytes | None:
        end = buffer.find(b"\n")
        if end < 0:
            if len(buffer) > 4096:
                buffer.clear()
                raise ValueError("Incoming UART message exceeds 4096 bytes")
            return None
        message = bytes(buffer[:end])
        del buffer[: end + 1]
        if len(message) > 4096:
            raise ValueError("Incoming UART message exceeds 4096 bytes")
        return message

    def decode_message(self, message: bytes) -> dict[str, object]:
        """Temporary incoming format, independent of outbound motor commands.

        {"type":"odometry","timestamp":1.0,"left_distance_m":0.0,
         "right_distance_m":0.0,"heading_deg":90.0}

        Distances are signed cumulative metres, positive forwards; heading is
        clockwise degrees. Timestamp is the sensor's monotonic time in seconds.
        Convert raw encoder counts/IMU units here if the firmware format changes.
        """
        data = json.loads(message)
        if not isinstance(data, dict):
            raise TypeError("Incoming UART message must be an object")
        if not isinstance(data.get("type"), str) or not data["type"]:
            raise ValueError("Incoming UART message needs a non-empty string type")
        return data
