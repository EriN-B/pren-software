// @ts-check
/**
 * @file The control rail and readouts: buttons that send commands, live values, the
 * connection and core state in the top bar, and the boxes over the dog's camera.
 */

/** @typedef {import("./protocol.js").FrameMessage} FrameMessage */
/** @typedef {import("./protocol.js").ClientMessage} ClientMessage */
/** @typedef {import("./protocol.js").Light} Light */

/** Keys for driving by hand: forward speed in m/s and steering angle in degrees. */
const DRIVE_KEYS = {
  KeyW: { speed: 0.15 }, ArrowUp: { speed: 0.15 },
  KeyS: { speed: -0.1 }, ArrowDown: { speed: -0.1 },
  KeyA: { angle: -25 }, ArrowLeft: { angle: -25 }, // negative = counter-clockwise
  KeyD: { angle: 25 }, ArrowRight: { angle: 25 },
};
/** @type {Record<string, Light>} The light buttons; "default" is the scene file's light. */
const LIGHT_PRESETS = {
  default: { brightness: 0.7, elevation: 90, azimuth: 0, ambient: 0.5 },
  dim: { brightness: 0.25, elevation: 70, azimuth: 0, ambient: 0.25 },
  low: { brightness: 0.8, elevation: 12, azimuth: 180, ambient: 0.3 },
};
const DRIVE_INTERVAL_MS = 100; // the Pico drops drive commands older than 0.5 s

/**
 * @param {string} id
 * @returns {HTMLElement}
 */
const byId = (id) => /** @type {HTMLElement} */ (document.getElementById(id));

export class Panel {
  /**
   * @param {(message: ClientMessage) => void} send Sends a message to the sim host.
   * @param {(object: "bone"|"person") => void} startPlacing Arms a floor click to place something.
   */
  constructor(send, startPlacing) {
    this.send = send;
    this.estopActive = false;
    /** @type {Set<string>} Driving keys held down right now. */
    this.keys = new Set();
    /** @type {Map<string, HTMLTableRowElement>} */
    this.jointRows = new Map();
    this.overlay = /** @type {HTMLCanvasElement} */ (byId("eye-overlay")).getContext("2d");
    this.wireButtons(startPlacing);
    this.wireKeyboard();
  }

  /** @param {(object: "bone"|"person") => void} startPlacing */
  wireButtons(startPlacing) {
    /**
     * Run `handler` for every button with `attribute` inside `container`.
     * @param {string} selector
     * @param {string} attribute
     * @param {(value: string, button: HTMLElement) => void} handler
     */
    const onClick = (selector, attribute, handler) => {
      document.querySelectorAll(`${selector} [${attribute}]`).forEach((element) => {
        const button = /** @type {HTMLElement} */ (element);
        button.addEventListener("click", () =>
          handler(button.getAttribute(attribute) ?? "", button),
        );
      });
    };
    onClick("#pico, #posture", "data-command", (command) =>
      this.send({ type: "pico", message: { command } }),
    );
    onClick("#voice", "data-word", (word) =>
      this.send({ type: "voice", word: /** @type {"hier"|"sitz"|"platz"|"auf"|"such"|"brav"} */ (word) }),
    );
    onClick("#pico", "data-rotate", (degrees) =>
      this.send({ type: "pico", message: { command: "rotate", degrees: Number(degrees) } }),
    );
    onClick(".rail", "data-place", (object) =>
      startPlacing(/** @type {"bone"|"person"} */ (object)),
    );
    byId("reset").addEventListener("click", () => this.send({ type: "reset" }));
    byId("random-bone").addEventListener("click", () => this.send({ type: "random_bone" }));
    const sliders = /** @type {HTMLInputElement[]} */ ([...byId("light").querySelectorAll("input")]);
    const sendLight = (/** @type {Light} */ light) => this.send({ type: "light", ...light });
    byId("light").addEventListener("input", () =>
      sendLight(/** @type {Light} */ (Object.fromEntries(sliders.map((s) => [s.name, Number(s.value)])))),
    );
    onClick("#light-presets", "data-light", (name) => sendLight(LIGHT_PRESETS[name]));
    byId("light-random").addEventListener("click", () => this.send({ type: "random_light" }));
    byId("estop").addEventListener("click", () => {
      this.send({ type: "emergency_stop", active: !this.estopActive });
    });
  }

  /** Hold W/A/S/D or the arrows to drive; letting go stops the dog. */
  wireKeyboard() {
    window.addEventListener("keydown", (event) => {
      if (event.code in DRIVE_KEYS && !(event.target instanceof HTMLInputElement)) {
        event.preventDefault();
        this.keys.add(event.code);
      }
    });
    window.addEventListener("keyup", (event) => {
      if (!this.keys.delete(event.code) || this.keys.size) return;
      this.send({ type: "pico", message: { command: "stop" } });
    });
    window.addEventListener("blur", () => this.keys.clear());
    setInterval(() => {
      if (!this.keys.size) return;
      let speed = 0;
      let angle = 0;
      for (const code of this.keys) {
        const key = DRIVE_KEYS[/** @type {keyof typeof DRIVE_KEYS} */ (code)];
        speed += "speed" in key ? key.speed : 0;
        angle += "angle" in key ? key.angle : 0;
      }
      // Steering needs some speed, so turning alone creeps forward.
      if (speed === 0 && angle !== 0) speed = 0.05;
      this.send({ type: "pico", message: { command: "drive", speed, angle } });
    }, DRIVE_INTERVAL_MS);
  }

  /** @param {boolean} connected */
  showConnection(connected) {
    const state = byId("connection");
    state.textContent = connected ? "Sim host connected" : "Sim host offline, retrying";
    state.className = `state ${connected ? "state-on" : "state-off"}`;
  }

  /**
   * Refresh every readout from a frame.
   * @param {FrameMessage} frame
   */
  update(frame) {
    byId("sim-time").textContent = `${frame.time.toFixed(1)} s`;
    const core = byId("core-state");
    core.textContent = frame.core.error
      ? "Core failed to start"
      : frame.core.attached
        ? `Core: ${(frame.core.state ?? "starting").replaceAll("_", " ")}`
        : "Core not attached";
    core.title = frame.core.error ?? "";
    core.className = `state ${frame.core.error ? "state-off" : frame.core.state ? "state-live" : ""}`;

    const pico = frame.pico;
    this.estopActive = pico.emergency_stop;
    byId("estop").classList.toggle("engaged", pico.emergency_stop);
    /** @type {HTMLElement} */ (document.querySelector(".topbar")).classList.toggle("alarm", pico.emergency_stop);
    byId("estop").textContent = pico.emergency_stop ? "Release Not-Aus" : "Not-Aus";
    for (const button of document.querySelectorAll("#posture button")) {
      button.classList.toggle("active", /** @type {HTMLElement} */ (button).dataset.command === pico.posture);
    }
    byId("speed").textContent = `${pico.speed.toFixed(2)} m/s`;
    byId("turn").textContent =
      pico.turning_to === null ? `${pico.turn_rate_deg.toFixed(0)} °/s` : `→ ${pico.turning_to.toFixed(0)}°`;

    for (const slider of /** @type {NodeListOf<HTMLInputElement>} */ (document.querySelectorAll("#light input"))) {
      // Not while it is dragged: the frame still has the light from before.
      if (slider !== document.activeElement) slider.value = String(frame.light[/** @type {keyof Light} */ (slider.name)]);
    }

    this.updateJoints(frame);
    this.updateSensors(frame);
    this.drawDetections(frame.detections, frame.core_detections ?? []);
  }

  /**
   * One row per motor: angle, and torque as a bar against the motor's limit.
   * @param {FrameMessage} frame
   */
  updateJoints(frame) {
    const body = byId("joints");
    for (const joint of frame.joints) {
      let row = this.jointRows.get(joint.name);
      if (!row) {
        row = document.createElement("tr");
        row.innerHTML = `<td>${joint.name.replaceAll("_", " ")}</td><td class="num"></td>
          <td><div class="bar"><span></span></div><span class="num torque"></span></td>`;
        body.append(row);
        this.jointRows.set(joint.name, row);
      }
      const isWheel = joint.name.startsWith("wheel");
      const angle = isWheel
        ? `${joint.velocity.toFixed(1)} rad/s`
        : `${((joint.angle * 180) / Math.PI).toFixed(1)}°`;
      const load = Math.min(1, Math.abs(joint.torque) / joint.limit);
      const cells = row.querySelectorAll("td");
      cells[1].textContent = angle;
      const bar = /** @type {HTMLElement} */ (row.querySelector(".bar span"));
      bar.style.width = `${(load * 100).toFixed(0)}%`;
      bar.dataset.level = load > 0.9 ? "max" : load > 0.6 ? "high" : "ok";
      /** @type {HTMLElement} */ (row.querySelector(".torque")).textContent =
        `${joint.torque.toFixed(2)} / ${joint.limit} Nm`;
    }
  }

  /** @param {FrameMessage} frame */
  updateSensors({ sensors, springs }) {
    const pull = (/** @type {string} */ end) =>
      springs.filter((s) => s.name.includes(end)).map((s) => s.force.toFixed(1)).join(" / ");
    const rows = [
      ["Encoder left", `${sensors.left_distance_m.toFixed(3)} m`],
      ["Encoder right", `${sensors.right_distance_m.toFixed(3)} m`],
      ["IMU heading", `${sensors.heading_deg.toFixed(1)}° cw`],
      ["Ultrasonic", sensors.sonar_m < 0 ? "nothing" : `${sensors.sonar_m.toFixed(2)} m`],
      ["IMU accel z", `${sensors.accel_z.toFixed(2)} m/s²`],
      ["True position", `${sensors.x.toFixed(2)}, ${sensors.y.toFixed(2)} m`],
      ["Springs front", `${pull("front")} N`],
      ["Springs rear", `${pull("rear")} N`],
    ];
    byId("sensors").innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
  }

  /**
   * Draw the boxes over the dog's camera view (its images are 640 x 480).
   * @param {Record<string, number[]>} detections True positions, drawn dashed.
   * @param {import("./protocol.js").CoreDetection[]} coreDetections What the core's detector found, drawn solid.
   */
  drawDetections(detections, coreDetections) {
    const context = this.overlay;
    if (!context) return;
    const { width, height } = context.canvas;
    const scale = width / 640;
    const pixel = width / (context.canvas.clientWidth || 1); // device pixels per CSS pixel
    context.clearRect(0, 0, width, height);
    context.font = `600 ${11 * pixel}px system-ui, sans-serif`;
    /** @type {number[][]} Label rectangles already drawn, so labels never overlap. */
    const placed = [];

    /**
     * A box with its label as a solid chip: above the box, inside it when the top edge
     * would clip, and moved down until it overlaps no other label.
     * @param {number[]} box
     * @param {string} text
     * @param {string} chip Chip colour.
     * @param {boolean} dashed
     */
    const draw = ([x1, y1, x2, y2], text, chip, dashed) => {
      const [bx, by, bw, bh] = [x1 * scale, y1 * scale, (x2 - x1) * scale, (y2 - y1) * scale];
      context.setLineDash(dashed ? [5 * pixel, 4 * pixel] : []);
      context.lineWidth = (dashed ? 1 : 2) * pixel;
      context.strokeStyle = dashed ? "rgb(255 255 255 / 0.85)" : chip;
      context.strokeRect(bx, by, bw, bh);
      const w = context.measureText(text).width + 10 * pixel;
      const h = 17 * pixel;
      let x = Math.min(Math.max(0, bx), width - w);
      let y = by - h >= 0 ? by - h : by + 2 * pixel;
      while (placed.some(([px, py, pw, ph]) => x < px + pw && px < x + w && y < py + ph && py < y + h)) {
        y += h + 2 * pixel;
      }
      placed.push([x, y, w, h]);
      context.setLineDash([]);
      context.fillStyle = chip;
      context.fillRect(x, y, w, h);
      context.fillStyle = "#ffffff";
      context.fillText(text, x + 5 * pixel, y + 12.5 * pixel);
    };

    for (const [label, position] of Object.entries(detections)) {
      draw(position, label.replace("_", " "), "rgb(17 17 17 / 0.82)", true); // real position
    }
    for (const found of coreDetections) {
      draw(found.box, `${found.label} ${found.confidence.toFixed(2)}`, "#1e9e4a", false); // a hit
    }
  }

}
