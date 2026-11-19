"""Shared definition of the data exchanged between the web simulator and the sim host.

Transport: one WebSocket (default ``ws://localhost:8780``), one JSON object per message,
each with a ``type`` field. The web side mirrors these types as JSDoc typedefs in
``apps/dog-simulator/src/protocol.js``; change both together.

Server to browser:
    - `SceneMessage` once after connecting: every shape to draw.
    - `FrameMessage` about 30 times a second: where everything is now.

Browser to server: the `ClientMessage` types below.
"""

from typing import Literal, TypedDict

PORT = 8780


class Geom(TypedDict):
    """One shape to draw. Sizes follow MuJoCo: half extents, radius, half length."""

    name: str
    body: str
    type: Literal["plane", "sphere", "capsule", "ellipsoid", "cylinder", "box"]
    size: list[float]
    rgba: list[float]


class SceneMessage(TypedDict):
    type: Literal["scene"]
    geoms: list[Geom]


class Joint(TypedDict):
    """One actuated joint, for the joint panel."""

    name: str
    angle: float  # rad
    velocity: float  # rad/s
    target: float  # actuator target: rad for servos, rad/s for wheels
    torque: float  # Nm the motor applies
    limit: float  # Nm the motor can apply at most


class Spring(TypedDict):
    """One leg tension spring ("Zugfeder")."""

    name: str
    start: list[float]  # world position of the body end
    end: list[float]  # world position of the leg end
    force: float  # N it pulls with; 0 when slack


class FrameMessage(TypedDict):
    type: Literal["frame"]
    time: float  # simulation time, s
    poses: list[list[float]]  # per geom of the scene: x, y, z, qw, qx, qy, qz
    camera: list[float]  # dog's eye: x, y, z, qw, qx, qy, qz (looks along -z)
    joints: list[Joint]
    sensors: dict[str, float]  # odometry, heading, sonar, IMU
    pico: dict  # posture, motion, emergency stop, UART log
    core: dict  # attached, state, error
    detections: dict[str, list[float]]  # label -> pixel box x1, y1, x2, y2 (640 x 480)
    springs: list[Spring]


class PicoMessage(TypedDict):
    """Send a UART command straight to the Pico, as the core would."""

    type: Literal["pico"]
    message: dict  # e.g. {"command": "drive", "speed": 0.1, "angle": 0}


class VoiceMessage(TypedDict):
    """Speak a word to the dog (needs the core)."""

    type: Literal["voice"]
    word: str


class GestureMessage(TypedDict):
    """Show a gesture to the camera, or ``None`` for no gesture (needs the core)."""

    type: Literal["gesture"]
    gesture: Literal["auf", "sitz", "platz"] | None


class EmergencyStopMessage(TypedDict):
    type: Literal["emergency_stop"]
    active: bool


class PlaceMessage(TypedDict):
    type: Literal["place"]
    object: Literal["bone", "person"]
    x: float
    y: float


class ResetMessage(TypedDict):
    type: Literal["reset"]


ClientMessage = (
    PicoMessage
    | VoiceMessage
    | GestureMessage
    | EmergencyStopMessage
    | PlaceMessage
    | ResetMessage
)
