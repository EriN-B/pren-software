"""Doing runs: trials in worker processes, the queue, and watching GitHub for commits."""

import logging
import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from dog_sim_host.bench import detector as det
from dog_sim_host.bench import store
from dog_sim_host.bench.trials import FLOOR_SEED, make_trial, score

log = logging.getLogger(__name__)


@dataclass
class Config:
    """Where the bench keeps its things and what it watches (from ``BENCH_*`` env)."""

    data: Path = field(
        default_factory=lambda: Path(os.environ.get("BENCH_DATA", "data"))
    )
    repo_url: str = os.environ.get(
        "BENCH_REPO", "https://github.com/EriN-B/pren-software.git"
    )
    branches: list[str] = field(
        default_factory=lambda: os.environ.get(
            "BENCH_BRANCHES", "dev-core,develop"
        ).split(",")
    )
    workers: int = int(os.environ.get("BENCH_WORKERS", "2"))
    poll_seconds: int = int(os.environ.get("BENCH_POLL", "900"))  # 0 = do not watch
    auto_trials: int = int(os.environ.get("BENCH_TRIALS", "1000"))

    @property
    def db_path(self) -> Path:
        return self.data / "bench.sqlite"

    @property
    def repo(self) -> Path:
        return self.data / "repo.git"

    @property
    def models(self) -> Path:
        return self.data / "models"

    def images(self, run_id: int) -> Path:
        return self.data / "images" / str(run_id)


# One scene and one detector per worker process, built once.
_worker: dict = {}


def _start_worker(code: Path, model: Path | None) -> None:
    from dog_sim_host.photos import Scene

    _worker["scene"] = Scene(np.random.default_rng(FLOOR_SEED))
    _worker["detector"] = det.Detector(code, model)


def _do_trial(job: tuple[int, Path]) -> dict:
    seed, image_dir = job
    trial, image = make_trial(_worker["scene"], seed)
    detections = _worker["detector"].detect(image)
    row = score(trial, detections).row()
    row["image"] = ""
    if (not trial.negative and not trial.hit) or trial.false_boxes:
        # Keep the picture of every miss and false alarm: green truth, red detections.
        if trial.box:
            cv2.rectangle(image, trial.box[:2], trial.box[2:], (0, 200, 0), 1)
        for (x1, y1, x2, y2), confidence in detections:
            cv2.rectangle(image, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 1)
            cv2.putText(
                image,
                f"{confidence:.2f}",
                (int(x1), max(10, int(y1) - 3)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 0, 255),
                1,
            )
        cv2.imwrite(
            str(image_dir / f"{seed}.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 85]
        )
        row["image"] = f"{seed}.jpg"
    return row


def execute(db, config: Config, run) -> None:
    """Do one run: fetch its commit, then all trials not stored yet (resumes)."""
    run_id = run["id"]
    store.set_status(db, run_id, "running", started=time.time(), error="")
    try:
        det.update_clone(config.repo, config.repo_url)
        commit = det.resolve(config.repo, run["ref"])
        code = det.detector_code(config.repo, commit, config.data / "code")
        model = None
        if run["model"]:
            model = config.models / run["model"]
            if not model.exists():
                raise ValueError(f"uploaded model {run['model']!r} is gone")
        store.set_status(db, run_id, "running", commit_hash=commit)
        done = {
            r[0]
            for r in db.execute("select seed from trials where run_id = ?", (run_id,))
        }
        todo = [seed for seed in range(run["trials"]) if seed not in done]
        image_dir = config.images(run_id)
        image_dir.mkdir(parents=True, exist_ok=True)
        with ProcessPoolExecutor(
            config.workers,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_start_worker,
            initargs=(code, model),
        ) as pool:
            batch = []
            for row in pool.map(_do_trial, [(s, image_dir) for s in todo], chunksize=4):
                batch.append(row)
                if len(batch) >= 50:
                    store.add_trials(db, run_id, batch)
                    batch = []
            store.add_trials(db, run_id, batch)
        store.set_status(db, run_id, "done", finished=time.time())
        log.info("Run %d done: %s", run_id, store.summary(db, run_id))
    except Exception as error:  # a bad commit or model fails its run, not the bench
        log.exception("Run %d failed", run_id)
        store.set_status(db, run_id, "failed", finished=time.time(), error=str(error))


def work_forever(config: Config) -> None:
    """Take runs from the queue one after another; a run cut off by a restart goes on."""
    db = store.connect(config.db_path)
    with db:
        db.execute("update runs set status = 'queued' where status = 'running'")
    while True:
        run = store.next_queued(db)
        if run is None:
            time.sleep(5)
        else:
            execute(db, config, run)


def check_branches(db, config: Config) -> list[int]:
    """Queue a run for each watched branch whose newest commit has none yet.

    A newer commit replaces a queued run of an older one on the same branch, so a busy
    branch never piles up a queue.
    """
    queued = []
    for branch, commit in det.remote_heads(config.repo_url, config.branches).items():
        seen = db.execute(
            "select 1 from runs where branch = ? and ref = ?", (branch, commit)
        ).fetchone()
        if seen:
            continue
        with db:
            db.execute(
                "update runs set status = 'skipped', error = 'newer commit came'"
                " where branch = ? and status = 'queued' and trigger = 'commit'",
                (branch,),
            )
        queued.append(
            store.enqueue(db, "commit", commit, config.auto_trials, branch=branch)
        )
        log.info("New commit on %s: %s, queued", branch, commit[:9])
    return queued


def poll_forever(config: Config) -> None:
    """Check the watched branches every `Config.poll_seconds`."""
    db = store.connect(config.db_path)
    while True:
        try:
            check_branches(db, config)
        except Exception:  # GitHub down or no network: try again next time
            log.exception("Checking branches failed")
        time.sleep(config.poll_seconds)
