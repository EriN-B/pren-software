"""The detector bench without a detector: trials, scoring, queue, watch, uploads, pages."""

import io
import zipfile

import numpy as np
import pytest
from dog_sim_host.bench import runner, store, web
from dog_sim_host.bench.trials import MIN_PIXELS, Trial, make_trial, score
from dog_sim_host.photos import Scene


@pytest.fixture(scope="module")
def scene():
    return Scene(np.random.default_rng(0))


def test_same_seed_gives_the_same_picture(scene):
    first, image = make_trial(scene, 7)
    make_trial(scene, 8)  # another trial in between changes nothing
    again, image_again = make_trial(scene, 7)
    assert first == again
    assert np.array_equal(image, image_again)
    assert image.shape == (480, 640, 3)


def test_trials_show_the_bone_fairly_or_not_at_all(scene):
    trials = [make_trial(scene, seed)[0] for seed in range(40)]
    for trial in trials:
        if trial.negative:
            assert trial.box is None and trial.pixels == 0
        else:
            assert trial.box and trial.pixels >= MIN_PIXELS
        assert 0.3 <= trial.distance <= 5 and -40 <= trial.angle <= 40
        assert 0 <= trial.rotation <= 90
    assert any(t.negative for t in trials) and not all(t.negative for t in trials)


def _trial(box=(100, 100, 200, 150)):
    return Trial(
        seed=0,
        negative=box is None,
        distance=1,
        angle=0,
        rotation=0,
        floor="field",
        brightness=0.5,
        elevation=60,
        person=False,
        faults=False,
        pixels=0 if box is None else 500,
        box=box,
    )


def test_score_counts_a_hit_and_false_boxes():
    trial = score(_trial(), [([102, 98, 198, 152], 0.8), ([400, 10, 420, 20], 0.4)])
    assert trial.hit and trial.false_boxes == 1 and trial.confidence == 0.8
    assert not score(_trial(), [([100, 100, 120, 110], 0.9)]).hit  # too little overlap
    empty = score(_trial(box=None), [([1, 1, 5, 5], 0.5)])
    assert not empty.hit and empty.false_boxes == 1


def test_queue_takes_manual_runs_first_and_summarises(tmp_path):
    db = store.connect(tmp_path / "b.sqlite")
    auto = store.enqueue(db, "commit", "abc", 2, branch="develop")
    manual = store.enqueue(db, "manual", "develop", 2)
    assert store.next_queued(db)["id"] == manual
    rows = [
        {
            **score(_trial(), [([100, 100, 200, 150], 0.9)]).row(),
            "seed": 0,
            "image": "",
        },
        {**score(_trial(box=None), []).row(), "seed": 1, "image": ""},
    ]
    store.add_trials(db, auto, rows)
    assert db.execute("select done from runs where id = ?", (auto,)).fetchone()[0] == 2
    result = store.summary(db, auto)
    assert result["hit_rate"] == 1 and result["false_alarm_rate"] == 0


def test_watch_queues_each_new_commit_once_and_drops_stale_ones(tmp_path, monkeypatch):
    config = runner.Config(data=tmp_path, branches=["develop"], auto_trials=5)
    db = store.connect(config.db_path)
    heads = {"develop": "1" * 40}
    monkeypatch.setattr(runner.det, "remote_heads", lambda url, branches: heads)
    first = runner.check_branches(db, config)
    assert len(first) == 1 and runner.check_branches(db, config) == []
    heads["develop"] = "2" * 40
    runner.check_branches(db, config)
    old = db.execute("select status from runs where id = ?", first).fetchone()[0]
    assert old == "skipped"


def test_upload_unpacks_an_ncnn_zip_and_refuses_bad_names(tmp_path):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for name in ("model.ncnn.param", "model.ncnn.bin", "metadata.yaml"):
            archive.writestr(f"best_ncnn_model/{name}", name)
    name = web.save_model(tmp_path, "best.zip", data.getvalue())
    assert name == "best_ncnn_model"
    assert (tmp_path / name / "model.ncnn.bin").read_text() == "model.ncnn.bin"
    with pytest.raises(ValueError):
        web.save_model(tmp_path, "../evil.zip", data.getvalue())
    with pytest.raises(ValueError):  # a pickle runs code when loaded
        web.save_model(tmp_path, "best.pt", b"pickle")


def test_pages_render(tmp_path):
    config = runner.Config(data=tmp_path, branches=["develop"])
    db = store.connect(config.db_path)
    a, b = (
        store.enqueue(db, "manual", "develop", 1),
        store.enqueue(db, "manual", "x", 1),
    )
    for run_id, hit in ((a, True), (b, False)):
        trial = score(_trial(), [([100, 100, 200, 150], 0.9)] if hit else [])
        store.add_trials(db, run_id, [{**trial.row(), "image": "" if hit else "0.jpg"}])
    assert "Runs" in web.index(db, config)
    assert "<svg" in web.run_page(db, b) and "seed 0" in web.run_page(db, b)
    assert "only run" in web.compare_page(db, a, b)
