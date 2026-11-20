// @ts-check
/**
 * @file The log dock: every log line of the sim host, the dog core and the UART, in one
 * list, filterable by source, level and text, docked at the bottom like an IDE's.
 */

import { format } from "./run.js";

/** @typedef {import("./protocol.js").LogEntry} LogEntry */
/** @typedef {LogEntry & {marker?: boolean}} Line A log entry, or a run marker the viewer adds. */

const MAX_LINES = 5000; // older lines drop off the top
const MIN_DOCK = 120; // px
const SOURCE_LABELS = { core: "core", sim: "sim host", uart: "uart" };
const LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];

/**
 * @param {string} id
 * @returns {HTMLElement}
 */
const byId = (id) => /** @type {HTMLElement} */ (document.getElementById(id));

export class LogDock {
  constructor() {
    /** @type {Line[]} */
    this.entries = [];
    this.lastSeq = 0;
    this.source = "all";
    this.minLevel = "INFO";
    /** @type {number | null} Wall-clock second the run started, for the run-time column. */
    this.runStart = null;
    this.query = "";
    this.list = byId("log-list");
    this.empty = byId("log-empty");
    this.follow = /** @type {HTMLInputElement} */ (byId("log-follow"));
    this.wireFilters();
    this.wireResize();
  }

  /**
   * Add new lines; lines already seen (a reconnect resends the backlog) are skipped.
   * @param {LogEntry[]} entries
   */
  add(entries) {
    const fresh = entries.filter((entry) => entry.seq > this.lastSeq);
    if (!fresh.length) return;
    this.lastSeq = fresh[fresh.length - 1].seq;
    this.entries.push(...fresh);
    const overflow = this.entries.length - MAX_LINES;
    if (overflow > 0) {
      this.entries.splice(0, overflow);
      for (let i = 0; i < overflow && this.list.children.length > 1; i++) {
        this.list.children[1].remove(); // [0] is the empty-state paragraph
      }
    }
    const rows = fresh.filter((entry) => this.matches(entry)).map((entry) => this.row(entry));
    this.list.append(...rows);
    this.afterChange();
  }

  /** The simulator restarted: its numbering starts again. */
  restart() {
    this.lastSeq = 0;
    this.runStart = null;
  }

  /**
   * Mark a run event as its own row: the run starting, a split beginning, the end.
   * @param {string} text
   */
  mark(text) {
    const now = Date.now() / 1000;
    if (text === "Run started") this.runStart = now;
    /** @type {Line} */
    const marker = { seq: this.lastSeq, time: now, source: "sim", level: "INFO", message: text, marker: true };
    this.entries.push(marker);
    this.list.append(this.row(marker));
    this.afterChange();
  }

  /**
   * @param {LogEntry} entry
   * @returns {boolean}
   */
  matches(entry) {
    if (/** @type {Line} */ (entry).marker) return true; // run markers stay as landmarks
    if (this.source !== "all" && entry.source !== this.source) return false;
    if (LEVELS.indexOf(entry.level) < LEVELS.indexOf(this.minLevel)) return false;
    return !this.query || entry.message.toLowerCase().includes(this.query);
  }

  /** Redraw the list after a filter change. */
  rerender() {
    const rows = this.entries.filter((e) => this.matches(e)).map((e) => this.row(e));
    this.list.replaceChildren(this.empty, ...rows);
    this.afterChange(true);
  }

  /** @param {boolean} [force] Scroll to the end even if following is off. */
  afterChange(force = false) {
    this.empty.hidden = this.list.children.length > 1;
    this.empty.textContent = this.entries.length
      ? "No lines match the filter."
      : "No log lines yet. They appear here as the simulator and the core run.";
    if (this.follow.checked || force) this.list.scrollTop = this.list.scrollHeight;
    this.updateCounts();
  }

  updateCounts() {
    /** @type {Record<string, number>} */
    const counts = { all: 0, core: 0, sim: 0, uart: 0 };
    for (const entry of this.entries) {
      if (entry.marker) continue;
      counts.all += 1;
      counts[entry.source] += 1;
    }
    for (const button of document.querySelectorAll("#log-sources button")) {
      const source = /** @type {HTMLElement} */ (button).dataset.source ?? "all";
      /** @type {HTMLElement} */ (button.querySelector("span")).textContent = String(counts[source]);
    }
  }

  wireFilters() {
    for (const element of document.querySelectorAll("#log-sources button")) {
      const button = /** @type {HTMLElement} */ (element);
      button.addEventListener("click", () => {
        this.source = button.dataset.source ?? "all";
        for (const other of document.querySelectorAll("#log-sources button")) {
          other.classList.toggle("active", other === button);
        }
        this.rerender();
      });
    }
    byId("log-level").addEventListener("change", (event) => {
      this.minLevel = /** @type {HTMLSelectElement} */ (event.target).value;
      this.rerender();
    });
    byId("log-search").addEventListener("input", (event) => {
      this.query = /** @type {HTMLInputElement} */ (event.target).value.trim().toLowerCase();
      this.rerender();
    });
    byId("log-clear").addEventListener("click", () => {
      this.entries = [];
      this.rerender();
    });
    // Scrolling up to read stops following; scrolling back to the end resumes it. Only the
    // user's own scrolling counts: a resize also moves the scroll position.
    let userScroll = false;
    for (const type of ["wheel", "touchmove", "keydown", "pointerdown"]) {
      this.list.addEventListener(type, () => (userScroll = true), { passive: true });
    }
    this.list.addEventListener("scroll", () => {
      const atEnd = this.list.scrollHeight - this.list.scrollTop - this.list.clientHeight < 24;
      if (atEnd) this.follow.checked = true;
      else if (userScroll) this.follow.checked = false;
      userScroll = false;
    });
    new ResizeObserver(() => {
      if (this.follow.checked) this.list.scrollTop = this.list.scrollHeight;
    }).observe(this.list);
  }

  /**
   * One line of the list: wall time, run time, source, level, message; or a run marker.
   * @param {Line} entry
   * @returns {HTMLElement}
   */
  row(entry) {
    const element = document.createElement("div");
    const run = this.runStart !== null && entry.time >= this.runStart ? `+${format(entry.time - this.runStart)}` : "";
    if (entry.marker) {
      element.className = "log-mark";
      const time = document.createElement("span");
      time.textContent = `${clockTime(entry.time)}  ${run}`;
      element.append(time, entry.message);
      return element;
    }
    const level = entry.level === "CRITICAL" ? "ERROR" : entry.level;
    element.className = `log-row ${level === "WARNING" ? "warning" : level === "ERROR" ? "error" : ""}`;
    for (const [className, text] of [
      ["t", clockTime(entry.time)],
      ["rt", run], // run time; not "run", the header's run area owns that class
      [`src-${entry.source}`, SOURCE_LABELS[entry.source] ?? entry.source],
      ["lvl", level === "WARNING" ? "WARN" : level],
      ["msg", entry.message],
    ]) {
      const cell = document.createElement("span");
      cell.className = className;
      cell.textContent = text;
      element.append(cell);
    }
    return element;
  }

  /** Drag the grip, or use the arrow keys on it, to change the dock's height. */
  wireResize() {
    const grip = byId("dock-grip");
    const root = document.documentElement;
    /** @param {number} height */
    const setHeight = (height) => {
      const max = window.innerHeight - 260;
      root.style.setProperty("--dock-h", `${Math.round(Math.max(MIN_DOCK, Math.min(max, height)))}px`);
    };
    grip.addEventListener("pointerdown", (event) => {
      grip.setPointerCapture(event.pointerId);
      const move = (/** @type {PointerEvent} */ e) => setHeight(window.innerHeight - e.clientY);
      grip.addEventListener("pointermove", move);
      grip.addEventListener("pointerup", () => grip.removeEventListener("pointermove", move), { once: true });
    });
    grip.addEventListener("keydown", (event) => {
      const now = byId("dock").getBoundingClientRect().height;
      if (event.key === "ArrowUp") setHeight(now + 40);
      if (event.key === "ArrowDown") setHeight(now - 40);
    });
  }
}

/**
 * The wall-clock time of a log entry, to the millisecond.
 * @param {number} seconds Seconds since 1970.
 * @returns {string}
 */
function clockTime(seconds) {
  const time = new Date(seconds * 1000);
  return `${time.toTimeString().slice(0, 8)}.${String(time.getMilliseconds()).padStart(3, "0")}`;
}
