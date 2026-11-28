"""Shared definition of the data exchanged between the web simulator and the sim host.

Transport: one WebSocket (default ``ws://localhost:8780``), one JSON object per message,
each with a ``type`` field. The web side mirrors these types as JSDoc typedefs in
``apps/dog-simulator/src/protocol.js``; change both together.

Server to browser:
    - `SceneMessage` once after connecting: every shape to draw.
    - `FrameMessage` about 30 times a second: where everything is now.

Browser to server: the `ClientMessage` types below.
"""

from typing import Literal, NotRequired, TypedDict

PORT = 8780


class Geom(TypedDict):
    """One shape to draw. Sizes follow MuJoCo: half extents, radius, half length."""

    name: str
    body: str
    type: Literal["plane", "sphere", "capsule", "ellipsoid", "cylinder", "box", "mesh"]
    size: list[float]
    rgba: list[float]
    mesh: NotRequired[str]  # key into SceneMessage.meshes, only for type "mesh"


class Mesh(TypedDict):
    """Triangles of a CAD part in metres, in the frame of the geoms that use it."""

    vertices: list[float]  # x, y, z, x, y, z, ...
    faces: list[int]  # three vertex indices per triangle


class SceneMessage(TypedDict):
    type: Literal["scene"]
    geoms: list[Geom]
    meshes: dict[str, Mesh]


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


class CoreDetection(TypedDict):
    """One box the core's own detector (YOLO) reported, read from the core's log."""

    label: Literal["bone", "person", "shoe"]
    box: list[float]  # pixel box x1, y1, x2, y2 in 640 x 480
    confidence: float


class Light(TypedDict):
    """Light of the dog's camera image; the viewer's 3D view keeps its own."""

    brightness: float  # sun, 0 to 1
    elevation: float  # sun height in degrees, 90 = straight above
    azimuth: float  # where the sun stands, degrees counter-clockwise from +x
    ambient: float  # light from all sides, 0 to 1


class FrameMessage(TypedDict):
    type: Literal["frame"]
    time: float  # simulation time, s
    poses: list[list[float]]  # per geom of the scene: x, y, z, qw, qx, qy, qz
    camera: list[float]  # dog's eye: x, y, z, qw, qx, qy, qz (looks along -z)
    joints: list[Joint]
    sensors: dict[str, float]  # odometry, heading, sonar, IMU
    pico: dict  # posture, motion, emergency stop, UART log
    light: "Light"  # of the dog's camera image
    core: dict  # attached, state, error
    detections: dict[
        str, list[float]
    ]  # true position: label -> box x1, y1, x2, y2 (640 x 480)
    core_detections: list[CoreDetection]  # what the core's detector found just now
    springs: list[Spring]


class LogEntry(TypedDict):
    """One log line: from the sim host, the dog core, or a UART command to the Pico."""

    seq: int  # increasing; a viewer that reconnects gets everything again
    time: float  # wall clock, seconds since 1970
    source: Literal["core", "sim", "uart"]
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    message: str


class LogsMessage(TypedDict):
    """New log lines, sent with the frames; the backlog once after connecting."""

    type: Literal["logs"]
    entries: list[LogEntry]


# Binary messages carry images: one byte for which image, then a JPEG.
# 0 = the dog's camera as the core gets it (640 x 480), 1 = the webcam the core's
# gesture model watches (480 wide). Both only with the core running.


class PicoMessage(TypedDict):
    """Send a UART command straight to the Pico, as the core would."""

    type: Literal["pico"]
    message: dict  # e.g. {"command": "drive", "speed": 0.1, "angle": 0}


class EmergencyStopMessage(TypedDict):
    type: Literal["emergency_stop"]
    active: bool


class PlaceMessage(TypedDict):
    type: Literal["place"]
    object: Literal["bone", "person"]
    x: float
    y: float
    yaw: float  # degrees, counter-clockwise; turns the bone, ignored for the person


class ResetMessage(TypedDict):
    """Reset world and Pico; with the core, restart the whole sim host (about 5 s)."""

    type: Literal["reset"]


class RandomBoneMessage(TypedDict):
    """Put the bone at a random spot in the search area, turned at random."""

    type: Literal["random_bone"]


class LightMessage(TypedDict):
    """Light of the dog's camera image, the one the core sees (see `Light`)."""

    type: Literal["light"]
    brightness: float
    elevation: float
    azimuth: float
    ambient: float


class RandomLightMessage(TypedDict):
    """A random light, in the ranges of the training images."""

    type: Literal["random_light"]


class VoiceMessage(TypedDict):
    """With the core: a voice command, as if its microphone had heard the word."""

    type: Literal["voice"]
    word: Literal["hier", "sitz", "platz", "auf", "such", "brav"]


ClientMessage = (
    PicoMessage
    | EmergencyStopMessage
    | PlaceMessage
    | ResetMessage
    | RandomBoneMessage
    | LightMessage
    | RandomLightMessage
    | VoiceMessage
)
