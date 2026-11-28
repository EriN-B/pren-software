"""A small web page to try the core's bone detector on images you upload.

Runs the same YOLO model, call and threshold as the core's search (``ObjectModel``) and
shows every candidate with its confidence, also the ones below the core's 0.30 cut-off.

    .venv-core/bin/python apps/sim-host/scripts/bone_tester.py   # then open http://localhost:8765
"""

import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

import cv2  # in the core environment
import numpy as np
from dog_perception.object_model import ObjectModel

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
CORE_THRESHOLD = 0.30  # the cut-off in ObjectModel.get_objects
SHOW_FROM = 0.05  # weaker candidates are noise
MAX_UPLOAD = 25_000_000

model = ObjectModel()


def to_camera(image: np.ndarray) -> np.ndarray:
    """Crop to the camera's 4:3 and scale to its 640 x 480, as detect_photos.py does."""
    height, width = image.shape[:2]
    keep_w, keep_h = min(width, height * 4 // 3), min(height, width * 3 // 4)
    top, left = (height - keep_h) // 2, (width - keep_w) // 2
    return cv2.resize(image[top : top + keep_h, left : left + keep_w], (640, 480))


def detect(data: bytes) -> dict:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("not an image OpenCV can read (try JPEG or PNG)")
    image = to_camera(image)
    # The core's own predict call, but without its 0.30 filter so weak candidates show too.
    result = model.object_model.predict(
        source=image,
        conf=SHOW_FROM,
        classes=model.bone_classes,
        imgsz=(384, 512),
        rect=False,
        device="cpu",
        max_det=300,
        verbose=False,
    )[0]
    found = []
    for (x1, y1, x2, y2), conf, cls in zip(
        result.boxes.xyxy.tolist(),
        result.boxes.conf.tolist(),
        result.boxes.cls.tolist(),
        strict=True,
    ):
        counts = conf >= CORE_THRESHOLD
        colour = (67, 159, 255) if counts else (150, 150, 150)
        cv2.rectangle(image, (int(x1), int(y1)), (int(x2), int(y2)), colour, 2)
        cv2.putText(
            image,
            f"{conf:.2f}",
            (int(x1), max(12, int(y1) - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            colour,
            1,
        )
        found.append(
            {"label": result.names[int(cls)], "confidence": conf, "counts": counts}
        )
    found.sort(key=lambda d: -d["confidence"])
    jpeg = cv2.imencode(".jpg", image)[1].tobytes()
    return {
        "image": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode(),
        "detections": found,
        "threshold": CORE_THRESHOLD,
    }


PAGE = """<!doctype html><html lang="en"><meta charset="utf-8">
<title>Bone detector test</title>
<style>
 :root{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--grid:#e4e3df;--bone:#2a78d6;--nobone:#eb6834}
 body{font:15px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:var(--ink);background:#f9f9f7}
 #drop{display:block;border:2px dashed #aaa;border-radius:8px;padding:2rem;text-align:center;cursor:pointer;background:var(--surface)}
 #drop.over{border-color:var(--bone);background:#eef4fc}
 .bar{display:flex;gap:1.5rem;align-items:center;flex-wrap:wrap;margin:1rem 0}
 .card{background:var(--surface);border:1px solid var(--grid);border-radius:8px;padding:1rem;margin-top:1rem}
 .tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.75rem}
 .tile b{display:block;font-size:1.8rem;font-variant-numeric:tabular-nums}
 .tile span{color:var(--ink2);font-size:.85rem}
 h2{font-size:1rem;margin:0 0 .25rem}.sub{color:var(--ink2);font-size:.85rem;margin:0 0 .5rem}
 .legend{display:flex;gap:1rem;font-size:.85rem;color:var(--ink2)}
 .key{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;vertical-align:middle}
 svg{width:100%;height:auto;overflow:visible}svg text{font:12px system-ui;fill:var(--ink2)}
 #tip{position:fixed;pointer-events:none;background:#0b0b0b;color:#fff;font-size:12px;padding:4px 8px;border-radius:4px;display:none;white-space:nowrap}
 .cm td,.cm th{padding:4px 12px;text-align:center;border:1px solid var(--grid)}.cm{border-collapse:collapse;font-variant-numeric:tabular-nums}
 .row{display:flex;gap:1rem;align-items:flex-start;margin-top:1rem;border-top:1px solid #ddd;padding-top:1rem}
 .row img{width:400px;max-width:50vw;border-radius:4px}
 .yes{color:#0a7d32;font-weight:600}.no{color:#b3261e;font-weight:600}
 td{padding:2px 10px 2px 0}.weak{color:#888}
</style>
<h1>Bone detector test</h1>
<p>Same model, call and 0.30 threshold as the core's search. Images are cropped to 4:3 and
scaled to 640&times;480 like the camera. Orange boxes count for the core, grey ones are below 0.30.</p>
<div class="bar">
 <span>Next uploads <b>contain a bone</b>?</span>
 <label><input type="radio" name="truth" value="1" checked> yes</label>
 <label><input type="radio" name="truth" value="0"> no (to test false alarms)</label>
</div>
<label id="drop">Drop images here or click to choose
 <input id="file" type="file" accept="image/*" multiple hidden></label>

<div class="card">
 <div class="bar" style="margin-top:0">
  <label>Threshold <input id="thr" type="range" min="0.05" max="0.95" step="0.01" value="0.30">
   <b id="thrv">0.30</b></label>
  <button id="core">back to core's 0.30</button>
  <button id="clear">clear results</button>
 </div>
 <div class="tiles">
  <div class="tile"><b id="t-n">0</b><span>images labelled (<span id="t-split">0 bone · 0 no bone</span>)</span></div>
  <div class="tile"><b id="t-rec">–</b><span>bones found (recall)</span></div>
  <div class="tile"><b id="t-fa">–</b><span>false alarms on no-bone images</span></div>
  <div class="tile"><b id="t-acc">–</b><span>correct overall (accuracy)</span></div>
  <div class="tile"><b id="t-med">–</b><span>median confidence on bone images</span></div>
 </div>
</div>

<div class="card">
 <h2>Best confidence per image</h2>
 <p class="sub">Each dot is one image, at the highest bone confidence the model gave it (left edge: nothing above 5 %).
 Dots right of the dashed line count as "bone found". Good: blue dots far right, orange dots far left.</p>
 <svg id="strip" viewBox="0 0 700 150" role="img" aria-label="Best confidence per image, by label"></svg>
</div>

<div class="card">
 <h2>Effect of the threshold</h2>
 <p class="sub">Share of bone images found and of no-bone images falsely flagged, for every threshold. Hover to read values.</p>
 <div class="legend"><span><i class="key" style="background:var(--bone)"></i>bones found</span>
  <span><i class="key" style="background:var(--nobone)"></i>false alarms</span></div>
 <svg id="curve" viewBox="0 0 700 260" role="img" aria-label="Recall and false alarm rate by threshold"></svg>
</div>

<div class="card">
 <h2>Confusion matrix at the threshold</h2>
 <table class="cm"><tr><th></th><th>model: bone</th><th>model: no bone</th></tr>
  <tr><th>image has bone</th><td id="c-tp">0</td><td id="c-fn">0</td></tr>
  <tr><th>image has no bone</th><td id="c-fp">0</td><td id="c-tn">0</td></tr></table>
</div>

<div id="out"></div>
<div id="tip"></div>
<script>
const $ = id => document.getElementById(id);
const drop = $('drop'), out = $('out'), tip = $('tip'), thr = $('thr');
const results = [];  // {name, best, truth}
const pct = v => (v * 100).toFixed(0) + ' %';
$('file').onchange = e => send(e.target.files);
drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
drop.ondragleave = () => drop.classList.remove('over');
drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); send(e.dataTransfer.files); };
thr.oninput = render;
$('core').onclick = () => { thr.value = 0.30; render(); };
$('clear').onclick = () => { results.length = 0; out.innerHTML = ''; render(); };

async function send(files) {
  const truth = document.querySelector('input[name=truth]:checked').value === '1';
  for (const file of files) {
    const row = document.createElement('div'); row.className = 'row';
    row.textContent = file.name + ': detecting…'; out.prepend(row);
    try {
      const r = await fetch('/detect', {method: 'POST', body: file});
      const d = await r.json();
      if (!r.ok) throw new Error(d.error);
      const best = d.detections.find(x => x.counts);
      const entry = {name: file.name, best: d.detections.length ? d.detections[0].confidence : 0, truth};
      results.push(entry);
      row.innerHTML = '<img alt=""><div><h3></h3><p></p><label><input type="checkbox"> image contains a bone</label><table></table></div>';
      row.querySelector('img').src = d.image;
      row.querySelector('h3').textContent = file.name;
      const box = row.querySelector('input'); box.checked = truth;
      box.onchange = () => { entry.truth = box.checked; render(); };
      const p = row.querySelector('p');
      p.className = best ? 'yes' : 'no';
      p.textContent = best ? `Bone found (${(best.confidence*100).toFixed(1)} %, core threshold)` : 'No bone found (core threshold)';
      row.querySelector('table').innerHTML = d.detections.length
        ? d.detections.map(x => `<tr class="${x.counts?'':'weak'}"><td>${x.label}</td><td>${(x.confidence*100).toFixed(1)} %</td></tr>`).join('')
        : '<tr class="weak"><td>no candidates above 5 %</td></tr>';
      render();
    } catch (err) { row.textContent = file.name + ': ' + err.message; }
  }
}

function rates(t) {
  const pos = results.filter(r => r.truth), neg = results.filter(r => !r.truth);
  const tp = pos.filter(r => r.best >= t).length, fp = neg.filter(r => r.best >= t).length;
  return {pos: pos.length, neg: neg.length, tp, fn: pos.length - tp, fp, tn: neg.length - fp,
          rec: pos.length ? tp / pos.length : null, fa: neg.length ? fp / neg.length : null};
}

// Shared plot geometry: x is confidence 0..1.
const L = 110, R = 680, X = v => L + v * (R - L);
const ns = 'http://www.w3.org/2000/svg';
function el(svg, tag, attrs, text) {
  const e = document.createElementNS(ns, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (text != null) e.textContent = text;
  svg.appendChild(e); return e;
}
function xAxis(svg, y) {
  for (const v of [0, .25, .5, .75, 1]) {
    el(svg, 'line', {x1: X(v), x2: X(v), y1: 10, y2: y, stroke: 'var(--grid)'});
    el(svg, 'text', {x: X(v), y: y + 16, 'text-anchor': 'middle'}, pct(v));
  }
}
function showTip(e, text) { tip.textContent = text; tip.style.display = 'block'; tip.style.left = Math.min(e.clientX + 12, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = e.clientY + 12 + 'px'; }
const hideTip = () => tip.style.display = 'none';

function render() {
  const t = +thr.value; $('thrv').textContent = t.toFixed(2);
  const s = rates(t);
  $('t-n').textContent = results.length;
  $('t-split').textContent = `${s.pos} bone · ${s.neg} no bone`;
  $('t-rec').textContent = s.rec == null ? '–' : `${pct(s.rec)} (${s.tp}/${s.pos})`;
  $('t-fa').textContent = s.fa == null ? '–' : `${pct(s.fa)} (${s.fp}/${s.neg})`;
  $('t-acc').textContent = results.length ? pct((s.tp + s.tn) / results.length) : '–';
  const confs = results.filter(r => r.truth).map(r => r.best).sort((a, b) => a - b);
  $('t-med').textContent = confs.length ? pct(confs[Math.floor((confs.length - 1) / 2)]) : '–';
  for (const k of ['tp', 'fn', 'fp', 'tn']) $('c-' + k).textContent = s[k];

  // Strip plot: one row per label.
  const strip = $('strip'); strip.innerHTML = '';
  xAxis(strip, 120);
  [[true, 40, 'has bone', 'var(--bone)'], [false, 90, 'no bone', 'var(--nobone)']].forEach(([truth, y, label, c]) => {
    el(strip, 'text', {x: 0, y: y + 4, fill: 'var(--ink)'}, label);
    results.filter(r => r.truth === truth).forEach((r, i) => {
      // small vertical jitter so equal confidences stay visible
      const dot = el(strip, 'circle', {cx: X(r.best), cy: y + ((i % 5) - 2) * 6, r: 6, fill: c, stroke: 'var(--surface)', 'stroke-width': 2});
      dot.onmousemove = e => showTip(e, `${r.name}: ${(r.best * 100).toFixed(1)} %`);
      dot.onmouseleave = hideTip;
    });
  });
  el(strip, 'line', {x1: X(t), x2: X(t), y1: 10, y2: 120, stroke: 'var(--ink)', 'stroke-dasharray': '4 3'});

  // Curves: recall and false-alarm rate over thresholds.
  const curve = $('curve'), H = 220, Y = v => 10 + (1 - v) * (H - 10);
  curve.innerHTML = '';
  for (const v of [0, .5, 1]) {
    el(curve, 'line', {x1: L, x2: R, y1: Y(v), y2: Y(v), stroke: 'var(--grid)'});
    el(curve, 'text', {x: L - 8, y: Y(v) + 4, 'text-anchor': 'end'}, pct(v));
  }
  for (const v of [0, .25, .5, .75, 1]) el(curve, 'text', {x: X(v), y: H + 18, 'text-anchor': 'middle'}, pct(v));
  el(curve, 'text', {x: (L + R) / 2, y: H + 36, 'text-anchor': 'middle'}, 'threshold');
  const steps = Array.from({length: 96}, (_, i) => 0.05 + i * 0.01);
  [['rec', 'var(--bone)'], ['fa', 'var(--nobone)']].forEach(([k, c]) => {
    const pts = steps.map(st => [st, rates(st)[k]]).filter(p => p[1] != null);
    if (!pts.length) return;
    el(curve, 'polyline', {points: pts.map(([a, b]) => `${X(a)},${Y(b)}`).join(' '), fill: 'none', stroke: c, 'stroke-width': 2});
    el(curve, 'circle', {cx: X(t), cy: Y(rates(t)[k]), r: 5, fill: c, stroke: 'var(--surface)', 'stroke-width': 2});
  });
  el(curve, 'line', {x1: X(t), x2: X(t), y1: 10, y2: H, stroke: 'var(--ink)', 'stroke-dasharray': '4 3'});
  const hair = el(curve, 'line', {y1: 10, y2: H, stroke: 'var(--ink2)', visibility: 'hidden'});
  const hit = el(curve, 'rect', {x: L, y: 0, width: R - L, height: H, fill: 'transparent'});
  hit.onmousemove = e => {
    const box = curve.getBoundingClientRect(), vx = (e.clientX - box.left) * 700 / box.width;
    const v = Math.min(1, Math.max(0.05, (vx - L) / (R - L))), r = rates(v);
    hair.setAttribute('x1', X(v)); hair.setAttribute('x2', X(v)); hair.setAttribute('visibility', 'visible');
    showTip(e, `threshold ${v.toFixed(2)}: bones found ${r.rec == null ? '–' : pct(r.rec)}, false alarms ${r.fa == null ? '–' : pct(r.fa)}`);
  };
  hit.onmouseleave = () => { hair.setAttribute('visibility', 'hidden'); hideTip(); };
}
render();
</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def reply(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self.reply(200, PAGE.encode(), "text/html; charset=utf-8")

    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", 0))
        if self.path != "/detect" or not 0 < size <= MAX_UPLOAD:
            self.reply(
                400, b'{"error":"send one image up to 25 MB"}', "application/json"
            )
            return
        try:
            body, status = detect(self.rfile.read(size)), 200
        except ValueError as err:
            body, status = {"error": str(err)}, 400
        self.reply(status, json.dumps(body).encode(), "application/json")


if __name__ == "__main__":
    # shortcut: bound to localhost only; use 0.0.0.0 if teammates should reach it on the LAN.
    print(f"Bone detector test on http://localhost:{PORT}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
