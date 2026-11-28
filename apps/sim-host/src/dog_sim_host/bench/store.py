"""The bench's SQLite database: runs (a queue) and their trials."""

import sqlite3
import time
from pathlib import Path

SCHEMA = """
create table if not exists runs (
    id integer primary key,
    created real not null,
    status text not null default 'queued',  -- queued, running, done, failed
    trigger text not null,                  -- manual, commit, upload
    ref text not null,                      -- branch or commit as asked for
    branch text not null default '',        -- set for runs started by a new commit
    commit_hash text not null default '',
    detector_tree text not null default '', -- git hash of the detector folder at the commit
    model text not null default '',         -- uploaded model name; '' = the commit's own
    trials integer not null,
    done integer not null default 0,
    error text not null default '',
    started real,
    finished real
);
create table if not exists trials (
    run_id integer not null references runs(id),
    seed integer not null,
    negative integer, distance real, angle real, rotation real, floor text,
    brightness real, elevation real, person integer, faults integer, pixels integer,
    box text, hit integer, iou real, confidence real, false_boxes integer,
    image text not null default '',
    primary key (run_id, seed)
);
"""
TRIAL_COLUMNS = [
    "seed",
    "negative",
    "distance",
    "angle",
    "rotation",
    "floor",
    "brightness",
    "elevation",
    "person",
    "faults",
    "pixels",
    "box",
    "hit",
    "iou",
    "confidence",
    "false_boxes",
    "image",
]


def connect(path: Path) -> sqlite3.Connection:
    """Open (and create) the database; rows read like dicts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("pragma journal_mode=wal")
    db.executescript(SCHEMA)
    columns = {row["name"] for row in db.execute("pragma table_info(runs)")}
    if "detector_tree" not in columns:  # databases from before the column
        db.execute("alter table runs add detector_tree text not null default ''")
    return db


def enqueue(
    db: sqlite3.Connection,
    trigger: str,
    ref: str,
    trials: int,
    model: str = "",
    branch: str = "",
    status: str = "queued",
    **fields,
) -> int:
    """Queue a run (or record one with another `status`) and return its id."""
    values = {
        "created": time.time(),
        "trigger": trigger,
        "ref": ref,
        "branch": branch,
        "model": model,
        "trials": trials,
        "status": status,
        **fields,
    }
    with db:
        cursor = db.execute(
            f"insert into runs ({', '.join(values)}) values ({', '.join('?' * len(values))})",
            tuple(values.values()),
        )
    return cursor.lastrowid


def next_queued(db: sqlite3.Connection) -> sqlite3.Row | None:
    """The run to do next: manual ones first, then the oldest."""
    return db.execute(
        "select * from runs where status = 'queued'"
        " order by trigger != 'manual', created limit 1"
    ).fetchone()


def add_trials(db: sqlite3.Connection, run_id: int, rows: list[dict]) -> None:
    """Store scored trials and count them as done."""
    names = ", ".join(TRIAL_COLUMNS)
    marks = ", ".join("?" * len(TRIAL_COLUMNS))
    with db:
        db.executemany(
            f"insert or replace into trials (run_id, {names}) values (?, {marks})",
            [(run_id, *(row[c] for c in TRIAL_COLUMNS)) for row in rows],
        )
        db.execute(
            "update runs set done = (select count(*) from trials where run_id = ?)"
            " where id = ?",
            (run_id, run_id),
        )


def set_status(db: sqlite3.Connection, run_id: int, status: str, **fields) -> None:
    """Change a run's status and any other of its columns."""
    fields["status"] = status
    names = ", ".join(f"{name} = ?" for name in fields)
    with db:
        db.execute(f"update runs set {names} where id = ?", (*fields.values(), run_id))


def summary(db: sqlite3.Connection, run_id: int) -> dict:
    """Hit rate on pictures with the bone, false alarm rate on pictures without."""
    row = db.execute(
        "select sum(not negative and hit) hits, sum(not negative) bones,"
        " sum(negative and false_boxes > 0) alarms, sum(negative) empty,"
        " sum(not negative and false_boxes > 0) extra"
        " from trials where run_id = ?",
        (run_id,),
    ).fetchone()
    bones, empty = row["bones"] or 0, row["empty"] or 0
    return {
        "hit_rate": (row["hits"] or 0) / bones if bones else None,
        "false_alarm_rate": (row["alarms"] or 0) / empty if empty else None,
        "bones": bones,
        "empty": empty,
        "extra_boxes": row["extra"] or 0,
    }
