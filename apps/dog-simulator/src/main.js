// @ts-check
/**
 * @file Starts the viewer: connects to the sim host and wires the views, the run clock,
 * the control rail and the log dock together.
 *
 * The sim host address defaults to `ws://localhost:8780`; override it with `?ws=...`.
 */
import "@fontsource/barlow-semi-condensed/300.css";
import "@fontsource/barlow-semi-condensed/400.css";
import { IMAGE_DOG_CAMERA, IMAGE_WEBCAM, SimConnection } from "./connection.js";
import { LogDock } from "./logs.js";
import { Panel } from "./panel.js";
import { RunClock } from "./run.js";
import { SimScene } from "./scene.js";

const CAMERA_W = 640; // the dog's camera, as the core gets it
const CAMERA_H = 480;
const IMAGE_TIMEOUT_MS = 1000; // no image for this long: fall back to the empty state

/**
 * @param {string} id
 * @returns {HTMLElement}
 */
const byId = (id) => /** @type {HTMLElement} */ (document.getElementById(id));

const url = new URLSearchParams(location.search).get("ws") ?? "ws://localhost:8780";
const eyeCanvas = /** @type {HTMLCanvasElement} */ (byId("eye"));
const overlay = /** @type {HTMLCanvasElement} */ (byId("eye-overlay"));
const scene = new SimScene(/** @type {HTMLCanvasElement} */ (byId("view")), eyeCanvas);
const logs = new LogDock();
const MARKERS = { start: "Run started", search: "Search started (SUCH)", found: "Bone found", return: "Returning", end: "Run complete" };
const run = new RunClock((event) => {
  const text = MARKERS[/** @type {keyof typeof MARKERS} */ (event)];
  if (text) logs.mark(text);
});

/**
 * An image fed by binary messages, hidden again when they stop. Created here, not in
 * the HTML, because it has no picture until the first one arrives.
 * @param {HTMLElement} parent
 * @param {string} alt
 * @param {(showing: boolean) => void} onChange
 */
function liveImage(parent, alt, onChange) {
  const image = document.createElement("img");
  image.alt = alt;
  image.hidden = true;
  parent.prepend(image);
  /** @type {ReturnType<typeof setTimeout> | undefined} */
  let timeout;
  return {
    /** @param {Blob} jpeg */
    show(jpeg) {
      URL.revokeObjectURL(image.src);
      image.src = URL.createObjectURL(jpeg);
      if (image.hidden) onChange(true);
      image.hidden = false;
      clearTimeout(timeout);
      timeout = setTimeout(() => {
        image.hidden = true;
        onChange(false);
      }, IMAGE_TIMEOUT_MS);
    },
  };
}

// The core's real camera image replaces the viewer's own rendering while it arrives.
const cameraImage = liveImage(
  byId("camera-stage"),
  "The dog's camera image as the core receives it",
  (showing) => {
    eyeCanvas.hidden = showing;
    byId("camera-source").textContent = showing
      ? "As the core receives it, 640 × 480"
      : "Viewer's own rendering (core not attached)";
  },
);
const webcamImage = liveImage(
  /** @type {HTMLElement} */ (document.querySelector(".webcam")),
  "Your webcam as the core's gesture model sees it",
  (showing) => (byId("webcam-empty").hidden = showing),
);

/** Fit the camera view into its panel at 4:3, as large as it goes. */
function fitCamera() {
  const body = /** @type {HTMLElement} */ (byId("camera-stage").parentElement);
  const scale = Math.min(body.clientWidth / CAMERA_W, body.clientHeight / CAMERA_H);
  const width = Math.floor(CAMERA_W * scale);
  const height = Math.floor(CAMERA_H * scale);
  const stage = byId("camera-stage");
  stage.style.width = `${width}px`;
  stage.style.height = `${height}px`;
  const ratio = Math.min(window.devicePixelRatio, 2);
  overlay.width = Math.round(width * ratio);
  overlay.height = Math.round(height * ratio);
  scene.resizeEye(width, height);
}
new ResizeObserver(fitCamera).observe(/** @type {HTMLElement} */ (byId("camera-stage").parentElement));

/** @type {"bone"|"person"|null} What the next floor click places, if anything. */
let placing = null;
/** Turn of the bone to place, degrees counter-clockwise; R adds 45. */
let placeYaw = 0;
/** Index of the dog's torso geom in the scene, for the trail and follow camera. */
let torsoIndex = -1;
let lastTime = 0;

const connection = new SimConnection(url, {
  onScene: (message) => {
    scene.build(message);
    torsoIndex = message.geoms.findIndex((geom) => geom.name === "torso");
  },
  onFrame: (frame) => {
    if (frame.time < lastTime - 1) logs.restart(); // the sim host restarted
    lastTime = frame.time;
    scene.update(frame, torsoIndex);
    panel.update(frame);
    run.update(frame);
  },
  onImage: (channel, jpeg) => {
    if (channel === IMAGE_DOG_CAMERA) cameraImage.show(jpeg);
    else if (channel === IMAGE_WEBCAM) webcamImage.show(jpeg);
  },
  onLogs: (entries) => logs.add(entries),
  onStatus: (connected) => panel.showConnection(connected),
});

const panel = new Panel(
  (message) => {
    if (message.type === "reset") {
      scene.clearTrail();
      run.reset();
    }
    connection.send(message);
  },
  (object) => {
    placing = object;
    byId("place-hint").hidden = false;
    byId("place-turn").hidden = object !== "bone";
    /** @type {HTMLElement} */ (byId("place-hint").querySelector("b")).textContent = object;
  },
);

function stopPlacing() {
  placing = null;
  byId("place-hint").hidden = true;
}

scene.canvas.addEventListener("click", (event) => {
  if (!placing) return;
  const point = scene.floorPoint(event.clientX, event.clientY);
  if (point) {
    connection.send({ type: "place", object: placing, x: point.x, y: point.y, yaw: placeYaw });
  }
  stopPlacing();
});
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") stopPlacing();
  if (placing === "bone" && event.key.toLowerCase() === "r") {
    placeYaw = (placeYaw + 45) % 360;
    byId("place-yaw").textContent = String(placeYaw);
  }
});
/** @type {HTMLInputElement} */ (byId("follow")).addEventListener("change", (event) => {
  scene.follow = /** @type {HTMLInputElement} */ (event.target).checked;
});

renderLoop();

/** Draw every animation frame; poses only change when a frame message arrives. */
function renderLoop() {
  scene.render();
  requestAnimationFrame(renderLoop);
}
