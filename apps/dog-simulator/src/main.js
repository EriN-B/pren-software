// @ts-check
/**
 * @file Starts the viewer: connects to the sim host and wires the 3D view to the panel.
 *
 * The sim host address defaults to `ws://localhost:8780`; override it with `?ws=...`.
 */
import { SimConnection } from "./connection.js";
import { Panel } from "./panel.js";
import { SimScene } from "./scene.js";

const url = new URLSearchParams(location.search).get("ws") ?? "ws://localhost:8780";
const scene = new SimScene(
  /** @type {HTMLCanvasElement} */ (document.getElementById("view")),
  /** @type {HTMLElement} */ (document.querySelector(".eye")),
);
const placeHint = /** @type {HTMLElement} */ (document.getElementById("place-hint"));

/** @type {"bone"|"person"|null} What the next floor click places, if anything. */
let placing = null;
/** Index of the dog's torso geom in the scene, for the trail and follow camera. */
let torsoIndex = -1;

const connection = new SimConnection(url, {
  onScene: (message) => {
    scene.build(message);
    torsoIndex = message.geoms.findIndex((geom) => geom.name === "torso");
  },
  onFrame: (frame) => {
    scene.update(frame, torsoIndex);
    panel.update(frame);
  },
  onStatus: (connected) => panel.showConnection(connected),
});

const panel = new Panel(
  (message) => {
    if (message.type === "reset") scene.clearTrail();
    connection.send(message);
  },
  (object) => {
    placing = object;
    placeHint.hidden = false;
    /** @type {HTMLElement} */ (placeHint.querySelector("b")).textContent = object;
  },
);

function stopPlacing() {
  placing = null;
  placeHint.hidden = true;
}

scene.canvas.addEventListener("click", (event) => {
  if (!placing) return;
  const point = scene.floorPoint(event.clientX, event.clientY);
  if (point) connection.send({ type: "place", object: placing, x: point.x, y: point.y });
  stopPlacing();
});
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") stopPlacing();
});
/** @type {HTMLInputElement} */ (document.getElementById("follow")).addEventListener(
  "change",
  (event) => {
    scene.follow = /** @type {HTMLInputElement} */ (event.target).checked;
  },
);

renderLoop();

/** Draw every animation frame; poses only change when a frame message arrives. */
function renderLoop() {
  scene.render();
  requestAnimationFrame(renderLoop);
}
