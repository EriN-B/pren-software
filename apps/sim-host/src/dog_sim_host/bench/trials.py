"""One trial: a seeded random picture of the bone, and the score of the detector's boxes."""

import math
from dataclasses import asdict, dataclass

import cv2
import numpy as np

from dog_sim_host.photos import FAR_AWAY, FLOOR_HALF, Scene, camera_effects

#: Same suite seed, same pictures: what makes two runs comparable.
SUITE_SEED = 2026
FLOOR_SEED = 0  # the generated floor textures
NEGATIVE_SHARE = 0.1  # pictures without the bone, for false alarms
DISTANCE = (
    0.3,
    5.0,
)  # m, camera to bone on the floor; 5 m is the far end of the search
ANGLE = 40.0  # degrees left or right of straight ahead; the picture is +-31 wide
EYE_HEIGHT, EYE_PITCH = (
    0.40,
    20.0,
)  # the dog's camera standing (dog.xml): m, degrees down
FIELD_X, FIELD_Y = (-4.8, 1.5), (-1.5, 1.5)  # where the bone can lie
IOU_HIT = 0.5  # a detection counts when it overlaps the true box this much
# Fewer visible bone pixels (hidden behind a shoe, cut off at the edge) is not a fair
# test: such trials are drawn again. A bone at 5 m still shows about 150.
MIN_PIXELS = 40


@dataclass
class Trial:
    """What a trial looked like and how the detector did on it.

    Angles are in degrees: ``angle`` is where the bone is seen, positive to the left of
    straight ahead; ``rotation`` is the bone's turn against the line of sight, 0 when it
    points at the camera, 90 when it lies across.
    """

    seed: int
    negative: bool
    distance: float
    angle: float
    rotation: float
    floor: str  # "field" (the real linoleum), "tiles" or "linoleum"
    brightness: float
    elevation: float
    person: bool  # a person stands in the direction the camera looks
    faults: bool  # blur, noise and JPEG artefacts added
    pixels: int  # visible bone pixels
    box: tuple[int, int, int, int] | None
    hit: bool = False
    iou: float = 0.0
    confidence: float = 0.0
    false_boxes: int = 0

    def row(self) -> dict:
        """The trial as a flat dict, for the database."""
        values = asdict(self)
        values["box"] = ",".join(map(str, self.box)) if self.box else ""
        return values


def make_trial(scene: Scene, seed: int) -> tuple[Trial, np.ndarray]:
    """Draw trial `seed` of the suite and render it.

    Returns:
        The trial (not yet scored) and the picture the detector gets: 640 x 480, BGR.
    """
    rng = np.random.default_rng([SUITE_SEED, seed])
    negative = bool(rng.random() < NEGATIVE_SHARE)
    while True:  # draws again when the pose does not fit (off the floor, bone unseen)
        bone = np.array([rng.uniform(*FIELD_X), rng.uniform(*FIELD_Y)])
        distance = rng.uniform(*DISTANCE)
        toward = rng.uniform(0, 360)  # compass direction from the camera to the bone
        camera = bone - distance * np.array(
            [math.cos(math.radians(toward)), math.sin(math.radians(toward))]
        )
        if np.abs(camera).max() > FLOOR_HALF - 0.5:  # beyond the floor plane is void
            continue
        angle = rng.uniform(-ANGLE, ANGLE)
        heading = toward - angle + (rng.uniform(70, 290) if negative else 0)
        bone_yaw = rng.uniform(0, 360)
        scene.place(
            bone,
            bone_yaw,
            (*camera, EYE_HEIGHT + rng.normal(0, 0.015)),
            heading,
            pitch=EYE_PITCH + rng.normal(0, 3),
            roll=rng.normal(0, 2),
        )
        person = bool(rng.random() < 0.3)
        if person:
            # Somewhere ahead, not on the bone.
            spot = camera + rng.uniform(0.8, 4) * _compass(
                heading + rng.uniform(-30, 30)
            )
            if np.linalg.norm(spot - bone) < 0.5:
                continue
            scene.place_person(*spot)
        else:
            scene.place_person(*FAR_AWAY)
        box, pixels = scene.bone_box()
        if (pixels == 0) if negative else (pixels >= MIN_PIXELS):
            break
    floor = (
        len(scene.floor_materials) - 1
        if rng.random() < 0.5
        else int(rng.integers(len(scene.floor_materials) - 1))
    )
    light = {
        "brightness": rng.uniform(0.2, 0.8),
        "elevation": rng.uniform(35, 90),
        "azimuth": rng.uniform(0, 360),
        "ambient": rng.uniform(0.25, 0.6),
    }
    scene.set_look(rng, floor=floor, light=light)
    image = scene.render()
    faults = bool(rng.random() < 0.5)
    if faults:
        image = camera_effects(image, rng)
        quality = int(rng.integers(60, 96))
        _, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        image = cv2.imdecode(jpeg, cv2.IMREAD_COLOR)
    trial = Trial(
        seed=seed,
        negative=negative,
        distance=round(float(distance), 3),
        angle=round(float(angle), 2),
        rotation=round(float(abs((bone_yaw - toward + 90) % 180 - 90)), 1),
        floor=_floor_kind(scene, floor),
        brightness=round(light["brightness"], 3),
        elevation=round(light["elevation"], 1),
        person=person,
        faults=faults,
        pixels=pixels,
        box=box,
    )
    return trial, image


def score(trial: Trial, detections: list[tuple[list[float], float]]) -> Trial:
    """Fill in how the detector did: its bone boxes as ([x1, y1, x2, y2], confidence).

    A hit is a box overlapping the true bone box by at least `IOU_HIT`; every other box
    is a false one. Without a bone in the picture every box is false.
    """
    best_iou, best_confidence = 0.0, 0.0
    if trial.box:
        for box, confidence in detections:
            overlap = iou(box, trial.box)
            if overlap > best_iou:
                best_iou, best_confidence = overlap, confidence
    trial.hit = best_iou >= IOU_HIT
    trial.iou = round(best_iou, 3)
    trial.confidence = round(float(best_confidence), 3)
    trial.false_boxes = len(detections) - int(trial.hit)
    return trial


def iou(a, b) -> float:
    """Intersection over union of two boxes (x1, y1, x2, y2)."""
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - w * h
    return w * h / union if union else 0.0


def _compass(degrees: float) -> np.ndarray:
    return np.array([math.cos(math.radians(degrees)), math.sin(math.radians(degrees))])


def _floor_kind(scene: Scene, floor: int) -> str:
    if floor == scene.field_floor:
        return "field"
    return (
        "tiles" if floor % 2 == 0 else "linoleum"
    )  # photos.generated_floors alternates
