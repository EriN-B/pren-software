"""Turn the bone scan (Knochen.stl) into the light mesh the simulator uses.

The scan has 685,000 triangles, lies at an angle and is 289 mm long. This lays it flat
(longest side along x, thinnest side up), centres it, scales it to the competition
bone's 21 cm and reduces it to a few thousand triangles.

    uv run --no-project --with trimesh --with fast-simplification python apps/sim-host/scripts/prepare_bone.py
"""

from pathlib import Path

import numpy as np
import trimesh

MESHES = Path(__file__).parents[1] / "src/dog_sim_host/assets/meshes/STL"
# Enough for the camera and the viewer; MuJoCo collides with the convex hull anyway.
FACES = 4000
LENGTH = 210.0  # mm, the competition bone (task, figure 3)


def main() -> None:
    mesh = trimesh.load(MESHES / "Knochen.stl")
    mesh = mesh.simplify_quadric_decimation(face_count=FACES)
    centred = mesh.vertices - mesh.vertices.mean(axis=0)
    axes = np.linalg.svd(centred, full_matrices=False)[2]  # longest, middle, thinnest
    if np.linalg.det(axes) < 0:
        axes[2] = -axes[2]  # keep it a rotation, not a mirror image
    mesh.vertices = centred @ axes.T
    mesh.vertices -= (mesh.vertices.max(axis=0) + mesh.vertices.min(axis=0)) / 2
    mesh.vertices *= LENGTH / np.ptp(mesh.vertices[:, 0])
    mesh.export(MESHES / "Knochen_sim.stl")
    size = mesh.vertices.max(axis=0) - mesh.vertices.min(axis=0)
    print(f"Knochen_sim.stl: {len(mesh.faces)} triangles, {size.round(1)} mm")


if __name__ == "__main__":
    main()
