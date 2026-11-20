"""Generate the four legs in dog.xml from the hole positions of the CAD parts.

Each leg is the CAD test setup ("Testaufbau"): a four-bar linkage on the mounting plate
(Grundkörper). The servo turns the drive strut (Antriebsstütze), the linkage swings on
the hip axle, and the leg (Bein) is the coupler between them, with the wheel (Rad) at its
end. Because both bars are nearly the same length, the leg stays almost upright while the
servo raises or lowers the body.

Run after a CAD change, then the tests:

    uv run python apps/sim-host/scripts/build_legs.py
    uv run pytest apps/sim-host

It rewrites the block between the ``legs:begin`` and ``legs:end`` markers in dog.xml and
the dog's start height.
"""

import math
import re
from pathlib import Path

import mujoco
import numpy as np

DOG_XML = Path(__file__).parents[1] / "src/dog_sim_host/assets/dog.xml"

# Hole centres in each STL's own frame, millimetres, measured from the meshes.
PLATE_HIP = np.array([-40.0, 60.0])  # Achse_Grundkörper, the 6 mm boss
# Assumption: the MG946R output shaft, 10 mm off the centre of its mounting holes
# (-64, 34.85), on the side that makes the linkage nearly a parallelogram. Confirm with CAD.
PLATE_SERVO = np.array([-64.0, 24.85])
CRANK_AXLE = np.array(
    [-107.4, 0.0]
)  # Antriebsstütze; the servo horn screw is at (0, 0)
LINK_LEG = np.array([-97.2, 0.0])  # linkage; the hip end is at (0, 0)
LINK_HOOK = np.array([-53.0, 4.0])  # small hole, taken as the spring hook
LEG_UPPER = np.array([25.0, 7.5])  # Bein: linkage joint
LEG_LOWER = np.array([69.0, 7.5])  # Bein: drive strut joint
LEG_WHEEL = np.array([160.0, 7.5])  # Bein: wheel axle (Achse_Rad)
LEG_HOOK = np.array([0.0, 4.0])  # small hole, taken as the spring hook
WHEEL_RADIUS = 20.0  # Rad

# Servo angle 0 (auf): the crank points this far below horizontal, so the legs are nearly
# stretched and the servos can lower the body by about 45 degrees (sitz, platz).
AUF_CRANK = math.radians(40)

# Placement on the torso, metres in the dog's frame (x forwards, y left, z up).
HIP_X = 0.10  # hip axle distance from the body centre, front and rear
HIP_Z = -0.04  # hip axle height relative to the torso centre
JOINT_Y = 0.12  # sideways position of all joints of one leg
# Sideways position of each part's mesh origin (its z = 0 face), so the parts stack
# outwards: plate against the torso, bars, leg, wheel.
LAYER_Y = {
    "plate": 0.100,
    "crank": 0.116,
    "linkage": 0.113,
    "leg": 0.124,
    "wheel": 0.135,
}

LEGS = {  # name: (fore +1 / aft -1, left +1 / right -1, wheel body name)
    "front_left": (1, 1, "wheel_left"),
    "front_right": (1, -1, "wheel_right"),
    "rear_left": (-1, 1, None),
    "rear_right": (-1, -1, None),
}


def solve_leg(crank_angle: float) -> tuple[np.ndarray, np.ndarray] | None:
    """Close the four-bar for a crank angle (plate frame, radians).

    Returns:
        The leg's two joint positions (upper, lower) in plate millimetres, or None when
        the bars cannot reach. Takes the open (uncrossed) solution.
    """
    crank = float(np.linalg.norm(CRANK_AXLE))
    link = float(np.linalg.norm(LINK_LEG))
    coupler = float(np.linalg.norm(LEG_LOWER - LEG_UPPER))
    lower = PLATE_SERVO + crank * np.array(
        [math.cos(crank_angle), math.sin(crank_angle)]
    )
    to_lower = lower - PLATE_HIP
    d = float(np.linalg.norm(to_lower))
    if not abs(link - coupler) < d < link + coupler:
        return None
    a = (link**2 - coupler**2 + d**2) / (2 * d)
    e = to_lower / d
    upper = PLATE_HIP + a * e + math.sqrt(link**2 - a**2) * np.array([-e[1], e[0]])
    return upper, lower


def leg_direction(crank_angle: float) -> float:
    """Angle of the leg (upper to lower joint) in the plate frame."""
    solved = solve_leg(crank_angle)
    assert solved is not None
    upper, lower = solved
    return math.atan2(*(lower - upper)[::-1])


def neutral_crank() -> float:
    """Crank angle (plate frame) of the auf pose: leg vertical, crank `AUF_CRANK` down."""
    # Leg minus crank direction falls as the crank turns up; bisect for the wanted angle.
    wanted = -math.pi / 2 + AUF_CRANK
    lo, hi = math.radians(-90), 0.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if leg_direction(mid) - mid > wanted:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def quat(columns: list[np.ndarray]) -> str:
    """MJCF quaternion of the rotation whose columns are the given axes."""
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.column_stack(columns).flatten())
    return fmt(q)


def fmt(values) -> str:
    return " ".join(f"{v:.5g}" if abs(v) > 1e-9 else "0" for v in values)


def build() -> tuple[str, float]:
    """Return the generated MJCF block and the torso height when standing on it."""
    theta0 = neutral_crank()
    phi = -math.pi / 2 - leg_direction(theta0)  # turn the plate so the leg points down
    rot = np.array([[math.cos(phi), -math.sin(phi)], [math.sin(phi), math.cos(phi)]])
    upper, lower = solve_leg(theta0)
    down = (lower - upper) / np.linalg.norm(lower - upper)
    wheel = upper + (LEG_WHEEL - LEG_UPPER)[0] * down
    lines = []
    for name, (fore, side, wheel_name) in LEGS.items():
        out = np.array([0.0, side, 0.0])  # outwards, the joints' common axis

        def at(p: np.ndarray, fore: int = fore, side: int = side) -> np.ndarray:
            """Plate millimetres to the dog's frame in metres, at the joints' y."""
            u, v = rot @ (p - PLATE_HIP) / 1000
            return np.array([fore * (HIP_X + u), side * JOINT_Y, HIP_Z + v])

        def bar(
            start: np.ndarray, end: np.ndarray, out: np.ndarray = out
        ) -> list[np.ndarray]:
            """Axes of a part whose +x points from end to start, thickness outwards."""
            x = (at(start) - at(end)) / np.linalg.norm(at(start) - at(end))
            return [x, np.cross(out, x), out]

        def place(
            origin: np.ndarray, axes: list[np.ndarray], hole: np.ndarray
        ) -> np.ndarray:
            """Dog-frame position of a hole given in a part's own millimetres."""
            return origin + np.column_stack(axes) @ np.append(hole / 1000, 0)

        def layer(part: str, out: np.ndarray = out) -> np.ndarray:
            """Sideways shift from the joints' y to where a part's mesh starts."""
            return out * (LAYER_Y[part] - JOINT_Y)

        hip, servo = at(PLATE_HIP), at(PLATE_SERVO)
        up, low, whl = at(upper), at(lower), at(wheel)
        # Plate: its x/y plane is the leg's plane. Mirror the mesh where a plain rotation
        # would turn the hip boss towards the torso (two of the four plates are mirrored).
        px = np.array([fore * rot[0, 0], 0, rot[1, 0]])
        py = np.array([fore * rot[0, 1], 0, rot[1, 1]])
        pz = np.cross(px, py)
        plate_mesh = "plate" if pz @ out > 0 else "plate_mirrored"
        plate_pos = at(np.zeros(2)) + layer("plate")
        crank_axes = bar(PLATE_SERVO, lower)
        link_axes = bar(PLATE_HIP, upper)
        leg_axes = bar(lower, upper)  # Bein's +x runs down the leg
        leg_origin = place(up, leg_axes, -LEG_UPPER)
        link_hook = place(hip, link_axes, LINK_HOOK)
        leg_hook = place(leg_origin, leg_axes, LEG_HOOK)
        tyre = layer("wheel") + out * 0.0025  # middle of the 5 mm thick Rad
        wheel_axes = quat([np.array([1.0, 0, 0]), np.cross(out, [1.0, 0, 0]), out])
        lines += [
            f'      <geom name="plate_{name}" class="part" mesh="{plate_mesh}" pos="{fmt(plate_pos)}" quat="{quat([px, py, pz])}"/>',
            f'      <body name="crank_{name}" pos="{fmt(servo)}">',
            f'        <joint name="servo_{name}" class="servo" axis="0 {-fore} 0"/>',
            f'        <geom name="crank_{name}" class="part" mesh="crank" pos="{fmt(layer("crank"))}" quat="{quat(crank_axes)}"/>',
            f'        <site name="crank_end_{name}" pos="{fmt(low - servo)}"/>',
            "      </body>",
            f'      <body name="linkage_{name}" pos="{fmt(hip)}">',
            f'        <joint name="hip_{name}" class="pin"/>',
            f'        <geom name="linkage_{name}" class="part" mesh="linkage" pos="{fmt(layer("linkage"))}" quat="{quat(link_axes)}"/>',
            f'        <site name="spring_link_{name}" pos="{fmt(link_hook - hip)}"/>',
            f'        <body name="leg_{name}" pos="{fmt(up - hip)}">',
            f'          <joint name="knee_{name}" class="knee"/>',
            f'          <geom name="leg_{name}" class="part" mesh="leg" pos="{fmt(leg_origin - up + layer("leg"))}" quat="{quat(leg_axes)}"/>',
            f'          <site name="leg_attach_{name}" pos="{fmt(low - up)}"/>',
            f'          <site name="spring_leg_{name}" pos="{fmt(leg_hook - up)}"/>',
        ]
        if wheel_name:
            lines += [
                f'          <body name="{wheel_name}" pos="{fmt(whl - up)}">',
                f'            <joint name="{wheel_name}" class="wheel"/>',
                f'            <geom name="{wheel_name}" class="wheel" pos="{fmt(tyre)}"/>',
                f'            <geom name="rad_{name}" class="part" mesh="wheel" pos="{fmt(layer("wheel"))}" quat="{wheel_axes}"/>',
                "          </body>",
            ]
        else:
            # Rear: the wheel is drawn, but touches the floor as a frictionless ball so
            # the dog can turn on its driven front wheels.
            lines += [
                f'          <geom name="caster_{name}" class="caster" pos="{fmt(whl - up + tyre)}"/>',
                f'          <geom name="rad_{name}" class="part" mesh="wheel" pos="{fmt(whl - up + layer("wheel"))}" quat="{wheel_axes}"/>',
            ]
        lines += ["        </body>", "      </body>"]
    height = WHEEL_RADIUS / 1000 - at(wheel)[2]
    return "\n".join(lines), height


def main() -> None:
    block, height = build()
    text = DOG_XML.read_text()
    text = re.sub(
        r"(<!-- legs:begin[^\n]*\n).*?([ \t]*<!-- legs:end -->)",
        lambda m: m[1] + block + "\n" + m[2],
        text,
        flags=re.DOTALL,
    )
    text = re.sub(
        r'(<body name="dog"[^>]*pos=")[^"]*"', rf'\g<1>0 0 {height:.4f}"', text
    )
    DOG_XML.write_text(text)
    print(f"wrote {DOG_XML.name}: torso centre {height:.3f} m above the floor standing")


if __name__ == "__main__":
    main()
