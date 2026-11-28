"""Generate the competition field in scene.xml: tape on the floor and pylons.

As in the task drawing (PREN Abbildung 3) and the photos of the taped field (2026-11-27):
the dog starts in a 20 x 50 cm start field in the middle of a taped circle of 1.5 m radius
(the interaction area). The search area is a 30 degree segment with its tip at the dog,
behind it (the core turns 180 degrees for "such"), from the circle out to 5 m: two straight
lines and an arc between the pylons, which stand on its two far corners (2588 mm apart).

    .venv/bin/python apps/sim-host/scripts/build_field.py

Rewrites the block between the ``field:begin`` and ``field:end`` markers in scene.xml.
"""

import math
import re
from pathlib import Path

SCENE_XML = Path(__file__).parents[1] / "src/dog_sim_host/assets/scene.xml"

START_FIELD = (0.5, 0.2)  # m along and across the search direction
INTERACTION_RADIUS = 1.5  # m
SEARCH_ANGLE = math.radians(30)
SEARCH_RADIUS = 5.0  # m from the dog, where the pylons stand
SEARCH_DIRECTION = math.pi  # behind the dog, which starts facing +x
TAPE_WIDTH = (
    0.02  # m, white floor tape (photos: about a seventh of the 14 cm cone base)
)
TAPE_HEIGHT = 0.0005  # m, half height: lies on the floor
ARC_STEP = math.radians(4)  # tape pieces along the circle


def tape(name: str, a: tuple[float, float], b: tuple[float, float]) -> str:
    """One straight piece of tape from a to b, as a flat box."""
    (x1, y1), (x2, y2) = a, b
    length = math.hypot(x2 - x1, y2 - y1)
    yaw = math.atan2(y2 - y1, x2 - x1)
    return (
        f'    <geom name="{name}" class="tape" pos="{(x1 + x2) / 2:.4f} {(y1 + y2) / 2:.4f} '
        f'{TAPE_HEIGHT:.4f}" size="{length / 2 + TAPE_WIDTH / 2:.4f} {TAPE_WIDTH / 2:.4f} '
        f'{TAPE_HEIGHT:.4f}" euler="0 0 {yaw:.4f}"/>'
    )


def polar(radius: float, angle: float) -> tuple[float, float]:
    return radius * math.cos(angle), radius * math.sin(angle)


def arc(name: str, radius: float, start: float, sweep: float) -> list[str]:
    """Tape along a circle from angle start, counter-clockwise by sweep, in short pieces."""
    steps = math.ceil(abs(sweep) / ARC_STEP)
    angles = [start + sweep * i / steps for i in range(steps + 1)]
    return [
        tape(f"{name}_{i}", polar(radius, a), polar(radius, b))
        for i, (a, b) in enumerate(zip(angles, angles[1:]))
    ]


def build() -> str:
    lines = []
    half_l, half_w = START_FIELD[0] / 2, START_FIELD[1] / 2
    corners = [
        (half_l, half_w),
        (-half_l, half_w),
        (-half_l, -half_w),
        (half_l, -half_w),
    ]
    for i in range(4):
        lines.append(tape(f"tape_start_{i}", corners[i], corners[(i + 1) % 4]))

    left = SEARCH_DIRECTION - SEARCH_ANGLE / 2
    right = SEARCH_DIRECTION + SEARCH_ANGLE / 2
    for side, angle in (("left", left), ("right", right)):
        start, end = polar(INTERACTION_RADIUS, angle), polar(SEARCH_RADIUS, angle)
        lines.append(tape(f"tape_search_{side}", start, end))
        x, y = end
        lines.append(
            f'    <geom name="pylon_{side}" class="pylon" pos="{x:.4f} {y:.4f} 0"/>'
        )

    lines += arc("tape_search_far", SEARCH_RADIUS, left, SEARCH_ANGLE)
    lines += arc("tape_circle", INTERACTION_RADIUS, 0, 2 * math.pi)
    return "\n".join(lines)


def main() -> None:
    text = SCENE_XML.read_text()
    text, count = re.subn(
        r"(<!-- field:begin[^\n]*\n).*?([ \t]*<!-- field:end -->)",
        lambda m: m[1] + build() + "\n" + m[2],
        text,
        flags=re.DOTALL,
    )
    if count != 1:
        raise SystemExit("scene.xml needs exactly one field:begin / field:end block")
    SCENE_XML.write_text(text)
    print(f"wrote the field into {SCENE_XML.name}")


if __name__ == "__main__":
    main()
