// @ts-check
/**
 * @file The side panel and overlays: buttons that send commands, and live readouts.
 */

/** @typedef {import("./protocol.js").FrameMessage} FrameMessage */
/** @typedef {import("./protocol.js").ClientMessage} ClientMessage */

/** Keys for driving by hand: forward speed in m/s and steering angle in degrees. */
const DRIVE_KEYS = {
  KeyW: { speed: 0.15 }, ArrowUp: { speed: 0.15 },
  KeyS: { speed: -0.1 }, ArrowDown: { speed: -0.1 },
  KeyA: { angle: -25 }, ArrowLeft: { angle: -25 }, // negative = counter-clockwise
  KeyD: { angle: 25 }, ArrowRight: { angle: 25 },
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
    onClick("#voice", "data-word", (word) => this.send({ type: "voice", word }));
    onClick("#gesture", "data-gesture", (gesture, button) => {
      document.querySelectorAll("#gesture button").forEach((b) => b.classList.remove("active"));
      button.classList.add("active");
      const value = /** @type {"auf"|"sitz"|"platz"|""} */ (gesture);
      this.send({ type: "gesture", gesture: value || null });
    });
    onClick("#pico", "data-command", (command) =>
      this.send({ type: "pico", message: { command } }),
    );
    onClick("#pico", "data-rotate", (degrees) =>
      this.send({ type: "pico", message: { command: "rotate", degrees: Number(degrees) } }),
    );
    onClick(".panel", "data-place", (object) =>
      startPlacing(/** @type {"bone"|"person"} */ (object)),
    );
    byId("reset").addEventListener("click", () => this.send({ type: "reset" }));
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
    const pill = byId("connection");
    pill.textContent = connected ? "sim host connected" : "sim host offline";
    pill.className = `pill ${connected ? "pill-on" : "pill-off"}`;
  }

  /**
   * Refresh every readout from a frame.
   * @param {FrameMessage} frame
   */
  update(frame) {
    byId("sim-time").textContent = `${frame.time.toFixed(1)} s`;
    const core = byId("core-state");
    core.textContent = frame.core.error
      ? "core failed"
      : frame.core.attached
        ? `core: ${frame.core.state ?? "starting"}`
        : "core not attached";
    core.title = frame.core.error ?? "";
    core.className = `pill ${frame.core.error ? "pill-off" : frame.core.state ? "pill-on" : ""}`;
    byId("core-hint").hidden = frame.core.attached;

    const pico = frame.pico;
    this.estopActive = pico.emergency_stop;
    byId("estop").classList.toggle("engaged", pico.emergency_stop);
    byId("estop").textContent = pico.emergency_stop ? "Not-Aus engaged · release" : "Not-Aus";
    byId("posture").textContent = pico.posture;
    byId("speed").textContent = `${pico.speed.toFixed(2)} m/s`;
    byId("turn").textContent =
      pico.turning_to === null ? `${pico.turn_rate_deg.toFixed(0)} °/s` : `→ ${pico.turning_to.toFixed(0)}°`;

    this.updateJoints(frame);
    this.updateSensors(frame);
    byId("uart-log").innerHTML = pico.log
      .slice()
      .reverse()
      .map((message) => `<li>${escapeHtml(JSON.stringify(message))}</li>`)
      .join("");
    this.drawDetections(frame.detections);
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
   * Draw the detector's boxes over the dog's camera inset (frames are 640 x 480).
   * @param {Record<string, number[]>} detections
   */
  drawDetections(detections) {
    const context = this.overlay;
    if (!context) return;
    const scale = context.canvas.width / 640;
    context.clearRect(0, 0, context.canvas.width, context.canvas.height);
    context.lineWidth = 2;
    context.font = "600 11px system-ui, sans-serif";
    for (const [label, [x1, y1, x2, y2]] of Object.entries(detections)) {
      const colour = label === "bone" ? "#ffd166" : label === "person" ? "#7cc4ff" : "#c39bff";
      context.strokeStyle = colour;
      context.fillStyle = colour;
      context.strokeRect(x1 * scale, y1 * scale, (x2 - x1) * scale, (y2 - y1) * scale);
      context.fillText(label.replace("_", " "), x1 * scale + 3, Math.max(11, y1 * scale - 4));
    }
  }
}

/**
 * @param {string} text
 * @returns {string}
 */
function escapeHtml(text) {
  return text.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`);
}
