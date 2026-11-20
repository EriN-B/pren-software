// @ts-check
/**
 * @file The run clock and its splits, read from the core's state like race timing.
 *
 * The competition run: commands face to face, then SUCH starts the search and its
 * 2-minute budget; the dog finds the bone, returns and sits. Each phase is one split:
 *
 * | split    | runs while the core is in                        |
 * | -------- | ------------------------------------------------ |
 * | Commands | anything before `searching`                      |
 * | Search   | `searching` (the 2-minute budget)                |
 * | Found    | `found`                                          |
 * | Return   | `returning`, until it sits or stands again       |
 *
 * The big clock shows the whole run from its first state; the bar under it and the
 * Search split show the search budget. Times are simulation seconds from the frames.
 */

/** @typedef {import("./protocol.js").FrameMessage} FrameMessage */

const SEARCH_BUDGET = 120; // s, the competition's limit after SUCH
const SPLITS = ["commands", "search", "found", "return"];
const LABELS = { commands: "Commands", search: "Search", found: "Found", return: "Return" };

/**
 * Which split a core state belongs to.
 * @param {string} state
 * @returns {string}
 */
function splitOf(state) {
  if (state.startsWith("searching")) return "search";
  if (state === "found") return "found";
  if (state === "returning") return "return";
  return "commands";
}

export class RunClock {
  /**
   * @param {(event: string) => void} onEvent Called with "start", a split name when it
   *   begins, or "end"; the log dock marks these in the log.
   */
  constructor(onEvent) {
    this.onEvent = onEvent;
    this.clock = /** @type {HTMLElement} */ (document.querySelector(".clock"));
    this.time = /** @type {HTMLElement} */ (document.getElementById("run-clock"));
    this.budget = /** @type {HTMLElement} */ (document.getElementById("run-budget"));
    this.fill = /** @type {HTMLElement} */ (document.getElementById("budget-fill"));
    this.delta = /** @type {HTMLElement} */ (document.getElementById("search-delta"));
    /** @type {Map<string, HTMLElement>} */
    this.cells = new Map(
      [...document.querySelectorAll("#splits li")].map((li) => [
        /** @type {HTMLElement} */ (li).dataset.split ?? "",
        /** @type {HTMLElement} */ (li),
      ]),
    );
    /** @type {Record<string, {start: number, end: number | null}>} When each split began and ended. */
    this.phases = {};
    /** @type {string | null} The split running now. */
    this.current = null;
    this.lastTime = 0;
    this.finished = false;
  }

  reset() {
    this.phases = {};
    this.current = null;
    this.lastTime = 0;
    this.finished = false;
  }

  /**
   * Advance from a frame.
   * @param {FrameMessage} frame
   */
  update(frame) {
    const now = frame.time;
    const state = frame.core.attached ? frame.core.state : null;
    if (now < this.lastTime || state === null || state === "startup") this.reset();
    this.lastTime = now;
    if (state && !this.finished) {
      const split = splitOf(state);
      if (this.current === "return" && split === "commands") {
        this.close("return", now);
        this.finished = true;
        this.onEvent("end");
      } else if (split !== this.current && SPLITS.indexOf(split) > SPLITS.indexOf(this.current ?? "")) {
        if (this.current) this.close(this.current, now);
        else this.onEvent("start");
        this.phases[split] = { start: now, end: null };
        this.current = split;
        this.onEvent(split);
      }
    }
    this.render(now, state);
  }

  /**
   * End a split, with a short flash on its chip.
   * @param {string} split
   * @param {number} now
   */
  close(split, now) {
    this.phases[split].end = now;
    const cell = this.cells.get(split);
    cell?.classList.remove("closed");
    void cell?.offsetWidth; // restart the animation
    cell?.classList.add("closed");
  }

  /**
   * @param {number} now
   * @param {string | null} state
   */
  render(now, state) {
    const first = this.phases.commands ?? this.phases[this.current ?? ""];
    const end = this.finished ? (this.phases.return?.end ?? now) : now;
    const search = this.phases.search;
    const searched = search ? (search.end ?? now) - search.start : 0;
    const over = searched > SEARCH_BUDGET;

    this.time.textContent = format(first ? end - first.start : 0);
    this.clock.classList.toggle("running", Boolean(first) && !this.finished);
    this.clock.classList.toggle("over", over);
    this.fill.style.width = `${Math.min(100, (searched / SEARCH_BUDGET) * 100)}%`;
    this.budget.textContent = !state
      ? "core not attached"
      : this.finished
        ? "run complete"
        : !search
          ? `${LABELS[/** @type {keyof typeof LABELS} */ (this.current ?? "commands")]} · search budget 2:00 starts at SUCH`
          : `search ${format(searched)} of ${format(SEARCH_BUDGET)}`;

    const left = SEARCH_BUDGET - searched;
    this.delta.textContent = search ? (left >= 0 ? `${format(left)} left` : `+${format(-left)} over`) : "";
    this.delta.className = search ? (left >= 0 ? "left" : "overrun") : "";

    for (const split of SPLITS) {
      const cell = /** @type {HTMLElement} */ (this.cells.get(split));
      const phase = this.phases[split];
      const live = Boolean(phase) && phase.end === null && !this.finished;
      const duration = phase ? (phase.end ?? now) - phase.start : 0;
      cell.classList.toggle("live", live);
      cell.classList.toggle("done", Boolean(phase) && !live);
      cell.classList.toggle("over", split === "search" && over);
      /** @type {HTMLElement} */ (cell.querySelector("output")).textContent = phase ? format(duration) : "–";
    }
  }
}

/**
 * Minutes, seconds and tenths, like a race clock: 1:13.4
 * @param {number} seconds
 * @returns {string}
 */
export function format(seconds) {
  const tenths = Math.max(0, Math.floor(seconds * 10));
  const minutes = Math.floor(tenths / 600);
  const rest = (tenths % 600) / 10;
  return `${minutes}:${rest.toFixed(1).padStart(4, "0")}`;
}
