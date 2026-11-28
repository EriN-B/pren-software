"""The bench's dashboard: runs, results per condition, comparisons, failed pictures.

Plain server-rendered pages from the standard library's HTTP server, meant for a home
network (no login). The queue worker and the GitHub watch run as threads beside it.
"""

import html
import io
import re
import shutil
import sqlite3
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dog_sim_host.bench import runner, store
from dog_sim_host.bench.trials import ANGLE, DISTANCE

MAX_UPLOAD = 300 * 1024 * 1024
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
DISTANCE_EDGES = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, DISTANCE[1]]
ANGLE_EDGES = list(range(-int(ANGLE), int(ANGLE) + 1, 10))
#: Groups for the "by condition" tables: title, SQL expression giving the group.
CONDITIONS = [
    (
        "Bone size in the picture",
        "case when pixels < 150 then '1 tiny (<150 px)' when pixels < 500 then '2 small' when pixels < 2000 then '3 medium' else '4 large' end",
    ),
    (
        "Bone turn",
        "case when rotation < 30 then '1 pointing at camera' when rotation < 60 then '2 diagonal' else '3 lying across' end",
    ),
    ("Floor", "floor"),
    (
        "Light",
        "case when brightness < 0.4 then '1 dim' when brightness < 0.6 then '2 medium' else '3 bright' end",
    ),
    ("Person in view direction", "case when person then 'yes' else 'no' end"),
    ("Camera faults", "case when faults then 'yes' else 'no' end"),
]
CSS = """
body { font: 14px/1.45 system-ui, sans-serif; margin: 24px auto; max-width: 1100px; padding: 0 16px; color: #1d1d1b; }
h1 { font-size: 22px; } h2 { font-size: 16px; margin-top: 28px; }
table { border-collapse: collapse; } td, th { padding: 4px 10px; border-bottom: 1px solid #e4e4de; text-align: left; }
th { font-weight: 600; color: #55554f; } td.num { text-align: right; font-variant-numeric: tabular-nums; }
.muted { color: #77776f; } .bad { color: #b3261e; } .good { color: #1e7b34; }
form.inline { display: flex; gap: 8px; align-items: end; flex-wrap: wrap; } label { display: grid; gap: 2px; color: #55554f; }
input, select, button { font: inherit; padding: 4px 8px; } .gallery { display: flex; flex-wrap: wrap; gap: 8px; }
.gallery figure { margin: 0; width: 256px; } .gallery img { width: 256px; display: block; } figcaption { font-size: 12px; color: #55554f; }
.grid { display: flex; gap: 32px; flex-wrap: wrap; align-items: start; }
"""


def serve(config: runner.Config, port: int) -> None:
    """Start the queue worker and the GitHub watch, then serve the dashboard forever."""
    threading.Thread(target=runner.work_forever, args=(config,), daemon=True).start()
    if config.poll_seconds:
        threading.Thread(
            target=runner.poll_forever, args=(config,), daemon=True
        ).start()
    Handler.config = config
    Handler.db = store.connect(config.db_path)
    print(f"Bench dashboard on http://0.0.0.0:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


class Handler(BaseHTTPRequestHandler):
    config: runner.Config
    db: sqlite3.Connection

    def do_GET(self) -> None:
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path == "/":
                self.page("Detector bench", index(self.db, self.config))
            elif match := re.fullmatch(r"/run/(\d+)", url.path):
                self.page(f"Run {match[1]}", run_page(self.db, int(match[1])))
            elif url.path == "/compare":
                a, b = int(query["a"]), int(query["b"])
                self.page(f"Run {a} vs {b}", compare_page(self.db, a, b))
            elif match := re.fullmatch(r"/image/(\d+)/(\d+\.jpg)", url.path):
                self.file(self.config.images(int(match[1])) / match[2], "image/jpeg")
            else:
                self.send_error(404)
        except (KeyError, ValueError, LookupError) as error:
            self.send_error(400, str(error))

    def do_POST(self) -> None:
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        size = int(self.headers.get("Content-Length", 0))
        if not 0 < size <= MAX_UPLOAD:
            self.send_error(413 if size else 400)
            return
        body = self.rfile.read(size)
        try:
            if url.path == "/runs":
                form = {k: v[0] for k, v in parse_qs(body.decode()).items()}
                model = form.get("model", "")
                if model and not (self.config.models / model).exists():
                    raise ValueError(f"no model {model!r}")
                ref = form.get("ref", "develop").strip()
                if not re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", ref):
                    raise ValueError("ref: a branch name or commit hash")
                trials = min(max(int(form.get("trials", 1000)), 10), 100_000)
                store.enqueue(self.db, "manual", ref, trials, model=model)
            elif url.path == "/models":
                name = save_model(self.config.models, query["name"], body)
                trials = self.config.auto_trials
                store.enqueue(
                    self.db, "upload", self.config.branches[-1], trials, model=name
                )
            else:
                self.send_error(404)
                return
        except (KeyError, ValueError, zipfile.BadZipFile) as error:
            self.send_error(400, str(error))
            return
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def page(self, title: str, body: str) -> None:
        refresh = (
            '<meta http-equiv="refresh" content="15">' if "data-live" in body else ""
        )
        text = (
            f"<!doctype html><html lang=en><meta charset=utf-8>{refresh}"
            f"<title>{html.escape(title)}</title><style>{CSS}</style>"
            f'<p class=muted><a href="/">Detector bench</a></p><h1>{html.escape(title)}</h1>{body}'
        )
        self.reply(200, text.encode(), "text/html; charset=utf-8")

    def file(self, path: Path, kind: str) -> None:
        if not path.is_file():
            self.send_error(404)
            return
        self.reply(200, path.read_bytes(), kind)

    def reply(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # quiet: the dashboard reloads itself
        pass


def save_model(models: Path, name: str, body: bytes) -> str:
    """Store an uploaded model: a ``.pt`` file, or a zip holding an NCNN folder.

    Returns:
        The name the model is stored and picked under.
    """
    if not NAME.match(name):
        raise ValueError("model name: letters, digits, . _ -")
    models.mkdir(parents=True, exist_ok=True)
    if name.endswith(".pt"):
        target = models / name
        target.write_bytes(body)
        return name
    stem = name.removesuffix(".zip").removesuffix("_ncnn_model")
    target = (
        models / f"{stem}_ncnn_model"
    )  # Ultralytics tells NCNN folders by this ending
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        params = [n for n in archive.namelist() if n.endswith("model.ncnn.param")]
        if not params:
            raise ValueError("the zip has no model.ncnn.param")
        folder = params[0].removesuffix("model.ncnn.param")
        if target.exists():
            shutil.rmtree(target)
        target.mkdir()
        for member in ("model.ncnn.param", "model.ncnn.bin", "metadata.yaml"):
            (target / member).write_bytes(archive.read(folder + member))
    return target.name


def index(db: sqlite3.Connection, config: runner.Config) -> str:
    runs = db.execute("select * from runs order by id desc limit 200").fetchall()
    models = (
        sorted(p.name for p in config.models.glob("*"))
        if config.models.exists()
        else []
    )
    options = '<option value="">the commit\'s own</option>' + "".join(
        f"<option>{html.escape(m)}</option>" for m in models
    )
    live = any(r["status"] in ("queued", "running") for r in runs)
    rows = []
    for r in runs:
        result = store.summary(db, r["id"]) if r["done"] else {}
        source = r["branch"] or r["ref"]
        rows.append(
            f"<tr><td><input type=checkbox name=pick value={r['id']}></td>"
            f"<td><a href=/run/{r['id']}>{r['id']}</a></td>"
            f"<td>{time.strftime('%d.%m. %H:%M', time.localtime(r['created']))}</td>"
            f"<td>{html.escape(r['trigger'])}</td><td>{html.escape(source[:20])}</td>"
            f"<td class=muted>{r['commit_hash'][:9]}</td><td>{html.escape(r['model']) or '<span class=muted>own</span>'}</td>"
            f"<td>{status(r)}</td><td class=num>{rate(result.get('hit_rate'))}</td>"
            f"<td class=num>{rate(result.get('false_alarm_rate'))}</td></tr>"
        )
    return f"""
<h2>Start a run</h2>
<form class=inline method=post action=/runs>
  <label>Core branch or commit <input name=ref value="{html.escape(config.branches[-1])}" required></label>
  <label>Model <select name=model>{options}</select></label>
  <label>Trials <input name=trials type=number value={config.auto_trials} min=10 max=100000></label>
  <button>Queue</button>
</form>
<h2>Upload a model</h2>
<p class=muted>An NCNN folder as .zip, or a .pt file. It is tested on {html.escape(config.branches[-1])} right away.</p>
<form class=inline id=upload><input type=file id=file accept=".zip,.pt" required><button>Upload</button></form>
<script>
document.getElementById('upload').onsubmit = async (e) => {{
  e.preventDefault();
  const file = document.getElementById('file').files[0];
  const reply = await fetch('/models?name=' + encodeURIComponent(file.name), {{method: 'POST', body: file}});
  if (!reply.ok) alert(await reply.text()); else location.reload();
}};
</script>
<h2>Runs</h2>
<p class=muted>Watching {html.escape(", ".join(config.branches))} for new commits.
Hit rate: bone found in pictures that show it. False alarms: a bone reported in pictures without one.</p>
<form action=/compare onsubmit="const p=[...this.querySelectorAll('[name=pick]:checked')].map(x=>x.value);
 if(p.length!==2){{alert('Pick two runs');return false}} this.a.value=p[1]; this.b.value=p[0];">
<input type=hidden name=a><input type=hidden name=b>
<table><tr><th></th><th>Run</th><th>Queued</th><th>Why</th><th>Core</th><th>Commit</th><th>Model</th><th>Status</th><th>Hit rate</th><th>False alarms</th></tr>
{"".join(rows) or "<tr><td colspan=10 class=muted>No runs yet.</td></tr>"}</table>
<p><button>Compare the two picked runs</button></p></form>
{"<span data-live></span>" if live else ""}"""


def status(run) -> str:
    if run["status"] == "running":
        return f"running {run['done']}/{run['trials']}"
    if run["status"] == "failed":
        return f'<span class=bad title="{html.escape(run["error"])}">failed</span>'
    return html.escape(run["status"])


def rate(value: float | None) -> str:
    return "–" if value is None else f"{value:.0%}"


def run_page(db: sqlite3.Connection, run_id: int) -> str:
    run = db.execute("select * from runs where id = ?", (run_id,)).fetchone()
    if run is None:
        raise LookupError(f"no run {run_id}")
    s = store.summary(db, run_id)
    head = (
        f"<p>Core <b>{html.escape(run['branch'] or run['ref'])}</b> "
        f"<span class=muted>{run['commit_hash'][:9]}</span>, model "
        f"<b>{html.escape(run['model']) or 'the commit’s own'}</b>, {status(run)}, "
        f"{run['done']} of {run['trials']} trials.</p>"
        + (f"<p class=bad>{html.escape(run['error'])}</p>" if run["error"] else "")
        + f"<p>Bone found in <b>{rate(s['hit_rate'])}</b> of {s['bones']} pictures with it; "
        f"false alarms in <b>{rate(s['false_alarm_rate'])}</b> of {s['empty']} without "
        f"({s['extra_boxes']} extra boxes next to a found bone).</p>"
    )
    failures = db.execute(
        "select * from trials where run_id = ? and image != '' order by negative, distance limit 80",
        (run_id,),
    ).fetchall()
    return (
        head
        + "<h2>Bone found, by distance and angle</h2><p class=muted>Rows: distance in m. "
        "Columns: where the bone is seen, degrees left (−) or right of straight ahead; "
        "beyond ±31 it is partly out of the picture.</p>"
        + heatmap(db, run_id)
        + "<h2>By condition</h2><div class=grid>"
        + "".join(
            condition_table(db, title, expr, [run_id]) for title, expr in CONDITIONS
        )
        + f"</div><h2>Missed and false alarms ({len(failures)} shown)</h2>"
        + gallery(run_id, failures)
        + ("<span data-live></span>" if run["status"] in ("queued", "running") else "")
    )


def heatmap(db: sqlite3.Connection, run_id: int, base: int | None = None) -> str:
    """SVG grid of hit rates; with `base`, the change against that run instead."""

    def cells(rid):
        grid = {}
        for row in db.execute(
            "select distance, angle, hit from trials where run_id = ? and not negative",
            (rid,),
        ):
            key = (
                _bin(row["distance"], DISTANCE_EDGES),
                _bin(-row["angle"], ANGLE_EDGES),
            )
            hits, count = grid.get(key, (0, 0))
            grid[key] = (hits + row["hit"], count + 1)
        return grid

    grid, other = cells(run_id), cells(base) if base else None
    w, h, left, top = 64, 26, 70, 22
    parts = [
        f'<svg width="{left + w * (len(ANGLE_EDGES) - 1)}" height="{top + h * (len(DISTANCE_EDGES) - 1) + 4}" font-size="11">'
    ]
    for c in range(len(ANGLE_EDGES) - 1):
        parts.append(
            f'<text x="{left + c * w + w / 2}" y="14" text-anchor="middle" fill="#55554f">{ANGLE_EDGES[c]}…{ANGLE_EDGES[c + 1]}°</text>'
        )
    for r in range(len(DISTANCE_EDGES) - 1):
        y = top + r * h
        parts.append(
            f'<text x="{left - 8}" y="{y + h / 2 + 4}" text-anchor="end" fill="#55554f">{DISTANCE_EDGES[r]:g}–{DISTANCE_EDGES[r + 1]:g} m</text>'
        )
        for c in range(len(ANGLE_EDGES) - 1):
            hits, count = grid.get((r, c), (0, 0))
            label, fill = "", "#f1f1ec"
            if count and other is None:
                value = hits / count
                label, fill = f"{value:.0%}", _colour(value)
            elif count and other.get((r, c), (0, 0))[1]:
                ohits, ocount = other[(r, c)]
                change = hits / count - ohits / ocount
                label = f"{change:+.0%}"
                fill = _colour(0.5 + change / 2)
            parts.append(
                f'<rect x="{left + c * w}" y="{y}" width="{w - 2}" height="{h - 2}" fill="{fill}"><title>{hits}/{count}</title></rect>'
                f'<text x="{left + c * w + w / 2 - 1}" y="{y + h / 2 + 3}" text-anchor="middle">{label}</text>'
            )
    return "".join(parts) + "</svg>"


def condition_table(
    db: sqlite3.Connection, title: str, expr: str, run_ids: list[int]
) -> str:
    by_run = []
    for rid in run_ids:
        rows = db.execute(
            f"select {expr} as grp, sum(hit) hits, count(*) n from trials"
            " where run_id = ? and not negative group by grp order by grp",
            (rid,),
        ).fetchall()
        by_run.append({r["grp"]: (r["hits"], r["n"]) for r in rows})
    groups = sorted(set().union(*by_run))
    head = "".join(f"<th>Run {rid}</th>" for rid in run_ids)
    body = ""
    for g in groups:
        cells = ""
        for result in by_run:
            hits, n = result.get(g, (0, 0))
            cells += f"<td class=num>{rate(hits / n if n else None)} <span class=muted>({n})</span></td>"
        body += f"<tr><td>{html.escape(str(g).lstrip('1234 '))}</td>{cells}</tr>"
    return f"<table><tr><th>{html.escape(title)}</th>{head}</tr>{body}</table>"


def gallery(run_id: int, trials) -> str:
    figures = []
    for t in trials:
        what = (
            "false alarm" if t["negative"] else f"missed, best overlap {t['iou']:.2f}"
        )
        figures.append(
            f'<figure><a href="/image/{run_id}/{t["image"]}"><img loading=lazy src="/image/{run_id}/{t["image"]}"></a>'
            f"<figcaption>seed {t['seed']}: {what}<br>{t['distance']:.1f} m, {t['angle']:+.0f}°, "
            f"turn {t['rotation']:.0f}°, {t['pixels']} px, {t['floor']}</figcaption></figure>"
        )
    return f"<div class=gallery>{''.join(figures) or '<p class=muted>None.</p>'}</div>"


def compare_page(db: sqlite3.Connection, a: int, b: int) -> str:
    sa, sb = store.summary(db, a), store.summary(db, b)
    runs = {
        r["id"]: r for r in db.execute("select * from runs where id in (?, ?)", (a, b))
    }
    if len(runs) != 2:
        raise LookupError("pick two existing runs")

    def label(rid):
        r = runs[rid]
        return f"run {rid}: {html.escape(r['branch'] or r['ref'][:12])} {r['commit_hash'][:9]}, {html.escape(r['model']) or 'own model'}"

    changed = db.execute(
        "select ta.seed, ta.distance, ta.angle, ta.rotation, ta.pixels, ta.floor, ta.hit hit_a,"
        " tb.hit hit_b, ta.image image_a, tb.image image_b from trials ta join trials tb"
        " on ta.seed = tb.seed and tb.run_id = ? where ta.run_id = ? and not ta.negative"
        " and ta.hit != tb.hit order by ta.distance limit 60",
        (b, a),
    ).fetchall()
    figures = []
    for t in changed:
        rid, image = (a, t["image_a"]) if not t["hit_a"] else (b, t["image_b"])
        who = f"only run {b} finds it" if not t["hit_a"] else f"only run {a} finds it"
        figures.append(
            f'<figure><img loading=lazy src="/image/{rid}/{image}"><figcaption>seed {t["seed"]}: {who}<br>'
            f"{t['distance']:.1f} m, {t['angle']:+.0f}°, turn {t['rotation']:.0f}°, {t['pixels']} px</figcaption></figure>"
        )
    return (
        f"<p>A = {label(a)}<br>B = {label(b)}</p>"
        f"<table><tr><th></th><th>A</th><th>B</th></tr>"
        f"<tr><td>Bone found</td><td class=num>{rate(sa['hit_rate'])}</td><td class=num>{rate(sb['hit_rate'])}</td></tr>"
        f"<tr><td>False alarms</td><td class=num>{rate(sa['false_alarm_rate'])}</td><td class=num>{rate(sb['false_alarm_rate'])}</td></tr>"
        f"<tr><td>Pictures with / without bone</td><td class=num>{sa['bones']} / {sa['empty']}</td><td class=num>{sb['bones']} / {sb['empty']}</td></tr></table>"
        "<p class=muted>Same seeds give the same pictures; compare runs with the same number of trials.</p>"
        "<h2>Change in bone found, B against A</h2>"
        + heatmap(db, b, base=a)
        + "<h2>By condition</h2><div class=grid>"
        + "".join(
            condition_table(db, title, expr, [a, b]) for title, expr in CONDITIONS
        )
        + f"</div><h2>Pictures where they differ ({len(changed)} shown)</h2>"
        + f"<div class=gallery>{''.join(figures) or '<p class=muted>None.</p>'}</div>"
    )


def _bin(value: float, edges: list[float]) -> int:
    for index in range(len(edges) - 1):
        if value < edges[index + 1]:
            return index
    return len(edges) - 2


def _colour(value: float) -> str:
    """Red (0) through yellow to green (1)."""
    value = min(max(value, 0.0), 1.0)
    red = 230 if value < 0.5 else int(230 - (value - 0.5) * 2 * 150)
    green = int(80 + value * 2 * 120) if value < 0.5 else 200
    return f"rgb({red},{green},90)"
