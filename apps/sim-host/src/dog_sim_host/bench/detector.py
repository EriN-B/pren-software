"""The core's bone detector at a given commit, optionally with another model file.

The bench takes ``object_model.py`` and its model from ``apps/robot/dog-perception`` at
that commit, so it runs exactly the robot's code and thresholds. Only that one file is
imported (not the package), so MediaPipe and the gesture model are not needed.
"""

import importlib.util
import io
import shutil
import subprocess
import tarfile
from pathlib import Path

PERCEPTION = "apps/robot/dog-perception/src/dog_perception"


def git(repo: Path, *args: str) -> str:
    """Run git on the bench's clone and return its output."""
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def update_clone(repo: Path, url: str) -> None:
    """Clone `url` once (without file contents until needed), then fetch all branches."""
    if not (repo / "HEAD").exists():
        repo.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "-q", "--bare", "--filter=blob:none", url, str(repo)],
            check=True,
        )
    git(repo, "fetch", "-q", "--prune", "origin", "+refs/heads/*:refs/heads/*")


def remote_heads(url: str, branches: list[str]) -> dict[str, str]:
    """Latest commit of each branch on the remote, without fetching."""
    out = subprocess.run(
        ["git", "ls-remote", url, *[f"refs/heads/{b}" for b in branches]],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    heads = {}
    for line in out.splitlines():
        commit, ref = line.split("\t")
        heads[ref.removeprefix("refs/heads/")] = commit
    return heads


def resolve(repo: Path, ref: str) -> str:
    """Full commit hash of a branch name or (short) hash."""
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")


def detector_tree(repo: Path, commit: str) -> str | None:
    """Git hash of the detector folder at a commit: equal hashes, equal detector."""
    try:
        return git(repo, "rev-parse", f"{commit}:{PERCEPTION}")
    except subprocess.CalledProcessError:
        return None


def detector_code(repo: Path, commit: str, cache: Path) -> Path:
    """Folder with that commit's ``object_model.py`` and its bundled model.

    Raises:
        ValueError: The commit has no detector at `PERCEPTION`.
    """
    target = cache / commit
    if (target / "object_model.py").exists():
        return target
    try:
        archive = subprocess.run(
            ["git", "-C", str(repo), "archive", commit, PERCEPTION],
            check=True,
            capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as error:
        raise ValueError(f"commit {commit[:9]} has no {PERCEPTION}") from error
    partial = cache / f"{commit}.partial"
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(partial, filter="data")
    (partial / PERCEPTION).rename(target)
    shutil.rmtree(partial)
    return target


class Detector:
    """The core's ``ObjectModel``, used the way the core's search uses it.

    Args:
        code: Folder from `detector_code`.
        model: Model file or NCNN folder to use instead of the commit's own, or None.
    """

    def __init__(self, code: Path, model: Path | None = None) -> None:
        spec = importlib.util.spec_from_file_location(
            f"bench_object_model_{code.name}", code / "object_model.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.model = module.ObjectModel(model)

    def detect(self, image) -> list[tuple[list[float], float]]:
        """Bone boxes as ([x1, y1, x2, y2], confidence) in a 640 x 480 BGR picture."""
        boxes = self.model.get_objects(image).boxes
        return list(zip(boxes.xyxy.tolist(), boxes.conf.tolist(), strict=True))
